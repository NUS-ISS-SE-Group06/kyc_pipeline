import unittest
from unittest.mock import patch, MagicMock

# This is the corrected import path for BaseTool, which is the root cause of the recent errors.
from crewai.tools import BaseTool
from src.kyc_pipeline.crew import KYCPipelineCrew

class TestDecisionAgent(unittest.TestCase):
    """
    Unit tests for the DecisionAgent's task.
    This version uses robust patching to ensure tests run reliably.
    """
    
    # We patch the tools directly where they are imported by the crew.py file.
    # This is the most reliable way to ensure the agent uses our mocks.
    @patch('src.kyc_pipeline.crew.persist_runlog', spec=BaseTool)
    @patch('src.kyc_pipeline.crew.send_decision_email', spec=BaseTool)
    @patch('src.kyc_pipeline.crew.llmrouter')
    def test_approve_scenario(self, mock_llmrouter, mock_send_email, mock_persist_runlog):
        """ Tests the full 'Approve' workflow for the DecisionAgent. """
        
        # 1. Configure the mocks that are passed into the test function
        mock_send_email.name = 'send_decision_email'
        mock_persist_runlog.name = 'persist_runlog'
        
        # 2. Configure the mock LLM to return tool calls
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.tool_calls = [
            {"name": "send_decision_email", "args": {"decision": "Approve", "explanation": "All KYC checks passed successfully."}, "id": "tool_call_1"},
            {"name": "persist_runlog", "args": {"final_decision": "Approve", "explanation": "All KYC checks passed successfully."}, "id": "tool_call_2"}
        ]
        mock_llmrouter.return_value = mock_llm

        # 3. Instantiate the crew. The agent will now be created with the mocked tools already in place.
        crew_instance = KYCPipelineCrew()
        decision_task = crew_instance.decision_task()

        # 4. Set context from previous tasks
        decision_task.context[0].output = "Mocked Extractor Output"
        decision_task.context[1].output = "Mocked Judge Output"
        decision_task.context[2].output = "Mocked BizRules Output"
        decision_task.context[3].output = "Mocked Risk Output"
        
        # 5. Execute the task
        # We access the agent via the task, as it's assigned during creation
        decision_task.agent.execute_task(task=decision_task)

        # 6. Assert that the 'run' method of our mock tools was called correctly
        mock_send_email.run.assert_called_once_with(decision="Approve", explanation="All KYC checks passed successfully.")
        mock_persist_runlog.run.assert_called_once_with(final_decision="Approve", explanation="All KYC checks passed successfully.")

    @patch('src.kyc_pipeline.crew.persist_runlog', spec=BaseTool)
    @patch('src.kyc_pipeline.crew.send_decision_email', spec=BaseTool)
    @patch('src.kyc_pipeline.crew.llmrouter')
    def test_reject_scenario(self, mock_llmrouter, mock_send_email, mock_persist_runlog):
        """ Tests the full 'Reject' workflow for the DecisionAgent. """
        
        # 1. Configure mocks
        mock_send_email.name = 'send_decision_email'
        mock_persist_runlog.name = 'persist_runlog'
        
        # 2. Configure mock LLM
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.tool_calls = [
            {"name": "send_decision_email", "args": {"decision": "Reject", "explanation": "Applicant found on fraud watchlist."}, "id": "tool_call_1"},
            {"name": "persist_runlog", "args": {"final_decision": "Reject", "explanation": "Applicant found on fraud watchlist."}, "id": "tool_call_2"}
        ]
        mock_llmrouter.return_value = mock_llm

        # 3. Instantiate crew
        crew_instance = KYCPipelineCrew()
        decision_task = crew_instance.decision_task()

        # 4. Set context for rejection
        decision_task.context[0].output = "Mocked Extractor Output"
        decision_task.context[1].output = "Mocked Judge Output"
        decision_task.context[2].output = "Mocked BizRules Output"
        decision_task.context[3].output = "Mocked Risk Output: High Risk"
        
        # 5. Execute the task
        decision_task.agent.execute_task(task=decision_task)

        # 6. Assert tools were called correctly
        mock_send_email.run.assert_called_once_with(decision="Reject", explanation="Applicant found on fraud watchlist.")
        mock_persist_runlog.run.assert_called_once_with(final_decision="Reject", explanation="Applicant found on fraud watchlist.")

if __name__ == '__main__':
    unittest.main()

