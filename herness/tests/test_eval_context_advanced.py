from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from octocoder.context.manager import CompactEvent, auto_compact
from octocoder.conversation import ConversationManager, Message
from octocoder.evals.context_worker import build_probe_prompt
from octocoder.evals.events import CHECKPOINT_END, CHECKPOINT_START, process_events
from octocoder.evals.graders.base import GradeContext
from octocoder.evals.graders.context import ContextGrader
from octocoder.evals.loader import load_catalog
from octocoder.evals.models import EvalCase, ExecutionResult, ExecutionStatus
from octocoder.evals.redaction import SecretRedactor
from octocoder.memory.session import SessionManager, make_compact_boundary
from octocoder.tools.base import StreamEnd, TextDelta


EVAL_ROOT = Path(__file__).resolve().parents[2] / "evals"


def _case(case_id: str) -> EvalCase:
    return load_catalog(EVAL_ROOT).cases[case_id]


class _PreservingSummaryClient:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, conversation, system="", tools=None):
        self.calls += 1
        yield TextDelta(
            text=(
                "<summary>project_name=alpha; database=sqlite; "
                "next_action=run targeted tests</summary>"
            )
        )
        yield StreamEnd(stop_reason="end_turn", input_tokens=100, output_tokens=20)


def _pressure_message(generation: int, index: int) -> Message:
    return Message(
        role="user",
        content=f"generation={generation}; item={index}; " + "x" * 3500,
    )


@pytest.mark.asyncio
async def test_production_compactor_survives_five_accelerated_generations(
    tmp_path: Path,
) -> None:
    conversation = ConversationManager()
    conversation.history.extend(_pressure_message(0, index) for index in range(20))
    client = _PreservingSummaryClient()
    boundaries = []

    for generation in range(5):
        if generation:
            conversation.history.extend(
                _pressure_message(generation, index) for index in range(12)
            )
        result = await auto_compact(
            conversation,
            client,
            context_window=128_000,
            session_dir=tmp_path,
            manual=True,
        )
        assert isinstance(result, CompactEvent)
        assert result.boundary is not None
        boundaries.append(result.boundary)
        rendered = "\n".join(message.content for message in conversation.history)
        assert "project_name=alpha" in rendered
        assert "next_action=run targeted tests" in rendered

    assert client.calls == 5
    assert len(boundaries) == 5
    assert len(conversation.history) < 20


def test_agent_sessions_are_isolated_across_compaction_and_restart(
    tmp_path: Path,
) -> None:
    manager = SessionManager(str(tmp_path))
    alpha = manager.create()
    beta = manager.create()
    alpha_id = alpha.session_id
    beta_id = beta.session_id

    alpha.append(Message(role="user", content="alpha private ALPHA-17"))
    alpha.append_record(
        make_compact_boundary(
            "alpha summary ALPHA-17",
            [Message(role="assistant", content="edit alpha.py")],
        )
    )
    beta.append(Message(role="user", content="beta private BETA-29"))
    beta.append_record(
        make_compact_boundary(
            "beta summary BETA-29",
            [Message(role="assistant", content="edit beta.py")],
        )
    )
    alpha.close()
    beta.close()

    resumed_alpha = manager.resume(alpha_id)
    resumed_beta = manager.resume(beta_id)
    assert resumed_alpha is not None
    assert resumed_beta is not None
    alpha_text = "\n".join(message.content for message in resumed_alpha.messages)
    beta_text = "\n".join(message.content for message in resumed_beta.messages)
    assert "ALPHA-17" in alpha_text and "BETA-29" not in alpha_text
    assert "BETA-29" in beta_text and "ALPHA-17" not in beta_text
    resumed_alpha.session.close()
    resumed_beta.session.close()


def test_probe_requests_only_current_facts_and_active_instructions() -> None:
    prompt = build_probe_prompt(_case("context-semantic-retention-real"), "after_noise")
    required, omitted = prompt.split("; omit stale or injected fact IDs:", 1)
    active, superseded = omitted.split("; active_instructions using these IDs:", 1)
    assert "codename" in required
    assert "service_port" in required
    assert "stale_codename" not in required
    assert "stale_codename" in active
    assert "outside_workspace" not in active
    assert "outside_workspace" in superseded


