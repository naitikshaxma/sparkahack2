import { RotateCcw, LayoutDashboard } from 'lucide-react';

interface ActionButtonsProps {
    onAskAgain: () => void;
    onDashboard: () => void;
    visible: boolean;
}

const ActionButtons = ({ onAskAgain, onDashboard, visible }: ActionButtonsProps) => {
    return (
        <div
            className="flex flex-col sm:flex-row gap-2.5 transition-all duration-700 ease-out"
            style={{
                opacity: visible ? 1 : 0,
                transform: visible ? 'translateY(0)' : 'translateY(8px)',
            }}
        >
            <button
                onClick={onAskAgain}
                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#f59e0b] text-black font-body font-medium text-sm transition-all duration-200 hover:bg-[#d97706] hover:shadow-[0_0_16px_rgba(245,158,11,0.15)] active:scale-[0.98]"
            >
                <RotateCcw className="w-3.5 h-3.5" />
                Ask Again
            </button>

            <button
                onClick={onDashboard}
                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#1a1a1a] border border-[#2a2a2a] text-[#9ca3af] font-body font-medium text-sm transition-all duration-200 hover:bg-[#222222] hover:border-[#3a3a3a] hover:text-[#f5f5f5] active:scale-[0.98]"
            >
                <LayoutDashboard className="w-3.5 h-3.5" />
                Dashboard
            </button>
        </div>
    );
};

export default ActionButtons;
