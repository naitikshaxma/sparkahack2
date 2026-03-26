from __future__ import annotations

from typing import Any, Dict, List


REQUIRED_SCHEME_FIELDS = (
    "id",
    "name",
    "keywords",
    "summary_en",
    "summary_hi",
)


class DatasetValidationError(ValueError):
    """Raised when schemes dataset records violate required shape."""


def _is_missing_value(field: str, value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if field == "keywords":
        if not isinstance(value, list):
            return True
        return len([item for item in value if str(item).strip()]) == 0
    return False


def validate_and_normalize_schemes(data: Any, dataset_name: str = "schemes_dataset.json") -> List[Dict[str, Any]]:
    """Validate required fields and apply optional description fallbacks.

    Required fields per record:
    - id
    - name
    - keywords
    - summary_en
    - summary_hi

    Optional fallback fields:
    - description_en -> summary_en
    - description_hi -> summary_hi
    """
    if not isinstance(data, list):
        raise DatasetValidationError(
            f"{dataset_name} must contain a list of scheme records."
        )

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise DatasetValidationError(
                f"{dataset_name}: record at index {idx} is invalid (expected object)."
            )

        missing_fields = [
            field
            for field in REQUIRED_SCHEME_FIELDS
            if _is_missing_value(field, item.get(field))
        ]
        if missing_fields:
            record_id = str(item.get("id") or "<missing-id>").strip() or "<missing-id>"
            raise DatasetValidationError(
                f"{dataset_name}: invalid record index={idx}, id='{record_id}', "
                f"missing required fields={missing_fields}"
            )

        scheme = dict(item)
        if not str(scheme.get("description_en") or "").strip():
            scheme["description_en"] = str(scheme.get("summary_en") or "").strip()
        if not str(scheme.get("description_hi") or "").strip():
            scheme["description_hi"] = str(scheme.get("summary_hi") or "").strip()

        normalized.append(scheme)

    return normalized
