import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import SparkleBackground from '@/components/result/SparkleBackground';
import ResultNavbar from '@/components/result/ResultNavbar';
import AudioPreviewCard from '@/components/result/AudioPreviewCard';
import WaveformProcessing from '@/components/result/WaveformProcessing';
import IntentBadge from '@/components/result/IntentBadge';
import ConfidenceMeter from '@/components/result/ConfidenceMeter';
import ResponseCard from '@/components/result/ResponseCard';
import ActionButtons from '@/components/result/ActionButtons';
import VoicePlayer from '@/components/result/VoicePlayer';

/* Mock response data per language */
const mockResponses: Record<string, {
    intent: string;
    category: 'banking' | 'government' | 'complaint' | 'general';
    confidence: number;
    confirmation: string;
    explanation: string;
    nextStep: string;
}> = {
    hi: {
        intent: 'खाता शेष पूछताछ',
        category: 'banking',
        confidence: 87,
        confirmation: 'आपने अपने बचत खाते का शेष जानना चाहा।',
        explanation: 'हमने सरकारी UPI गेटवे के माध्यम से आपके बैंक से कनेक्ट किया। आपका वर्तमान शेष सुरक्षित रूप से प्राप्त किया गया है।',
        nextStep: 'आप हाल के लेनदेन देख सकते हैं, फंड ट्रांसफर कर सकते हैं, या कोई अन्य खाता चेक कर सकते हैं।',
    },
    en: {
        intent: 'Account Balance Inquiry',
        category: 'banking',
        confidence: 92,
        confirmation: 'You asked about your bank account balance for your savings account.',
        explanation: 'We connected to your linked bank through the government UPI gateway. Your current available balance has been retrieved securely.',
        nextStep: 'You can ask to view your recent transactions, transfer funds, or check a different account.',
    },
    mr: {
        intent: 'खाते शिल्लक चौकशी',
        category: 'banking',
        confidence: 85,
        confirmation: 'तुम्ही तुमच्या बचत खात्याची शिल्लक विचारली.',
        explanation: 'आम्ही सरकारी UPI गेटवेद्वारे तुमच्या बँकेशी कनेक्ट केले.',
        nextStep: 'तुम्ही अलीकडील व्यवहार पाहू शकता किंवा निधी हस्तांतरित करू शकता.',
    },
    bn: {
        intent: 'অ্যাকাউন্ট ব্যালেন্স জিজ্ঞাসা',
        category: 'banking',
        confidence: 83,
        confirmation: 'আপনি আপনার সেভিংস অ্যাকাউন্টের ব্যালেন্স জানতে চেয়েছেন।',
        explanation: 'আমরা সরকারি UPI গেটওয়ের মাধ্যমে আপনার ব্যাংকের সাথে সংযুক্ত হয়েছি।',
        nextStep: 'আপনি সাম্প্রতিক লেনদেন দেখতে বা তহবিল স্থানান্তর করতে পারেন।',
    },
    ta: {
        intent: 'கணக்கு இருப்பு விசாரணை',
        category: 'government',
        confidence: 88,
        confirmation: 'உங்கள் சேமிப்புக் கணக்கின் இருப்பை கேட்டீர்கள்.',
        explanation: 'அரசாங்க UPI நுழைவாயில் மூலம் உங்கள் வங்கியுடன் இணைக்கப்பட்டது.',
        nextStep: 'சமீபத்திய பரிவர்த்தனைகளைப் பார்க்கலாம் அல்லது நிதியை மாற்றலாம்.',
    },
    te: {
        intent: 'ఖాతా బ్యాలెన్స్ విచారణ',
        category: 'government',
        confidence: 86,
        confirmation: 'మీ సేవింగ్స్ ఖాతా బ్యాలెన్స్ కోసం అడిగారు.',
        explanation: 'ప్రభుత్వ UPI గేట్‌వే ద్వారా మీ బ్యాంకుకు కనెక్ట్ చేయబడింది.',
        nextStep: 'ఇటీవలి లావాదేవీలు చూడవచ్చు లేదా నిధులు బదిలీ చేయవచ్చు.',
    },
    kn: {
        intent: 'ಖಾತೆ ಬ್ಯಾಲೆನ್ಸ್ ವಿಚಾರಣೆ',
        category: 'banking',
        confidence: 84,
        confirmation: 'ನಿಮ್ಮ ಉಳಿತಾಯ ಖಾತೆಯ ಬ್ಯಾಲೆನ್ಸ್ ಕೇಳಿದ್ದೀರಿ.',
        explanation: 'ಸರ್ಕಾರಿ UPI ಗೇಟ್‌ವೇ ಮೂಲಕ ನಿಮ್ಮ ಬ್ಯಾಂಕ್‌ಗೆ ಸಂಪರ್ಕಿಸಲಾಗಿದೆ.',
        nextStep: 'ಇತ್ತೀಚಿನ ವಹಿವಾಟುಗಳನ್ನು ನೋಡಬಹುದು ಅಥವಾ ಹಣ ವರ್ಗಾಯಿಸಬಹುದು.',
    },
    ml: {
        intent: 'അക്കൗണ്ട് ബാലൻസ് അന്വേഷണം',
        category: 'banking',
        confidence: 81,
        confirmation: 'നിങ്ങളുടെ സേവിംഗ്‌സ് അക്കൗണ്ട് ബാലൻസ് ചോദിച്ചു.',
        explanation: 'സർക്കാർ UPI ഗേറ്റ്‌വേ വഴി നിങ്ങളുടെ ബാങ്കിലേക്ക് കണക്ട് ചെയ്‌തു.',
        nextStep: 'സമീപകാല ഇടപാടുകൾ കാണാം അല്ലെങ്കിൽ ഫണ്ട് ട്രാൻസ്ഫർ ചെയ്യാം.',
    },
    pa: {
        intent: 'ਖਾਤਾ ਬੈਲੈਂਸ ਪੁੱਛਗਿੱਛ',
        category: 'banking',
        confidence: 80,
        confirmation: 'ਤੁਸੀਂ ਆਪਣੇ ਬੱਚਤ ਖਾਤੇ ਦਾ ਬੈਲੈਂਸ ਪੁੱਛਿਆ।',
        explanation: 'ਸਰਕਾਰੀ UPI ਗੇਟਵੇ ਰਾਹੀਂ ਤੁਹਾਡੇ ਬੈਂਕ ਨਾਲ ਕਨੈਕਟ ਕੀਤਾ ਗਿਆ।',
        nextStep: 'ਤੁਸੀਂ ਹਾਲੀਆ ਲੈਣ-ਦੇਣ ਦੇਖ ਸਕਦੇ ਹੋ ਜਾਂ ਫੰਡ ਟ੍ਰਾਂਸਫਰ ਕਰ ਸਕਦੇ ਹੋ।',
    },
    gu: {
        intent: 'ખાતા બેલેન્સ પૂછપરછ',
        category: 'banking',
        confidence: 82,
        confirmation: 'તમે તમારા બચત ખાતાનું બેલેન્સ પૂછ્યું.',
        explanation: 'સરકારી UPI ગેટવે દ્વારા તમારી બેંક સાથે કનેક્ટ કરવામાં આવ્યું.',
        nextStep: 'તમે તાજેતરના વ્યવહારો જોઈ શકો છો અથવા ફંડ ટ્રાન્સફર કરી શકો છો.',
    },
};

