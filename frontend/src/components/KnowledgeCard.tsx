interface KnowledgeCardProps {
  title?: string;
  description?: string;
  eligibility?: string;
  uiLanguage: "hi" | "en";
}

const KnowledgeCard = ({ title, description, eligibility, uiLanguage }: KnowledgeCardProps) => {
  if (!title && !description && !eligibility) return null;

  return (
    <div className="rounded-2xl border border-white/10 bg-[#111827] px-4 py-3 text-white">
      <p className="text-xs uppercase tracking-wide text-amber-200/80 mb-2">{uiLanguage === "hi" ? "योजना जानकारी" : "Scheme Knowledge"}</p>
      {title && <p className="text-sm font-semibold mb-1">{title}</p>}
      {description && <p className="text-sm text-gray-300">{description}</p>}
      {eligibility && (
        <p className="text-xs text-gray-300 mt-2">
          <span className="font-semibold">{uiLanguage === "hi" ? "पात्रता:" : "Eligibility:"}</span> {eligibility}
        </p>
      )}
    </div>
  );
};

export default KnowledgeCard;
