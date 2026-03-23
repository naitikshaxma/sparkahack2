export function detectTextLanguage(text: string): "hi" | "en" {
  return /[\u0900-\u097F]/.test(text || "") ? "hi" : "en";
}

export function getGreeting(language: "hi" | "en"): string {
  return language === "hi"
    ? "नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?"
    : "Hello, I am VoiceOS Bharat. How can I help you today?";
}

export function getFriendlyError(message: string, language: "hi" | "en"): string {
  if (!message) {
    return language === "hi" ? "कुछ समस्या हुई। कृपया फिर से कोशिश करें।" : "Something went wrong. Please try again.";
  }

  const lowered = message.toLowerCase();
  if (lowered.includes("network") || lowered.includes("failed") || lowered.includes("fetch")) {
    return language === "hi"
      ? "नेटवर्क समस्या आई। कृपया दोबारा प्रयास करें।"
      : "We hit a network issue. Please retry.";
  }

  return language === "hi" ? "क्षमा करें, मैं अभी जवाब नहीं दे पाया।" : "Sorry, I could not complete that just now.";
}
