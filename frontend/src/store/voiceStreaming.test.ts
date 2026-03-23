import { beforeEach, describe, expect, it } from "vitest";
import { useVoiceStore } from "@/store/voiceStore";

describe("voiceStore streaming behavior", () => {
  beforeEach(() => {
    useVoiceStore.getState().resetConversationState();
    useVoiceStore.getState().setLanguage("en");
  });

  it("appends streamed text word segments", () => {
    const store = useVoiceStore.getState();
    store.clearResponseStream();
    store.appendResponseStream("This");
    store.appendResponseStream("is");
    store.appendResponseStream("streamed");
    store.appendResponseStream("response");

    expect(useVoiceStore.getState().responseStream).toBe("This is streamed response");
  });

  it("preserves selected language on reset", () => {
    const store = useVoiceStore.getState();
    store.setLanguage("hi");
    store.setDetectedLanguage("hi");
    store.setFinalTranscript("नमस्ते");
    store.setResponseText("नमस्ते");

    store.resetConversationState();

    const next = useVoiceStore.getState();
    expect(next.language).toBe("hi");
    expect(next.detectedLanguage).toBe("hi");
    expect(next.transcriptFinal).toBe("");
    expect(next.responseText).toBe("");
  });
});
