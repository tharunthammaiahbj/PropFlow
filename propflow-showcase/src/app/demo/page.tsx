import Link from "next/link";
import ChatWidget from "@/components/ChatWidget";

export const metadata = {
  title: "Live Demo — PropFlow",
  description: "Talk to Sophia, PropFlow's AI interior design consultant.",
};

export default function DemoPage() {
  return (
    <div
      className="h-screen flex flex-col overflow-hidden"
      style={{ background: "var(--bg)", color: "var(--text)" }}
    >
      {/* Nav */}
      <nav className="nav-blur flex-shrink-0 px-6 h-14 flex items-center justify-between">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm transition-colors"
          style={{ color: "var(--muted)" }}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </Link>
        <div className="flex items-center gap-2.5">
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center"
            style={{ background: "var(--accent)" }}
          >
            <span className="font-bold text-[10px]" style={{ color: "#111411" }}>P</span>
          </div>
          <span className="font-semibold tracking-tight text-sm">PropFlow</span>
        </div>
        <div className="w-16" />
      </nav>

      {/* Body */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden max-w-6xl mx-auto w-full px-4 py-6 gap-5">

        {/* Left panel */}
        <div className="lg:w-72 flex-shrink-0 overflow-y-auto chat-scroll">
          <div className="card rounded-2xl p-6 h-full" style={{ background: "var(--surface)" }}>
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
              style={{ background: "var(--surface2)", border: "1px solid var(--border)", color: "var(--accent)" }}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.6} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
            </div>

            <div className="mono-label mb-3" style={{ color: "var(--accent)" }}>Interior Consultant</div>
            <h1 className="font-bold mb-2 text-base" style={{ color: "var(--text)" }}>Talk to Sophia</h1>
            <p className="text-sm leading-relaxed mb-6" style={{ color: "var(--muted)" }}>
              Sophia is PropFlow&apos;s interior design consultant. She&apos;ll understand your project
              through natural conversation and collect everything your team needs to follow up.
            </p>

            <div className="space-y-3 mb-6">
              {[
                "Collects project type, city, area, budget, timeline & more",
                "Handles pricing guardrails & off-topic messages gracefully",
                "Same AI that runs on WhatsApp and live phone calls",
                "Conversation saved in your browser — refresh safely",
              ].map((item) => (
                <div key={item} className="flex gap-2.5 items-start">
                  <span className="mt-0.5 flex-shrink-0 text-xs font-bold" style={{ color: "var(--accent)" }}>✓</span>
                  <span className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{item}</span>
                </div>
              ))}
            </div>

            <div style={{ borderTop: "1px solid var(--border)", paddingTop: "1.25rem" }}>
              <div className="mono-label mb-3" style={{ color: "var(--muted)" }}>Services available</div>
              <div className="flex flex-wrap gap-1.5">
                {["Interiors", "Construction", "Solar", "Painting", "Plumbing", "Electrical"].map((s) => (
                  <span key={s} className="tag">{s}</span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Chat panel */}
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div
            className="card rounded-2xl flex flex-col overflow-hidden flex-1"
            style={{ background: "var(--surface)" }}
          >
            <ChatWidget />
          </div>
        </div>
      </div>
    </div>
  );
}
