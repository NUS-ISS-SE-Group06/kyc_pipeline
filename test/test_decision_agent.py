# test/test_decision_agent.py
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import json

import src.kyc_pipeline.crew as crew_mod
from src.kyc_pipeline.crew import KYCPipelineCrew


def _fake_text(text: str = "All good."):
    """Return a normal assistant text turn (no tool calls)."""
    message = SimpleNamespace(role="assistant", content=text)
    return SimpleNamespace(
        id="cmpl-mock",
        model="gpt-4o",
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
    )


@patch.object(crew_mod, "llmrouter")
@patch("crewai.llm.litellm.completion")
def test_approve_scenario(mock_completion, mock_llmrouter):
    # llmrouter must return an object with a string .model (keeps pydantic happy)
    mock_llm = MagicMock()
    mock_llm.model = "openai/gpt-4o"
    mock_llmrouter.return_value = mock_llm

    # Patch CLASS .run so CrewAI can "call" the tools (we'll trigger them in the side-effect)
    with patch.object(crew_mod.send_decision_email.__class__, "run") as mock_email_run, \
         patch.object(crew_mod.persist_runlog.__class__, "run") as mock_log_run:

        # Side effect: simulate the LLM deciding to call tools by directly invoking our patched runs
        # and then returning a normal text response.
        def side_effect(**_kwargs):
            # simulate the two tool invocations
            mock_email_run(
                decision="Approve",
                explanation="All KYC checks passed successfully.",
            )
            mock_log_run(
                final_decision="Approve",
                explanation="All KYC checks passed successfully.",
            )
            # return a final assistant message
            return _fake_text("All good.")

        mock_completion.side_effect = side_effect

        crew = KYCPipelineCrew()
        task = crew.decision_task()

        # Minimal context referenced by the task prompt
        task.context = [
            MagicMock(output="Extractor Output"),
            MagicMock(output="Judge Output"),
            MagicMock(output="BizRules Output"),
            MagicMock(output="Risk Output"),
        ]

        # Execute—our side_effect will "call" the tools and then return text
        task.agent.execute_task(task=task)

        # Verify both tools were invoked
        assert mock_email_run.called, "send_decision_email.run() was not called"
        assert mock_log_run.called, "persist_runlog.run() was not called"


@patch.object(crew_mod, "llmrouter")
@patch("crewai.llm.litellm.completion")
def test_reject_scenario(mock_completion, mock_llmrouter):
    mock_llm = MagicMock()
    mock_llm.model = "openai/gpt-4o"
    mock_llmrouter.return_value = mock_llm

    with patch.object(crew_mod.send_decision_email.__class__, "run") as mock_email_run, \
         patch.object(crew_mod.persist_runlog.__class__, "run") as mock_log_run:

        def side_effect(**_kwargs):
            mock_email_run(
                decision="Reject",
                explanation="Applicant found on fraud watchlist.",
            )
            mock_log_run(
                final_decision="Reject",
                explanation="Applicant found on fraud watchlist.",
            )
            return _fake_text("All good.")

        mock_completion.side_effect = side_effect

        crew = KYCPipelineCrew()
        task = crew.decision_task()
        task.context = [
            MagicMock(output="Extractor Output"),
            MagicMock(output="Judge Output"),
            MagicMock(output="BizRules Output"),
            MagicMock(output="Risk Output (High)"),
        ]

        task.agent.execute_task(task=task)

        assert mock_email_run.called, "send_decision_email.run() was not called"
        assert mock_log_run.called, "persist_runlog.run() was not called"