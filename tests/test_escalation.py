"""Tests for EscalationDecision logic â€” no DB/Redis required."""
import pytest
from backend.agents.escalation_agent import EscalationDecision
from backend.schemas import IntentResult


def _state(tier="free", turns=0, kb_conf=0.7, **ir_kwargs):
    ir_defaults = dict(intent="general_inquiry", confidence=0.8, sentiment_score=0.0,
                       sentiment_label="NEUTRAL", urgency="LOW")
    ir_defaults.update(ir_kwargs)
    return {
        "user_tier": tier, "total_turns": turns, "kb_confidence": kb_conf,
        "intent_result": IntentResult(**ir_defaults),
        "conversation_id": "test-conv", "user_id": "test-user",
        "message": "test",
    }


def test_frustrated_triggers_escalation():
    escalate, reason, trigger = EscalationDecision(_state(sentiment_label="FRUSTRATED")).should_escalate
    assert escalate is True
    assert trigger == "SENTIMENT"


def test_enterprise_always_escalates():
    escalate, _, trigger = EscalationDecision(_state(tier="enterprise")).should_escalate
    assert escalate is True
    assert trigger == "ENTERPRISE_TIER"


def test_high_kb_confidence_informational_no_escalation():
    escalate, _, _ = EscalationDecision(_state(kb_conf=0.92, intent="general_inquiry")).should_escalate
    assert escalate is False


def test_stuck_loop_triggers_escalation():
    escalate, _, trigger = EscalationDecision(_state(turns=10)).should_escalate
    assert escalate is True
    assert trigger == "REPEAT_CONTACT"


def test_explicit_request_escalates():
    escalate, _, trigger = EscalationDecision(_state(intent="escalation_request")).should_escalate
    assert escalate is True
    assert trigger == "EXPLICIT_REQUEST"


def test_critical_priority_for_enterprise():
    d = EscalationDecision(_state(tier="enterprise"))
    assert d.priority == "CRITICAL"


def test_low_priority_for_low_urgency():
    d = EscalationDecision(_state(urgency="LOW", sentiment_label="POSITIVE",
                                  escalation_recommended=True))
    assert d.priority == "LOW"
