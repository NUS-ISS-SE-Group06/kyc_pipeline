# src/kyc_pipeline/crew.py
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

# Tools
from .tools.ocr import ocr_extract
from .tools.bizrules import fetch_business_rules
from .tools.watchlist import watchlist_search
from .tools.runlog import persist_runlog

# Use YOUR new tools here (do not import notify.send_decision_email again)
from .tools.emails_decision import send_decision_email
from .tools.persist import save_decision_record

# Router
from .router.router import llmrouter


@CrewBase
class KYCPipelineCrew:
  """Agentic KYC crew with a manager (Planner)."""

  agents_config = 'config/agents.yaml'
  tasks_config  = 'config/tasks.yaml'

  # ──────────────── Agents ────────────────
  @agent  # Manager
  def planner(self) -> Agent:
    return Agent(
      config=self.agents_config['planner'],
      verbose=True,
      memory=False,
      tools=[],
      llm=llmrouter(),
    )

  @agent
  def extractor(self) -> Agent:
    return Agent(
      config=self.agents_config['extractor'],
      tools=[ocr_extract, persist_runlog],
      verbose=True,
      llm=llmrouter(),
      max_iter=1,
      allow_delegation=False
    )

  @agent
  def judge(self) -> Agent:
    return Agent(
      config=self.agents_config['judge'],
      tools=[persist_runlog],
      verbose=True,
      llm=llmrouter(),
      max_iter=1,
    )

  @agent
  def bizrules(self) -> Agent:
    return Agent(
      config=self.agents_config['bizrules'],
      tools=[fetch_business_rules, persist_runlog],
      verbose=True,
      llm=llmrouter(),
      max_iter=1,
    )

  @agent
  def risk(self) -> Agent:
    return Agent(
      tools=[watchlist_search, persist_runlog],
      verbose=True,
      llm=llmrouter(),
      role="Fraud-Risk Agent",
      goal="Run watchlist screening and output a single risk decision.",
      backstory="Grades risk based on watchlist matches; no coworker chatter.",
      allow_delegation=False,
      max_iter=1,
    )

  # Decision Agent
  @agent
  def decision_agent(self) -> Agent:
    return Agent(
      role="KYC Decision Maker",
      goal=(
        "Collate all KYC checks (document extraction, content validation, "
        "business rule checks, risk scans) and make a final disposition."
      ),
      backstory=(
        "You are the final decision authority in the KYC pipeline. "
        "Your primary responsibility is to ensure compliance and accuracy "
        "while providing clear communication of the outcome."
      ),
      allow_delegation=False,
      llm=llmrouter(),
      tools=[send_decision_email, save_decision_record],
      verbose=True,
      max_iter=1,
    )

  # ──────────────── Tasks ────────────────
  @task
  def extract_task(self) -> Task:
    return Task(
      config=self.tasks_config['extract_task'],
      agent=self.extractor(),
      verbose=True,
    )

  @task
  def judge_task(self) -> Task:
    return Task(
      config=self.tasks_config['judge_task'],
      agent=self.judge(),
    )

  @task
  def bizrules_task(self) -> Task:
    return Task(
      config=self.tasks_config['bizrules_task'],
      agent=self.bizrules(),
    )

  @task
  def risk_task(self) -> Task:
    return Task(
      config=self.tasks_config['risk_task'],
      agent=self.risk(),
    )

  @task
  def decision_task(self) -> Task:
    return Task(
      description=(
        "Review the following KYC processing results: "
        "- Extracted Document Data: {extract_task.output} "
        "- Content Structure Judgment: {judge_task.output} "
        "- Business Rules Compliance: {bizrules_task.output} "
        "- Fraud Risk Assessment: {risk_task.output} \n"
        "Synthesize all this information to make a final decision. "
        "The decision must be one of: 'Approve', 'Reject', or 'Manual Review'.\n"
        "Finally, use your tools to: "
        "1. Send an email notification containing the final decision and a brief, clear explanation. "
        "2. Persist the complete run log with the final decision and explanation included."
      ),
      expected_output=(
        "A succinct final decision and confirmation that notification and persistence "
        "have been triggered successfully. If tools were called, mention it."
      ),
      agent=self.decision_agent(),
    )

  # ──────────────── Crew ────────────────
  @crew
  def crew(self) -> Crew:
    return Crew(
      # Do NOT include the manager here
      agents=[
        self.extractor(),
        self.judge(),
        self.bizrules(),
        self.risk(),
        self.decision_agent(),
      ],
      tasks=[
        self.extract_task(),
        self.judge_task(),
        self.bizrules_task(),
        self.risk_task(),
        self.decision_task(),
      ],
      process=Process.hierarchical,
      manager_agent=self.planner(),
      manager_llm=llmrouter(),
      function_calling_llm=llmrouter(),
      verbose=True,
    )