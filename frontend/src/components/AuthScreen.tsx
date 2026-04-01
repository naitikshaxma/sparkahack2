import { useState } from "react";
import SparkleBackground from "./SparkleBackground";

interface AuthScreenProps {
  onAuthenticated: (user: { name: string; phone: string }) => void;
}

const PHONE_STORAGE_KEY = "voice_os_user_phone";
const MOCK_OTP = "123456";

type AuthStep = "details" | "otp";

const AuthScreen = ({ onAuthenticated }: AuthScreenProps) => {
  const [step, setStep] = useState<AuthStep>("details");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState(() => localStorage.getItem(PHONE_STORAGE_KEY) || "");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");

  const normalizedPhone = phone.replace(/\D/g, "").slice(0, 10);
  const trimmedName = name.trim();

  const canContinue = trimmedName.length > 1 && normalizedPhone.length === 10;
  const canVerify = otp.length === 6;

  const handleContinue = () => {
    setError("");
    if (!trimmedName) {
      setError("कृपया नाम भरें / Please enter your name");
      return;
    }
    if (normalizedPhone.length !== 10) {
      setError("कृपया 10 अंकों का फोन नंबर दें / Enter a 10-digit phone");
      return;
    }
    setStep("otp");
  };

  const handleVerify = () => {
    setError("");
    if (!canVerify) {
      setError("कृपया 6 अंकों का OTP डालें / Enter 6-digit OTP");
      return;
    }
    if (otp !== MOCK_OTP) {
      setError("OTP गलत है / Incorrect OTP");
      return;
    }
    const payload = { name: trimmedName, phone: normalizedPhone };
    onAuthenticated(payload);
  };

  return (
    <div className="relative min-h-screen bg-[linear-gradient(180deg,#0B0B0B_0%,#020202_100%)] text-white flex items-center justify-center px-4 py-6 sm:py-10">
      <SparkleBackground />
      <div className="relative z-10 w-full max-w-xl overflow-hidden rounded-3xl border border-amber-300/20 bg-[linear-gradient(180deg,rgba(15,23,42,0.96)_0%,rgba(10,16,32,0.94)_100%)] p-6 md:p-8 shadow-[0_24px_70px_rgba(0,0,0,0.55)] backdrop-blur-xl space-y-6">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-300/60 to-transparent" />
        {step === "details" ? (
          <>
            <div className="space-y-3">
              <span className="inline-flex items-center rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-xs font-medium tracking-[0.14em] text-amber-100/90 uppercase">
                Quick Access
              </span>
              <h2 className="text-3xl md:text-5xl font-semibold leading-tight text-white">
                अपनी जानकारी भरें / Enter your details
              </h2>
              <p className="text-sm md:text-base text-slate-300/80 mt-2">
                नाम और फोन नंबर डालें / Enter your name and phone number
              </p>
            </div>

            <div className="space-y-4">
              <input
                type="text"
                placeholder="नाम / Name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="w-full h-14 rounded-2xl border border-white/10 bg-white/[0.06] px-4 text-lg md:text-xl text-white placeholder:text-slate-400 outline-none transition-all duration-200 focus:border-amber-300/60 focus:bg-white/[0.09] focus:shadow-[0_0_0_3px_rgba(251,191,36,0.14)]"
                aria-label="Name"
                autoComplete="name"
              />

              <input
                type="tel"
                inputMode="numeric"
                placeholder="फोन नंबर / Phone"
                value={phone}
                onChange={(event) => setPhone(event.target.value.replace(/\D/g, "").slice(0, 10))}
                className="w-full h-14 rounded-2xl border border-white/10 bg-white/[0.06] px-4 text-lg md:text-xl text-white placeholder:text-slate-400 outline-none transition-all duration-200 focus:border-amber-300/60 focus:bg-white/[0.09] focus:shadow-[0_0_0_3px_rgba(251,191,36,0.14)]"
                aria-label="Phone"
                autoComplete="tel"
              />
            </div>

            {error ? (
              <p className="rounded-xl border border-red-300/20 bg-red-950/30 px-3 py-2 text-sm text-red-200">
                {error}
              </p>
            ) : null}

            <button
              type="button"
              onClick={handleContinue}
              disabled={!canContinue}
              className="w-full h-14 rounded-2xl text-xl font-semibold border border-amber-300/40 bg-gradient-to-r from-amber-300/90 via-amber-400/90 to-amber-300/90 text-slate-900 shadow-[0_10px_28px_rgba(251,191,36,0.28)] transition-all duration-200 hover:brightness-105 hover:shadow-[0_12px_34px_rgba(251,191,36,0.36)] disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none"
            >
              आगे बढ़ें / Continue
            </button>
          </>
        ) : (
          <>
            <div className="space-y-3">
              <span className="inline-flex items-center rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-xs font-medium tracking-[0.14em] text-amber-100/90 uppercase">
                Secure Step
              </span>
              <h2 className="text-3xl md:text-5xl font-semibold leading-tight text-white">OTP सत्यापन / OTP verification</h2>
              <p className="text-sm md:text-base text-slate-300/80 mt-2">6 अंकों का OTP डालें / Enter the 6-digit OTP</p>
            </div>

            <div className="space-y-4">
              <input
                type="text"
                inputMode="numeric"
                placeholder="OTP / ओटीपी"
                value={otp}
                onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))}
                maxLength={6}
                className="w-full h-14 rounded-2xl border border-white/10 bg-white/[0.06] px-4 text-xl tracking-[0.32em] text-center text-white placeholder:text-slate-400 outline-none transition-all duration-200 focus:border-amber-300/60 focus:bg-white/[0.09] focus:shadow-[0_0_0_3px_rgba(251,191,36,0.14)]"
                aria-label="OTP"
              />

              <p className="text-sm text-amber-100/90">डेमो OTP: 123456 / Demo OTP: 123456</p>
            </div>

            {error ? (
              <p className="rounded-xl border border-red-300/20 bg-red-950/30 px-3 py-2 text-sm text-red-200">
                {error}
              </p>
            ) : null}

            <button
              type="button"
              onClick={handleVerify}
              disabled={!canVerify}
              className="w-full h-14 rounded-2xl text-xl font-semibold border border-amber-300/40 bg-gradient-to-r from-amber-300/90 via-amber-400/90 to-amber-300/90 text-slate-900 shadow-[0_10px_28px_rgba(251,191,36,0.28)] transition-all duration-200 hover:brightness-105 hover:shadow-[0_12px_34px_rgba(251,191,36,0.36)] disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none"
            >
              सत्यापित करें / Verify
            </button>
          </>
        )}
      </div>
    </div>
  );
};

export default AuthScreen;
