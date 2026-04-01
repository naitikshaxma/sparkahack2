import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Set, Tuple


NORMALIZATION_STOPWORDS = {"scheme", "yojana", "program", "initiative"}
GENERIC_NOISY_KEYWORDS = {"yojana", "scheme", "apply", "benefit"}


def normalize_text(value: str) -> str:
	if value is None:
		return ""
	text = str(value).lower().strip()
	text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
	text = text.replace("_", " ")
	text = re.sub(r"\s+", " ", text).strip()
	if not text:
		return ""
	tokens = [tok for tok in text.split(" ") if tok and tok not in NORMALIZATION_STOPWORDS]
	return " ".join(tokens)


def tokenize(value: str) -> List[str]:
	text = normalize_text(value)
	if not text:
		return []
	return [tok for tok in text.split(" ") if tok]


def generate_bigrams(tokens: List[str]) -> List[str]:
	if len(tokens) < 2:
		return []
	return [f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)]


def similarity(a: str, b: str) -> float:
	return SequenceMatcher(None, a, b).ratio()


@dataclass
class SchemeAggregate:
	scheme_name: str
	keywords: Set[str] = field(default_factory=set)
	query_variants: Set[str] = field(default_factory=set)
	source_count: int = 0


class UnionFind:
	def __init__(self, n: int) -> None:
		self.parent = list(range(n))
		self.rank = [0] * n

	def find(self, x: int) -> int:
		while self.parent[x] != x:
			self.parent[x] = self.parent[self.parent[x]]
			x = self.parent[x]
		return x

	def union(self, a: int, b: int) -> None:
		ra = self.find(a)
		rb = self.find(b)
		if ra == rb:
			return
		if self.rank[ra] < self.rank[rb]:
			self.parent[ra] = rb
		elif self.rank[ra] > self.rank[rb]:
			self.parent[rb] = ra
		else:
			self.parent[rb] = ra
			self.rank[ra] += 1


def choose_canonical_name(names: List[str]) -> str:
	return sorted(names, key=lambda n: (-len(tokenize(n)), -len(n), n))[0]


def clean_dataset(input_path: Path, output_path: Path) -> Dict[str, int]:
	with input_path.open("r", encoding="utf-8", newline="") as f:
		reader = csv.DictReader(f)
		rows = list(reader)

	original_size = len(rows)

	normalized_rows: List[Dict[str, str]] = []
	seen_row_keys: Set[Tuple[Tuple[str, str], ...]] = set()
	for row in rows:
		normalized: Dict[str, str] = {}
		for key, value in row.items():
			if isinstance(value, str):
				normalized[key] = normalize_text(value)
			else:
				normalized[key] = ""
		row_key = tuple(sorted(normalized.items()))
		if row_key in seen_row_keys:
			continue
		seen_row_keys.add(row_key)
		normalized_rows.append(normalized)

	exact_duplicate_rows_removed = original_size - len(normalized_rows)

	exact_scheme_map: Dict[str, SchemeAggregate] = {}
	for row in normalized_rows:
		scheme = normalize_text(row.get("scheme_name", ""))
		if not scheme:
			continue
		agg = exact_scheme_map.setdefault(scheme, SchemeAggregate(scheme_name=scheme))
		agg.source_count += 1

		query_text = normalize_text(row.get("query", ""))
		if query_text:
			agg.query_variants.add(query_text)

		existing_keywords = []
		if row.get("keywords"):
			existing_keywords.extend([k.strip() for k in row["keywords"].split(",") if k.strip()])
		if row.get("query_variants"):
			existing_keywords.extend([k.strip() for k in row["query_variants"].split(",") if k.strip()])

		candidate_tokens = set(tokenize(scheme))
		if query_text:
			candidate_tokens.update(tokenize(query_text))
		for k in existing_keywords:
			candidate_tokens.update(tokenize(k))

		for token in candidate_tokens:
			if token and token not in GENERIC_NOISY_KEYWORDS:
				agg.keywords.add(token)

	exact_scheme_count = len(exact_scheme_map)

	schemes = list(exact_scheme_map.keys())
	uf = UnionFind(len(schemes))
	for i in range(len(schemes)):
		for j in range(i + 1, len(schemes)):
			if similarity(schemes[i], schemes[j]) > 0.85:
				uf.union(i, j)

	groups: Dict[int, List[str]] = {}
	for idx, name in enumerate(schemes):
		root = uf.find(idx)
		groups.setdefault(root, []).append(name)

	fuzzy_groups_merged = sum(1 for names in groups.values() if len(names) > 1)

	cleaned: List[SchemeAggregate] = []
	for names in groups.values():
		canonical = choose_canonical_name(names)
		merged_keywords: Set[str] = set()
		merged_queries: Set[str] = set()
		source_count = 0
		for name in names:
			agg = exact_scheme_map[name]
			merged_keywords.update(agg.keywords)
			merged_queries.update(agg.query_variants)
			source_count += agg.source_count

		canonical_tokens = tokenize(canonical)
		merged_keywords.update(canonical_tokens)
		merged_keywords.update(generate_bigrams(canonical_tokens))

		filtered_keywords = {
			kw
			for kw in merged_keywords
			if kw
			and kw not in GENERIC_NOISY_KEYWORDS
			and kw not in NORMALIZATION_STOPWORDS
			and any(ch.isalnum() for ch in kw)
		}

		meaningful_tokens = [t for t in canonical_tokens if t not in GENERIC_NOISY_KEYWORDS]
		if len(filtered_keywords) < 2:
			continue
		if len(meaningful_tokens) < 3:
			continue

		cleaned.append(
			SchemeAggregate(
				scheme_name=canonical,
				keywords=filtered_keywords,
				query_variants=merged_queries,
				source_count=source_count,
			)
		)

	cleaned.sort(key=lambda x: x.scheme_name)

	with output_path.open("w", encoding="utf-8", newline="") as f:
		fieldnames = ["scheme_name", "keywords", "query_variants", "source_count"]
		writer = csv.DictWriter(f, fieldnames=fieldnames)
		writer.writeheader()
		for item in cleaned:
			writer.writerow(
				{
					"scheme_name": item.scheme_name,
					"keywords": ", ".join(sorted(item.keywords)),
					"query_variants": " || ".join(sorted(item.query_variants)),
					"source_count": item.source_count,
				}
			)

	stats = {
		"original_size": original_size,
		"cleaned_size": len(cleaned),
		"duplicates_removed": exact_duplicate_rows_removed + (exact_scheme_count - len(groups)),
		"ambiguous_groups_merged": fuzzy_groups_merged,
	}
	return stats


def main() -> None:
	parser = argparse.ArgumentParser(description="Clean scheme dataset for resolver quality.")
	parser.add_argument("--input", default="data/final_voice_ready_dataset.csv")
	parser.add_argument("--output", default="cleaned_dataset.csv")
	args = parser.parse_args()

	stats = clean_dataset(Path(args.input), Path(args.output))
	print(f"original size: {stats['original_size']}")
	print(f"cleaned size: {stats['cleaned_size']}")
	print(f"duplicates removed: {stats['duplicates_removed']}")
	print(f"ambiguous groups merged: {stats['ambiguous_groups_merged']}")


if __name__ == "__main__":
	main()
