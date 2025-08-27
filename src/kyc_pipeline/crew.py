
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from .tools.ocr import ocr_extract
from .tools.bizrules import fetch_business_rules
from .tools.watchlist import watchlist_search
from .tools.notify import send_decision_email
from .tools.runlog import persist_runlog

@CrewBase
class KYCPipelineCrew:
    """Agentic KYC crew with a manager (Planner)."""

    agents_config = 'config/agents.yaml'
    tasks_config  = 'config/tasks.yaml'

    # ---- Local LLM via Ollama (using llama3.2:1b) ----
    def _local_llm(self) -> LLM:
        return LLM(
            model="ollama/llama3.2:1b",
            base_url="http://localhost:11434",
            temperature=0.2,
    )

    # ──────────────── Agents ────────────────
    @agent  #manager
    def planner(self) -> Agent:
        return Agent(
            config=self.agents_config['planner'], 
            verbose=True, 
            memory=False,
            llm=self._local_llm(),
        )

    @agent
    def extractor(self) -> Agent:
        return Agent(
            config=self.agents_config['extractor'],
            tools=[ocr_extract, persist_runlog], 
            verbose=True,
            llm=self._local_llm(),
        )

    @agent
    def judge(self) -> Agent:
        return Agent(
            config=self.agents_config['judge'], 
            tools=[persist_runlog], 
            verbose=True,
             llm=self._local_llm(),
        )

    @agent
    def bizrules(self) -> Agent:
        return Agent(
            config=self.agents_config['bizrules'], 
            tools=[fetch_business_rules, persist_runlog], 
            verbose=True,
             llm=self._local_llm(),
        )

    @agent
    def risk(self) -> Agent:
        return Agent(
            config=self.agents_config['risk'], 
            tools=[watchlist_search, persist_runlog], 
            verbose=True,
            llm=self._local_llm(),
        )

    @agent
    def notifier(self) -> Agent:
        return Agent(
            config=self.agents_config['notifier'], 
            tools=[send_decision_email, persist_runlog], 
            verbose=True,
            llm=self._local_llm(),
        )

    # ──────────────── Tasks ────────────────
    @task
    def extract_task(self) -> Task:
        return Task(
            config=self.tasks_config['extract_task'], 
            agent=self.extractor(), 
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
    def notify_task(self) -> Task:
        return Task(
            config=self.tasks_config['notify_task'], 
            agent=self.notifier(), 
        )

    # ──────────────── Crew ────────────────
    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.extractor(),
                self.judge(),
                self.bizrules(),
                self.risk(),
                self.notifier(),
            ],
            tasks=[
                self.extract_task(),
                self.judge_task(),
                self.bizrules_task(),
                self.risk_task(),
                self.notify_task(),
            ],
            process=Process.hierarchical,   # manager-led agentic flow
            manager_agent=self.planner(),
            manager_llm=locals,
            function_calling_llm=locals,
            verbose=True,
            # knowledge_sources=self.knowledge_sources,  # if enabled above
        )
