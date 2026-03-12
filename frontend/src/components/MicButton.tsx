import { Mic, Loader2 } from 'lucide-react';

interface MicButtonProps {
  isListening: boolean;
  isProcessing: boolean;
  isSpeaking: boolean;
  onClick: () => void;
}

const MicButton = ({ isListening, isProcessing, isSpeaking, onClick }: MicButtonProps) => {
  return (
    <div className="relative flex items-center justify-center">
      {/* Pulse rings when listening */}
      {isListening && (
        <>
          <div className="absolute w-48 h-48 rounded-full bg-[#f59e0b]/10 animate-ping" style={{ animationDuration: '2s' }} />
          <div className="absolute w-40 h-40 rounded-full bg-[#f59e0b]/15 animate-ping" style={{ animationDuration: '1.5s' }} />
        </>
      )}

      {/* Speaking indicator ring */}
      {isSpeaking && (
        <div className="absolute w-44 h-44 rounded-full border-2 border-[#14b8a6]/40 animate-pulse" />
      )}

      {/* Main button */}
      <button
        onClick={onClick}
        disabled={isProcessing}
        className={`relative z-10 w-28 h-28 md:w-32 md:h-32 rounded-full flex items-center justify-center transition-all duration-300 ${isListening
            ? 'bg-[#f59e0b] scale-105 shadow-[0_0_40px_rgba(245,158,11,0.3)]'
            : 'bg-[#1a1a1a] border border-[#2a2a2a] shadow-[0_8px_32px_rgba(0,0,0,0.4)]'
          } ${isProcessing ? 'opacity-70' : 'hover:scale-105 active:scale-95'}`}
      >
        {isProcessing ? (
          <Loader2 className="w-10 h-10 text-[#f5f5f5] animate-spin" />
        ) : (
          <Mic className={`w-10 h-10 transition-transform duration-300 ${isListening ? 'text-black scale-110' : 'text-[#f5f5f5]'
            }`} />
        )}
      </button>
    </div>
  );
};

export default MicButton;
