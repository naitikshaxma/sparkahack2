import { useMemo, useState } from "react";
import SparkleBackground from "./SparkleBackground";

interface Language {
  code: string;
  name: string;
  nativeName: string;
  greeting: string;
}

interface PhoneEntryScreenProps {
  language: Language;
  onContinue: (phone: string) => void;
  onBack: () => void;
}

const PHONE_STORAGE_KEY = "voice_os_user_phone";

const PhoneEntryScreen = ({ language, onContinue, onBack }: PhoneEntryScreenProps) => {
  const isHindi = (language.code || "en") === "hi";
  const [phone, setPhone] = useState<string>(() => localStorage.getItem(PHONE_STORAGE_KEY) || "");

  const normalizedPhone = phone.replace(/\D/g, "").slice(0, 10);

  const helperText = useMemo(
    () => (isHindi
      ? "फोन नंबर डालिए और आगे बढ़िए / Enter your phone number and continue"
      : "Enter your phone number and continue"),
    [isHindi],
  );

  const handleContinue = () => {
    if (normalizedPhone.length !== 10) {
      return;
    }
    localStorage.setItem(PHONE_STORAGE_KEY, normalizedPhone);
    onContinue(normalizedPhone);
  };

  return (
    <div className="relative min-h-screen bg-[linear-gradient(180deg,#0B0B0B_0%,#020202_100%)] text-white flex items-center justify-center px-4">
      <SparkleBackground />
      <div className="relative z-10 w-full max-w-lg rounded-2xl border border-white/10 bg-[#111827] p-6 md:p-8 space-y-5">
        <button
          type="button"
          onClick={onBack}
          className="text-sm px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10"
        >
          {isHindi ? "भाषा बदलें / Change language" : "Change language"}
        </button>

        <div>
          <h2 className="text-3xl md:text-4xl font-semibold leading-tight">{isHindi ? "फोन से शुरू करें / Start with phone" : "Start with phone"}</h2>
          <p className="text-base text-gray-400 mt-2">{helperText}</p>
        </div>

        <input
          type="tel"
          inputMode="numeric"
          placeholder={isHindi ? "फोन नंबर / Phone number" : "Phone number"}
          value={phone}
          onChange={(event) => setPhone(event.target.value.replace(/\D/g, "").slice(0, 10))}
          className="w-full h-14 rounded-xl bg-white/5 border border-white/10 px-4 text-xl text-white placeholder:text-gray-400 outline-none focus:border-amber-300/50"
          aria-label={isHindi ? "फोन नंबर / Phone number" : "Phone number"}
        />

        <button
          type="button"
          onClick={handleContinue}
          disabled={normalizedPhone.length !== 10}
          className="w-full h-14 rounded-xl text-xl font-semibold border border-white/10 bg-white/5 hover:bg-white/10 text-amber-200 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isHindi ? "आगे बढ़ें / Continue" : "Continue"}
        </button>
      </div>
    </div>
  );
};

export default PhoneEntryScreen;
