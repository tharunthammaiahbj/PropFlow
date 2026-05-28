import Link from "next/link";

const features = [
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.6} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
    title: "WhatsApp & Voice",
    desc: "Clients reach out on WhatsApp or via phone. PropFlow handles both with the same intelligent conversation engine — instantly.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.6} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
    title: "Named AI Personas",
    desc: "Each service has a dedicated consultant — Sophia for interiors, Ryan for construction, and more. Warm, expert, locally aware.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.6} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
    ),
    title: "Structured Lead Capture",
    desc: "Collects 9 required fields through natural conversation, generates a project brief, and forwards it to your CRM — automatically.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.6} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    title: "Admin Dashboard",
    desc: "Live session browser, transcript viewer, extracted field inspection, performance metrics, and webhook audit trails.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.6} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
      </svg>
    ),
    title: "Multilingual",
    desc: "Supports English, Hindi, Kannada, and Tamil with natural code-switching. Designed for the Indian market.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.6} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
    ),
    title: "Built-in Guardrails",
    desc: "Never quotes prices, never promises timelines, handles off-topic messages gracefully, and maintains persona under pressure.",
  },
];

const stack = [
  { label: "FastAPI", sub: "Python backend" },
  { label: "Gemini Flash", sub: "Primary LLM" },
  { label: "Twilio", sub: "WhatsApp" },
  { label: "Vapi", sub: "Voice calls" },
  { label: "Upstash Redis", sub: "Session cache" },
  { label: "Supabase", sub: "Persistent storage" },
  { label: "Next.js 15", sub: "Showcase frontend" },
  { label: "Render", sub: "Backend hosting" },
];

export default function HomePage() {
  return (
    <main style={{ background: "var(--bg)", color: "var(--text)" }}>
      {/* Nav */}
      <nav className="nav-blur fixed top-0 left-0 right-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-emerald-500 flex items-center justify-center">
              <span className="text-white font-bold text-xs">P</span>
            </div>
            <span className="font-semibold tracking-tight" style={{ color: "var(--text)" }}>PropFlow</span>
          </div>
          <Link
            href="/demo"
            className="btn-glow text-sm bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-4 py-2 rounded-lg transition-all"
          >
            Try live demo →
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-36 pb-28 px-6 text-center overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-100 pointer-events-none" />
        <div className="absolute inset-0 hero-glow pointer-events-none" />
        <div className="relative max-w-4xl mx-auto">
          <div className="fade-up inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-8"
            style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-medium tracking-widest uppercase" style={{ color: "var(--muted)" }}>
              AI Intake Platform · Live Demo Available
            </span>
          </div>

          <h1 className="fade-up-2 text-5xl sm:text-6xl lg:text-7xl font-bold leading-[1.08] tracking-tight mb-6">
            Your AI consultant,{" "}
            <br className="hidden sm:block" />
            <span className="text-gradient">on every channel</span>
          </h1>

          <p className="fade-up-3 text-lg leading-relaxed max-w-2xl mx-auto mb-10" style={{ color: "var(--muted)" }}>
            PropFlow handles WhatsApp and voice calls as a named consultant.
            It collects structured client requirements through natural conversation
            and forwards them to your team — automatically.
          </p>

          <div className="fade-up-4 flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/demo"
              className="btn-glow bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-8 py-3.5 rounded-xl text-base transition-all"
            >
              Try the live demo
            </Link>
            <a
              href="#how-it-works"
              className="card font-medium px-8 py-3.5 rounded-xl text-base"
              style={{ color: "var(--muted)" }}
            >
              How it works ↓
            </a>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-24 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">How it works</h2>
            <p className="max-w-lg mx-auto" style={{ color: "var(--muted)" }}>
              A client reaches out — PropFlow takes over the intake, so your team receives a
              complete structured brief instead of a raw enquiry.
            </p>
          </div>
          <div className="grid sm:grid-cols-3 gap-5">
            {[
              {
                step: "01",
                title: "Client reaches out",
                body: "Via WhatsApp message or phone call. PropFlow answers instantly as the right consultant for the service.",
              },
              {
                step: "02",
                title: "Natural conversation",
                body: "The AI collects 9 required fields through warm expert dialogue — no forms, no dropdowns, no friction.",
              },
              {
                step: "03",
                title: "Structured brief delivered",
                body: "A project summary is generated and posted to your CRM or PM tool automatically.",
              },
            ].map((item) => (
              <div key={item.step} className="card rounded-2xl p-7">
                <div className="step-num mb-4">{item.step}</div>
                <h3 className="font-semibold mb-2 text-base" style={{ color: "var(--text)" }}>{item.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-24 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">What PropFlow does</h2>
            <p style={{ color: "var(--muted)" }}>Production-grade AI intake, built for property and design services.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((f) => (
              <div key={f.title} className="card rounded-2xl p-6 group cursor-default">
                <div
                  className="w-9 h-9 rounded-xl flex items-center justify-center mb-4 text-emerald-400 transition-colors"
                  style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
                >
                  {f.icon}
                </div>
                <h3 className="font-semibold mb-2 text-sm" style={{ color: "var(--text)" }}>{f.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech stack */}
      <section className="py-24 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">Built with</h2>
          <p className="mb-12" style={{ color: "var(--muted)" }}>
            Production-grade stack. Deployed and live.
          </p>
          <div className="flex flex-wrap justify-center gap-2.5">
            {stack.map((s) => (
              <div key={s.label} className="card rounded-xl px-4 py-3 text-left cursor-default">
                <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>{s.label}</div>
                <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>{s.sub}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="relative max-w-2xl mx-auto text-center overflow-hidden">
          <div className="absolute inset-0 hero-glow pointer-events-none" />
          <div className="relative">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">See it in action</h2>
            <p className="mb-10 text-lg" style={{ color: "var(--muted)" }}>
              Talk to Sophia — PropFlow&apos;s interior design consultant — right here in the browser.
              No WhatsApp required.
            </p>
            <Link
              href="/demo"
              className="btn-glow inline-block bg-emerald-500 hover:bg-emerald-400 text-black font-semibold px-10 py-4 rounded-xl text-base transition-all"
            >
              Start the demo →
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 text-center text-xs" style={{ borderTop: "1px solid var(--border)", color: "var(--muted)" }}>
        PropFlow · AI Intake Platform
      </footer>
    </main>
  );
}
