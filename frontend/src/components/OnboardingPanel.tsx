interface OnboardingPanelProps {
  uiLanguage: "hi" | "en";
  onSamplePick: (query: string) => void;
}

const OnboardingPanel = ({ uiLanguage, onSamplePick }: OnboardingPanelProps) => {
  const intro = uiLanguage === "hi"
    ? "मैं VoiceOS Bharat हूँ। सरकारी योजनाओं की जानकारी और आवेदन सहायता के लिए तैयार हूँ।"
    : "I am VoiceOS Bharat. I can guide you through schemes and applications in real time.";

  const samples = uiLanguage === "hi"
    ? ["PM Kisan क्या है?", "Loan के लिए आवेदन कैसे करूँ?", "पेंशन योजना बताइए"]
    : ["What is PM Kisan?", "How do I apply for a loan?", "Tell me a pension scheme"];

  return (
    <section className="rounded-2xl border border-amber-300/30 bg-amber-500/10 p-4 space-y-3 animate-[fadeIn_260ms_ease-out]">
      <p className="text-sm text-amber-50 leading-relaxed">{intro}</p>
      <div className="flex flex-wrap gap-2">
        {samples.map((sample) => (
          <button
            key={sample}
            type="button"
            onClick={() => onSamplePick(sample)}
            className="px-3 py-1.5 rounded-full text-xs border border-amber-200/50 bg-white/10 text-amber-50 hover:bg-amber-200/20"
          >
            {sample}
          </button>
        ))}
      </div>
      <p className="text-xs text-amber-100/90 font-semibold">
        {uiLanguage === "hi" ? "अब माइक्रोफोन टैप करें और बोलना शुरू करें" : "Tap the microphone and start speaking"}
      </p>
    </section>
  );
};

export default OnboardingPanel;
