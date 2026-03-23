import type { QuickAction } from "@/services/api";

interface QuickActionsProps {
  uiLanguage: "hi" | "en";
  actions?: QuickAction[];
  disabled?: boolean;
  onSelect: (value: string) => void;
}

const QuickActions = ({ uiLanguage, actions, disabled = false, onSelect }: QuickActionsProps) => {
  const fallbackActions: QuickAction[] = uiLanguage === "hi"
    ? [
        { label: "पात्रता बताएं", value: "show_eligibility" },
        { label: "और जानकारी", value: "more_info" },
        { label: "आवेदन शुरू करें", value: "start_application" },
      ]
    : [
        { label: "Show eligibility", value: "show_eligibility" },
        { label: "More info", value: "more_info" },
        { label: "Start application", value: "start_application" },
      ];
  const dynamicActions = actions && actions.length > 0 ? actions : fallbackActions;

  return (
    <div className="flex flex-wrap gap-2">
      {dynamicActions.map((action) => (
        <button
          key={`${action.value}-${action.label}`}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(action.value)}
          className="px-3 py-1.5 rounded-full text-xs border border-white/25 bg-white/10 text-white hover:border-yellow-300/70 disabled:opacity-50"
        >
          {action.label}
        </button>
      ))}
    </div>
  );
};

export default QuickActions;
