"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import ChatWidget from "./ChatWidget";

const STORAGE_KEY_FIELDS = "propflow_demo_fields";

/* ── Field metadata ───────────────────────────────────────────── */

const FIELD_ORDER = [
  "service",
  "project_type",
  "scope_type",
  "location",
  "city",
  "rooms",
  "size_sqft",
  "plot_size_sqft",
  "capacity_kw",
  "grid_type",
  "roof_type",
  "monthly_units",
  "load_requirement",
  "current_system",
  "safety_audit",
  "painting_scope",
  "paint_finish",
  "style",
  "budget",
  "timeline",
  "preferred_start",
  "notes",
];

const FIELD_LABELS: Record<string, string> = {
  service:         "Service",
  project_type:    "Type",
  scope_type:      "Scope",
  location:        "Location",
  city:            "City",
  rooms:           "Rooms",
  size_sqft:       "Area (sq ft)",
  plot_size_sqft:  "Plot Size",
  capacity_kw:     "Capacity",
  grid_type:       "Grid",
  roof_type:       "Roof",
  monthly_units:   "Monthly kWh",
  load_requirement:"Load (kW)",
  current_system:  "Setup",
  safety_audit:    "Safety",
  painting_scope:  "Paint Scope",
  paint_finish:    "Finish",
  style:           "Style",
  budget:          "Budget",
  timeline:        "Timeline",
  preferred_start: "Start",
  notes:           "Notes",
};

/* ── Info panel (default state) ───────────────────────────────── */

function InfoPanel() {
  return (
    <div
      className="rounded-2xl p-5 h-full"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
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
            <span className="mt-px flex-shrink-0 text-xs font-bold" style={{ color: "var(--accent)", opacity: 0.8 }}>
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
          {["Interiors", "Construction", "Solar", "Painting", "Plumbing", "Electrical"].map((s) => (
            <span key={s} className="tag">{s}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Completion panel (after enquiry is done) ─────────────────── */

function CompletionPanel({
  fields,
  createdAt,
}: {
  fields: Record<string, string>;
  createdAt: string;
}) {
  const orderedEntries = [
    ...FIELD_ORDER.filter((k) => fields[k]).map((k): [string, string] => [k, fields[k]]),
    ...Object.entries(fields).filter(([k]) => !FIELD_ORDER.includes(k)),
  ];

  return (
    <div
      className="rounded-2xl p-5 h-full flex flex-col fade-up"
      style={{
        background: "var(--surface)",
        border: "1px solid rgba(156,204,101,0.22)",
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span
          className="w-1.5 h-1.5 rounded-full animate-pulse flex-shrink-0"
          style={{ background: "var(--accent)" }}
        />
        <span className="mono-label" style={{ color: "var(--accent)" }}>
          Project Created
        </span>
      </div>

      {/* Status bar */}
      <div
        className="flex items-center gap-2 px-3 py-2.5 rounded-xl mb-4"
        style={{
          background: "var(--surface2)",
          border: "1px solid rgba(156,204,101,0.15)",
        }}
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
        <span className="text-xs font-medium" style={{ color: "var(--text)" }}>
          Brief submitted to team
        </span>
        {createdAt && (
          <span className="ml-auto text-xs flex-shrink-0" style={{ color: "var(--muted)" }}>
            {createdAt}
          </span>
        )}
      </div>

      {/* Field list */}
      <div className="flex-1 overflow-y-auto chat-scroll min-h-0 -mx-1 px-1">
        {orderedEntries.map(([key, value], i) => (
          <div
            key={key}
            className="flex items-baseline gap-2.5 py-2.5"
            style={
              i < orderedEntries.length - 1
                ? { borderBottom: "1px solid var(--border)" }
                : {}
            }
          >
            <span
              className="mono-label flex-shrink-0"
              style={{ color: "var(--muted)", width: "4.25rem" }}
            >
              {FIELD_LABELS[key] || key.replace(/_/g, " ")}
            </span>
            <span className="text-xs leading-relaxed tabular-nums" style={{ color: "var(--text)" }}>
              {value}
            </span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="pt-4 mt-2" style={{ borderTop: "1px solid var(--border)" }}>
        <p className="text-xs leading-relaxed mb-3.5" style={{ color: "var(--muted)", lineHeight: "1.65" }}>
          A PropFlow specialist will review this brief and reach out to you shortly.
        </p>
        <button
          onClick={() => {
            ["propflow_demo_messages","propflow_demo_session_id","propflow_demo_completed",STORAGE_KEY_FIELDS]
              .forEach((k) => localStorage.removeItem(k));
            window.location.reload();
          }}
          className="btn-primary w-full text-xs py-2.5 rounded-xl"
        >
          Start new enquiry →
        </button>
      </div>
    </div>
  );
}

/* ── Main shell ───────────────────────────────────────────────── */

export default function DemoContent() {
  const [briefFields, setBriefFields] = useState<Record<string, string> | null>(null);
  const [createdAt,   setCreatedAt]   = useState("");

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_FIELDS);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed?.fields && typeof parsed.fields === "object") {
          setBriefFields(parsed.fields);
          setCreatedAt(parsed.createdAt || "");
        }
      }
    } catch { /* ignore */ }
  }, []);

  const handleComplete = (fields: Record<string, string>) => {
    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    setBriefFields(fields);
    setCreatedAt(now);
    try {
      localStorage.setItem(STORAGE_KEY_FIELDS, JSON.stringify({ fields, createdAt: now }));
    } catch { /* ignore */ }
  };

  return (
    <div
      className="relative h-screen flex flex-col overflow-hidden"
      style={{ background: "var(--bg)", color: "var(--text)" }}
    >
      {/* Ambient accent glow */}
      <div
        className="accent-glow-blob"
        style={{ top: "-12rem", right: "-10rem", zIndex: 0 }}
      />
      {/* Nav */}
      <nav className="nav-blur flex-shrink-0 px-6 h-14 grid grid-cols-3 items-center relative z-10">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm transition-opacity hover:opacity-70 justify-self-start"
          style={{ color: "var(--muted)" }}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </Link>
        <div className="flex items-center gap-2.5 justify-self-center">
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center"
            style={{ background: "var(--accent)" }}
          >
            <span className="font-black text-[10px]" style={{ color: "#0d110d" }}>P</span>
          </div>
          <span className="font-display font-semibold tracking-tight text-base">PropFlow</span>
        </div>
        <span
          className="mono-label justify-self-end"
          style={{ color: "var(--muted)" }}
        >
          Demo
        </span>
      </nav>

      {/* Body */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden max-w-6xl mx-auto w-full px-4 py-5 gap-4 relative z-10">

        {/* Left panel — transforms on completion */}
        <div className="lg:w-60 flex-shrink-0 overflow-y-auto chat-scroll">
          {briefFields ? (
            <CompletionPanel fields={briefFields} createdAt={createdAt} />
          ) : (
            <InfoPanel />
          )}
        </div>

        {/* Chat panel */}
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div
            className="rounded-2xl flex flex-col overflow-hidden flex-1"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            <ChatWidget onComplete={handleComplete} />
          </div>
        </div>
      </div>
    </div>
  );
}
