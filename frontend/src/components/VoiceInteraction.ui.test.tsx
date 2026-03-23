import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import VoiceInteraction from "@/components/VoiceInteraction";
import { useVoiceStore } from "@/store/voiceStore";

vi.mock("@/services/api", () => ({
  clearSessionId: vi.fn(),
  getOrCreateSessionId: vi.fn(() => "test-session-1"),
  interruptTts: vi.fn(async () => ({ session_id: "test-session-1", interrupted: true, state: "interrupted" })),
  processText: vi.fn(async () => ({ response_text: "ok" })),
  processTextStream: vi.fn(async () => undefined),
  resetSession: vi.fn(async () => ({ status: "reset", session_id: "test-session-1" })),
  synthesizeTts: vi.fn(async () => ({ response_text: "hello", audio_base64: "" })),
}));

vi.mock("@/components/result/SparkleBackground", () => ({
  default: () => null,
}));

class MockAudio {
  currentTime = 0;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {}
  pause() {}
  play() {
    if (this.onended) {
      this.onended();
    }
    return Promise.resolve();
  }
}

Object.defineProperty(window, "Audio", {
  writable: true,
  value: MockAudio,
});

describe("VoiceInteraction UI states", () => {
  it("renders listening status from centralized store", () => {
    useVoiceStore.getState().resetConversationState();
    useVoiceStore.getState().setVoiceState("listening");

    render(
      <VoiceInteraction
        language={{ code: "en", name: "English", nativeName: "English", greeting: "Hello" }}
        onBack={() => undefined}
      />,
    );

    expect(screen.getByText(/Listening/i)).toBeInTheDocument();
  });
});
