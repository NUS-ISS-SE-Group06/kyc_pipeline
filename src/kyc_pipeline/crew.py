from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from .tools.ocr import ocr_extract
from .tools.bizrules import fetch_business_rules
from .tools.watchlist import watchlist_search
#from .tools.notify import send_decision_email
from .tools.runlog import persist_runlog
from .router.router import llmrouter
from .tools.emails_decision import  trigger_decision_email
from .tools.persist import save_decision_record
from .models import FinalDecision


@CrewBase
class KYCPipelineCrew:
    """Agentic KYC crew with a manager (Planner)."""

    agents_config = 'config/agents.yaml'
    tasks_config  = 'config/tasks.yaml'
    

    # ──────────────── Agents ────────────────
    @agent  #manager
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
            allow_delegation=False   # <- prevents coworker ping-pong
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
            max_iter=1
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
            max_iter=1
        )

   
 

  # Decision Agent
    @agent
    def decision_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['decision_agent'],
            llm=llmrouter(),
            tools=[trigger_decision_email, save_decision_record],
        )

    # ──────────────── Tasks ────────────────
    @task
    def extract_task(self) -> Task:
        return Task(
            config=self.tasks_config['extract_task'], 
            agent=self.extractor(),
            verbose=True
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
            config=self.tasks_config['decision_task'],  # load description/expected_output from YAML
            agent=self.decision_agent(),
            output_pydantic=FinalDecision,              # enforce schema at runtime
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
                self.decision_agent(),
            ],
            tasks=[
                self.extract_task(),
                self.judge_task(),
                self.bizrules_task(),
                self.risk_task(),
                self.decision_task(),
            ],
            process=Process.hierarchical,   # manager-led agentic flow
            manager_agent=self.planner(),
            manager_llm=locals,
            function_calling_llm=locals,
            verbose=True,
            # knowledge_sources=self.knowledge_sources,  # if enabled above
        )