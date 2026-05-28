"use client";

import { useState, useEffect, useRef, useCallback } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const STORAGE_KEY_MESSAGES = "propflow_demo_messages";
const STORAGE_KEY_SESSION = "propflow_demo_session_id";
const STORAGE_KEY_DONE = "propflow_demo_completed";

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
      <span className="typing-dot w-2 h-2 rounded-full bg-green-400 inline-block" />
      <span className="typing-dot w-2 h-2 rounded-full bg-green-400 inline-block" />
      <span className="typing-dot w-2 h-2 rounded-full bg-green-400 inline-block" />
    </div>
  );
}

export default function ChatWidget() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [started, setStarted] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Hydrate from localStorage on mount
  useEffect(() => {
    const storedSession = localStorage.getItem(STORAGE_KEY_SESSION);
    const storedMessages = localStorage.getItem(STORAGE_KEY_MESSAGES);
    const storedDone = localStorage.getItem(STORAGE_KEY_DONE);

    const sid = storedSession || generateSessionId();
    if (!storedSession) localStorage.setItem(STORAGE_KEY_SESSION, sid);
    setSessionId(sid);

    if (storedMessages) {
      try {
        const parsed: Message[] = JSON.parse(storedMessages);
        if (parsed.length > 0) {
          setMessages(parsed);
          setStarted(true);
        }
      } catch {
        // ignore parse errors
      }
    }

    if (storedDone === "true") setCompleted(true);
  }, []);

  // Persist messages whenever they change
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(messages));
    }
  }, [messages]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || loading || !sessionId) return;

      const userMsg: Message = { role: "user", content: text.trim() };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setLoading(true);

      try {
        const res = await fetch("/api/webhook/web", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message: text.trim() }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: { reply: string; completed: boolean } = await res.json();

        const assistantMsg: Message = { role: "assistant", content: data.reply };
        setMessages((prev) => [...prev, assistantMsg]);

        if (data.completed) {
          setCompleted(true);
          localStorage.setItem(STORAGE_KEY_DONE, "true");
        }
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Something went wrong — please try again in a moment.",
          },
        ]);
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [loading, sessionId]
  );

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
        {
          role: "assistant",
          content: "Hi! I had trouble connecting. Please refresh and try again.",
        },
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
    window.location.reload();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Chat header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 bg-white">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-green-100 rounded-full flex items-center justify-center">
            <span className="text-green-700 font-bold text-sm">S</span>
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-900">Sophia</div>
            <div className="text-xs text-gray-400">Interior Design Consultant · PropFlow</div>
          </div>
        </div>
        <button
          onClick={resetConversation}
          className="text-xs text-gray-400 hover:text-gray-600 transition-colors px-2 py-1 rounded-md hover:bg-gray-100"
          title="Start a new conversation"
        >
          Reset
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto chat-scroll px-4 py-5 space-y-3 bg-gray-50">
        {!started ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4">
            <div className="w-16 h-16 bg-green-100 rounded-2xl flex items-center justify-center">
              <span className="text-3xl">🏠</span>
            </div>
            <div>
              <div className="font-semibold text-gray-800 mb-1">Talk to Sophia</div>
              <div className="text-sm text-gray-400 max-w-xs">
                PropFlow&apos;s AI interior design consultant. She&apos;ll understand your project and
                collect everything your team needs.
              </div>
            </div>
            <button
              onClick={startConversation}
              className="bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-6 py-2.5 rounded-xl transition-colors"
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
                <div
                  className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-green-600 text-white rounded-br-sm"
                      : "bg-white text-gray-800 border border-gray-100 shadow-sm rounded-bl-sm"
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-bl-sm">
                  <TypingIndicator />
                </div>
              </div>
            )}

            {completed && (
              <div className="flex justify-center pt-2">
                <div className="bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-xs text-green-700 text-center max-w-xs">
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
        <div className="px-4 py-3 border-t border-gray-100 bg-white">
          <div className="flex gap-2 items-center">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={completed ? "Enquiry complete" : "Type a message…"}
              disabled={loading || completed}
              className="flex-1 text-sm bg-gray-100 rounded-xl px-4 py-2.5 outline-none focus:ring-2 focus:ring-green-300 disabled:opacity-50 transition-all placeholder:text-gray-400"
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={loading || !input.trim() || completed}
              className="w-9 h-9 bg-green-600 hover:bg-green-700 disabled:bg-gray-200 text-white rounded-xl flex items-center justify-center transition-colors flex-shrink-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
