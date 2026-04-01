import type { QuickAction } from "@/services/api";

interface QuickActionsProps {
  uiLanguage: "hi" | "en";
  actions?: QuickAction[];
  disabled?: boolean;
  onSelect: (value: string) => void;
}

const DEFAULT_FIXED_ACTIONS: QuickAction[] = [
  { label: "Apply kaise kare?", value: "Apply kaise kare?" },
  { label: "Kitna paisa milega?", value: "Kitna paisa milega?" },
  { label: "Documents kya chahiye?", value: "Documents kya chahiye?" },
];

const QuickActions = ({ uiLanguage, actions, disabled = false, onSelect }: QuickActionsProps) => {
  const resolvedActions = actions && actions.length > 0 ? actions : DEFAULT_FIXED_ACTIONS;

  return (
    <div className="flex flex-wrap gap-2 md:gap-3">
      {resolvedActions.map((action) => (
        <button
          key={`${action.value}-${action.label}`}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(action.value)}
          aria-label={`${uiLanguage === "hi" ? "त्वरित प्रश्न" : "Quick query"}: ${action.label}`}
          className="px-4 py-3 rounded-2xl text-sm md:text-base font-semibold border border-white/25 bg-white/10 text-white hover:border-yellow-300/70 disabled:opacity-50"
        >
          {action.label}
        </button>
      ))}
    </div>
  );
};

export default QuickActions;
