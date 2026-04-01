import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Menu, Mic, RotateCcw } from "lucide-react";
import BackButton from "./BackButton";
import SparkleBackground from "./SparkleBackground";
import {
  clearSessionId,
  getOrCreateSessionId,
  interruptTts,
  resetSession,
  resolveApiUrl,
  setSessionId,
  synthesizeTts,
} from "@/services/api";
import { useVoiceStore } from "@/store/voiceStore";
import { detectTextLanguage, getGreeting } from "@/lib/languageUtils";
import { logFrontendEvent } from "@/services/frontendTelemetry";
import type { ConversationTurn } from "@/store/voiceStore";

type BrowserSpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: any) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  onspeechend: (() => void) | null;
  start: () => void;
  stop: () => void;
};


interface Language {
  code: string;
  name: string;
  nativeName: string;
  greeting: string;
}

interface VoiceInteractionProps {
  language: Language;
  onBack: () => void;
}

interface StoredConversation {
  id: string;
  sessionId: string;
  title: string;
  messages: ConversationTurn[];
  updatedAt: number;
}

interface RoleMessage {
  role: "user" | "assistant";
  text: string;
}

interface RoleConversation {
  id: string;
  title: string;
  messages: RoleMessage[];
  updatedAt?: number;
}

const MAX_CONVERSATIONS = 10;
const MAX_MESSAGES_PER_CONVERSATION = 5;
const PHONE_STORAGE_KEY = "voice_os_user_phone";
const ROLE_CONVERSATIONS_KEY = "voice_os_conversations";
const ROLE_ACTIVE_CONVERSATION_KEY = "voice_os_active_conversation_id";
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || "";
const CONVERSATION_SYNC_DEBOUNCE_MS = 800;
const LEGACY_PLACEHOLDERS = ["aapki awaaz mil gayi", "your voice was transcribed"];

type UiCopy = {
  appLabel: string;
  closeMenu: string;
  openMenu: string;
  chats: string;
  newChat: string;
  noConversations: string;
  changeLanguage: string;
  restart: string;
  startConversationHint: string;
  statusListening: string;
  statusProcessing: string;
  statusSpeaking: string;
  statusInterrupted: string;
  statusIdle: string;
  liveTranscript: string;
  speechWillAppear: string;
  typeHere: string;
  send: string;
  retry: string;
  micControl: string;
  textInput: string;
  simpleError: string;
  processingAudio: string;
  quickApply: string;
  quickAmount: string;
  quickDocs: string;
  quickApplyQuery: (scheme: string) => string;
  quickAmountQuery: (scheme: string) => string;
  quickDocsQuery: (scheme: string) => string;
};

