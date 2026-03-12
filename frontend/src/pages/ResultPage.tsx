import { useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Mic, RotateCcw } from 'lucide-react';

interface ResultState {
  transcript?: string;
  intent?: string;
  confidence?: number;
  response_text?: string | { confirmation?: string; explanation?: string; next_step?: string };
  audio_base64?: string;
  language?: string;
  languageCode?: string;
}

const ResultPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as ResultState;

  const transcript = state.transcript || 'No voice input detected.';
  const intent = state.intent || 'Unknown';
  const confidence = state.confidence ? Math.round(state.confidence) : 0;
  
  // Handle case where response_text is either a string or a structured object
  let responseTextStr = 'No response available.';
  if (typeof state.response_text === 'string') {
    responseTextStr = state.response_text;
  } else if (state.response_text) {
    responseTextStr = [
      state.response_text.confirmation,
      state.response_text.explanation,
      state.response_text.next_step
    ].filter(Boolean).join(' ');
  }

  const audioSrc = state.audio_base64 
    ? (state.audio_base64.startsWith('data:') ? state.audio_base64 : `data:audio/mp3;base64,${state.audio_base64}`)
    : '';

  const handleAskAnother = useCallback(() => {
    // Return to the assistant page with the same language context if possible, otherwise root
    if (state.languageCode) {
      navigate(`/assistant?lang=${state.languageCode}`);
    } else {
      navigate(-1);
    }
  }, [navigate, state.languageCode]);

  const handleStartOver = useCallback(() => {
    navigate('/');
  }, [navigate]);

  return (
    <div className="min-h-screen bg-black text-[#f5f5f5] flex flex-col relative font-body">
      {/* Background Sparkles (Optional subtle ambient effect mimicking old theme) */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0 flex justify-center items-center opacity-30">
        <div className="w-[800px] h-[800px] bg-[#f59e0b] rounded-full blur-[150px] opacity-10 mix-blend-screen" />
        <div className="w-[600px] h-[600px] bg-[#14b8a6] rounded-full blur-[120px] opacity-10 mix-blend-screen -ml-[400px] mt-[200px]" />
      </div>

      <div className="relative z-10 flex-1 flex flex-col items-center justify-center p-4 sm:p-6 w-full max-w-3xl mx-auto">
        
        {/* Top Section */}
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-5xl font-heading font-bold text-[#f5f5f5] mb-2 tracking-tight">
            Voice OS Bharat
          </h1>
          <p className="text-[#9ca3af] text-sm md:text-base px-4">
            AI Voice Assistant for Government & Banking Services
          </p>
        </div>

        {/* Center Card */}
        <div className="w-full bg-[#111111] border border-[#2a2a2a] shadow-2xl rounded-2xl p-6 md:p-8 flex flex-col gap-6">
          
          {/* 1. User Speech Transcript */}
          <div>
            <h3 className="text-xs font-semibold text-[#f59e0b] uppercase tracking-wider mb-2">
              Your Voice Input
            </h3>
            <div className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4">
              <p className="text-[#e5e7eb] text-lg leading-relaxed">
                "{transcript}"
              </p>
            </div>
          </div>

          {/* 2. Detected Intent */}
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4 flex flex-col justify-center">
              <span className="text-xs text-[#9ca3af] uppercase tracking-wider mb-1">Intent</span>
              <span className="text-[#14b8a6] font-medium text-lg capitalize">
                {intent.replace(/_/g, ' ')}
              </span>
            </div>
            <div className="flex-1 bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4 flex flex-col justify-center">
              <span className="text-xs text-[#9ca3af] uppercase tracking-wider mb-1">Confidence</span>
              <div className="flex items-end gap-2">
                <span className="text-[#f5f5f5] font-semibold text-2xl">{confidence}%</span>
                <div className="flex-1 h-1.5 bg-[#2a2a2a] rounded-full mb-1.5 overflow-hidden">
                  <div 
                    className="h-full bg-[#f59e0b] rounded-full" 
                    style={{ width: `${confidence}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* 3. AI Response */}
          <div>
            <h3 className="text-xs font-semibold text-[#f59e0b] uppercase tracking-wider mb-2">
              Assistant Response
            </h3>
            <div className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4">
              <p className="text-[#e5e7eb] text-base leading-relaxed">
                {responseTextStr}
              </p>
            </div>
          </div>

          {/* 4. Audio Playback */}
          {audioSrc && (
            <div className="mt-2 w-full flex flex-col gap-2">
               <span className="text-xs text-[#9ca3af] uppercase tracking-wider">Audio Playback</span>
               <audio 
                  controls 
                  autoPlay
                  src={audioSrc} 
                  className="w-full h-12 rounded-xl focus:outline-none"
                  style={{
                    backgroundColor: '#1a1a1a',
                  }}
               />
            </div>
          )}
        </div>

        {/* 5. Buttons */}
        <div className="w-full flex flex-col sm:flex-row gap-4 mt-8 justify-center items-center">
          <button
            onClick={handleAskAnother}
            className="flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-3.5 bg-[#f59e0b] hover:bg-[#d97706] text-black font-semibold rounded-full shadow-[0_0_20px_rgba(245,158,11,0.2)] transition-all duration-300"
          >
            <Mic className="w-5 h-5" />
            <span>Ask Another Question</span>
          </button>
          
          <button
            onClick={handleStartOver}
            className="flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-3.5 bg-[#1a1a1a] hover:bg-[#2a2a2a] border border-[#333333] hover:border-[#555555] text-[#f5f5f5] font-medium rounded-full transition-all duration-300"
          >
            <RotateCcw className="w-5 h-5" />
            <span>Start Over</span>
          </button>
        </div>

      </div>
    </div>
  );
};

export default ResultPage;
