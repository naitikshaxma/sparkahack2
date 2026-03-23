/**
 * Shared voice synthesis helpers used by the voice interaction UI.
 * Centralizes language-to-BCP-47 tag mapping and voice selection logic.
 */

export const langVoiceTags: Record<string, string[]> = {
  hi: ['hi-IN', 'hi'],
  en: ['en-IN', 'en-US', 'en-GB', 'en'],
};

export const langSearchNames: Record<string, string[]> = {
  hi: ['hindi', 'हिन्दी', 'swara'],
  en: ['english', 'heera'],
};

/** Bottom-of-page hint text per language on the voice interaction page */
export const micHints: Record<string, string> = {
  hi: 'माइक बटन दबाएं और बोलें',
  en: 'Tap the microphone and speak',
};

/**
 * Find the best matching SpeechSynthesisVoice for a language code.
 * Prefers local voices, then remote voices.
 */
export function findVoice(
  voices: SpeechSynthesisVoice[],
  langCode: string,
): SpeechSynthesisVoice | null {
  const tags = langVoiceTags[langCode] ?? [`${langCode}-IN`, langCode];
  const localVoices = voices.filter((v) => v.localService);
  const remoteVoices = voices.filter((v) => !v.localService);

  for (const voiceSet of [localVoices, remoteVoices]) {
    for (const tag of tags) {
      const v = voiceSet.find((v) => v.lang === tag);
      if (v) return v;
    }
    for (const tag of tags) {
      const v = voiceSet.find((v) => v.lang.startsWith(tag));
      if (v) return v;
    }
    const names = langSearchNames[langCode] ?? [];
    for (const name of names) {
      const v = voiceSet.find((v) =>
        v.name.toLowerCase().includes(name.toLowerCase()),
      );
      if (v) return v;
    }
  }
  return null;
}

/**
 * Speak text using the Web Speech API.
 * Cancels any in-progress speech first.
 */
export function speakText(
  text: string,
  langCode: string,
  voices: SpeechSynthesisVoice[],
  onStart?: () => void,
  onEnd?: () => void,
  onError?: () => void,
): void {
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const voice = findVoice(voices, langCode);
  if (voice) {
    utterance.voice = voice;
    utterance.lang = voice.lang;
  } else {
    utterance.lang = langCode === 'en' ? 'en-IN' : `${langCode}-IN`;
  }
  utterance.rate = 0.9;
  utterance.pitch = 1;
  utterance.volume = 1;
  if (onStart) utterance.onstart = onStart;
  if (onEnd) utterance.onend = onEnd;
  if (onError) utterance.onerror = onError;
  speechSynthesis.speak(utterance);
  // Chromium sometimes starts paused — kick it
  setTimeout(() => {
    if (speechSynthesis.paused) speechSynthesis.resume();
  }, 150);
}