const UI_COPY: Record<string, UiCopy> = {
  en: {
    appLabel: "Voice assistant interface",
    closeMenu: "Close menu",
    openMenu: "Open menu",
    chats: "Chats",
    newChat: "New chat",
    noConversations: "No conversations yet",
    changeLanguage: "Change language",
    restart: "Restart",
    startConversationHint: "Start a new conversation",
    statusListening: "Listening...",
    statusProcessing: "Processing...",
    statusSpeaking: "Speaking...",
    statusInterrupted: "Tap the mic to speak again",
    statusIdle: "Tap the mic to speak",
    liveTranscript: "Live transcript",
    speechWillAppear: "Your speech will appear here",
    typeHere: "Type here...",
    send: "Send",
    retry: "Retry",
    micControl: "Control microphone",
    textInput: "Text input",
    simpleError: "I didn't catch that. Please say it again.",
    processingAudio: "(🎤 Processing audio...)",
    quickApply: "How to apply?",
    quickAmount: "How much money will I get?",
    quickDocs: "What documents are needed?",
    quickApplyQuery: (scheme) => `How to apply for ${scheme}?`,
    quickAmountQuery: (scheme) => `How much money will I get from ${scheme}?`,
    quickDocsQuery: (scheme) => `What documents are needed for ${scheme}?`,
  },
  hi: {
    appLabel: "वॉइस असिस्टेंट इंटरफेस",
    closeMenu: "मेनू बंद करें",
    openMenu: "मेनू खोलें",
    chats: "बातचीत",
    newChat: "नई बातचीत",
    noConversations: "अभी कोई बातचीत नहीं",
    changeLanguage: "भाषा बदलें",
    restart: "रीस्टार्ट",
    startConversationHint: "नई बात शुरू करें",
    statusListening: "सुन रहा हूँ...",
    statusProcessing: "समझ रहा हूँ...",
    statusSpeaking: "बोल रहा हूँ...",
    statusInterrupted: "माइक दबाकर फिर बोलिए",
    statusIdle: "माइक दबाकर बोलिए",
    liveTranscript: "लाइव ट्रांसक्रिप्ट",
    speechWillAppear: "आपकी बात यहां दिखेगी",
    typeHere: "यहाँ लिखें...",
    send: "भेजें",
    retry: "फिर से",
    micControl: "माइक्रोफ़ोन नियंत्रित करें",
    textInput: "टेक्स्ट इनपुट",
    simpleError: "समझ नहीं आया, फिर से बोलिए।",
    processingAudio: "(🎤 ऑडियो प्रोसेस हो रहा है...)",
    quickApply: "आवेदन कैसे करें?",
    quickAmount: "कितना पैसा मिलेगा?",
    quickDocs: "कौन से दस्तावेज़ चाहिए?",
    quickApplyQuery: (scheme) => `${scheme} के लिए आवेदन कैसे करें?`,
    quickAmountQuery: (scheme) => `${scheme} से कितना पैसा मिलेगा?`,
    quickDocsQuery: (scheme) => `${scheme} के लिए कौन से दस्तावेज़ चाहिए?`,
  },
  bn: {
    appLabel: "ভয়েস সহকারী ইন্টারফেস",
    closeMenu: "মেনু বন্ধ করুন",
    openMenu: "মেনু খুলুন",
    chats: "আলাপ",
    newChat: "নতুন আলাপ",
    noConversations: "এখনও কোনো আলাপ নেই",
    changeLanguage: "ভাষা বদলান",
    restart: "রিস্টার্ট",
    startConversationHint: "নতুন করে কথা শুরু করুন",
    statusListening: "শুনছি...",
    statusProcessing: "বুঝছি...",
    statusSpeaking: "বলছি...",
    statusInterrupted: "মাইক চাপুন ও আবার বলুন",
    statusIdle: "মাইক চাপুন ও বলুন",
    liveTranscript: "লাইভ ট্রান্সক্রিপ্ট",
    speechWillAppear: "আপনার কথা এখানে দেখা যাবে",
    typeHere: "এখানে লিখুন...",
    send: "পাঠান",
    retry: "আবার চেষ্টা করুন",
    micControl: "মাইক্রোফোন নিয়ন্ত্রণ করুন",
    textInput: "টেক্সট ইনপুট",
    simpleError: "বুঝতে পারিনি, আবার বলুন।",
    processingAudio: "(🎤 অডিও প্রসেস হচ্ছে...)",
    quickApply: "কীভাবে আবেদন করব?",
    quickAmount: "কত টাকা পাব?",
    quickDocs: "কোন নথি লাগবে?",
    quickApplyQuery: (scheme) => `${scheme} এর জন্য কীভাবে আবেদন করব?`,
    quickAmountQuery: (scheme) => `${scheme} থেকে কত টাকা পাব?`,
    quickDocsQuery: (scheme) => `${scheme} এর জন্য কোন নথি লাগবে?`,
  },
  pa: {
    appLabel: "ਵੌਇਸ ਸਹਾਇਕ ਇੰਟਰਫੇਸ",
    closeMenu: "ਮੈਨੂ ਬੰਦ ਕਰੋ",
    openMenu: "ਮੈਨੂ ਖੋਲ੍ਹੋ",
    chats: "ਗੱਲਬਾਤ",
    newChat: "ਨਵੀਂ ਗੱਲਬਾਤ",
    noConversations: "ਹਾਲੇ ਕੋਈ ਗੱਲਬਾਤ ਨਹੀਂ",
    changeLanguage: "ਭਾਸ਼ਾ ਬਦਲੋ",
    restart: "ਰੀਸਟਾਰਟ",
    startConversationHint: "ਨਵੀਂ ਗੱਲ ਸ਼ੁਰੂ ਕਰੋ",
    statusListening: "ਸੁਣ ਰਿਹਾ ਹਾਂ...",
    statusProcessing: "ਸਮਝ ਰਿਹਾ ਹਾਂ...",
    statusSpeaking: "ਬੋਲ ਰਿਹਾ ਹਾਂ...",
    statusInterrupted: "ਮਾਈਕ ਦਬਾਓ ਅਤੇ ਫਿਰ ਬੋਲੋ",
    statusIdle: "ਮਾਈਕ ਦਬਾਓ ਅਤੇ ਬੋਲੋ",
    liveTranscript: "ਲਾਈਵ ਟ੍ਰਾਂਸਕ੍ਰਿਪਟ",
    speechWillAppear: "ਤੁਹਾਡੀ ਗੱਲ ਇੱਥੇ ਦਿਖੇਗੀ",
    typeHere: "ਇੱਥੇ ਲਿਖੋ...",
    send: "ਭੇਜੋ",
    retry: "ਮੁੜ ਕੋਸ਼ਿਸ਼ ਕਰੋ",
    micControl: "ਮਾਈਕ ਕੰਟਰੋਲ ਕਰੋ",
    textInput: "ਟੈਕਸਟ ਇਨਪੁੱਟ",
    simpleError: "ਸਮਝ ਨਹੀਂ ਆਇਆ, ਫਿਰ ਤੋਂ ਬੋਲੋ।",
    processingAudio: "(🎤 ਆਡੀਓ ਪ੍ਰੋਸੈਸ ਹੋ ਰਿਹਾ ਹੈ...)",
    quickApply: "ਅਰਜ਼ੀ ਕਿਵੇਂ ਕਰੀਏ?",
    quickAmount: "ਕਿੰਨਾ ਪੈਸਾ ਮਿਲੇਗਾ?",
    quickDocs: "ਕਿਹੜੇ ਦਸਤਾਵੇਜ਼ ਚਾਹੀਦੇ ਹਨ?",
    quickApplyQuery: (scheme) => `${scheme} ਲਈ ਅਰਜ਼ੀ ਕਿਵੇਂ ਕਰੀਏ?`,
    quickAmountQuery: (scheme) => `${scheme} ਤੋਂ ਕਿੰਨਾ ਪੈਸਾ ਮਿਲੇਗਾ?`,
    quickDocsQuery: (scheme) => `${scheme} ਲਈ ਕਿਹੜੇ ਦਸਤਾਵੇਜ਼ ਚਾਹੀਦੇ ਹਨ?`,
  },
  ta: {
    appLabel: "குரல் உதவி இடைமுகம்",
    closeMenu: "மெனுவை மூடு",
    openMenu: "மெனுவை திற",
    chats: "உரையாடல்கள்",
    newChat: "புதிய உரையாடல்",
    noConversations: "இன்னும் உரையாடல்கள் இல்லை",
    changeLanguage: "மொழியை மாற்று",
    restart: "மறுதொடங்கு",
    startConversationHint: "புதிய உரையாடலை தொடங்கு",
    statusListening: "கேட்கிறேன்...",
    statusProcessing: "புரிந்துகொள்கிறேன்...",
    statusSpeaking: "பேசுகிறேன்...",
    statusInterrupted: "மைக் அழுத்தி மீண்டும் பேசுங்கள்",
    statusIdle: "மைக் அழுத்தி பேசுங்கள்",
    liveTranscript: "நேரடி உரை",
    speechWillAppear: "உங்கள் பேச்சு இங்கே காணப்படும்",
    typeHere: "இங்கே எழுதுங்கள்...",
    send: "அனுப்பு",
    retry: "மீண்டும் முயலவும்",
    micControl: "மைக்ரோஃபோனை கட்டுப்படுத்து",
    textInput: "உரை உள்ளீடு",
    simpleError: "புரியவில்லை, மீண்டும் சொல்லுங்கள்.",
    processingAudio: "(🎤 ஆடியோ செயலாக்கப்படுகிறது...)",
    quickApply: "எப்படி விண்ணப்பிக்கலாம்?",
    quickAmount: "எவ்வளவு பணம் கிடைக்கும்?",
    quickDocs: "எந்த ஆவணங்கள் தேவை?",
    quickApplyQuery: (scheme) => `${scheme} க்கு எப்படி விண்ணப்பிக்கலாம்?`,
    quickAmountQuery: (scheme) => `${scheme} மூலம் எவ்வளவு பணம் கிடைக்கும்?`,
    quickDocsQuery: (scheme) => `${scheme} க்கு எந்த ஆவணங்கள் தேவை?`,
  },
  te: {
    appLabel: "వాయిస్ సహాయక ఇంటర్‌ఫేస్",
    closeMenu: "మెనూ మూసండి",
    openMenu: "మెనూ తెరవండి",
    chats: "సంభాషణలు",
    newChat: "కొత్త సంభాషణ",
    noConversations: "ఇంకా సంభాషణలు లేవు",
    changeLanguage: "భాష మార్చండి",
    restart: "రీస్టార్ట్",
    startConversationHint: "కొత్త సంభాషణ ప్రారంభించండి",
    statusListening: "వింటున్నాను...",
    statusProcessing: "అర్థం చేసుకుంటున్నాను...",
    statusSpeaking: "మాట్లాడుతున్నాను...",
    statusInterrupted: "మైక్ నొక్కి మళ్లీ మాట్లాడండి",
    statusIdle: "మైక్ నొక్కి మాట్లాడండి",
    liveTranscript: "లైవ్ ట్రాన్స్క్రిప్ట్",
    speechWillAppear: "మీ మాట ఇక్కడ కనిపిస్తుంది",
    typeHere: "ఇక్కడ టైప్ చేయండి...",
    send: "పంపండి",
    retry: "మళ్లీ ప్రయత్నించండి",
    micControl: "మైక్రోఫోన్ నియంత్రణ",
    textInput: "టెక్స్ట్ ఇన్‌పుట్",
    simpleError: "అర్థం కాలేదు, మళ్లీ చెప్పండి.",
    processingAudio: "(🎤 ఆడియో ప్రాసెస్ అవుతోంది...)",
    quickApply: "ఎలా దరఖాస్తు చేయాలి?",
    quickAmount: "ఎంత డబ్బు వస్తుంది?",
    quickDocs: "ఏ పత్రాలు కావాలి?",
    quickApplyQuery: (scheme) => `${scheme} కోసం ఎలా దరఖాస్తు చేయాలి?`,
    quickAmountQuery: (scheme) => `${scheme} నుంచి ఎంత డబ్బు వస్తుంది?`,
    quickDocsQuery: (scheme) => `${scheme} కోసం ఏ పత్రాలు కావాలి?`,
  },
  mr: {
    appLabel: "व्हॉइस सहाय्यक इंटरफेस",
    closeMenu: "मेनू बंद करा",
    openMenu: "मेनू उघडा",
    chats: "संभाषणे",
    newChat: "नवीन संभाषण",
    noConversations: "अजून संभाषणे नाहीत",
    changeLanguage: "भाषा बदला",
    restart: "रीस्टार्ट",
    startConversationHint: "नवीन संभाषण सुरू करा",
    statusListening: "ऐकत आहे...",
    statusProcessing: "समजून घेत आहे...",
    statusSpeaking: "बोलत आहे...",
    statusInterrupted: "माइक दाबून पुन्हा बोला",
    statusIdle: "माइक दाबून बोला",
    liveTranscript: "लाइव्ह ट्रान्सक्रिप्ट",
    speechWillAppear: "तुमचे बोलणे इथे दिसेल",
    typeHere: "इथे लिहा...",
    send: "पाठवा",
    retry: "पुन्हा प्रयत्न करा",
    micControl: "मायक्रोफोन नियंत्रित करा",
    textInput: "टेक्स्ट इनपुट",
    simpleError: "समजले नाही, पुन्हा बोला.",
    processingAudio: "(🎤 ऑडिओ प्रक्रिया होत आहे...)",
    quickApply: "अर्ज कसा करायचा?",
    quickAmount: "किती पैसे मिळतील?",
    quickDocs: "कोणती कागदपत्रे लागतील?",
    quickApplyQuery: (scheme) => `${scheme} साठी अर्ज कसा करायचा?`,
    quickAmountQuery: (scheme) => `${scheme} मधून किती पैसे मिळतील?`,
    quickDocsQuery: (scheme) => `${scheme} साठी कोणती कागदपत्रे लागतील?`,
  },
  gu: {
    appLabel: "વોઇસ સહાયક ઇન્ટરફેસ",
    closeMenu: "મેનુ બંધ કરો",
    openMenu: "મેનુ ખોલો",
    chats: "વાતચીત",
    newChat: "નવી વાતચીત",
    noConversations: "હજુ વાતચીત નથી",
    changeLanguage: "ભાષા બદલો",
    restart: "રીસ્ટાર્ટ",
    startConversationHint: "નવી વાતચીત શરૂ કરો",
    statusListening: "સાંભળી રહ્યો છું...",
    statusProcessing: "સમજી રહ્યો છું...",
    statusSpeaking: "બોલી રહ્યો છું...",
    statusInterrupted: "માઇક દબાવીને ફરી બોલો",
    statusIdle: "માઇક દબાવીને બોલો",
    liveTranscript: "લાઇવ ટ્રાન્સક્રિપ્ટ",
    speechWillAppear: "તમારી વાત અહીં દેખાશે",
    typeHere: "અહીં લખો...",
    send: "મોકલો",
    retry: "ફરી પ્રયાસ કરો",
    micControl: "માઇક્રોફોન નિયંત્રિત કરો",
    textInput: "ટેક્સ્ટ ઇનપુટ",
    simpleError: "સમજાયું નથી, ફરી બોલો.",
    processingAudio: "(🎤 ઓડિઓ પ્રક્રિયા થઈ રહી છે...)",
    quickApply: "અરજી કેવી રીતે કરવી?",
    quickAmount: "કેટલા પૈસા મળશે?",
    quickDocs: "કયા દસ્તાવેજો જોઈએ?",
    quickApplyQuery: (scheme) => `${scheme} માટે અરજી કેવી રીતે કરવી?`,
    quickAmountQuery: (scheme) => `${scheme}માંથી કેટલા પૈસા મળશે?`,
    quickDocsQuery: (scheme) => `${scheme} માટે કયા દસ્તાવેજો જોઈએ?`,
  },
  kn: {
    appLabel: "ಧ್ವನಿ ಸಹಾಯಕ ಇಂಟರ್‌ಫೇಸ್",
    closeMenu: "ಮೆನು ಮುಚ್ಚಿ",
    openMenu: "ಮೆನು ತೆರೆಯಿ",
    chats: "ಸಂಭಾಷಣೆಗಳು",
    newChat: "ಹೊಸ ಸಂಭಾಷಣೆ",
    noConversations: "ಇನ್ನೂ ಸಂಭಾಷಣೆಗಳು ಇಲ್ಲ",
    changeLanguage: "ಭಾಷೆ ಬದಲಿಸಿ",
    restart: "ರೀಸ್ಟಾರ್ಟ್",
    startConversationHint: "ಹೊಸ ಸಂಭಾಷಣೆಯನ್ನು ಆರಂಭಿಸಿ",
    statusListening: "ಕೇಳುತ್ತಿದ್ದೇನೆ...",
    statusProcessing: "ಅರ್ಥಮಾಡಿಕೊಳ್ಳುತ್ತಿದ್ದೇನೆ...",
    statusSpeaking: "ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ...",
    statusInterrupted: "ಮೈಕ್ ಒತ್ತಿ ಮತ್ತೆ ಮಾತನಾಡಿ",
    statusIdle: "ಮೈಕ್ ಒತ್ತಿ ಮಾತನಾಡಿ",
    liveTranscript: "ಲೈವ್ ಟ್ರಾನ್ಸ್‌ಕ್ರಿಪ್ಟ್",
    speechWillAppear: "ನಿಮ್ಮ ಮಾತು ಇಲ್ಲಿ ಕಾಣಿಸುತ್ತದೆ",
    typeHere: "ಇಲ್ಲಿ ಬರೆಯಿರಿ...",
    send: "ಕಳುಹಿಸಿ",
    retry: "ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ",
    micControl: "ಮೈಕ್ರೋಫೋನ್ ನಿಯಂತ್ರಿಸಿ",
    textInput: "ಪಠ್ಯ ಇನ್‌ಪುಟ್",
    simpleError: "ಅರ್ಥವಾಗಲಿಲ್ಲ, ಮತ್ತೆ ಹೇಳಿ.",
    processingAudio: "(🎤 ಆಡಿಯೋ ಪ್ರಕ್ರಿಯೆಯಲ್ಲಿದೆ...)",
    quickApply: "ಅರ್ಜಿಯನ್ನು ಹೇಗೆ ಸಲ್ಲಿಸಬೇಕು?",
    quickAmount: "ಎಷ್ಟು ಹಣ ಸಿಗುತ್ತದೆ?",
    quickDocs: "ಯಾವ ದಾಖಲೆಗಳು ಬೇಕು?",
    quickApplyQuery: (scheme) => `${scheme}ಗಾಗಿ ಅರ್ಜಿ ಹೇಗೆ ಸಲ್ಲಿಸಬೇಕು?`,
    quickAmountQuery: (scheme) => `${scheme}ರಿಂದ ಎಷ್ಟು ಹಣ ಸಿಗುತ್ತದೆ?`,
    quickDocsQuery: (scheme) => `${scheme}ಗಾಗಿ ಯಾವ ದಾಖಲೆಗಳು ಬೇಕು?`,
  },
  ur: {
    appLabel: "وائس اسسٹنٹ انٹرفیس",
    closeMenu: "مینو بند کریں",
    openMenu: "مینو کھولیں",
    chats: "گفتگو",
    newChat: "نئی گفتگو",
    noConversations: "ابھی کوئی گفتگو نہیں",
    changeLanguage: "زبان تبدیل کریں",
    restart: "ری اسٹارٹ",
    startConversationHint: "نئی گفتگو شروع کریں",
    statusListening: "سن رہا ہوں...",
    statusProcessing: "سمجھ رہا ہوں...",
    statusSpeaking: "بول رہا ہوں...",
    statusInterrupted: "مائیک دبا کر دوبارہ بولیں",
    statusIdle: "مائیک دبا کر بولیں",
    liveTranscript: "لائیو ٹرانسکرپٹ",
    speechWillAppear: "آپ کی بات یہاں نظر آئے گی",
    typeHere: "یہاں لکھیں...",
    send: "بھیجیں",
    retry: "دوبارہ کوشش کریں",
    micControl: "مائیکروفون کنٹرول کریں",
    textInput: "متن ان پٹ",
    simpleError: "سمجھ نہیں آیا، دوبارہ بولیں۔",
    processingAudio: "(🎤 آڈیو پروسیس ہو رہا ہے...)",
    quickApply: "درخواست کیسے کریں؟",
    quickAmount: "کتنے پیسے ملیں گے؟",
    quickDocs: "کون سے دستاویزات چاہئیں؟",
    quickApplyQuery: (scheme) => `${scheme} کے لیے درخواست کیسے کریں؟`,
    quickAmountQuery: (scheme) => `${scheme} سے کتنے پیسے ملیں گے؟`,
    quickDocsQuery: (scheme) => `${scheme} کے لیے کون سے دستاویزات چاہئیں؟`,
  },
};

