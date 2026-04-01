type TelemetryEvent =
  | "mic_tap"
  | "barge_in"
  | "voice_state"
  | "stream_first_chunk"
  | "stream_done"
  | "latency"
  | "error"
  | "quick_action"
  | "language_detected"
  | "audio_queue_trimmed";

interface TelemetryPayload {
  event: TelemetryEvent;
  at: number;
  sessionId?: string;
  details?: Record<string, unknown>;
}

const ENABLE_DEBUG = import.meta.env.DEV;

export function logFrontendEvent(event: TelemetryEvent, details?: Record<string, unknown>, sessionId?: string): void {
  const payload: TelemetryPayload = {
    event,
    at: Date.now(),
    sessionId,
    details,
  };

  if (ENABLE_DEBUG) {
    // Keep frontend logs lightweight and structured for easy filtering.
    console.debug("[voice-ui-telemetry]", payload);
  }
}
