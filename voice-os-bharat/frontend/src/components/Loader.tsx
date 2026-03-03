import { Loader2 } from 'lucide-react';

/** Processing spinner overlay */
interface LoaderProps {
    message?: string;
}

const Loader = ({ message = 'Processing...' }: LoaderProps) => {
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-4">
                <Loader2 className="w-12 h-12 text-[#f59e0b] animate-spin" />
                <p className="text-lg font-heading font-semibold text-[#f5f5f5]">
                    {message}
                </p>
            </div>
        </div>
    );
};

export default Loader;