const getUiCopy = (language: string): UiCopy => UI_COPY[language] || UI_COPY.en;

const VoiceInteraction = ({ language, onBack }: VoiceInteractionProps) => {
  const selectedLanguage = localStorage.getItem("voice_os_language") || localStorage.getItem("language") || language.code || "en";
  const uiLanguage = selectedLanguage || "en";
  const voiceLanguage = uiLanguage;
  const backendLanguage: "hi" | "en" = voiceLanguage === "hi" ? "hi" : "en";
  const copy = useMemo(() => getUiCopy(uiLanguage), [uiLanguage]);

  const state = useVoiceStore((s) => s.voiceState);
  const transcriptFinal = useVoiceStore((s) => s.transcriptFinal);
  const assistantText = useVoiceStore((s) => s.responseText);
  const backendResponse = useVoiceStore((s) => s.backendResponse);
  const errorState = useVoiceStore((s) => s.errorState);
  const latency = useVoiceStore((s) => s.latency);
  const conversationHistory = useVoiceStore((s) => s.conversationHistory);
  const liveTranscript = useVoiceStore((s) => s.transcriptLive);

  const setVoiceState = useVoiceStore((s) => s.setVoiceState);
  const setLanguage = useVoiceStore((s) => s.setLanguage);
  const setDetectedLanguage = useVoiceStore((s) => s.setDetectedLanguage);
  const setLiveTranscript = useVoiceStore((s) => s.setLiveTranscript);
  const setFinalTranscript = useVoiceStore((s) => s.setFinalTranscript);
  const setResponseText = useVoiceStore((s) => s.setResponseText);
  const clearResponseStream = useVoiceStore((s) => s.clearResponseStream);
  const setStreamDone = useVoiceStore((s) => s.setStreamDone);
  const setBackendResponse = useVoiceStore((s) => s.setBackendResponse);
  const setErrorState = useVoiceStore((s) => s.setErrorState);
  const beginLatencyTracking = useVoiceStore((s) => s.beginLatencyTracking);
  const markFirstResponse = useVoiceStore((s) => s.markFirstResponse);
  const endLatencyTracking = useVoiceStore((s) => s.endLatencyTracking);
  const addConversationTurn = useVoiceStore((s) => s.addConversationTurn);
  const updateConversationAssistantText = useVoiceStore((s) => s.updateConversationAssistantText);
  const replaceConversationHistory = useVoiceStore((s) => s.replaceConversationHistory);
  const clearConversationHistory = useVoiceStore((s) => s.clearConversationHistory);
  const resetConversationState = useVoiceStore((s) => s.resetConversationState);

  const [textFallback, setTextFallback] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState<StoredConversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [roleConversations, setRoleConversations] = useState<RoleConversation[]>([]);
  const [isRecording, setIsRecording] = useState(false);

  const phoneId = useMemo(() => localStorage.getItem(PHONE_STORAGE_KEY) || "guest", []);
  const conversationsStorageKey = useMemo(() => `voice_conversations_${phoneId}`, [phoneId]);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaChunksRef = useRef<BlobPart[]>([]);
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const stopRequestedRef = useRef(false);
  const silenceTimerRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const currentTtsAudioRef = useRef<HTMLAudioElement | null>(null);
  const hasPlayedGreetingRef = useRef(false);
  const requestCounterRef = useRef(0);
  const processingRef = useRef(false);
  const lastTranscriptRef = useRef<{ text: string; ts: number }>({ text: "", ts: 0 });
  const activeTurnIdRef = useRef<string | null>(null);
  const liveTranscriptRef = useRef("");
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const syncTimerRef = useRef<number | null>(null);

  const getConversationTitle = useCallback((messages: ConversationTurn[]) => {
    const firstUser = messages.find((message) => message.userText && message.userText.trim());
    if (!firstUser) {
      return "";
    }
    const normalized = firstUser.userText.replace(/\s+/g, " ").trim();
    if (!normalized) {
      return "";
    }
    if (normalized.length > 32) {
      return `${normalized.slice(0, 32).trim()}...`;
    }
    return normalized;
  }, []);

  const syncConversationsToSupabase = useCallback(
    (payload: StoredConversation[]) => {
      if (!SUPABASE_URL || !SUPABASE_ANON_KEY || !phoneId || phoneId === "guest") {
        return;
      }
      const endpoint = `${SUPABASE_URL}/rest/v1/voice_conversations?on_conflict=user_id`;
      const body = JSON.stringify([
        {
          user_id: phoneId,
          payload: { conversations: payload },
          updated_at: new Date().toISOString(),
        },
      ]);

      fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
          Prefer: "resolution=merge-duplicates",
        },
        body,
      }).catch(() => undefined);
    },
    [phoneId],
  );

  const scheduleSupabaseSync = useCallback(
    (payload: StoredConversation[]) => {
      if (syncTimerRef.current !== null) {
        window.clearTimeout(syncTimerRef.current);
      }
      syncTimerRef.current = window.setTimeout(() => {
        syncTimerRef.current = null;
        syncConversationsToSupabase(payload);
      }, CONVERSATION_SYNC_DEBOUNCE_MS);
    },
    [syncConversationsToSupabase],
  );

  const sanitizeConversationMessages = useCallback(
    (messages: ConversationTurn[]) => messages.slice(-MAX_MESSAGES_PER_CONVERSATION),
    [],
  );

  const sanitizeRoleMessages = useCallback((messages: unknown): RoleMessage[] => {
    if (!Array.isArray(messages)) {
      return [];
    }
    return messages
      .filter((message) =>
        Boolean(message)
        && typeof (message as RoleMessage).text === "string"
        && ((message as RoleMessage).role === "user" || (message as RoleMessage).role === "assistant"),
      )
      .map((message) => ({
        role: (message as RoleMessage).role,
        text: (message as RoleMessage).text,
      }))
      .filter((message) => message.text.trim().length > 0)
      .filter((message) => {
        const normalized = message.text.trim().toLowerCase();
        return !LEGACY_PLACEHOLDERS.some((phrase) => normalized.includes(phrase));
      })
      .slice(-MAX_MESSAGES_PER_CONVERSATION);
  }, []);

  const buildRoleMessagesFromTurns = useCallback((messages: ConversationTurn[]) => {
    const roleMessages: RoleMessage[] = [];
    messages.forEach((turn) => {
      if (turn.userText) {
        roleMessages.push({ role: "user", text: turn.userText });
      }
      if (turn.assistantText) {
        roleMessages.push({ role: "assistant", text: turn.assistantText });
      }
    });
    return roleMessages.slice(-MAX_MESSAGES_PER_CONVERSATION);
  }, []);

  const buildTurnsFromRoleMessages = useCallback(
    (messages: RoleMessage[] | unknown) => {
      const turns: ConversationTurn[] = [];
      const sanitizedMessages = sanitizeRoleMessages(messages);
      let currentTurn: ConversationTurn | null = null;

      sanitizedMessages.forEach((message, index) => {
        if (message.role === "user") {
          if (currentTurn) {
            turns.push(currentTurn);
          }
          currentTurn = {
            id: `turn-${Date.now()}-${index}`,
            userText: message.text,
            assistantText: "",
            language: backendLanguage,
            createdAt: Date.now(),
          };
          return;
        }

        if (!currentTurn) {
          currentTurn = {
            id: `turn-${Date.now()}-${index}`,
            userText: "",
            assistantText: message.text,
            language: backendLanguage,
            createdAt: Date.now(),
          };
          if (currentTurn) {
            turns.push(currentTurn);
          }
          currentTurn = null;
          return;
        }

        currentTurn.assistantText = message.text;
        turns.push(currentTurn);
        currentTurn = null;
      });

      if (currentTurn) {
        turns.push(currentTurn);
      }

      return sanitizeConversationMessages(turns);
    },
    [backendLanguage, sanitizeConversationMessages, sanitizeRoleMessages],
  );

  const getRoleConversationTitle = useCallback((messages: RoleMessage[] | unknown) => {
    const sanitizedMessages = sanitizeRoleMessages(messages);
    const firstUser = sanitizedMessages.find((message) => message.role === "user" && message.text.trim());
    if (!firstUser) {
      return "";
    }
    return firstUser.text.trim().slice(0, 20);
  }, [sanitizeRoleMessages]);

  const setSimpleError = useCallback(() => {
    setErrorState(copy.simpleError);
  }, [copy.simpleError, setErrorState]);

  const ensureActiveConversationId = useCallback(() => {
    if (activeConversationId) {
      return activeConversationId;
    }
    const sessionId = `${Date.now()}`;
    setSessionId(sessionId);
    setActiveConversationId(sessionId);
    localStorage.setItem(ROLE_ACTIVE_CONVERSATION_KEY, sessionId);
    return sessionId;
  }, [activeConversationId, setActiveConversationId, setSessionId]);

  const stopListening = useCallback(() => {
    if (silenceTimerRef.current !== null) {
      window.clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    stopRequestedRef.current = true;
    setIsRecording(false);

    const recognition = recognitionRef.current;
    if (recognition) {
      try {
        recognition.onend = null;
        recognition.stop();
      } catch {
        // no-op
      }
      recognitionRef.current = null;
    }

    const recorder = mediaRecorderRef.current;
    if (recorder) {
      if (recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          // no-op
        }
      }
      mediaRecorderRef.current = null;
    }

    if (mediaStreamRef.current) {
      try {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      } catch {
        // no-op
      }
      mediaStreamRef.current = null;
    }

    mediaChunksRef.current = [];
  }, []);

  const stopAudio = useCallback(() => {
    if (!audioRef.current) return;
    try {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current.removeAttribute("src");
      audioRef.current.load();
    } catch {
      // no-op
    }
  }, []);

  const loadConversationIntoUi = useCallback(
    (conversation: StoredConversation) => {
      const sessionId = conversation.sessionId || conversation.id;
      stopListening();
      stopAudio();
      setActiveConversationId(conversation.id);
      replaceConversationHistory(sanitizeConversationMessages(conversation.messages || []));

      const lastAssistant = [...(conversation.messages || [])]
        .reverse()
        .find((message) => message.assistantText && message.assistantText.trim())?.assistantText;
      if (lastAssistant) {
        setResponseText(lastAssistant);
      } else {
        setResponseText(getGreeting(backendLanguage));
      }

      setLiveTranscript("");
      setFinalTranscript("");
      clearResponseStream();
      setStreamDone(false);
      setErrorState(null);
      setVoiceState("idle");
      setTextFallback("");
      setSessionId(sessionId);
    },
    [
      clearResponseStream,
      replaceConversationHistory,
      sanitizeConversationMessages,
      setErrorState,
      setFinalTranscript,
      setLiveTranscript,
      setResponseText,
      setSessionId,
      setStreamDone,
      setVoiceState,
      stopAudio,
      stopListening,
      voiceLanguage,
    ],
  );

  const handleSelectConversation = useCallback(
    (conversationId: string) => {
      const stored = roleConversations.find((item) => item.id === conversationId);
      const conversation: StoredConversation = {
        id: conversationId,
        sessionId: conversationId,
        title: stored?.title || "",
        messages: stored ? buildTurnsFromRoleMessages(stored.messages) : [],
        updatedAt: stored?.updatedAt || Date.now(),
      };
      localStorage.setItem(ROLE_ACTIVE_CONVERSATION_KEY, conversationId);
      setSidebarOpen(false);
      loadConversationIntoUi(conversation);
    },
    [buildTurnsFromRoleMessages, loadConversationIntoUi, roleConversations],
  );

  const handleNewChat = useCallback(() => {
    stopListening();
    stopAudio();
    requestCounterRef.current += 1;
    processingRef.current = false;
    lastTranscriptRef.current = { text: "", ts: 0 };

    const newId = `${Date.now()}`;
    localStorage.setItem(ROLE_ACTIVE_CONVERSATION_KEY, newId);
    const emptyConversation: StoredConversation = {
      id: newId,
      sessionId: newId,
      title: "",
      messages: [],
      updatedAt: Date.now(),
    };
    setSidebarOpen(false);
    loadConversationIntoUi(emptyConversation);
  }, [loadConversationIntoUi, stopAudio, stopListening]);

  const parseStoredConversations = useCallback(
    (raw: string) => {
      try {
        const parsed = JSON.parse(raw) as StoredConversation[];
        if (!Array.isArray(parsed)) {
          return [];
        }
        const sanitized = parsed.map((item) => {
          const messages = sanitizeConversationMessages(Array.isArray(item.messages) ? item.messages : []);
          const sessionId = typeof item.sessionId === "string" && item.sessionId ? item.sessionId : item.id;
          const id = typeof item.id === "string" && item.id ? item.id : sessionId;
          const title = typeof item.title === "string" && item.title ? item.title : getConversationTitle(messages);
          const updatedAt = typeof item.updatedAt === "number" ? item.updatedAt : Date.now();
          return {
            id,
            sessionId,
            title,
            messages,
            updatedAt,
          };
        });
        return [...sanitized].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_CONVERSATIONS);
      } catch {
        return [];
      }
    },
    [getConversationTitle, sanitizeConversationMessages],
  );

  useEffect(() => {
    const roleRaw = localStorage.getItem(ROLE_CONVERSATIONS_KEY);
    let parsedRoleConversations: RoleConversation[] = [];
    if (roleRaw) {
      try {
        const parsed = JSON.parse(roleRaw);
        parsedRoleConversations = Array.isArray(parsed) ? (parsed as RoleConversation[]) : [];
      } catch {
        parsedRoleConversations = [];
      }
    }

    if (parsedRoleConversations.length > 0) {
      const mapped = parsedRoleConversations
        .map((item, index) => {
          if (!item || typeof item.id !== "string") {
            return null;
          }
          const roleMessages = sanitizeRoleMessages(item.messages);
          if (roleMessages.length === 0) {
            return null;
          }
          const updatedAt = typeof item.updatedAt === "number" ? item.updatedAt : Date.now();
          return {
            id: item.id,
            sessionId: item.id,
            title: item.title || getRoleConversationTitle(item.messages),
            messages: buildTurnsFromRoleMessages(item.messages),
            updatedAt,
            order: index,
          };
        })
        .filter((item): item is StoredConversation & { order: number } => Boolean(item));

      const ordered = [...mapped]
        .sort((a, b) => (b.updatedAt - a.updatedAt) || (a.order - b.order))
        .slice(0, MAX_CONVERSATIONS)
        .map(({ order, ...rest }) => rest);

      if (ordered.length > 0) {
        const orderedRole = ordered.map((item) => ({
          id: item.id,
          title: item.title,
          messages: buildRoleMessagesFromTurns(item.messages),
          updatedAt: item.updatedAt,
        }));
        setRoleConversations(orderedRole);
        const storedActive = localStorage.getItem(ROLE_ACTIVE_CONVERSATION_KEY);
        const resolvedActive = storedActive
          ? ordered.find((item) => item.id === storedActive) || ordered[0]
          : ordered[0];
        if (resolvedActive?.id && (!storedActive || resolvedActive.id !== storedActive)) {
          localStorage.setItem(ROLE_ACTIVE_CONVERSATION_KEY, resolvedActive.id);
        }
        setConversations(ordered);
        if (resolvedActive) {
          loadConversationIntoUi(resolvedActive);
        }
        return;
      }

      setRoleConversations([]);
      setConversations([]);
    }

    const raw = localStorage.getItem(conversationsStorageKey);
    if (raw) {
      const parsed = parseStoredConversations(raw);
      if (parsed.length > 0) {
        setConversations(parsed);
        const roleSeed = parsed
          .map((item) => ({
            id: item.id,
            title: item.title,
            messages: buildRoleMessagesFromTurns(item.messages),
            updatedAt: item.updatedAt,
          }))
          .filter((item) => item.messages.length > 0)
          .slice(0, MAX_CONVERSATIONS);
        setRoleConversations(roleSeed);
        loadConversationIntoUi(parsed[0]);
        return;
      }
    }

    const sessionId = getOrCreateSessionId();
    const legacyKey = `voice_history_${sessionId}`;
    const legacyRaw = localStorage.getItem(legacyKey);
    let legacyMessages: ConversationTurn[] = [];
    if (legacyRaw) {
      try {
        const parsed = JSON.parse(legacyRaw) as ConversationTurn[];
        if (Array.isArray(parsed)) {
          legacyMessages = parsed;
        }
      } catch {
        legacyMessages = [];
      }
    }

    const seedMessages = sanitizeConversationMessages(legacyMessages);
    if (seedMessages.length > 0) {
      const seedConversation: StoredConversation = {
        id: sessionId,
        sessionId,
        title: getConversationTitle(seedMessages),
        messages: seedMessages,
        updatedAt: Date.now(),
      };
      setConversations([seedConversation]);
      setRoleConversations([
        {
          id: seedConversation.id,
          title: seedConversation.title,
          messages: buildRoleMessagesFromTurns(seedConversation.messages),
          updatedAt: seedConversation.updatedAt,
        },
      ]);
      loadConversationIntoUi(seedConversation);
      return;
    }

    setSessionId(sessionId);
  }, [
    buildRoleMessagesFromTurns,
    conversationsStorageKey,
    getConversationTitle,
    loadConversationIntoUi,
    parseStoredConversations,
    sanitizeConversationMessages,
    setSessionId,
  ]);

  useEffect(() => {
    if (!activeConversationId) {
      return;
    }
    const trimmed = sanitizeConversationMessages(conversationHistory);
    if (trimmed.length === 0) {
      return;
    }
    setConversations((prev) => {
      const now = Date.now();
      let updated = false;
      const next = prev.map((item) => {
        if (item.id !== activeConversationId) {
          return item;
        }
        updated = true;
        return {
          ...item,
          title: item.title || getConversationTitle(trimmed),
          messages: trimmed,
          updatedAt: now,
        };
      });

      if (!updated) {
        next.unshift({
          id: activeConversationId,
          sessionId: activeConversationId,
          title: getConversationTitle(trimmed),
          messages: trimmed,
          updatedAt: now,
        });
      }

      return [...next].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_CONVERSATIONS);
    });
  }, [activeConversationId, conversationHistory, getConversationTitle, sanitizeConversationMessages]);

  useEffect(() => {
    if (conversations.length === 0) {
      return;
    }
    localStorage.setItem(conversationsStorageKey, JSON.stringify(conversations));
    const activeConversation = conversations.find((item) => item.id === activeConversationId);
    if (activeConversation) {
      const legacyKey = `voice_history_${activeConversation.sessionId}`;
      localStorage.setItem(legacyKey, JSON.stringify(activeConversation.messages));
    }

    const orderedConversations = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);
    const roleConversations = orderedConversations
      .map((conversation) => {
        const roleMessages = buildRoleMessagesFromTurns(conversation.messages);
        if (roleMessages.length === 0) {
          return null;
        }
        return {
          id: conversation.id,
          title: conversation.title || getRoleConversationTitle(roleMessages),
          messages: roleMessages,
          updatedAt: conversation.updatedAt,
        };
      })
      .filter((item): item is RoleConversation & { updatedAt: number } => Boolean(item))
      .slice(0, MAX_CONVERSATIONS);

    if (roleConversations.length > 0) {
      localStorage.setItem(ROLE_CONVERSATIONS_KEY, JSON.stringify(roleConversations));
      setRoleConversations(roleConversations);
      if (activeConversationId) {
        localStorage.setItem(ROLE_ACTIVE_CONVERSATION_KEY, activeConversationId);
      }
    }

    scheduleSupabaseSync(conversations);
  }, [
    activeConversationId,
    buildRoleMessagesFromTurns,
    conversations,
    conversationsStorageKey,
    getRoleConversationTitle,
    scheduleSupabaseSync,
  ]);

  useEffect(() => {
    return () => {
      if (syncTimerRef.current !== null) {
        window.clearTimeout(syncTimerRef.current);
      }
    };
  }, []);

  // Auto-scroll to newest message
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversationHistory]);

  useEffect(() => {
    liveTranscriptRef.current = liveTranscript || "";
  }, [liveTranscript]);

  const playAudioFromBase64 = useCallback(
    async (audioBase64?: string | null) => {
      if (!audioBase64) return;

      // Always stop active recognition while assistant is speaking.
      stopListening();
      stopAudio();
      setVoiceState("speaking");

      const src = audioBase64.startsWith("data:audio") ? audioBase64 : `data:audio/mp3;base64,${audioBase64}`;

      await new Promise<void>((resolve) => {
        const audio = audioRef.current;
        if (!audio) {
          setVoiceState("idle");
          resolve();
          return;
        }

        audio.pause();
        audio.currentTime = 0;

        audio.src = src;
        audio.load();

        audio.onended = () => {
          setVoiceState("idle");
          resolve();
        };

        audio.onerror = () => {
          setVoiceState("idle");
          resolve();
        };

        audio.play().catch((err) => {
          if (import.meta.env.DEV) console.warn("playAudioFromBase64 play failed:", err);
          setVoiceState("idle");
          resolve();
        });
      });
    },
    [setVoiceState, stopAudio, stopListening],
  );

  const speakText = useCallback(
    async (text: string) => {
      try {
        const tts = await synthesizeTts(text, voiceLanguage);
        await playAudioFromBase64(tts.audio_base64);
      } catch {
        setVoiceState("idle");
      }
    },
    [playAudioFromBase64, setVoiceState, voiceLanguage],
  );

  const playTts = useCallback(
    async (text: string) => {
      const safeText = (text || "").trim();
      if (!safeText) {
        setVoiceState("idle");
        return;
      }

      try {
        setVoiceState("speaking");
        if (currentTtsAudioRef.current) {
          try {
            currentTtsAudioRef.current.pause();
          } catch {
            // no-op
          }
          currentTtsAudioRef.current = null;
        }

        const response = await fetch(resolveApiUrl("/tts"), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-language": voiceLanguage,
          },
          body: JSON.stringify({ text: safeText, language: voiceLanguage }),
        });

        if (!response.ok) {
          throw new Error(`TTS request failed: ${response.status}`);
        }

        const payload = await response.json() as {
          audio_base64?: string;
        };
        console.log("TTS response:", payload);
        const base64 = String(payload?.audio_base64 || "").trim();
        if (!base64) {
          throw new Error("TTS response missing audio_base64");
        }

        const src = base64.startsWith("data:audio") ? base64 : `data:audio/mp3;base64,${base64}`;
        const audio = new Audio(src);
        currentTtsAudioRef.current = audio;
        await new Promise<void>((resolve) => {
          const speakFallback = () => {
            try {
              const utterance = new SpeechSynthesisUtterance(safeText);
              utterance.lang = voiceLanguage === "hi" ? "hi-IN" : "en-US";
              utterance.onend = () => resolve();
              utterance.onerror = () => resolve();
              window.speechSynthesis.cancel();
              window.speechSynthesis.speak(utterance);
            } catch {
              resolve();
            }
          };

          audio.onended = () => {
            if (currentTtsAudioRef.current === audio) {
              currentTtsAudioRef.current = null;
            }
            resolve();
          };
          audio.onerror = () => {
            if (currentTtsAudioRef.current === audio) {
              currentTtsAudioRef.current = null;
            }
            speakFallback();
          };
          audio.play().catch(() => {
            if (currentTtsAudioRef.current === audio) {
              currentTtsAudioRef.current = null;
            }
            speakFallback();
          });
        });
      } catch {
        try {
          const utterance = new SpeechSynthesisUtterance(safeText);
          utterance.lang = voiceLanguage === "hi" ? "hi-IN" : "en-US";
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(utterance);
        } catch {
          setSimpleError();
        }
      } finally {
        setVoiceState("idle");
      }
    },
    [setSimpleError, setVoiceState, voiceLanguage],
  );

  const handleIntent = useCallback(
    async (text: string, turnId: string) => {
      const cleaned = (text || "").trim();
      if (!cleaned) {
        setSimpleError();
        return;
      }

      try {
        const response = await fetch(resolveApiUrl("/intent"), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-language": voiceLanguage,
          },
          body: JSON.stringify({ text: cleaned, language: voiceLanguage }),
        });
        if (!response.ok) {
          throw new Error(`Intent request failed: ${response.status}`);
        }

        const data = await response.json() as {
          success?: boolean;
          type?: string;
          message?: string;
          confidence?: number;
          data?: {
            message?: string;
            scheme?: string;
            summary?: string;
            next_step?: string;
          };
        };

        const mergedResponse = String(data?.message || "❌ केवल इन योजनाओं के बारे में पूछें (15 schemes only supported)").trim();

        setBackendResponse({
          session_id: getOrCreateSessionId(),
          response_text: mergedResponse,
          field_name: null,
          validation_passed: data?.success !== false,
          validation_error: data?.success === false ? (data?.message || "Request failed") : null,
          session_complete: false,
          confidence: Number(data?.confidence || 0),
          action: data?.type || null,
          mode: "info",
          scheme_details: data?.data?.scheme
            ? {
                title: data.data.scheme,
                description: data?.data?.summary || undefined,
                next_step: data?.data?.next_step || undefined,
              }
            : null,
        });
        setResponseText(mergedResponse);
        updateConversationAssistantText(turnId, mergedResponse);
        markFirstResponse();
        await playTts(mergedResponse);
      } catch {
        const errorMessage = "❌ केवल इन योजनाओं के बारे में पूछें (15 schemes only supported)";
        setBackendResponse({
          session_id: getOrCreateSessionId(),
          response_text: errorMessage,
          field_name: null,
          validation_passed: false,
          validation_error: errorMessage,
          session_complete: false,
          confidence: 1,
          action: "error",
          mode: "info",
          scheme_details: null,
        });
        setResponseText(errorMessage);
        updateConversationAssistantText(turnId, errorMessage);
        markFirstResponse();
        await playTts(errorMessage);
      }
    },
    [markFirstResponse, playTts, setBackendResponse, setResponseText, setSimpleError, updateConversationAssistantText, voiceLanguage],
  );

  const handleRecordedAudioStop = useCallback(
    async (turnId: string) => {
      try {
        const blob = new Blob(mediaChunksRef.current, { type: "audio/webm" });
        mediaChunksRef.current = [];
        if (!blob.size) {
          throw new Error("Empty recording");
        }

        setVoiceState("processing");

        const formData = new FormData();
        formData.append("audio", blob, "recording.webm");
        formData.append("file", blob, "recording.webm");
        formData.append("language", voiceLanguage);

        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 15000);

        const transcribeResponse = await fetch(`${resolveApiUrl("/transcribe")}?lang=${voiceLanguage}`, {
          method: "POST",
          headers: {
            "x-language": voiceLanguage,
            "x-live-transcript": liveTranscriptRef.current || "",
          },
          signal: controller.signal,
          body: formData,
        });
        window.clearTimeout(timeoutId);
        if (!transcribeResponse.ok) {
          throw new Error(`Transcribe request failed: ${transcribeResponse.status}`);
        }

        const transcribeData = await transcribeResponse.json() as {
          transcript?: string;
          text?: string;
          data?: {
            transcript?: string;
            text?: string;
          };
        };
        const transcript = String(
          transcribeData?.transcript
            || transcribeData?.text
            || transcribeData?.data?.transcript
            || transcribeData?.data?.text
            || "",
        ).trim();

        const resolvedTranscript = transcript || String(liveTranscriptRef.current || "").trim();
        if (!resolvedTranscript) {
          throw new Error("No transcript returned");
        }

        setFinalTranscript(resolvedTranscript);
        setLiveTranscript(resolvedTranscript);
        setDetectedLanguage(detectTextLanguage(resolvedTranscript));
        useVoiceStore.getState().replaceConversationHistory(
          useVoiceStore.getState().conversationHistory.map((turn) => (
            turn.id === turnId ? { ...turn, userText: resolvedTranscript } : turn
          )),
        );
        await handleIntent(resolvedTranscript, turnId);
      } catch {
        const liveFallback = String(liveTranscriptRef.current || "").trim();
        if (liveFallback) {
          setFinalTranscript(liveFallback);
          setLiveTranscript(liveFallback);
          setDetectedLanguage(detectTextLanguage(liveFallback));
          useVoiceStore.getState().replaceConversationHistory(
            useVoiceStore.getState().conversationHistory.map((turn) => (
              turn.id === turnId ? { ...turn, userText: liveFallback } : turn
            )),
          );
          await handleIntent(liveFallback, turnId);
        } else {
          setSimpleError();
        }
      } finally {
        processingRef.current = false;
        setStreamDone(true);
        setVoiceState("idle");
        setIsRecording(false);
        if (mediaStreamRef.current) {
          try {
            mediaStreamRef.current.getTracks().forEach((track) => track.stop());
          } catch {
            // no-op
          }
          mediaStreamRef.current = null;
        }
      }
    },
    [handleIntent, setDetectedLanguage, setFinalTranscript, setLiveTranscript, setSimpleError, setStreamDone, setVoiceState, voiceLanguage],
  );

  const stopRecordingAndSend = useCallback((turnId: string | null) => {
    if (!turnId || stopRequestedRef.current) {
      return;
    }
    stopRequestedRef.current = true;

    if (silenceTimerRef.current !== null) {
      window.clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    const recognition = recognitionRef.current;
    if (recognition) {
      try {
        recognition.onend = null;
        recognition.stop();
      } catch {
        // no-op
      }
      recognitionRef.current = null;
    }

    setIsRecording(false);

    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
        return;
      } catch {
        // no-op
      }
    }

    void handleRecordedAudioStop(turnId).finally(() => {
      endLatencyTracking();
    });
  }, [endLatencyTracking, handleRecordedAudioStop]);

  const handleTextQuery = useCallback(
    async (text: string) => {
      const cleaned = (text || "").trim();
      if (!cleaned) {
        return;
      }
      if (isRecording || state === "processing" || state === "speaking") {
        return;
      }

      const now = Date.now();
      if (lastTranscriptRef.current.text === cleaned && now - lastTranscriptRef.current.ts < 1000) {
        return;
      }
      lastTranscriptRef.current = { text: cleaned, ts: now };

      ensureActiveConversationId();
      beginLatencyTracking();
      processingRef.current = true;
      setVoiceState("processing");
      setLiveTranscript(cleaned);
      setFinalTranscript(cleaned);
      setBackendResponse(null);
      setErrorState(null);
      setResponseText("");
      clearResponseStream();
      setStreamDone(false);

      const turnId = `turn-${Date.now()}-${++requestCounterRef.current}`;
      activeTurnIdRef.current = turnId;
      addConversationTurn({
        id: turnId,
        userText: cleaned,
        assistantText: "",
        language: backendLanguage,
        createdAt: Date.now(),
      });

      try {
        await handleIntent(cleaned, turnId);
      } finally {
        processingRef.current = false;
        setStreamDone(true);
        endLatencyTracking();
      }
    },
    [
      addConversationTurn,
      beginLatencyTracking,
      clearResponseStream,
      endLatencyTracking,
      ensureActiveConversationId,
      handleIntent,
      isRecording,
      setBackendResponse,
      setErrorState,
      setFinalTranscript,
      setLiveTranscript,
      setResponseText,
      setStreamDone,
      setVoiceState,
      state,
      voiceLanguage,
    ],
  );

  const startListening = useCallback(() => {
    if (isRecording || processingRef.current || state === "processing" || state === "speaking" || state === "listening") {
      return;
    }

    stopListening();
    stopAudio();
    setErrorState(null);
    setLiveTranscript("");
    setFinalTranscript("");

    ensureActiveConversationId();
    beginLatencyTracking();
    processingRef.current = true;
    stopRequestedRef.current = false;
    const requestId = ++requestCounterRef.current;
    const turnId = `turn-${Date.now()}-${requestId}`;
    activeTurnIdRef.current = turnId;
    addConversationTurn({
      id: turnId,
      userText: copy.processingAudio,
      assistantText: "",
      language: backendLanguage,
      createdAt: Date.now(),
    });
    clearResponseStream();
    setStreamDone(false);
    setErrorState(null);
    setResponseText("");
    setBackendResponse(null);
    setLiveTranscript("");

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        const SpeechRecognitionCtor = (
          (window as Window & { SpeechRecognition?: new () => BrowserSpeechRecognition; webkitSpeechRecognition?: new () => BrowserSpeechRecognition }).SpeechRecognition
          || (window as Window & { SpeechRecognition?: new () => BrowserSpeechRecognition; webkitSpeechRecognition?: new () => BrowserSpeechRecognition }).webkitSpeechRecognition
        );
        if (!SpeechRecognitionCtor) {
          throw new Error("SpeechRecognition not supported");
        }

        const recognition = new SpeechRecognitionCtor();
        recognition.lang = uiLanguage === "hi" ? "hi-IN" : "en-US";
        recognition.continuous = false;
        recognition.interimResults = true;

        const recorder = new MediaRecorder(stream);
        recognitionRef.current = recognition;
        mediaRecorderRef.current = recorder;
        mediaStreamRef.current = stream;
        mediaChunksRef.current = [];
        setIsRecording(true);

        if (silenceTimerRef.current !== null) {
          window.clearTimeout(silenceTimerRef.current);
        }
        silenceTimerRef.current = window.setTimeout(() => {
          const current = mediaRecorderRef.current;
          if (current && current.state !== "inactive") {
            try {
              current.stop();
            } catch {
              // no-op
            }
          }
        }, 2500);

        recognition.onresult = (event) => {
          let transcript = "";

          for (let i = event.resultIndex; i < event.results.length; i += 1) {
            transcript += String(event.results[i]?.[0]?.transcript || "");
          }

          const cleanedTranscript = transcript.trim();
          setLiveTranscript(cleanedTranscript);
          liveTranscriptRef.current = cleanedTranscript;

          if (silenceTimerRef.current !== null) {
            window.clearTimeout(silenceTimerRef.current);
          }
          silenceTimerRef.current = window.setTimeout(() => {
            stopRecordingAndSend(turnId);
          }, 1400);
        };

        recognition.onspeechend = () => {
          if (silenceTimerRef.current !== null) {
            window.clearTimeout(silenceTimerRef.current);
          }
          silenceTimerRef.current = window.setTimeout(() => {
            stopRecordingAndSend(turnId);
          }, 700);
        };

        recognition.onend = () => {
          stopRecordingAndSend(turnId);
        };

        recognition.onerror = () => {
          stopRecordingAndSend(turnId);
        };

        recorder.ondataavailable = (event: BlobEvent) => {
          if (event.data && event.data.size > 0) {
            mediaChunksRef.current.push(event.data);
          }
        };

        recorder.onerror = () => {
          setSimpleError();
          processingRef.current = false;
          setVoiceState("idle");
          setIsRecording(false);
        };

        recorder.onstop = () => {
          if (silenceTimerRef.current !== null) {
            window.clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = null;
          }
          mediaRecorderRef.current = null;
          void handleRecordedAudioStop(turnId).finally(() => {
            endLatencyTracking();
          });
        };

        recorder.start();
        recognition.start();
        setVoiceState("listening");
        logFrontendEvent("voice_state", { state: "listening" }, getOrCreateSessionId());
      })
      .catch(() => {
        processingRef.current = false;
        setVoiceState("idle");
        setSimpleError();
        setIsRecording(false);
        endLatencyTracking();
      });
  }, [
    addConversationTurn,
    beginLatencyTracking,
    clearResponseStream,
    copy.processingAudio,
    endLatencyTracking,
    ensureActiveConversationId,
    handleRecordedAudioStop,
    stopRecordingAndSend,
    setErrorState,
    setBackendResponse,
    setFinalTranscript,
    setLiveTranscript,
    setResponseText,
    setSimpleError,
    setStreamDone,
    setVoiceState,
    isRecording,
    state,
    stopAudio,
    stopListening,
    uiLanguage,
    voiceLanguage,
  ]);

  const handleMicClick = useCallback(() => {
    if (isRecording || state === "processing" || state === "speaking") {
      return;
    }
    logFrontendEvent("mic_tap", { state }, getOrCreateSessionId());

    if (state === "listening") {
      stopRecordingAndSend(activeTurnIdRef.current);
      return;
    }

    // Unlock autoplay by "touching" the audio element on first user gesture
    if (audioRef.current) {
      const audio = audioRef.current;
      if (!audio.src || audio.src === window.location.href) {
        audio.src = "data:audio/mp3;base64,//NExAAAAANIAAAAAExBTUUzLjEwMKqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq";
        audio.load();
        audio.play().catch(() => {});
      }
    }

    startListening();
  }, [isRecording, startListening, state, stopRecordingAndSend]);

  const handleRestart = useCallback(async () => {
    stopListening();
    stopAudio();
    requestCounterRef.current += 1;
    processingRef.current = false;
    lastTranscriptRef.current = { text: "", ts: 0 };

    const previousSessionId = getOrCreateSessionId();
    try {
      await resetSession(previousSessionId);
    } catch {
      // Ignore reset errors; we still rotate client session id.
    }

    clearSessionId();
    const nextSessionId = getOrCreateSessionId();
    localStorage.removeItem(`voice_history_${previousSessionId}`);
    localStorage.removeItem(`voice_history_${nextSessionId}`);

    const resetConversation: StoredConversation = {
      id: nextSessionId,
      sessionId: nextSessionId,
      title: "",
      messages: [],
      updatedAt: Date.now(),
    };
    setConversations((prev) => [resetConversation, ...prev].slice(0, MAX_CONVERSATIONS));
    setActiveConversationId(nextSessionId);
    setSessionId(nextSessionId);

    resetConversationState();
    clearConversationHistory();
    setVoiceState("idle");
    setTextFallback("");

    const greeting = getGreeting(backendLanguage);
    setResponseText(greeting);
    clearResponseStream();
    void speakText(greeting);
  }, [
    clearConversationHistory,
    clearResponseStream,
    resetConversationState,
    setActiveConversationId,
    setConversations,
    setResponseText,
    setSessionId,
    setVoiceState,
    speakText,
    stopAudio,
    stopListening,
    voiceLanguage,
  ]);

  useEffect(() => {
    if (hasPlayedGreetingRef.current) return;
    hasPlayedGreetingRef.current = true;
    setLanguage(backendLanguage);
    setDetectedLanguage(backendLanguage);

    const greeting = getGreeting(backendLanguage);

    setResponseText(greeting);
    void speakText(greeting);
  }, [backendLanguage, setDetectedLanguage, setLanguage, setResponseText, speakText]);

  useEffect(() => {
    return () => {
      stopListening();
      stopAudio();
      if (currentTtsAudioRef.current) {
        try {
          currentTtsAudioRef.current.pause();
        } catch {
          // no-op
        }
        currentTtsAudioRef.current = null;
      }
      void interruptTts().catch(() => undefined);
    };
  }, [stopAudio, stopListening]);

  useEffect(() => {
    if (!latency.lastRoundTripMs) {
      return;
    }
    logFrontendEvent(
      "latency",
      {
        roundTripMs: Math.round(latency.lastRoundTripMs),
        firstResponseMs: latency.requestStartedAt && latency.firstResponseAt
          ? Math.round(latency.firstResponseAt - latency.requestStartedAt)
          : null,
        firstAudioChunkMs: latency.requestStartedAt && latency.firstAudioChunkAt
          ? Math.round(latency.firstAudioChunkAt - latency.requestStartedAt)
          : null,
      },
      getOrCreateSessionId(),
    );
  }, [latency.firstAudioChunkAt, latency.firstResponseAt, latency.lastRoundTripMs, latency.requestStartedAt]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (event.code === "Space" || event.code === "Enter") {
        event.preventDefault();
        handleMicClick();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [handleMicClick]);

  const statusText =
    state === "listening"
      ? copy.statusListening
      : state === "processing"
        ? copy.statusProcessing
      : state === "speaking"
        ? copy.statusSpeaking
        : state === "interrupted"
          ? copy.statusInterrupted
          : copy.statusIdle;
  const statusWithEmoji =
    state === "listening"
      ? `🎤 ${copy.statusListening}`
      : state === "processing"
        ? `🤖 ${copy.statusProcessing}`
        : state === "speaking"
          ? `🔊 ${copy.statusSpeaking}`
          : statusText;

  const displayedAssistantText = assistantText;
  const effectiveErrorText = errorState || "";
  const transcriptLine = liveTranscript || transcriptFinal;
  const confidenceLabel = useMemo(() => {
    const raw = Number(backendResponse?.confidence ?? 0);
    if (!Number.isFinite(raw) || raw <= 0) {
      return "Low";
    }
    const normalized = raw > 1 ? raw / 100 : raw;
    if (normalized >= 0.8) {
      return "High";
    }
    if (normalized >= 0.5) {
      return "Medium";
    }
    return "Low";
  }, [backendResponse?.confidence]);
  const lastAssistantText = useMemo(() => {
    for (let i = conversationHistory.length - 1; i >= 0; i -= 1) {
      const text = conversationHistory[i]?.assistantText?.trim();
      if (text) {
        return text;
      }
    }
    return displayedAssistantText || "";
  }, [conversationHistory, displayedAssistantText]);

  const conversationHistoryForDisplay = useMemo(() => {
    const clarificationHints = [
      "कृपया अपना प्रश्न",
      "थोड़ा स्पष्ट",
    ];

    return conversationHistory.reduce<ConversationTurn[]>((acc, turn) => {
      const userNorm = (turn.userText || "").trim().toLowerCase();
      const assistantNormRaw = (turn.assistantText || "").trim().toLowerCase();
      if (LEGACY_PLACEHOLDERS.some((phrase) => userNorm.includes(phrase) || assistantNormRaw.includes(phrase))) {
        return acc;
      }

      const prev = acc[acc.length - 1];
      const currAssistant = (turn.assistantText || "").trim();
      const prevAssistant = (prev?.assistantText || "").trim();

      if (currAssistant && prevAssistant) {
        const currNorm = currAssistant.toLowerCase().replace(/\s+/g, " ");
        const prevNorm = prevAssistant.toLowerCase().replace(/\s+/g, " ");
        const isSameAssistant = currNorm === prevNorm;
        const looksClarification = clarificationHints.some((hint) => currNorm.includes(hint));
        if (isSameAssistant || looksClarification) {
          return acc;
        }
      }

      acc.push(turn);
      return acc;
    }, []);
  }, [conversationHistory]);

  const detectedScheme = useMemo(
    () => (backendResponse?.scheme_details?.title || "").trim(),
    [backendResponse?.scheme_details?.title],
  );

  const schemeBadgeName = useMemo(() => {
    if (detectedScheme) {
      return detectedScheme;
    }
    return "";
  }, [detectedScheme]);

  const showStandaloneResponseCard = useMemo(() => {
    if (!displayedAssistantText) {
      return false;
    }
    const normalized = displayedAssistantText.trim().toLowerCase().replace(/\s+/g, " ");
    const alreadyInHistory = conversationHistoryForDisplay.some(
      (turn) => (turn.assistantText || "").trim().toLowerCase().replace(/\s+/g, " ") === normalized,
    );
    return !alreadyInHistory;
  }, [conversationHistoryForDisplay, displayedAssistantText]);

  const quickActions = useMemo(
    () => [
      {
        label: copy.quickApply,
        fallback: copy.quickApply,
        buildQuery: (scheme: string) => copy.quickApplyQuery(scheme),
      },
      {
        label: copy.quickAmount,
        fallback: copy.quickAmount,
        buildQuery: (scheme: string) => copy.quickAmountQuery(scheme),
      },
      {
        label: copy.quickDocs,
        fallback: copy.quickDocs,
        buildQuery: (scheme: string) => copy.quickDocsQuery(scheme),
      },
    ],
    [copy],
  );

  const handleQuickActionClick = useCallback(
    (action: { label: string; fallback: string; buildQuery: (scheme: string) => string }) => {
      if (state !== "idle") {
        return;
      }
      const query = detectedScheme ? action.buildQuery(detectedScheme) : action.fallback;
      void handleTextQuery(query);
    },
    [detectedScheme, handleTextQuery, state],
  );
  const activeSidebarId = activeConversationId || localStorage.getItem(ROLE_ACTIVE_CONVERSATION_KEY) || null;
  const sidebarItems = useMemo(() => {
    if (roleConversations.length === 0) {
      return [];
    }
    if (!activeSidebarId) {
      return roleConversations;
    }
    const exists = roleConversations.some((item) => item.id === activeSidebarId);
    if (exists) {
      return roleConversations;
    }
    return roleConversations;
  }, [activeSidebarId, roleConversations]);

  const submitFallbackText = useCallback(() => {
    const cleaned = textFallback.trim();
    if (!cleaned || state === "processing") {
      return;
    }
    setTextFallback("");
    void handleTextQuery(cleaned);
  }, [handleTextQuery, state, textFallback]);

  const retryLast = useCallback(() => {
    if (!transcriptFinal) {
      return;
    }
    void handleTextQuery(transcriptFinal);
  }, [handleTextQuery, transcriptFinal]);

  return (
    <div className="relative min-h-screen bg-[linear-gradient(180deg,#0B0B0B_0%,#020202_100%)] text-white flex" role="application" aria-label={copy.appLabel}>
      <SparkleBackground />
      {sidebarOpen ? (
        <button
          type="button"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 bg-black/60 z-20 md:hidden"
          aria-label={copy.closeMenu}
        />
      ) : null}

      <aside
        className={`fixed md:static top-0 left-0 h-full w-64 border-r border-white/10 bg-[#111827]/90 backdrop-blur-xl p-4 z-30 transition-transform duration-200 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-wide text-gray-400">
              {copy.chats}
            </p>
          </div>
          <button
            type="button"
            onClick={handleNewChat}
            className="mt-3 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-semibold text-amber-200 hover:bg-white/10"
          >
            {copy.newChat}
          </button>

          <div className="mt-4 flex-1 overflow-y-auto space-y-2">
            {sidebarItems.length === 0 ? (
              <p className="text-sm text-gray-400">
                {copy.noConversations}
              </p>
            ) : null}
            {sidebarItems.map((conversation) => {
              const isActive = conversation.id === activeSidebarId;
              const baseTitle = conversation.title || copy.newChat;
              const title = baseTitle.length > 25 ? `${baseTitle.slice(0, 25).trim()}...` : baseTitle;
              return (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => handleSelectConversation(conversation.id)}
                  className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                    isActive
                      ? "border-amber-300/50 bg-white/10 text-amber-100"
                      : "border-white/10 bg-white/5 text-white hover:bg-white/10"
                  }`}
                >
                  <span className="block text-sm font-semibold truncate">{title}</span>
                </button>
              );
            })}
          </div>
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="md:hidden inline-flex items-center justify-center w-9 h-9 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10"
              aria-label={copy.openMenu}
            >
              <Menu className="w-4 h-4" />
            </button>
            <BackButton onClick={onBack} label={copy.changeLanguage} />
          </div>
          <button
            type="button"
            onClick={() => {
              void handleRestart();
            }}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-xs"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            {copy.restart}
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {conversationHistory.length === 0 ? (
            <p className="text-sm text-gray-400">
              {copy.startConversationHint}
            </p>
          ) : null}

          {conversationHistoryForDisplay.map((turn) => (
            <div key={turn.id} className="space-y-3">
              {turn.userText ? (
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl border border-white/10 bg-[#111827] px-4 py-2 text-lg leading-relaxed text-white">
                    {turn.userText}
                  </div>
                </div>
              ) : null}
              {turn.assistantText ? (
                <div className="flex justify-start">
                  <div className="max-w-[80%] rounded-2xl border border-white/10 bg-[#111827] px-4 py-2 text-lg leading-relaxed text-white">
                    {turn.assistantText}
                  </div>
                </div>
              ) : null}
            </div>
          ))}
          {lastAssistantText ? (
            <div className="flex flex-wrap gap-3 pt-2">
              {quickActions.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  onClick={() => handleQuickActionClick(action)}
                  disabled={state !== "idle"}
                  className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-base font-semibold text-white hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {action.label}
                </button>
              ))}
            </div>
          ) : null}

          {showStandaloneResponseCard ? (
            <div className="rounded-2xl border border-amber-300/20 bg-[linear-gradient(180deg,rgba(17,24,39,0.95)_0%,rgba(15,23,42,0.92)_100%)] px-4 py-4 shadow-[0_18px_40px_rgba(0,0,0,0.45)] animate-[fadeIn_220ms_ease-out] space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-[0.14em] text-amber-200/85">Assistant Response</p>
                <span className="rounded-full border border-amber-300/35 bg-amber-300/10 px-2.5 py-1 text-[11px] font-semibold text-amber-100">
                  Confidence: {confidenceLabel}
                </span>
              </div>
              {schemeBadgeName ? (
                <div className="inline-flex items-center rounded-full border border-amber-300/35 bg-amber-300/10 px-3 py-1 text-xs font-semibold text-amber-100">
                  Scheme: {schemeBadgeName}
                </div>
              ) : null}
              <p className="text-base leading-relaxed text-slate-100">{displayedAssistantText}</p>
            </div>
          ) : null}
          <div ref={chatEndRef} />
        </div>

        <div className="px-4 py-4 border-t border-white/10">
          <div className="flex flex-col items-center gap-3">
            <button
              type="button"
              onClick={handleMicClick}
              disabled={state === "processing" || isRecording}
              aria-label={copy.micControl}
              aria-pressed={state === "listening"}
              className={`relative w-28 h-28 rounded-full border text-white grid place-items-center disabled:opacity-55 transition-all duration-300 ${
                state === "listening"
                  ? "border-amber-300/60 bg-[#111827] shadow-[0_0_40px_rgba(251,191,36,0.45)] scale-105 animate-[pulse_1.6s_ease-in-out_infinite]"
                  : "border-white/10 bg-[#111827] shadow-[0_8px_24px_rgba(0,0,0,0.35)]"
              }`}
            >
              {state === "listening" ? (
                <span className="pointer-events-none absolute inset-0 rounded-full border border-amber-300/35 animate-ping" />
              ) : null}
              <Mic className="w-12 h-12" />
            </button>

            <p className="text-lg font-semibold" aria-live="polite" role="status">{statusWithEmoji}</p>

            <div className="w-full max-w-xl rounded-xl bg-white/5 border border-white/10 p-3 animate-[fadeIn_220ms_ease-out]">
              <p className="text-[11px] uppercase tracking-[0.12em] text-amber-100/80">{copy.liveTranscript}</p>
              <p className="mt-1 text-sm text-gray-100 min-h-[1.5rem]" aria-live="polite">
                {transcriptLine || copy.speechWillAppear}
              </p>
              <p className="mt-2 text-xs text-gray-300" aria-live="polite">📝 {liveTranscript || copy.speechWillAppear}</p>
              <p className="mt-1 text-xs text-emerald-200" aria-live="polite">✔ {transcriptFinal || "-"}</p>
              <p className="mt-1 text-xs text-amber-200" aria-live="polite">🤖 {(displayedAssistantText || "-").slice(0, 140)}</p>
            </div>
          </div>
        </div>

        <div className="px-4 pb-5">
          <div className="flex gap-2">
            <input
              value={textFallback}
              onChange={(event) => setTextFallback(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  submitFallbackText();
                }
              }}
              placeholder={copy.typeHere}
              className="flex-1 h-12 rounded-xl bg-white/5 border border-white/10 px-3 text-base text-white placeholder:text-gray-400 outline-none focus:border-amber-300/50"
              aria-label={copy.textInput}
            />
            <button
              type="button"
              onClick={submitFallbackText}
              disabled={state === "processing" || !textFallback.trim()}
              className="h-12 px-4 rounded-xl text-sm font-semibold border border-white/10 bg-white/5 hover:bg-white/10 text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {copy.send}
            </button>
          </div>

          {effectiveErrorText ? (
            <div className="mt-3 rounded-xl border border-red-300/30 bg-red-500/10 px-3 py-2 text-red-200 text-sm">
              <p>{effectiveErrorText}</p>
              <button
                type="button"
                onClick={retryLast}
                className="mt-2 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 px-3 py-1 text-xs font-semibold"
              >
                {copy.retry}
              </button>
            </div>
          ) : null}
        </div>
      </div>
      <audio ref={audioRef} className="hidden" playsInline crossOrigin="anonymous" />
    </div>
  );
};

export default VoiceInteraction;
