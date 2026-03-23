interface KnowledgeCardProps {
  title?: string;
  description?: string;
  eligibility?: string;
  uiLanguage: "hi" | "en";
}

const KnowledgeCard = ({ title, description, eligibility, uiLanguage }: KnowledgeCardProps) => {
  if (!title && !description && !eligibility) return null;

  return (
    <div className="rounded-2xl border border-cyan-300/30 bg-cyan-500/10 px-4 py-3 text-cyan-50 shadow-[0_10px_24px_rgba(6,182,212,0.12)]">
      <p className="text-xs uppercase tracking-wide text-cyan-200/80 mb-2">{uiLanguage === "hi" ? "योजना जानकारी" : "Scheme Knowledge"}</p>
      {title && <p className="text-sm font-semibold mb-1">{title}</p>}
      {description && <p className="text-sm text-cyan-50/90">{description}</p>}
      {eligibility && (
        <p className="text-xs text-cyan-100/90 mt-2">
          <span className="font-semibold">{uiLanguage === "hi" ? "पात्रता:" : "Eligibility:"}</span> {eligibility}
        </p>
      )}
    </div>
  );
};

export default KnowledgeCard;
