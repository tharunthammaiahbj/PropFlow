import Link from "next/link";

function FloorPlanSVG() {
  return (
    <svg viewBox="0 0 440 340" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
      {/* Outer walls */}
      <rect x="40" y="40" width="360" height="260" stroke="#9ccc65" strokeWidth="1.5" />

      {/* Internal partition walls */}
      <line x1="40" y1="170" x2="230" y2="170" stroke="#9ccc65" strokeWidth="1" />
      <line x1="230" y1="40" x2="230" y2="220" stroke="#9ccc65" strokeWidth="1" />
      <line x1="230" y1="220" x2="400" y2="220" stroke="#9ccc65" strokeWidth="1" />
      <line x1="310" y1="40" x2="310" y2="170" stroke="#9ccc65" strokeWidth="1" />

      {/* Door swing — living area */}
      <line x1="230" y1="170" x2="230" y2="142" stroke="#9ccc65" strokeWidth="0.75" />
      <path d="M 230 170 A 28 28 0 0 1 258 142" stroke="#9ccc65" strokeWidth="0.75" strokeDasharray="3 2.5" />

      {/* Window marks — top wall */}
      <line x1="80" y1="40" x2="80" y2="32" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="170" y1="40" x2="170" y2="32" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="80" y1="32" x2="170" y2="32" stroke="#9ccc65" strokeWidth="0.75" />

      <line x1="250" y1="40" x2="250" y2="32" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="360" y1="40" x2="360" y2="32" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="250" y1="32" x2="360" y2="32" stroke="#9ccc65" strokeWidth="0.75" />

      {/* Window marks — left wall */}
      <line x1="40" y1="80" x2="32" y2="80" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="40" y1="145" x2="32" y2="145" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="32" y1="80" x2="32" y2="145" stroke="#9ccc65" strokeWidth="0.75" />

      <line x1="40" y1="205" x2="32" y2="205" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="40" y1="265" x2="32" y2="265" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="32" y1="205" x2="32" y2="265" stroke="#9ccc65" strokeWidth="0.75" />

      {/* Window marks — right wall */}
      <line x1="400" y1="75" x2="408" y2="75" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="400" y1="140" x2="408" y2="140" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="408" y1="75" x2="408" y2="140" stroke="#9ccc65" strokeWidth="0.75" />

      {/* Corner markers */}
      <circle cx="40"  cy="40"  r="2.5" fill="#9ccc65" />
      <circle cx="400" cy="40"  r="2.5" fill="#9ccc65" />
      <circle cx="40"  cy="300" r="2.5" fill="#9ccc65" />
      <circle cx="400" cy="300" r="2.5" fill="#9ccc65" />

      {/* Dimension line — horizontal */}
      <line x1="40"  y1="318" x2="400" y2="318" stroke="#9ccc65" strokeWidth="0.5" strokeDasharray="4 3" />
      <line x1="40"  y1="313" x2="40"  y2="323" stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="400" y1="313" x2="400" y2="323" stroke="#9ccc65" strokeWidth="0.75" />

      {/* Dimension line — vertical */}
      <line x1="418" y1="40"  x2="418" y2="300" stroke="#9ccc65" strokeWidth="0.5" strokeDasharray="4 3" />
      <line x1="413" y1="40"  x2="423" y2="40"  stroke="#9ccc65" strokeWidth="0.75" />
      <line x1="413" y1="300" x2="423" y2="300" stroke="#9ccc65" strokeWidth="0.75" />

      {/* North indicator */}
      <line x1="418" y1="318" x2="418" y2="332" stroke="#9ccc65" strokeWidth="1" />
      <polygon points="418,316 415,325 421,325" fill="#9ccc65" />

      {/* Room centroid dots */}
      <circle cx="135" cy="105" r="1.5" fill="#9ccc65" opacity="0.45" />
      <circle cx="135" cy="235" r="1.5" fill="#9ccc65" opacity="0.45" />
      <circle cx="315" cy="105" r="1.5" fill="#9ccc65" opacity="0.45" />
      <circle cx="315" cy="260" r="1.5" fill="#9ccc65" opacity="0.45" />
    </svg>
  );
}

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
      {/* ── Nav ─────────────────────────────────────────── */}
      <nav className="nav-blur fixed top-0 left-0 right-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div
              className="w-6 h-6 rounded-md flex items-center justify-center"
              style={{ background: "var(--accent)" }}
            >
              <span className="font-black text-[10px]" style={{ color: "#111411" }}>P</span>
            </div>
            <span className="font-semibold tracking-tight text-sm" style={{ color: "var(--text)" }}>PropFlow</span>
          </div>
          <Link href="/demo" className="btn-nav">
            Live demo →
          </Link>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────── */}
      <section className="relative pt-44 pb-36 px-6 overflow-hidden">
        <div className="absolute inset-0 bg-grid pointer-events-none" />
        <div className="absolute inset-0 hero-glow pointer-events-none" />

        <div className="relative max-w-6xl mx-auto">
          {/* Label row */}
          <div className="fade-up flex items-center gap-3 mb-14">
            <span className="mono-label" style={{ color: "var(--muted)" }}>01</span>
            <span className="w-6 h-px inline-block" style={{ background: "var(--border)" }} />
            <span className="mono-label" style={{ color: "var(--muted)" }}>AI Intake Platform</span>
          </div>

          {/* Content grid */}
          <div className="grid lg:grid-cols-[1fr_380px] gap-12 xl:gap-20 items-center">
            {/* Text */}
            <div>
              <h1 className="fade-up-2 font-black leading-[1.04] tracking-tight mb-8"
                style={{ fontSize: "clamp(2.8rem, 6vw, 5.25rem)" }}>
                Your AI consultant,
                <br />
                <span className="text-gradient">on every channel.</span>
              </h1>

              <p className="fade-up-3 text-lg leading-relaxed mb-12"
                style={{ color: "var(--muted)", maxWidth: "38rem" }}>
                PropFlow handles WhatsApp and voice calls as a named consultant.
                Structured client requirements collected through natural conversation,
                delivered to your team — automatically.
              </p>

              <div className="fade-up-4 flex flex-wrap gap-3">
                <Link href="/demo" className="btn-primary px-8 py-3.5 rounded-xl text-base">
                  Try the live demo
                </Link>
                <a href="#how-it-works" className="btn-ghost px-8 py-3.5 rounded-xl text-base">
                  How it works ↓
                </a>
              </div>
            </div>

            {/* Architectural floor plan decoration */}
            <div className="hidden lg:block fade-up-5" style={{ opacity: 0.16 }}>
              <FloorPlanSVG />
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────── */}
      <section id="how-it-works" className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto">
          <div className="mb-16">
            <p className="mono-label mb-3" style={{ color: "var(--muted)" }}>Process</p>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3">How it works</h2>
            <p className="max-w-md text-base leading-relaxed" style={{ color: "var(--muted)" }}>
              A client reaches out. PropFlow handles the intake. Your team receives a complete structured brief — not a raw enquiry.
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
                body: "A project summary is generated and posted to your CRM or PM tool automatically.",
              },
            ].map((item) => (
              <div key={item.step} className="card rounded-2xl p-7">
                <p className="step-num mb-5">{item.step} —</p>
                <h3 className="font-semibold mb-2.5 text-base" style={{ color: "var(--text)" }}>{item.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────── */}
      <section className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto">
          <div className="mb-16">
            <p className="mono-label mb-3" style={{ color: "var(--muted)" }}>Capabilities</p>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3">What PropFlow does</h2>
            <p className="text-base" style={{ color: "var(--muted)" }}>
              Production-grade AI intake, built for property and design services.
            </p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {features.map((f) => (
              <div key={f.title} className="card rounded-2xl p-6 cursor-default">
                <p className="step-num mb-4">{f.num}</p>
                <h3 className="font-semibold mb-2 text-sm" style={{ color: "var(--text)" }}>{f.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tech Stack ────────────────────────────────────── */}
      <section className="py-28 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto">
          <div className="mb-12">
            <p className="mono-label mb-3" style={{ color: "var(--muted)" }}>Stack</p>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">Built with</h2>
            <p className="text-sm" style={{ color: "var(--muted)" }}>Deployed and live.</p>
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

      {/* ── CTA ───────────────────────────────────────────── */}
      <section className="py-36 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="relative max-w-6xl mx-auto overflow-hidden">
          <div className="absolute inset-0 hero-glow pointer-events-none" />
          <div className="relative">
            <p className="mono-label mb-6" style={{ color: "var(--muted)" }}>Demo</p>
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-5 leading-tight">
              See it in action.
            </h2>
            <p className="text-lg leading-relaxed mb-10" style={{ color: "var(--muted)", maxWidth: "38rem" }}>
              Talk to Sophia — PropFlow&apos;s interior design consultant — right here in the browser.
              No WhatsApp required.
            </p>
            <Link href="/demo" className="btn-primary px-10 py-4 rounded-xl text-base">
              Start conversation →
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────── */}
      <footer className="py-8 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className="w-5 h-5 rounded flex items-center justify-center"
              style={{ background: "var(--accent)" }}
            >
              <span className="font-black text-[9px]" style={{ color: "#111411" }}>P</span>
            </div>
            <span className="text-xs font-medium" style={{ color: "var(--muted)" }}>PropFlow</span>
          </div>
          <span className="text-xs" style={{ color: "var(--muted)" }}>AI Intake Platform</span>
        </div>
      </footer>
    </main>
  );
}
