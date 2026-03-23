interface ModeIndicatorProps {
  mode: "info" | "action" | "clarify";
}

const ModeIndicator = ({ mode }: ModeIndicatorProps) => {
  const isInfo = mode === "info";
  const isClarify = mode === "clarify";

  const label = isInfo
    ? "📘 Information Mode"
    : isClarify
      ? "❓ Clarification Needed"
      : "📝 Application Mode";

  return (
    <div
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold",
        isClarify
          ? "border-amber-400/40 bg-amber-500/10 text-amber-100"
          : isInfo
            ? "border-cyan-400/40 bg-cyan-500/10 text-cyan-100"
            : "border-emerald-400/40 bg-emerald-500/10 text-emerald-100",
      ].join(" ")}
    >
      <span>{label}</span>
    </div>
  );
};

export default ModeIndicator;
