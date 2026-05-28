import Link from "next/link";

function ProjectBriefCard() {
  const fields = [
    { label: "Client",   value: "Priya Sharma" },
    { label: "Service",  value: "Interior Design" },
    { label: "Property", value: "3BHK Apartment" },
    { label: "City",     value: "Bangalore, KA" },
    { label: "Area",     value: "1,450 sq ft" },
    { label: "Config",   value: "Open plan · 3 BR" },
    { label: "Budget",   value: "₹18 – 22 Lakhs" },
    { label: "Timeline", value: "4 – 6 months" },
    { label: "Style",    value: "Scandinavian minimal" },
  ];

  return (
    <div
      className="rounded-2xl overflow-hidden w-full"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      {/* Card header */}
      <div
        className="px-5 pt-4 pb-3.5 flex items-center gap-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full flex-shrink-0 animate-pulse"
          style={{ background: "var(--accent)" }}
        />
        <span className="mono-label" style={{ color: "var(--muted)" }}>
          Project Brief · Auto-generated
        </span>
      </div>

      {/* Fields */}
      <div className="px-5 py-1.5">
        {fields.map((f, i) => (
          <div
            key={f.label}
            className="flex items-baseline gap-3 py-2.5"
            style={i < fields.length - 1 ? { borderBottom: "1px solid var(--border)" } : {}}
          >
            <span
              className="mono-label flex-shrink-0 w-[4.5rem]"
              style={{ color: "var(--muted)" }}
            >
              {f.label}
            </span>
            <span className="text-[0.78rem] leading-snug" style={{ color: "var(--text)" }}>
              {f.value}
            </span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div
        className="px-5 py-3 flex items-center gap-2"
        style={{ borderTop: "1px solid var(--border)", background: "var(--surface2)" }}
      >
        <svg
          className="w-3 h-3 flex-shrink-0"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          viewBox="0 0 24 24"
          style={{ color: "var(--accent)" }}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
        <span className="text-[0.68rem]" style={{ color: "var(--muted)" }}>
          9 / 9 fields collected · Ready for team handoff
        </span>
      </div>
    </div>
  );
}

const features = [
  {
    num: "01",
    title: "WhatsApp & Voice",
    desc: "Clients reach out on WhatsApp or via phone. PropFlow handles both channels instantly with the same conversation engine.",
  },
  {
    num: "02",
    title: "Named AI Personas",
    desc: "Each service has a dedicated consultant — Sophia for interiors, Ryan for construction. Warm, expert, and locally aware.",
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
  { label: "FastAPI",        sub: "Python backend" },
  { label: "Gemini Flash",   sub: "Primary LLM" },
  { label: "Twilio",         sub: "WhatsApp" },
  { label: "Vapi",           sub: "Voice calls" },
  { label: "Upstash Redis",  sub: "Session cache" },
  { label: "Supabase",       sub: "Persistent storage" },
  { label: "Next.js 15",     sub: "Showcase frontend" },
  { label: "Render",         sub: "Backend hosting" },
];

export default function HomePage() {
  return (
    <main style={{ background: "var(--bg)", color: "var(--text)" }}>

      {/* ── Nav ───────────────────────────────────── */}
      <nav className="nav-blur fixed top-0 left-0 right-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div
              className="w-6 h-6 rounded-md flex items-center justify-center"
              style={{ background: "var(--accent)" }}
            >
              <span className="font-black text-[10px]" style={{ color: "#0d110d" }}>P</span>
            </div>
            <span className="font-semibold text-sm tracking-tight" style={{ color: "var(--text)" }}>
              PropFlow
            </span>
          </div>
          <Link href="/demo" className="btn-nav">
            Live demo →
          </Link>
        </div>
      </nav>

      {/* ── Hero ──────────────────────────────────── */}
      <section className="relative pt-44 pb-32 px-6 overflow-hidden">
        <div className="absolute inset-0 bg-grid pointer-events-none" />
        <div className="absolute inset-0 hero-glow pointer-events-none" />
        {/* Subtle bottom glow-line */}
        <div
          className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[28rem] h-px pointer-events-none"
          style={{
            background: "linear-gradient(90deg, transparent, rgba(156,204,101,0.18), transparent)",
          }}
        />

        <div className="relative max-w-6xl mx-auto">
          {/* Label row */}
          <div className="flex items-center gap-3 mb-14 fade-up">
            <span className="mono-label" style={{ color: "var(--muted)" }}>AI Intake Platform</span>
            <span
              className="w-8 h-px inline-block flex-shrink-0"
              style={{ background: "var(--border)" }}
            />
            <span className="mono-label" style={{ color: "var(--muted)" }}>Live Demo Available</span>
          </div>

          {/* Two-column grid */}
          <div className="grid lg:grid-cols-[1fr_308px] xl:grid-cols-[1fr_328px] gap-14 xl:gap-24 items-center">

            {/* Left: copy */}
            <div>
              <h1
                className="font-display font-bold tracking-tight mb-8 fade-up-2"
                style={{ fontSize: "clamp(2.9rem, 5.5vw, 5.25rem)", lineHeight: 1.06 }}
              >
                Your AI consultant,
                <br />
                <em className="not-italic italic text-gradient">on every channel.</em>
              </h1>

              <p
                className="text-[1.05rem] leading-relaxed mb-12 fade-up-3"
                style={{ color: "var(--muted)", maxWidth: "37rem" }}
              >
                PropFlow handles WhatsApp and voice calls as a named consultant. Structured
                client requirements collected through natural conversation, delivered to
                your team — automatically.
              </p>

              <div className="flex flex-wrap gap-3 fade-up-4">
                <Link href="/demo" className="btn-primary px-7 py-3.5 rounded-xl text-sm">
                  Try the live demo
                </Link>
                <a href="#how-it-works" className="btn-ghost px-7 py-3.5 rounded-xl text-sm">
                  How it works ↓
                </a>
              </div>
            </div>

            {/* Right: actual project brief output — the product's value made visible */}
            <div className="hidden lg:block fade-up-5">
              <ProjectBriefCard />
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ──────────────────────────── */}
      <section
        id="how-it-works"
        className="py-28 px-6"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <div className="max-w-6xl mx-auto">
          <div className="mb-16">
            <p className="mono-label mb-4" style={{ color: "var(--muted)" }}>Process</p>
            <h2
              className="font-display font-bold tracking-tight mb-4"
              style={{ fontSize: "clamp(2rem, 3.5vw, 3rem)" }}
            >
              How it works
            </h2>
            <p className="max-w-md text-base leading-relaxed" style={{ color: "var(--muted)" }}>
              A client reaches out. PropFlow handles the intake. Your team receives a
              structured brief — not a raw enquiry.
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
                <p className="step-num mb-5">{item.step} —</p>
                <h3
                  className="font-display font-bold text-xl mb-2.5"
                  style={{ color: "var(--text)" }}
                >
                  {item.title}
                </h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                  {item.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ──────────────────────────────── */}
      <section className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto">
          <div className="mb-16">
            <p className="mono-label mb-4" style={{ color: "var(--muted)" }}>Capabilities</p>
            <h2
              className="font-display font-bold tracking-tight mb-4"
              style={{ fontSize: "clamp(2rem, 3.5vw, 3rem)" }}
            >
              What PropFlow does
            </h2>
            <p className="text-base" style={{ color: "var(--muted)" }}>
              Production-grade AI intake, built for property and design services.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((f) => (
              <div key={f.title} className="card rounded-2xl p-6 cursor-default">
                <p className="step-num mb-4">{f.num}</p>
                <h3
                  className="font-display font-bold text-lg mb-2"
                  style={{ color: "var(--text)" }}
                >
                  {f.title}
                </h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
                  {f.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tech stack ────────────────────────────── */}
      <section className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto">
          <div className="mb-12">
            <p className="mono-label mb-4" style={{ color: "var(--muted)" }}>Stack</p>
            <h2
              className="font-display font-bold tracking-tight mb-2"
              style={{ fontSize: "clamp(2rem, 3.5vw, 3rem)" }}
            >
              Built with
            </h2>
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              Production-grade. Deployed and live.
            </p>
          </div>
          <div className="flex flex-wrap gap-2.5">
            {stack.map((s) => (
              <div key={s.label} className="card rounded-xl px-4 py-3 cursor-default">
                <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                  {s.label}
                </div>
                <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>{s.sub}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────── */}
      <section className="py-36 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="relative max-w-6xl mx-auto overflow-hidden">
          <div className="absolute inset-0 hero-glow pointer-events-none" />
          <div className="relative">
            <p className="mono-label mb-6" style={{ color: "var(--muted)" }}>Demo</p>
            <h2
              className="font-display font-bold tracking-tight mb-5 leading-tight"
              style={{ fontSize: "clamp(2.5rem, 5vw, 4.5rem)" }}
            >
              See it in action.
            </h2>
            <p
              className="text-lg leading-relaxed mb-10"
              style={{ color: "var(--muted)", maxWidth: "38rem" }}
            >
              Talk to Sophia — PropFlow&apos;s interior design consultant — right here in the
              browser. No WhatsApp required.
            </p>
            <Link href="/demo" className="btn-primary px-10 py-4 rounded-xl text-sm">
              Start conversation →
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────── */}
      <footer className="py-8 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className="w-5 h-5 rounded flex items-center justify-center"
              style={{ background: "var(--accent)" }}
            >
              <span className="font-black text-[9px]" style={{ color: "#0d110d" }}>P</span>
            </div>
            <span className="text-xs font-medium" style={{ color: "var(--muted)" }}>PropFlow</span>
          </div>
          <span className="text-xs" style={{ color: "var(--muted)" }}>AI Intake Platform</span>
        </div>
      </footer>
    </main>
  );
}
