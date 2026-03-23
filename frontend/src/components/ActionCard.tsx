interface ActionCardProps {
  stepsDone: number;
  stepsTotal: number;
  uiLanguage: "hi" | "en";
  completedFields?: string[];
}

const ActionCard = ({ stepsDone, stepsTotal, uiLanguage, completedFields = [] }: ActionCardProps) => {
  const total = Math.max(stepsTotal, 1);
  const progress = Math.min(100, Math.round((stepsDone / total) * 100));

  return (
    <div className="rounded-2xl border border-emerald-300/30 bg-emerald-500/10 px-4 py-3 text-emerald-50 shadow-[0_10px_24px_rgba(16,185,129,0.12)]">
      <p className="text-xs uppercase tracking-wide text-emerald-100/90 mb-2">{uiLanguage === "hi" ? "आवेदन प्रगति" : "Application Progress"}</p>
      <div className="h-2 rounded-full bg-emerald-900/50 overflow-hidden mb-2">
        <div className="h-full bg-gradient-to-r from-emerald-300 to-teal-300" style={{ width: `${progress}%` }} />
      </div>
      <p className="text-xs text-emerald-50/90 mb-2 font-semibold">
        {uiLanguage === "hi" ? `चरण ${stepsDone} / ${stepsTotal}` : `Step ${stepsDone} of ${stepsTotal}`}
      </p>
      {completedFields.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {completedFields.map((field) => (
            <span key={field} className="px-2 py-1 rounded-full text-[11px] bg-emerald-200/20 border border-emerald-200/30 text-emerald-50">
              {field} ✔️
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

export default ActionCard;
