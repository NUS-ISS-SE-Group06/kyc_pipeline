
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from .models import ExtractedKyc, JudgeVerdict, RuleEvaluation, RiskAssessment
from .tools.ocr import ocr_extract
from .tools.rules import fetch_business_rules
from .tools.watchlist import watchlist_search
from .tools.notify import send_decision_email
from .tools.runlog import persist_runlog

@CrewBase
class KYCPipelineCrew:
    """Agentic KYC crew with a manager (Planner)."""

    agents_config = 'config/agents.yaml'
    tasks_config  = 'config/tasks.yaml'

    # If you add PDFs/MDs under rules/, mount knowledge sources here:
    # from crewai.knowledge.source.pdf_knowledge_source import PDFKnowledgeSource
    # knowledge_sources = [PDFKnowledgeSource(file_paths=['rules/policy.pdf'])]

    # ──────────────── Agents ────────────────
    @agent
    def planner(self) -> Agent:
        return Agent(config=self.agents_config['planner'], tools=[persist_runlog], verbose=True, memory=False)

    @agent
    def extractor(self) -> Agent:
        return Agent(config=self.agents_config['extractor'], tools=[ocr_extract, persist_runlog], verbose=True)

    @agent
    def judge(self) -> Agent:
        return Agent(config=self.agents_config['judge'], tools=[persist_runlog], verbose=True)

    @agent
    def bizrules(self) -> Agent:
        return Agent(config=self.agents_config['bizrules'], tools=[fetch_business_rules, persist_runlog], verbose=True)

    @agent
    def risk(self) -> Agent:
        return Agent(config=self.agents_config['risk'], tools=[watchlist_search, persist_runlog], verbose=True)

    @agent
    def notifier(self) -> Agent:
        return Agent(config=self.agents_config['notifier'], tools=[send_decision_email, persist_runlog], verbose=True)

    # ──────────────── Tasks ────────────────
    @task
    def extract_task(self) -> Task:
        return Task(config=self.tasks_config['extract_task'], agent=self.extractor(), output_json=ExtractedKyc)

    @task
    def judge_task(self) -> Task:
        return Task(config=self.tasks_config['judge_task'], agent=self.judge(), output_json=JudgeVerdict)

    @task
    def rules_task(self) -> Task:
        return Task(config=self.tasks_config['rules_task'], agent=self.bizrules(), output_json=RuleEvaluation)

    @task
    def risk_task(self) -> Task:
        return Task(config=self.tasks_config['risk_task'], agent=self.risk(), output_json=RiskAssessment)

    @task
    def notify_task(self) -> Task:
        return Task(config=self.tasks_config['notify_task'], agent=self.notifier(), output_json=dict)

    # ──────────────── Crew ────────────────
    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.hierarchical,   # manager-led agentic flow
            manager_agent=self.planner(),
            verbose=2,
            # knowledge_sources=self.knowledge_sources,  # if enabled above
        )
