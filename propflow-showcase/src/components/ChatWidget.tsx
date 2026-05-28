"use client";

import { useState, useEffect, useRef, useCallback } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const STORAGE_KEY_MESSAGES = "propflow_demo_messages";
const STORAGE_KEY_SESSION  = "propflow_demo_session_id";
const STORAGE_KEY_DONE     = "propflow_demo_completed";

function generateSessionId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function TypingIndicator() {
  return (
    <div className="flex gap-1 items-center px-4 py-3">
      <span className="typing-dot w-1.5 h-1.5 rounded-full inline-block" style={{ background: "var(--accent)" }} />
      <span className="typing-dot w-1.5 h-1.5 rounded-full inline-block" style={{ background: "var(--accent)" }} />
      <span className="typing-dot w-1.5 h-1.5 rounded-full inline-block" style={{ background: "var(--accent)" }} />
    </div>
  );
}

export default function ChatWidget() {
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
      const res  = await fetch("/api/webhook/web", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { reply: string; completed: boolean } = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      if (data.completed) { setCompleted(true); localStorage.setItem(STORAGE_KEY_DONE, "true"); }
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Something went wrong — please try again." }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [loading, sessionId]);

  const startConversation = useCallback(async () => {
    if (started || loading || !sessionId) return;
    setStarted(true);
    setLoading(true);
    try {
      const res  = await fetch("/api/webhook/web", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: "hi" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { reply: string; completed: boolean } = await res.json();
      setMessages([{ role: "assistant", content: data.reply }]);
    } catch {
      setMessages([{ role: "assistant", content: "Hi! I had trouble connecting. Please refresh and try again." }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [started, loading, sessionId]);

  const resetConversation = () => {
    localStorage.removeItem(STORAGE_KEY_MESSAGES);
    localStorage.removeItem(STORAGE_KEY_SESSION);
    localStorage.removeItem(STORAGE_KEY_DONE);
    window.location.reload();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-3.5 flex-shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
            style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
          >
            <span className="font-bold text-sm" style={{ color: "var(--accent)" }}>S</span>
          </div>
          <div>
            <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>Sophia</div>
            <div className="text-xs" style={{ color: "var(--muted)" }}>Interior Design Consultant · PropFlow</div>
          </div>
        </div>
        <button
          onClick={resetConversation}
          className="text-xs px-2.5 py-1 rounded-lg transition-colors"
          style={{ color: "var(--muted)", border: "1px solid var(--border)" }}
          title="Start a new conversation"
        >
          Reset
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto chat-scroll px-4 py-5 space-y-3" style={{ background: "var(--bg)" }}>
        {!started ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-5 px-4">
            <div
              className="w-14 h-14 rounded-2xl flex items-center justify-center"
              style={{ background: "var(--surface2)", border: "1px solid var(--border)" }}
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.5}
                style={{ color: "var(--accent)" }} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div>
              <div className="font-semibold mb-1.5 text-sm" style={{ color: "var(--text)" }}>Talk to Sophia</div>
              <div className="text-sm max-w-xs leading-relaxed" style={{ color: "var(--muted)" }}>
                PropFlow&apos;s AI interior design consultant. She&apos;ll understand your project and
                collect everything your team needs.
              </div>
            </div>
            <button
              onClick={startConversation}
              className="btn-primary text-sm font-semibold px-6 py-2.5 rounded-xl"
            >
              Start conversation
            </button>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === "user" ? "rounded-br-sm" : "rounded-bl-sm"
                  }`}
                  style={
                    msg.role === "user"
                      ? { background: "#2e5018", color: "#cde0b4" }
                      : { background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }
                  }
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div
                  className="rounded-2xl rounded-bl-sm"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                >
                  <TypingIndicator />
                </div>
              </div>
            )}

            {completed && (
              <div className="flex justify-center pt-2">
                <div
                  className="rounded-xl px-4 py-3 text-xs text-center max-w-xs"
                  style={{ background: "var(--surface2)", border: "1px solid rgba(156,204,101,0.18)", color: "var(--muted)" }}
                >
                  Enquiry complete — a PropFlow specialist will follow up shortly.
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      {started && (
        <div
          className="px-4 py-3 flex-shrink-0"
          style={{ borderTop: "1px solid var(--border)", background: "var(--surface)" }}
        >
          <div className="flex gap-2 items-center">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={completed ? "Enquiry complete" : "Type a message…"}
              disabled={loading || completed}
              className="flex-1 text-sm rounded-xl px-4 py-2.5 outline-none disabled:opacity-40 transition-all"
              style={{
                background: "var(--surface2)",
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={loading || !input.trim() || completed}
              className="w-9 h-9 rounded-xl flex items-center justify-center transition-all flex-shrink-0 disabled:opacity-25"
              style={{ background: "var(--accent)" }}
            >
              <svg className="w-4 h-4" fill="none" stroke="#111411" strokeWidth={2.2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
