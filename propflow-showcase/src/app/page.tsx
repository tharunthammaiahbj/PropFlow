import Link from "next/link";

const features = [
  {
    num: "01",
    title: "WhatsApp & Voice",
    desc: "Clients reach out on WhatsApp or via phone. PropFlow handles both with the same intelligent conversation engine — instantly.",
  },
  {
    num: "02",
    title: "Named AI Personas",
    desc: "Each service has a dedicated consultant — Sophia for interiors, Ryan for construction, and more. Warm, expert, locally aware.",
  },
  {
    num: "03",
    title: "Structured Lead Capture",
    desc: "Collects 9 required fields through natural conversation, generates a project brief, and forwards it to your CRM automatically.",
  },
  {
    num: "04",
    title: "Admin Dashboard",
    desc: "Live session browser, transcript viewer, extracted field inspection, performance metrics, and webhook audit trails.",
  },
  {
    num: "05",
    title: "Multilingual",
    desc: "Supports English, Hindi, Kannada, and Tamil with natural code-switching. Designed for the Indian market.",
  },
  {
    num: "06",
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
          <div className="flex items-center gap-2.5">
            <div
              className="w-7 h-7 rounded-md flex items-center justify-center"
              style={{ background: "var(--accent)" }}
            >
              <span className="font-bold text-[11px]" style={{ color: "#111411" }}>P</span>
            </div>
            <span className="font-semibold tracking-tight text-sm" style={{ color: "var(--text)" }}>PropFlow</span>
          </div>
          <Link
            href="/demo"
            className="btn-primary text-sm px-5 py-2 rounded-lg"
          >
            Try live demo →
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-44 pb-36 px-6 overflow-hidden">
        <div className="absolute inset-0 bg-grid pointer-events-none" />
        <div className="absolute inset-0 hero-glow pointer-events-none" />

        <div className="relative max-w-5xl mx-auto">
          {/* Label row */}
          <div className="fade-up flex items-center gap-0 mb-10">
            <span className="mono-label" style={{ color: "var(--accent)" }}>AI Intake Platform</span>
            <span className="divider-accent" />
            <span className="mono-label" style={{ color: "var(--muted)" }}>Live Demo Available</span>
          </div>

          {/* Headline */}
          <h1 className="fade-up-2 text-5xl sm:text-6xl lg:text-7xl xl:text-[5.5rem] font-bold leading-[1.05] tracking-tight mb-8">
            Your AI consultant,
            <br />
            <span className="text-gradient">on every channel.</span>
          </h1>

          <p className="fade-up-3 text-lg leading-relaxed max-w-lg mb-12" style={{ color: "var(--muted)" }}>
            PropFlow handles WhatsApp and voice calls as a named consultant.
            It collects structured client requirements through natural conversation
            and delivers them to your team — automatically.
          </p>

          <div className="fade-up-4 flex flex-col sm:flex-row gap-3">
            <Link
              href="/demo"
              className="btn-primary inline-flex items-center justify-center px-8 py-3.5 rounded-xl text-base"
            >
              Try the live demo
            </Link>
            <a
              href="#how-it-works"
              className="btn-ghost inline-flex items-center justify-center px-8 py-3.5 rounded-xl text-base"
            >
              How it works ↓
            </a>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-5xl mx-auto">
          <div className="mb-16">
            <div className="mono-label mb-4" style={{ color: "var(--accent)" }}>Process</div>
            <h2 className="text-3xl sm:text-4xl font-bold mb-3">How it works</h2>
            <p className="max-w-md" style={{ color: "var(--muted)" }}>
              A client reaches out. PropFlow takes over the intake. Your team receives a complete structured brief — not a raw enquiry.
            </p>
          </div>
          <div className="grid sm:grid-cols-3 gap-5">
            {[
              {
                step: "01",
                title: "Client reaches out",
                body: "Via WhatsApp or phone. PropFlow answers instantly as the right consultant for the service requested.",
              },
              {
                step: "02",
                title: "Natural conversation",
                body: "The AI collects 9 required fields through warm expert dialogue — no forms, no dropdowns, no friction.",
              },
              {
                step: "03",
                title: "Brief delivered",
                body: "A structured project summary is generated and posted to your CRM or PM tool automatically.",
              },
            ].map((item) => (
              <div key={item.step} className="card rounded-2xl p-7">
                <div className="step-label mb-5">{item.step} —</div>
                <h3 className="font-semibold mb-2.5" style={{ color: "var(--text)" }}>{item.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-5xl mx-auto">
          <div className="mb-16">
            <div className="mono-label mb-4" style={{ color: "var(--accent)" }}>Capabilities</div>
            <h2 className="text-3xl sm:text-4xl font-bold mb-3">What PropFlow does</h2>
            <p style={{ color: "var(--muted)" }}>Production-grade AI intake, built for property and design services.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((f) => (
              <div key={f.title} className="card rounded-2xl p-6 group cursor-default">
                <div className="step-label mb-4">{f.num}</div>
                <h3 className="font-semibold mb-2 text-sm" style={{ color: "var(--text)" }}>{f.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech stack */}
      <section className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-5xl mx-auto">
          <div className="mb-12">
            <div className="mono-label mb-4" style={{ color: "var(--accent)" }}>Stack</div>
            <h2 className="text-3xl sm:text-4xl font-bold mb-3">Built with</h2>
            <p style={{ color: "var(--muted)" }}>Production-grade. Deployed and live.</p>
          </div>
          <div className="flex flex-wrap gap-2.5">
            {stack.map((s) => (
              <div key={s.label} className="card rounded-xl px-4 py-3 cursor-default">
                <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>{s.label}</div>
                <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>{s.sub}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-36 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="relative max-w-5xl mx-auto overflow-hidden">
          <div className="absolute inset-0 hero-glow pointer-events-none" />
          <div className="relative">
            <div className="mono-label mb-6" style={{ color: "var(--accent)" }}>Demo</div>
            <h2 className="text-4xl sm:text-5xl font-bold mb-5 leading-tight">
              See it in action.
            </h2>
            <p className="mb-10 text-lg leading-relaxed" style={{ color: "var(--muted)", maxWidth: "36rem" }}>
              Talk to Sophia — PropFlow&apos;s interior design consultant — right here in the browser.
              No WhatsApp required.
            </p>
            <Link
              href="/demo"
              className="btn-primary inline-flex items-center gap-2 px-10 py-4 rounded-xl text-base"
            >
              Start conversation →
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className="w-5 h-5 rounded flex items-center justify-center"
              style={{ background: "var(--accent)" }}
            >
              <span className="font-bold text-[9px]" style={{ color: "#111411" }}>P</span>
            </div>
            <span className="text-xs font-medium" style={{ color: "var(--muted)" }}>PropFlow</span>
          </div>
          <span className="text-xs" style={{ color: "var(--muted)" }}>AI Intake Platform</span>
        </div>
      </footer>
    </main>
  );
}
