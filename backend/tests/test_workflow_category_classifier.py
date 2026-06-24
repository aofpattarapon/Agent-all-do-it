"""Unit tests for workflow_category_classifier.classify_workflow_category."""

from dataclasses import dataclass

import pytest

from app.services.workflow_category_classifier import classify_workflow_category


@dataclass
class _FakeWorkflow:
    name: str
    definition_json: dict


def test_definition_category_wins_over_name():
    wf = _FakeWorkflow(name="Trade Foo", definition_json={"category": "research"})
    assert classify_workflow_category(wf) == "research"


def test_definition_category_only_works_for_known_values():
    wf = _FakeWorkflow(name="Crypto Trade Pipeline", definition_json={"category": "not_a_category"})
    assert classify_workflow_category(wf) == "trade"


def test_trade_pipeline_by_name():
    assert classify_workflow_category(workflow_name="Crypto Trade Pipeline — Proposal to Execution") == "trade"
    assert classify_workflow_category(workflow_name="Crypto Trade Pipeline — Auto 30m") == "trade"


def test_market_watch_by_name():
    assert classify_workflow_category(workflow_name="Crypto Market Watch — Continuous Research") == "research"


def test_position_monitor_by_name():
    assert classify_workflow_category(workflow_name="Crypto Position Monitor — Active Positions") == "monitor"


def test_screener_by_name():
    assert classify_workflow_category(workflow_name="Crypto Trade Screener — Primary 30m") == "screener"


def test_unknown_fallback():
    assert classify_workflow_category(workflow_name="Foo Bar") == "unknown"


def test_empty_inputs_are_unknown():
    assert classify_workflow_category() == "unknown"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Crypto Trade Pipeline — Proposal to Execution", "trade"),
        ("Crypto Trade Pipeline — Auto 30m", "trade"),
        ("Crypto Trade Pipeline — Auto 15m", "trade"),
        ("Crypto Market Watch — Continuous Research", "research"),
        ("Crypto Position Monitor — Active Positions", "monitor"),
        ("Crypto Trade Screener — Primary 30m", "screener"),
        ("Crypto Trade Screener — Secondary 15m", "screener"),
    ],
)
def test_all_crypto_workflow_names(name, expected):
    assert classify_workflow_category(workflow_name=name) == expected
