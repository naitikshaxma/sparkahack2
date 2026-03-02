const ResultNavbar = () => {
    return (
        <nav className="relative z-10 w-full px-6 py-4 border-b border-[#2a2a2a]">
            <div className="max-w-7xl mx-auto flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-[#f59e0b] flex items-center justify-center">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                            <line x1="12" x2="12" y1="19" y2="22" />
                        </svg>
                    </div>
                    <span className="text-[#f5f5f5] font-heading font-semibold text-base tracking-tight">
                        Voice OS <span className="text-[#f59e0b]">Bharat</span>
                    </span>
                </div>
                <span className="text-[#9ca3af] text-sm font-body hidden sm:block">
                    Voice Assistant
                </span>
            </div>
        </nav>
    );
};

export default ResultNavbar;
