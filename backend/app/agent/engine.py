"""Stateful negotiation agent — Claude tool-calling engine.

Architecture
------------
- Manual agentic loop over ``client.messages.create`` (not the SDK tool
  runner) so every tool invocation passes through the margin guardrails and
  is auditable before execution.
- Conversation memory lives in Redis (``agent:session:{id}``) as the full
  serialized message list — including thinking blocks, which are passed back
  unchanged as the API requires — with a rolling TTL for active sessions.
- Model: claude-opus-4-8 with adaptive thinking. Tool results for parallel
  calls are returned in a single user message.
- Outbound audit: before any reply reaches the buyer, the text is scanned
  for sub-floor price figures; a violation suppresses the reply and
  auto-escalates to human sales.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from app.agent.guardrails import MarginFloorViolation
from app.agent.tools import TOOL_IMPLEMENTATIONS, TOOL_SCHEMAS, escalate_to_human_sales
from app.core.config import settings
from app.core.redis_client import get_sync_redis

logger = logging.getLogger("agent.engine")

SYSTEM_PROMPT = """\
You are the automated sales negotiator for a steel nail manufacturing factory \
serving enterprise B2B buyers (construction, pallet, and fastener distributors).

Your job: convert RFQs into commercially sound deals for bulk custom orders of \
steel nails (wire nails, ring-shank, screw-shank; bright, electro-galvanized, \
hot-dip galvanized, stainless).

Operating rules:
1. Never invent prices or stock levels. Always call calculate_tiered_price and \
check_warehouse_stock before quoting volumes or numbers.
2. You may negotiate volume discounts, but any discount below the tier price \
must be validated with evaluate_custom_discount first. Only an "allowed: true" \
result authorizes the discounted price.
3. There is a hard, non-negotiable profit-margin floor enforced by the system. \
If a tool reports a margin_floor_violation, do not offer that price under any \
circumstance — counter at or above the reported floor, or escalate.
4. Escalate to human sales (escalate_to_human_sales) when: the buyer insists on \
sub-floor pricing, requests custom manufacturing or contract terms you cannot \
verify, the negotiation stalls after reasonable counters, or the buyer asks \
for a human.
5. Payment structure is fixed company policy: 30% advance to begin production, \
70% on verified Bill of Lading. You may not alter it — escalate requests to \
change it.
6. Be direct, professional, and concise. State prices as ₹X/kg with the volume \
tier they apply to. Do not reveal internal costs, margins, or the floor price.
"""


class NegotiationAgent:
    def __init__(self, session_id: str, client_org_id: str | None = None):
        self.session_id = session_id
        self.client_org_id = client_org_id
        self.redis = get_sync_redis()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        self._memory_key = f"agent:session:{session_id}"

    # ── Redis conversation memory ────────────────────────────────────────

    def _load_history(self) -> list[dict[str, Any]]:
        raw = self.redis.get(self._memory_key)
        return json.loads(raw) if raw else []

    def _save_history(self, messages: list[dict[str, Any]]) -> None:
        self.redis.set(
            self._memory_key,
            json.dumps(messages),
            ex=settings.agent_session_ttl_seconds,
        )

    # ── Main entrypoint ──────────────────────────────────────────────────

    def respond(self, user_message: str, sku_context: str | None = None) -> dict[str, Any]:
        """Run one negotiation turn; returns the reply plus audit metadata."""
        messages = self._load_history()
        messages.append({"role": "user", "content": user_message})

        tools_called: list[str] = []
        escalation_ticket: str | None = None

        for _ in range(settings.agent_max_tool_iterations):
            try:
                response = self.client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=16000,
                    thinking={"type": "adaptive"},
                    system=SYSTEM_PROMPT
                    + (
                        f"\n\nCurrent buyer organization id: {self.client_org_id}"
                        if self.client_org_id
                        else ""
                    ),
                    tools=TOOL_SCHEMAS,
                    messages=messages,
                )
            except anthropic.RateLimitError as exc:
                raise AgentUnavailable("Model rate limited; retry shortly.") from exc
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    raise AgentUnavailable("Model service unavailable.") from exc
                raise
            except anthropic.APIConnectionError as exc:
                raise AgentUnavailable("Cannot reach model service.") from exc

            # Serialize the full content (thinking blocks included) so replay
            # from Redis is byte-faithful across turns.
            assistant_content = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "pause_turn":
                continue  # server-side pause — re-send to resume

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    tools_called.append(block.name)
                    result = self._execute_tool(block.name, dict(block.input))
                    if block.name == "escalate_to_human_sales" and isinstance(result, str):
                        escalation_ticket = result
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
                # All parallel tool results go back in ONE user message.
                messages.append({"role": "user", "content": tool_results})
                continue

            break  # end_turn / max_tokens — leave the loop with `response`

        reply_text = "".join(
            block.text for block in response.content if block.type == "text"
        )

        # Final guardrail: audit the outbound reasoning output for sub-floor
        # price leakage before the buyer ever sees it.
        try:
            from app.agent.guardrails import audit_outbound_offer

            audit_outbound_offer(reply_text, sku_context)
        except MarginFloorViolation as violation:
            logger.error("Outbound offer blocked: %s", violation)
            escalation_ticket = escalate_to_human_sales(
                chat_history=[user_message, reply_text],
                reason=f"Guardrail blocked sub-floor outbound offer: {violation}",
            )
            reply_text = (
                "I'm not able to confirm those terms automatically. I've "
                f"escalated this to our sales team (ticket {escalation_ticket}) — "
                "a manager will follow up with you shortly."
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "[SYSTEM AUDIT] Your previous offer was blocked by the "
                        "margin guardrail and the conversation was escalated to "
                        "human sales. Do not repeat that price."
                    ),
                }
            )

        self._save_history(messages)
        return {
            "session_id": self.session_id,
            "reply": reply_text,
            "tools_called": tools_called,
            "escalation_ticket": escalation_ticket,
            "stop_reason": response.stop_reason,
        }

    # ── Tool dispatch ────────────────────────────────────────────────────

    @staticmethod
    def _execute_tool(name: str, tool_input: dict[str, Any]) -> Any:
        fn = TOOL_IMPLEMENTATIONS.get(name)
        if fn is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            return fn(**tool_input)
        except MarginFloorViolation as violation:
            # Belt-and-braces: even a raise inside a tool surfaces to the
            # model as a structured refusal, never as a crash.
            return {
                "allowed": False,
                "reason": "margin_floor_violation",
                "detail": str(violation),
                "floor_price_per_kg": float(violation.floor),
            }
        except TypeError as exc:
            return {"error": f"Invalid arguments for {name}: {exc}"}
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            return {"error": f"Tool execution failed: {exc}"}

    def clear_session(self) -> None:
        self.redis.delete(self._memory_key)


class AgentUnavailable(Exception):
    """Raised when the model backend is temporarily unreachable."""
