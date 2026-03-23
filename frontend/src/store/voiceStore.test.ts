import { beforeEach, describe, expect, it, vi } from "vitest";
import { useVoiceStore } from "@/store/voiceStore";

describe("voiceStore lifecycle", () => {
  beforeEach(() => {
    useVoiceStore.getState().resetConversationState();
    useVoiceStore.getState().setLanguage("en");
    vi.useFakeTimers();
  });

  it("tracks voice lifecycle states", () => {
    const store = useVoiceStore.getState();
    store.setVoiceState("listening");
    expect(useVoiceStore.getState().voiceState).toBe("listening");

    store.setVoiceState("processing");
    expect(useVoiceStore.getState().voiceState).toBe("processing");

    store.setVoiceState("speaking");
    expect(useVoiceStore.getState().voiceState).toBe("speaking");

    store.setVoiceState("interrupted");
    expect(useVoiceStore.getState().voiceState).toBe("interrupted");
  });

  it("tracks latency markers", () => {
    const store = useVoiceStore.getState();
    store.beginLatencyTracking();
    vi.advanceTimersByTime(80);
    store.markFirstResponse();
    vi.advanceTimersByTime(60);
    store.markFirstAudioChunk();
    vi.advanceTimersByTime(120);
    store.endLatencyTracking();

    const latency = useVoiceStore.getState().latency;
    expect(latency.requestStartedAt).not.toBeNull();
    expect(latency.firstResponseAt).not.toBeNull();
    expect(latency.firstAudioChunkAt).not.toBeNull();
    expect(latency.lastRoundTripMs).not.toBeNull();
    expect(latency.lastRoundTripMs || 0).toBeGreaterThan(0);
  });
});