const ResultPage = () => {
    const navigate = useNavigate();
    const location = useLocation();

    const state = location.state as {
        language?: string;
        languageCode?: string;
        transcript?: string;
    } | null;

    const langCode = state?.languageCode || 'en';
    const langName = state?.language || 'English';
    const transcript = state?.transcript || 'How can I check my account balance?';

    const result = mockResponses[langCode] || mockResponses.en;

    const [isProcessing, setIsProcessing] = useState(true);
    const [showResults, setShowResults] = useState(false);

    useEffect(() => {
        const timer = setTimeout(() => {
            setIsProcessing(false);
            setTimeout(() => setShowResults(true), 200);
        }, 3000);
        return () => clearTimeout(timer);
    }, []);

    const handleAskAgain = useCallback(() => {
        navigate('/');
    }, [navigate]);

    const handleDashboard = useCallback(() => {
        navigate('/');
    }, [navigate]);

    return (
        <div className="min-h-screen relative">
            <SparkleBackground />

            <div className="relative z-10 min-h-screen flex flex-col">
                <ResultNavbar />

                {/* Page header — tight spacing */}
                <div className="max-w-7xl mx-auto w-full px-4 sm:px-6 pt-6 pb-1">
                    <h1 className="text-2xl md:text-3xl font-heading font-bold text-[#f5f5f5]">
                        Voice Assistant
                    </h1>
                    <p className="mt-1 text-sm font-body text-[#9ca3af]">
                        {isProcessing ? 'Processing your request' : 'Here are your results'}
                    </p>
                    {transcript && (
                        <div className="mt-2 px-3 py-1.5 rounded-md bg-[#111111] border border-[#2a2a2a] inline-block">
                            <span className="text-[11px] text-[#555555] font-body">You said: </span>
                            <span className="text-xs text-[#9ca3af] font-body">"{transcript}"</span>
                        </div>
                    )}
                </div>

                {/* Three-column grid — tighter gaps, consistent spacing */}
                <div className="max-w-7xl mx-auto w-full px-4 sm:px-6 py-4 flex-1">
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

                        {/* LEFT — Audio Input + Intent + Confidence */}
                        <div className="space-y-4">
                            <AudioPreviewCard
                                language={langName}
                                languageCode={langCode}
                                duration="0:04"
                                isProcessing={isProcessing}
                            />
                            {/* Intent + Confidence grouped under audio */}
                            <div className="bg-[#111111] border border-[#2a2a2a] rounded-xl p-5 space-y-4">
                                <IntentBadge
                                    intent={result.intent}
                                    category={result.category}
                                    visible={showResults}
                                />
                                <div className="border-t border-[#2a2a2a]" />
                                <ConfidenceMeter
                                    confidence={result.confidence}
                                    visible={showResults}
                                />
                            </div>
                        </div>

                        {/* CENTER — Processing Waveform */}
                        <div className="space-y-4">
                            <WaveformProcessing isProcessing={isProcessing} />
                        </div>

                        {/* RIGHT — Response Card + Voice Player (grouped as system output) */}
                        <div className="space-y-4">
                            <ResponseCard
                                confirmation={result.confirmation}
                                explanation={result.explanation}
                                nextStep={result.nextStep}
                                visible={showResults}
                            />
                            {/* Voice player directly under response — connected as one output */}
                            {showResults && (
                                <VoicePlayer
                                    text={`${result.confirmation} ${result.explanation}`}
                                    langCode={langCode}
                                    autoPlay={true}
                                />
                            )}
                        </div>
                    </div>

                    {/* Action buttons — tight spacing */}
                    <div className="mt-6 flex justify-center">
                        <ActionButtons
                            onAskAgain={handleAskAgain}
                            onDashboard={handleDashboard}
                            visible={showResults}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ResultPage;
