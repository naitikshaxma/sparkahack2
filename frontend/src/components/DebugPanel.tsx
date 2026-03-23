import { useMemo, useState } from "react";
import { useVoiceStore } from "@/store/voiceStore";

const DebugPanel = () => {
  const [open, setOpen] = useState(false);
  const voiceState = useVoiceStore((s) => s.voiceState);
  const latency = useVoiceStore((s) => s.latency);
  const detectedLanguage = useVoiceStore((s) => s.detectedLanguage);
  const requestId = useVoiceStore((s) => s.requestId);

  const firstResponseMs = useMemo(() => {
    if (!latency.requestStartedAt || !latency.firstResponseAt) {
      return null;
    }
    return Math.round(latency.firstResponseAt - latency.requestStartedAt);
  }, [latency.firstResponseAt, latency.requestStartedAt]);

  const firstAudioMs = useMemo(() => {
    if (!latency.requestStartedAt || !latency.firstAudioChunkAt) {
      return null;
    }
    return Math.round(latency.firstAudioChunkAt - latency.requestStartedAt);
  }, [latency.firstAudioChunkAt, latency.requestStartedAt]);

  if (!import.meta.env.DEV) {
    return null;
  }

  return (
    <div className="fixed bottom-3 right-3 z-50">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="px-3 py-1.5 rounded-full border border-cyan-300/40 bg-cyan-500/20 text-cyan-100 text-xs font-semibold"
      >
        {open ? "Hide Debug" : "Show Debug"}
      </button>
      {open ? (
        <div className="mt-2 w-[300px] rounded-xl border border-white/15 bg-[#020617]/95 text-cyan-100 text-xs p-3 space-y-1 shadow-[0_20px_50px_rgba(0,0,0,0.45)]">
          <p><span className="text-cyan-300">voice_state:</span> {voiceState}</p>
          <p><span className="text-cyan-300">detected_language:</span> {detectedLanguage}</p>
          <p><span className="text-cyan-300">request_id:</span> {requestId || "n/a"}</p>
          <p><span className="text-cyan-300">first_response_ms:</span> {firstResponseMs ?? "n/a"}</p>
          <p><span className="text-cyan-300">first_audio_ms:</span> {firstAudioMs ?? "n/a"}</p>
          <p><span className="text-cyan-300">roundtrip_ms:</span> {latency.lastRoundTripMs ? Math.round(latency.lastRoundTripMs) : "n/a"}</p>
        </div>
      ) : null}
    </div>
  );
};

export default DebugPanel;
