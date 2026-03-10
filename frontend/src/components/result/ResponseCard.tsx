import { CheckCircle, Info, ArrowRight } from 'lucide-react';

interface ResponseCardProps {
    confirmation: string;
    explanation: string;
    nextStep: string;
    visible: boolean;
}

const ResponseCard = ({ confirmation, explanation, nextStep, visible }: ResponseCardProps) => {
    return (
        <div
            className="bg-[#111111] border border-[#2a2a2a] rounded-xl overflow-hidden transition-all duration-700 ease-out"
            style={{
                opacity: visible ? 1 : 0,
                transform: visible ? 'translateY(0)' : 'translateY(16px)',
            }}
        >
            <div className="px-5 py-4 border-b border-[#2a2a2a]">
                <h3 className="text-sm font-body font-medium text-[#9ca3af] uppercase tracking-wider">
                    Response
                </h3>
            </div>

            <div className="p-5 space-y-5">
                {/* Confirmation */}
                <div className="flex gap-3">
                    <CheckCircle className="w-5 h-5 text-[#14b8a6] mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs font-body text-[#9ca3af] uppercase tracking-wider mb-1">
                            Confirmation
                        </p>
                        <p className="text-sm font-body text-[#f5f5f5] leading-relaxed">
                            {confirmation}
                        </p>
                    </div>
                </div>

                {/* Divider */}
                <div className="border-t border-[#2a2a2a]" />

                {/* Explanation */}
                <div className="flex gap-3">
                    <Info className="w-5 h-5 text-[#f59e0b] mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs font-body text-[#9ca3af] uppercase tracking-wider mb-1">
                            Explanation
                        </p>
                        <p className="text-sm font-body text-[#f5f5f5] leading-relaxed">
                            {explanation}
                        </p>
                    </div>
                </div>

                {/* Divider */}
                <div className="border-t border-[#2a2a2a]" />

                {/* Next Step */}
                <div className="flex gap-3">
                    <ArrowRight className="w-5 h-5 text-[#d4a843] mt-0.5 shrink-0" />
                    <div>
                        <p className="text-xs font-body text-[#9ca3af] uppercase tracking-wider mb-1">
                            Next Step
                        </p>
                        <p className="text-sm font-body text-[#f5f5f5] leading-relaxed">
                            {nextStep}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ResponseCard;
