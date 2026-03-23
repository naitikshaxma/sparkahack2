import type { ConversationTurn } from "@/store/voiceStore";

interface ConversationHistoryProps {
  history: ConversationTurn[];
  uiLanguage: "hi" | "en";
}

const ConversationHistory = ({ history, uiLanguage }: ConversationHistoryProps) => {
  if (history.length === 0) {
    return null;
  }

  return (
    <section className="rounded-2xl border border-white/10 bg-black/25 p-3">
      <p className="text-[11px] uppercase tracking-wide text-gray-300 mb-2 font-semibold">
        {uiLanguage === "hi" ? "बातचीत इतिहास" : "Conversation History"}
      </p>
      <div className="max-h-56 overflow-y-auto pr-1 space-y-2">
        {history.map((turn) => (
          <div key={turn.id} className="space-y-1.5">
            <div className="ml-auto max-w-[85%] rounded-2xl bg-[#1e293b] text-slate-100 px-3 py-2 text-sm">
              {turn.userText}
            </div>
            <div className="max-w-[90%] rounded-2xl bg-cyan-500/15 border border-cyan-300/20 text-cyan-50 px-3 py-2 text-sm">
              {turn.assistantText || (uiLanguage === "hi" ? "सोच रहा हूँ..." : "Thinking...")}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

export default ConversationHistory;