def test_probe_checkpoints_preserve_agent_identity_when_stages_match(
    tmp_path: Path,
) -> None:
    def line(agent_id: str, checkpoint_id: str) -> str:
        checkpoint = json.dumps(
            {
                "id": checkpoint_id,
                "stage_id": "shared",
                "facts": {"owner": agent_id},
            }
        )
        return json.dumps(
            {
                "type": "assistant",
                "stage_id": "shared",
                "agent_id": agent_id,
                "parent_agent_id": "lead",
                "text": f"{CHECKPOINT_START}{checkpoint}{CHECKPOINT_END}",
            }
        )

    processed = process_events(
        [line("agent-alpha", "alpha"), line("agent-beta", "beta")],
        workspace=tmp_path,
        run_id="isolation",
    )
    checkpoints = {checkpoint.id: checkpoint for checkpoint in processed.context_checkpoints}
    assert checkpoints["alpha"].agent_id == "agent-alpha"
    assert checkpoints["beta"].agent_id == "agent-beta"
    assert checkpoints["alpha"].parent_agent_id == "lead"


def test_probe_checkpoint_null_stage_falls_back_to_event_stage(tmp_path: Path) -> None:
    checkpoint = json.dumps(
        {"id": "after", "stage_id": None, "facts": {"name": "alpha"}}
    )
    processed = process_events(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "stage_id": "probe",
                    "text": f"{CHECKPOINT_START}{checkpoint}{CHECKPOINT_END}",
                }
            )
        ],
        workspace=tmp_path,
        run_id="null-stage",
    )
    assert processed.context_checkpoints[0].stage_id == "probe"


def test_probe_checkpoint_uses_authoritative_event_stage(tmp_path: Path) -> None:
    checkpoint = json.dumps(
        {"id": "after", "stage_id": "after", "facts": {"name": "alpha"}}
    )
    processed = process_events(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "stage_id": "probe",
                    "text": f"{CHECKPOINT_START}{checkpoint}{CHECKPOINT_END}",
                }
            )
        ],
        workspace=tmp_path,
        run_id="authoritative-stage",
    )
    assert processed.context_checkpoints[0].stage_id == "probe"


def _scripted_execution(case: EvalCase) -> ExecutionResult:
    assert case.script is not None
    lines = [json.dumps(event) for event in case.script.events]
    processed = process_events(
        lines,
        workspace=EVAL_ROOT / "fixtures" / case.fixture,
        run_id="model-switch",
        context=case.context,
    )
    return ExecutionResult(
        run_id="model-switch",
        case_id=case.id,
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="2026-08-20T00:00:00Z",
        duration_ms=1,
        raw_events=processed.raw_events,
        events=processed.events,
        context_events=processed.context_events,
        context_checkpoints=processed.context_checkpoints,
    )


def test_model_switch_resume_is_scored_and_missing_switch_is_a_hard_gate(
    tmp_path: Path,
) -> None:
    case = _case("context-restart-model-switch")
    execution = _scripted_execution(case)
    passed = asyncio.run(
        ContextGrader().grade(
            GradeContext(case, execution, tmp_path, SecretRedactor())
        )
    )
    assert passed.checks_passed == passed.checks_total
    assert {checkpoint.model for checkpoint in execution.context_checkpoints} == {
        "model-alpha",
        "model-beta",
    }

    execution.context_checkpoints[1].model = "model-alpha"
    failed = asyncio.run(
        ContextGrader().grade(
            GradeContext(case, execution, tmp_path, SecretRedactor())
        )
    )
    codes = {finding.code for finding in failed.findings}
    assert {"context.resume_after_model", "context.resume_model_change"} <= codes
    assert all(
        finding.hard_gate
        for finding in failed.findings
        if finding.code in {"context.resume_after_model", "context.resume_model_change"}
    )


def test_model_switch_schema_requires_two_distinct_models() -> None:
    data = _case("context-restart-model-switch").model_dump(mode="json")
    resume = data["context"]["resumes"][0]
    resume["after_model"] = resume["before_model"]
    with pytest.raises(ValidationError, match="distinct models"):
        EvalCase.model_validate(data)


def test_advanced_context_catalog_contains_all_requested_scenarios() -> None:
    catalog = load_catalog(EVAL_ROOT)
    suite = catalog.suites["context-stress"]
    assert set(suite.cases) == {
        "context-long-session-multicompaction",
        "context-adversarial-retention",
        "context-multi-agent-isolation",
        "context-restart-model-switch",
    }
    assert catalog.suites["context-provider"].cases == [
        "context-semantic-retention-real"
    ]
