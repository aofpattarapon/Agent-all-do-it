"""Quality-gate handoff contracts between workflow steps.

A handoff contract asserts that the output of an upstream step contains certain
required concepts (keywords) before a downstream step is allowed to consume it.
``check_handoff`` performs a case-insensitive substring check and reports any
missing concepts. Optionally invoked by the run executor.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HandoffContract:
    name: str
    source_step_kinds: tuple[str, ...]
    required_concepts: tuple[str, ...]  # keywords that must appear in upstream output


def check_handoff(upstream_output: str, contract: HandoffContract) -> tuple[bool, list[str]]:
    """Check whether ``upstream_output`` satisfies a handoff contract.

    Args:
        upstream_output: The text produced by the upstream step.
        contract: The contract to validate against.

    Returns:
        A tuple ``(passed, missing_concepts)``. ``passed`` is True when every
        required concept appears (case-insensitive substring) in the output.
    """
    haystack = (upstream_output or "").lower()
    missing = [concept for concept in contract.required_concepts if concept.lower() not in haystack]
    return (not missing, missing)


DEFAULT_CONTRACTS: tuple[HandoffContract, ...] = (
    HandoffContract(
        name="dev_to_qa",
        source_step_kinds=("dev", "implementation", "code"),
        required_concepts=("test", "build"),
    ),
    HandoffContract(
        name="analysis_to_decision",
        source_step_kinds=("analysis", "research"),
        required_concepts=("recommendation",),
    ),
    HandoffContract(
        name="design_to_dev",
        source_step_kinds=("design", "spec"),
        required_concepts=("requirement", "interface"),
    ),
    HandoffContract(
        name="qa_to_release",
        source_step_kinds=("qa", "review", "test"),
        required_concepts=("passed", "result"),
    ),
)


def contracts_for_step_kind(step_kind: str) -> list[HandoffContract]:
    """Return the default contracts whose source kinds include ``step_kind``."""
    return [c for c in DEFAULT_CONTRACTS if step_kind in c.source_step_kinds]
