import type { ConversationTurn } from "@/store/voiceStore";

interface ConversationHistoryProps {
  history: ConversationTurn[];
  uiLanguage: "hi" | "en";
}

const ConversationHistory = ({ history, uiLanguage }: ConversationHistoryProps) => {
  if (history.length === 0) {
    return null;
  }

  const recentHistory = history.slice(-5);

  return (
    <section className="rounded-2xl border border-white/10 bg-[#111827] p-3">
      <p className="text-[11px] uppercase tracking-wide text-gray-300 mb-2 font-semibold">
        {uiLanguage === "hi" ? "बातचीत इतिहास" : "Conversation History"}
      </p>
      <div className="space-y-2">
        {recentHistory.map((turn) => (
          <div key={turn.id} className="space-y-1.5">
            <div className="ml-auto max-w-[85%] rounded-2xl border border-white/10 bg-white/5 text-white px-3 py-2 text-sm">
              {turn.userText}
            </div>
            <div className="max-w-[90%] rounded-2xl border border-white/10 bg-[#111827] text-white px-3 py-2 text-sm">
              {turn.assistantText || "Samajh raha hoon..."}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

export default ConversationHistory;
