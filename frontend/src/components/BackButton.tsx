import { ArrowLeft } from 'lucide-react';

interface BackButtonProps {
  onClick: () => void;
  label?: string;
}

const BackButton = ({ onClick, label = 'Back' }: BackButtonProps) => {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-4 py-2 rounded-xl text-gray-300 bg-white/5 border border-white/10 transition-all duration-200 hover:bg-white/10 hover:text-white font-body text-sm font-medium"
    >
      <ArrowLeft className="w-4 h-4" />
      <span>{label}</span>
    </button>
  );
};

export default BackButton;
