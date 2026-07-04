"""RFQ state machine — illegal transitions must never be permitted, and the
terminal states (Fulfilled, Rejected) must have no way out.
"""
from app.models.models import RFQ, RFQ_TRANSITIONS, RFQStatus


def test_every_status_has_a_transition_table_entry():
    for status in RFQStatus:
        assert status in RFQ_TRANSITIONS


def test_submitted_can_move_to_negotiating_review_or_rejected():
    rfq = RFQ(status=RFQStatus.RFQ_SUBMITTED)
    assert rfq.can_transition_to(RFQStatus.AI_NEGOTIATING)
    assert rfq.can_transition_to(RFQStatus.SALES_REVIEW)
    assert rfq.can_transition_to(RFQStatus.REJECTED)
    assert not rfq.can_transition_to(RFQStatus.APPROVED)
    assert not rfq.can_transition_to(RFQStatus.FULFILLED)


def test_approved_can_only_advance_to_contract_generated():
    rfq = RFQ(status=RFQStatus.APPROVED)
    assert rfq.can_transition_to(RFQStatus.CONTRACT_GENERATED)
    assert not rfq.can_transition_to(RFQStatus.RFQ_SUBMITTED)
    assert not rfq.can_transition_to(RFQStatus.REJECTED)


def test_contract_generated_can_only_advance_to_fulfilled():
    rfq = RFQ(status=RFQStatus.CONTRACT_GENERATED)
    assert rfq.can_transition_to(RFQStatus.FULFILLED)
    assert not rfq.can_transition_to(RFQStatus.APPROVED)


def test_terminal_states_have_no_outbound_transitions():
    for terminal in (RFQStatus.FULFILLED, RFQStatus.REJECTED):
        rfq = RFQ(status=terminal)
        for candidate in RFQStatus:
            assert not rfq.can_transition_to(candidate), f"{terminal} -> {candidate} should be illegal"


def test_sales_review_can_bounce_back_to_ai_negotiating():
    """Sales can kick a deal back to the agent for further negotiation."""
    rfq = RFQ(status=RFQStatus.SALES_REVIEW)
    assert rfq.can_transition_to(RFQStatus.AI_NEGOTIATING)
    assert rfq.can_transition_to(RFQStatus.APPROVED)
    assert rfq.can_transition_to(RFQStatus.REJECTED)
