import Link from "next/link";

const features = [
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
    title: "WhatsApp & Voice",
    description:
      "Clients reach out on WhatsApp or via phone call. PropFlow handles both channels with the same intelligent questionnaire engine.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
    title: "Named AI Personas",
    description:
      "Each service has a dedicated consultant — Sophia for interiors, Ryan for construction, and more. Warm, expert, locally aware.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
    ),
    title: "Structured Lead Capture",
    description:
      "Collects 9 required fields through natural conversation, then generates a project brief and forwards it to your CRM automatically.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
    title: "Admin Dashboard",
    description:
      "Live session browser, transcript viewer, extracted field inspection, performance metrics, and webhook audit trails.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
      </svg>
    ),
    title: "Multilingual",
    description:
      "Supports English, Hindi, Kannada, and Tamil with natural code-switching. Designed for the Indian market.",
  },
  {
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
    ),
    title: "Built-in Guardrails",
    description:
      "Never quotes prices, never makes timeline promises, handles off-topic messages gracefully, and maintains persona under pressure.",
  },
];

const stack = [
  { label: "FastAPI", sub: "Python backend" },
  { label: "Gemini 2.0", sub: "Primary LLM" },
  { label: "Twilio", sub: "WhatsApp" },
  { label: "Vapi", sub: "Voice calls" },
  { label: "Upstash Redis", sub: "Session cache" },
  { label: "Supabase", sub: "Persistent storage" },
  { label: "React + Vite", sub: "Admin dashboard" },
  { label: "Render", sub: "Backend hosting" },
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-white">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <span className="font-semibold text-gray-900 tracking-tight">PropFlow</span>
          <Link
            href="/demo"
            className="text-sm bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
          >
            Try live demo
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-24 px-6 text-center">
        <div className="max-w-3xl mx-auto">
          <span className="inline-block text-xs font-semibold text-green-700 bg-green-50 border border-green-200 px-3 py-1 rounded-full mb-6 tracking-wide uppercase">
            AI Intake Platform
          </span>
          <h1 className="text-5xl sm:text-6xl font-bold text-gray-900 leading-tight tracking-tight mb-6">
            Your AI consultant,{" "}
            <span className="text-green-600">on every channel</span>
          </h1>
          <p className="text-lg text-gray-500 max-w-xl mx-auto mb-10 leading-relaxed">
            PropFlow handles WhatsApp and voice calls as a named consultant. It collects structured
            client requirements through natural conversation and forwards them to your team — automatically.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/demo"
              className="bg-green-600 hover:bg-green-700 text-white px-8 py-3.5 rounded-xl font-semibold text-base transition-colors shadow-sm"
            >
              Try the live demo
            </Link>
            <a
              href="#how-it-works"
              className="border border-gray-200 hover:border-gray-300 text-gray-700 px-8 py-3.5 rounded-xl font-medium text-base transition-colors"
            >
              How it works
            </a>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-20 px-6 bg-gray-50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-gray-900 text-center mb-4">How it works</h2>
          <p className="text-gray-500 text-center mb-14 max-w-xl mx-auto">
            A client reaches out — PropFlow takes over the intake, so your team receives a
            complete, structured brief instead of a raw enquiry.
          </p>
          <div className="grid sm:grid-cols-3 gap-6">
            {[
              {
                step: "01",
                title: "Client reaches out",
                body: "Via WhatsApp message or phone call. PropFlow answers instantly as the right consultant for the service.",
              },
              {
                step: "02",
                title: "Natural conversation",
                body: "The AI collects 9 required fields through warm, expert dialogue — no forms, no dropdowns.",
              },
              {
                step: "03",
                title: "Structured brief delivered",
                body: "A project summary is generated and posted to your CRM or PM tool automatically.",
              },
            ].map((item) => (
              <div key={item.step} className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm">
                <div className="text-xs font-bold text-green-600 mb-3 tracking-widest">{item.step}</div>
                <h3 className="font-semibold text-gray-900 mb-2">{item.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-gray-900 text-center mb-14">What PropFlow does</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f) => (
              <div key={f.title} className="p-6 rounded-2xl border border-gray-100 hover:border-green-200 transition-colors">
                <div className="w-10 h-10 bg-green-50 text-green-600 rounded-xl flex items-center justify-center mb-4">
                  {f.icon}
                </div>
                <h3 className="font-semibold text-gray-900 mb-2">{f.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{f.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech stack */}
      <section className="py-20 px-6 bg-gray-50">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">Built with</h2>
          <p className="text-gray-500 mb-10">Production-grade stack, deployed and live.</p>
          <div className="flex flex-wrap justify-center gap-3">
            {stack.map((s) => (
              <div key={s.label} className="bg-white border border-gray-200 rounded-xl px-4 py-3 text-left shadow-sm">
                <div className="text-sm font-semibold text-gray-900">{s.label}</div>
                <div className="text-xs text-gray-400">{s.sub}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 px-6 text-center">
        <div className="max-w-xl mx-auto">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">See it in action</h2>
          <p className="text-gray-500 mb-8">
            Talk to Sophia — PropFlow&apos;s interior design consultant — right here in the browser.
            No WhatsApp required.
          </p>
          <Link
            href="/demo"
            className="inline-block bg-green-600 hover:bg-green-700 text-white px-10 py-4 rounded-xl font-semibold text-base transition-colors shadow-sm"
          >
            Start the demo
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-100 py-8 px-6 text-center text-sm text-gray-400">
        PropFlow · Built by PropFlow
      </footer>
    </main>
  );
}
