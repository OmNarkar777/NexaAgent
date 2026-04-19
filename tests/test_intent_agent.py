"""Tests for intent classification logic."""
import pytest
from backend.agents.intent_agent import _apply_overrides
from backend.schemas import IntentResult


def _make_intent(**kwargs) -> IntentResult:
    defaults = dict(intent="general_inquiry", confidence=0.8, sentiment_score=0.0,
                    sentiment_label="NEUTRAL", urgency="LOW")
    defaults.update(kwargs)
    return IntentResult(**defaults)


def test_frustration_marker_overrides_sentiment():
    result = _apply_overrides(_make_intent(), "This is absolutely ridiculous!")
    assert result.sentiment_label == "FRUSTRATED"
    assert result.escalation_recommended is True
    assert result.sentiment_score <= -0.85


def test_urgency_marker_sets_high():
    result = _apply_overrides(_make_intent(), "I need help URGENT my account is broken")
    assert result.urgency == "HIGH"
    assert result.escalation_recommended is True


def test_escalation_request_always_escalates():
    result = _apply_overrides(_make_intent(intent="escalation_request"), "I want to speak to a human")
    assert result.escalation_recommended is True
    assert result.urgency == "HIGH"


def test_no_override_on_positive_message():
    result = _apply_overrides(_make_intent(sentiment_label="POSITIVE", sentiment_score=0.9), "Thanks, this is great!")
    assert result.sentiment_label == "POSITIVE"
    assert result.escalation_recommended is False
