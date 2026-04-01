import { Link } from "react-router-dom";
import SparkleBackground from "@/components/SparkleBackground";

const ResultPage = () => {
  return (
    <div className="relative min-h-screen bg-[linear-gradient(180deg,#0B0B0B_0%,#020202_100%)] text-white px-6 py-16">
      <SparkleBackground />
      <section className="relative z-10 mx-auto max-w-2xl rounded-2xl border border-white/10 bg-[#111827] p-8">
        <h1 className="text-2xl font-semibold mb-3">Application Result</h1>
        <p className="text-gray-400 mb-6">
          Your latest application status and recommendations will appear here.
        </p>
        <Link
          to="/assistant"
          className="inline-flex items-center rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-amber-200 hover:bg-white/10"
        >
          Back To Assistant
        </Link>
      </section>
    </div>
  );
};

export default ResultPage;
