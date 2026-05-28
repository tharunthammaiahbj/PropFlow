import Link from "next/link";
import ChatWidget from "@/components/ChatWidget";

export const metadata = {
  title: "Live Demo — PropFlow",
  description: "Talk to Sophia, PropFlow's AI interior design consultant.",
};

export default function DemoPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Nav */}
      <nav className="bg-white border-b border-gray-100 px-6 h-14 flex items-center justify-between flex-shrink-0">
        <Link href="/" className="flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors text-sm">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </Link>
        <span className="font-semibold text-gray-900 tracking-tight text-sm">PropFlow Demo</span>
        <div className="w-16" />
      </nav>

      {/* Main layout */}
      <div className="flex-1 flex flex-col lg:flex-row max-w-6xl mx-auto w-full px-4 py-8 gap-8">
        {/* Left: context */}
        <div className="lg:w-72 flex-shrink-0">
          <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm">
            <div className="w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center mb-4">
              <span className="text-2xl">🏠</span>
            </div>
            <h1 className="font-bold text-gray-900 mb-2">Talk to Sophia</h1>
            <p className="text-sm text-gray-500 leading-relaxed mb-5">
              Sophia is PropFlow&apos;s interior design consultant. She&apos;ll understand your
              project through natural conversation and collect everything your team needs to follow up.
            </p>

            <div className="space-y-3 text-xs text-gray-400">
              <div className="flex gap-2 items-start">
                <span className="mt-0.5 text-green-500">✓</span>
                <span>Collects project type, city, area, budget, timeline &amp; more</span>
              </div>
              <div className="flex gap-2 items-start">
                <span className="mt-0.5 text-green-500">✓</span>
                <span>Handles domain questions, pricing guardrails &amp; off-topic messages</span>
              </div>
              <div className="flex gap-2 items-start">
                <span className="mt-0.5 text-green-500">✓</span>
                <span>Same AI that runs on WhatsApp and live phone calls</span>
              </div>
              <div className="flex gap-2 items-start">
                <span className="mt-0.5 text-green-500">✓</span>
                <span>Conversation saved in your browser — refresh safely</span>
              </div>
            </div>

            <div className="mt-6 pt-5 border-t border-gray-100">
              <div className="text-xs text-gray-400 mb-2 font-medium">Services available</div>
              <div className="flex flex-wrap gap-1.5">
                {["Interiors", "Construction", "Solar", "Painting", "Plumbing", "Electrical"].map(
                  (s) => (
                    <span
                      key={s}
                      className="text-xs bg-gray-50 border border-gray-200 text-gray-600 rounded-md px-2 py-0.5"
                    >
                      {s}
                    </span>
                  )
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right: chat */}
        <div className="flex-1 min-h-[560px] lg:min-h-0">
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm h-full flex flex-col overflow-hidden" style={{ minHeight: "560px" }}>
            <ChatWidget />
          </div>
        </div>
      </div>
    </div>
  );
}
