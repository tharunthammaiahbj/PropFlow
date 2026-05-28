import Link from "next/link";
import ChatWidget from "@/components/ChatWidget";

export const metadata = {
  title: "Live Demo — PropFlow",
  description: "Talk to Jessica, PropFlow's AI consultant.",
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
          className="flex items-center gap-2 text-sm transition-opacity hover:opacity-70"
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
            <span className="font-black text-[10px]" style={{ color: "#0d110d" }}>P</span>
          </div>
          <span className="font-semibold tracking-tight text-sm">PropFlow</span>
        </div>
        <div className="w-16" />
      </nav>

      {/* Body */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden max-w-6xl mx-auto w-full px-4 py-5 gap-4">

        {/* Left info panel */}
        <div className="lg:w-60 flex-shrink-0 overflow-y-auto chat-scroll">
          <div
            className="rounded-2xl p-5 h-full"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            {/* Sparkle icon — signals AI intelligence */}
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center mb-4"
              style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                style={{ color: "var(--accent)" }}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z"
                />
              </svg>
            </div>

            <p className="mono-label mb-2" style={{ color: "var(--muted)" }}>AI Consultant</p>
            <h1
              className="font-display font-semibold text-base mb-2.5 leading-snug"
              style={{ color: "var(--text)" }}
            >
              Talk to Jessica
            </h1>
            <p className="text-xs leading-relaxed mb-5" style={{ color: "var(--muted)", lineHeight: "1.65" }}>
              Jessica is PropFlow&apos;s AI consultant. She handles all services and collects
              everything your team needs through natural conversation.
            </p>

            <div className="space-y-2.5 mb-5">
              {[
                "Collects project type, city, area, budget, timeline & more",
                "Handles pricing guardrails & off-topic messages gracefully",
                "Same AI that runs on WhatsApp and live phone calls",
                "Conversation saved in your browser — refresh safely",
              ].map((item) => (
                <div key={item} className="flex gap-2 items-start">
                  <span
                    className="mt-px flex-shrink-0 text-xs font-bold"
                    style={{ color: "var(--accent)", opacity: 0.8 }}
                  >
                    ✓
                  </span>
                  <span className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
                    {item}
                  </span>
                </div>
              ))}
            </div>

            <div style={{ borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
              <p className="mono-label mb-2.5" style={{ color: "var(--muted)" }}>Services</p>
              <div className="flex flex-wrap gap-1.5">
                {["Interiors", "Construction", "Solar", "Painting", "Plumbing", "Electrical"].map(
                  (s) => (
                    <span key={s} className="tag">{s}</span>
                  )
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Chat panel */}
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div
            className="rounded-2xl flex flex-col overflow-hidden flex-1"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            <ChatWidget />
          </div>
        </div>
      </div>
    </div>
  );
}
