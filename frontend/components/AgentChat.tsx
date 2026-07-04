"use client";

import { useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth-context";
import { chatWithAgent, resetAgentSession } from "@/lib/api";
import { ui } from "@/lib/ui";

interface ChatTurn {
  role: "user" | "agent";
  text: string;
  toolsCalled?: string[];
}

export function AgentChat({ sessionId, skuContext }: { sessionId: string; skuContext?: string }) {
  const { accessToken } = useAuth();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [escalationTicket, setEscalationTicket] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!accessToken || !input.trim() || sending) return;
    const message = input.trim();
    setInput("");
    setError(null);
    setTurns((t) => [...t, { role: "user", text: message }]);
    setSending(true);
    try {
      const res = await chatWithAgent(accessToken, sessionId, message, skuContext);
      setTurns((t) => [...t, { role: "agent", text: res.reply, toolsCalled: res.tools_called }]);
      if (res.escalation_ticket) setEscalationTicket(res.escalation_ticket);
      setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The negotiation agent is unavailable.");
    } finally {
      setSending(false);
    }
  }

  async function onReset() {
    if (!accessToken) return;
    await resetAgentSession(accessToken, sessionId);
    setTurns([]);
    setEscalationTicket(null);
  }

  return (
    <div style={ui.card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
        <h2 style={{ fontSize: "1.05rem", margin: 0 }}>Negotiate with the sales agent</h2>
        <button onClick={onReset} style={{ ...ui.buttonSecondary, padding: "0.3rem 0.6rem", fontSize: 12 }}>
          Reset conversation
        </button>
      </div>

      {escalationTicket && (
        <div style={{ ...ui.errorBox, background: "#fef3c7", color: "#92400e" }}>
          Escalated to human sales — ticket <strong>{escalationTicket}</strong>. A sales manager will
          follow up shortly.
        </div>
      )}
      {error && <div style={ui.errorBox}>{error}</div>}

      <div
        ref={scrollRef}
        style={{
          maxHeight: 340,
          overflowY: "auto",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          padding: "0.75rem",
          marginBottom: "0.75rem",
          background: "#fafaf9",
        }}
      >
        {turns.length === 0 && (
          <p style={{ fontSize: 13, color: "#9ca3af", margin: 0 }}>
            Ask about volume pricing, delivery timelines, or request a discount — the agent will check
            live stock and pricing tiers before responding.
          </p>
        )}
        {turns.map((turn, i) => (
          <div key={i} style={{ marginBottom: "0.6rem", textAlign: turn.role === "user" ? "right" : "left" }}>
            <div
              style={{
                display: "inline-block",
                maxWidth: "80%",
                padding: "0.5rem 0.75rem",
                borderRadius: 10,
                fontSize: 14,
                lineHeight: 1.5,
                background: turn.role === "user" ? "#b45309" : "#e5e7eb",
                color: turn.role === "user" ? "#fff" : "#1f2937",
                textAlign: "left",
              }}
            >
              {turn.text}
              {turn.toolsCalled && turn.toolsCalled.length > 0 && (
                <div style={{ marginTop: "0.35rem", fontSize: 10, opacity: 0.7 }}>
                  tools: {turn.toolsCalled.join(", ")}
                </div>
              )}
            </div>
          </div>
        ))}
        {sending && <p style={{ fontSize: 13, color: "#9ca3af" }}>Agent is thinking…</p>}
      </div>

      <form onSubmit={onSubmit} style={{ display: "flex", gap: "0.5rem" }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. Can you do ₹88/kg for 15 tons of hot-dip galvanized ring shank?"
          style={{ ...ui.input, marginBottom: 0, flex: 1 }}
        />
        <button type="submit" disabled={sending} style={ui.button}>
          Send
        </button>
      </form>
    </div>
  );
}
