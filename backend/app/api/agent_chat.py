"""Conversational endpoint for the autonomous negotiation agent."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agent.engine import AgentUnavailable, NegotiationAgent
from app.core.rbac import require_roles
from app.models.models import Role, User
from app.schemas.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: User = Depends(require_roles(Role.CLIENT_PROCUREMENT)),
):
    """One negotiation turn. Session memory is held in Redis, so the buyer can
    resume the same session across requests until the TTL lapses."""
    # Namespace the session under the caller's org so one tenant can never
    # read or hijack another tenant's negotiation memory.
    agent = NegotiationAgent(
        session_id=f"{user.org_id}:{payload.session_id}",
        client_org_id=user.org_id,
    )
    try:
        result = agent.respond(payload.message, sku_context=payload.sku_context)
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return ChatResponse(
        session_id=payload.session_id,
        reply=result["reply"],
        tools_called=result["tools_called"],
        escalation_ticket=result["escalation_ticket"],
    )


@router.delete("/chat/{session_id}", status_code=204)
def reset_session(
    session_id: str,
    user: User = Depends(require_roles(Role.CLIENT_PROCUREMENT)),
):
    NegotiationAgent(session_id=f"{user.org_id}:{session_id}").clear_session()
