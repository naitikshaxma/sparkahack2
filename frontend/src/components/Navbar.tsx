const Navbar = () => {
    return (
        <nav className="relative z-10 w-full px-6 py-4 border-b border-white/10">
            <div className="max-w-6xl mx-auto flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-[#f59e0b] flex items-center justify-center">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                            <line x1="12" x2="12" y1="19" y2="22" />
                        </svg>
                    </div>
                    <div>
                        <h1 className="text-lg font-bold font-heading tracking-tight leading-tight text-white">
                            Voice OS <span className="text-[#f59e0b]">Bharat</span>
                        </h1>
                    </div>
                </div>
                <p className="hidden sm:block text-sm text-gray-400 font-body">
                    A Multilingual AI Assistant for Bharat
                </p>
            </div>
        </nav>
    );
};

export default Navbar;
