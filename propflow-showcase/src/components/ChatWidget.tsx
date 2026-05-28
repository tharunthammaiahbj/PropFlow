"use client";

import { useState, useEffect, useRef, useCallback } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const STORAGE_KEY_MESSAGES = "propflow_demo_messages";
const STORAGE_KEY_SESSION  = "propflow_demo_session_id";
const STORAGE_KEY_DONE     = "propflow_demo_completed";
const STORAGE_KEY_FIELDS   = "propflow_demo_fields";

function generateSessionId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function TypingIndicator() {
  return (
    <div className="flex gap-1.5 items-center px-4 py-3.5">
      <span className="typing-dot w-1.5 h-1.5 rounded-full inline-block" style={{ background: "var(--accent)", opacity: 0.7 }} />
      <span className="typing-dot w-1.5 h-1.5 rounded-full inline-block" style={{ background: "var(--accent)", opacity: 0.7 }} />
      <span className="typing-dot w-1.5 h-1.5 rounded-full inline-block" style={{ background: "var(--accent)", opacity: 0.7 }} />
    </div>
  );
}

interface ChatWidgetProps {
  onComplete?: (fields: Record<string, string>) => void;
}

export default function ChatWidget({ onComplete }: ChatWidgetProps) {
  const [messages,  setMessages]  = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [input,     setInput]     = useState("");
  const [loading,   setLoading]   = useState(false);
  const [completed, setCompleted] = useState(false);
  const [started,   setStarted]   = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const storedSession  = localStorage.getItem(STORAGE_KEY_SESSION);
    const storedMessages = localStorage.getItem(STORAGE_KEY_MESSAGES);
    const storedDone     = localStorage.getItem(STORAGE_KEY_DONE);

    const sid = storedSession || generateSessionId();
    if (!storedSession) localStorage.setItem(STORAGE_KEY_SESSION, sid);
    setSessionId(sid);

    if (storedMessages) {
      try {
        const parsed: Message[] = JSON.parse(storedMessages);
        if (parsed.length > 0) { setMessages(parsed); setStarted(true); }
      } catch { /* ignore */ }
    }
    if (storedDone === "true") setCompleted(true);
  }, []);

  useEffect(() => {
    if (messages.length > 0) localStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading || !sessionId) return;
    setMessages((prev) => [...prev, { role: "user", content: text.trim() }]);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch("/api/webhook/web", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { reply: string; completed: boolean; fields?: Record<string, string> } = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      if (data.completed) {
        setCompleted(true);
        localStorage.setItem(STORAGE_KEY_DONE, "true");
        if (data.fields && onComplete) {
          onComplete(data.fields);
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong — please try again." },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [loading, sessionId, onComplete]);

  const startConversation = useCallback(async () => {
    if (started || loading || !sessionId) return;
    setStarted(true);
    setLoading(true);
    try {
      const res = await fetch("/api/webhook/web", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: "hi" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { reply: string; completed: boolean } = await res.json();
      setMessages([{ role: "assistant", content: data.reply }]);
    } catch {
      setMessages([
        { role: "assistant", content: "Hi! I had trouble connecting. Please refresh and try again." },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [started, loading, sessionId]);

  const resetConversation = () => {
    localStorage.removeItem(STORAGE_KEY_MESSAGES);
    localStorage.removeItem(STORAGE_KEY_SESSION);
    localStorage.removeItem(STORAGE_KEY_DONE);
    localStorage.removeItem(STORAGE_KEY_FIELDS);
    window.location.reload();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Header ─────────────────────────────── */}
      <div
        className="flex items-center justify-between px-5 py-4 flex-shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
            style={{
              background: "var(--surface2)",
              outline: "1.5px solid rgba(156,204,101,0.22)",
              outlineOffset: "2px",
            }}
          >
            <span className="font-display font-bold text-sm" style={{ color: "var(--accent)" }}>J</span>
          </div>
          <div>
            <div className="text-sm font-semibold font-display" style={{ color: "var(--text)" }}>
              Jessica
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: "var(--accent)", opacity: 0.8 }} />
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                AI Consultant · PropFlow
              </span>
            </div>
          </div>
        </div>
        <button
          onClick={resetConversation}
          className="text-xs transition-opacity hover:opacity-60"
          style={{ color: "var(--muted)" }}
          title="Start a new conversation"
        >
          Reset
        </button>
      </div>

      {/* ── Messages ───────────────────────────── */}
      <div
        className="flex-1 overflow-y-auto chat-scroll px-5 py-5 space-y-4"
        style={{ background: "var(--bg)" }}
      >
        {!started ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-5 px-4">
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center"
              style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
            >
              <svg
                className="w-5 h-5"
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
            <div>
              <div className="font-display font-bold text-base mb-1.5" style={{ color: "var(--text)" }}>
                Talk to Jessica
              </div>
              <div className="text-sm leading-relaxed max-w-[260px]" style={{ color: "var(--muted)" }}>
                PropFlow&apos;s AI consultant. She&apos;ll collect everything
                your team needs through natural conversation.
              </div>
            </div>
            <button
              onClick={startConversation}
              className="btn-primary text-sm px-6 py-2.5 rounded-xl"
            >
              Start conversation
            </button>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role === "user" ? (
                  <div
                    className="text-sm leading-relaxed rounded-2xl rounded-br-md px-4 py-2.5"
                    style={{
                      background: "#253f14",
                      color: "#c2dda6",
                      maxWidth: "75%",
                      width: "fit-content",
                    }}
                  >
                    {msg.content}
                  </div>
                ) : (
                  <div
                    className="text-sm leading-relaxed rounded-2xl rounded-bl-md px-4 py-3"
                    style={{
                      background: "var(--surface)",
                      color: "var(--text)",
                      maxWidth: "82%",
                    }}
                  >
                    {msg.content}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-md" style={{ background: "var(--surface)" }}>
                  <TypingIndicator />
                </div>
              </div>
            )}

            {completed && (
              <div className="flex justify-center pt-3">
                <div
                  className="rounded-xl px-4 py-3 text-xs text-center"
                  style={{
                    background: "var(--surface2)",
                    border: "1px solid rgba(156,204,101,0.18)",
                    color: "var(--muted)",
                    maxWidth: "280px",
                  }}
                >
                  Enquiry complete — your project brief has been created.
                  Check the panel on the left.
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input ──────────────────────────────── */}
      {started && (
        <div
          className="px-4 py-3.5 flex-shrink-0"
          style={{
            borderTop: "1px solid rgba(31,45,31,0.6)",
            background: "var(--surface)",
          }}
        >
          <div className="flex gap-2.5 items-center">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={completed ? "Enquiry complete — see brief on the left" : "Type a message…"}
              disabled={completed}
              className="flex-1 text-sm rounded-2xl px-4 py-2.5 outline-none disabled:opacity-40 transition-all"
              style={{
                background: "var(--bg)",
                border: "1px solid var(--border)",
                color: "var(--text)",
                fontFamily: "var(--font-sans), system-ui, sans-serif",
              }}
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={loading || !input.trim() || completed}
              className="w-9 h-9 rounded-full flex items-center justify-center transition-all flex-shrink-0 disabled:opacity-25 hover:scale-105"
              style={{ background: "var(--accent)" }}
            >
              <svg
                className="w-4 h-4"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#0d110d"
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
