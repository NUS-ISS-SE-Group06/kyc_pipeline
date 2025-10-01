
# Agentic KYC Document Processor 
An event-driven KYC pipeline that starts when a document lands in S3. A ManagerCrew kicks off a sequence of YAML-defined tasks handled by five focused agents: Planner, Extractor,Judge, BizRule, Risk, Notifier


## How it runs (end-to-end)
1. **Trigger**: New KYC file uploaded to **S3**
2. **Process**: The S3 event invokes the **CrewAI endpoint**.
3. **Execution**: ManagerCrew(hierarchical) orchestrates YAML-defined tasks. Agents rely on deterministic tools and constrained LLM checks.
3. **Outputs**: Final Decision + explaination are produced and stored to persistent.

## Agents
- **Planner** — Planner Agent (Manager)
    - Goal: Plan & route KYC flows; request rework when confidence is low; keep provenance.
    - Backstory: Decides next steps and keeps everyone honest with logs.
    - Notes: Acts as the hierarchical manager in CrewAI (delegates tasks to other agents, aggregates outcomes).

- **Extractor** — Extraction Agent
    - Goal: Extract name, dob, address, id_number, face_photo_presence from the document.
    - Backstory: Uses OCR tool and heuristics.
    - Tools: ocr_extract
    - Outputs: extracted_fields, raw OCR text, confidence scores.

- **Judge** — Judgement Agent
    - Goal: Validate completeness; produce pass/fail with rationale & confidence; ask rework if needed.
    - Backstory: Structured QA and reflection.
    - Outputs: judge.verdict, judge.rationale, judge.confidence.

- **Bizrules** — Business-Rule Agent
    - Goal: Apply org rules and cite the source; produce violations[] and decision hint.
    - Backstory: Rule wonk with a love for citations.
    - Outputs: rules.violations[], rules.hint, rules.citations[].

- **Risk** — Fraud-Risk Agent
    - Goal: Watchlist check with fuzzy reconciliation; produce risk grade & explanation.
    - Backstory: Careful with ambiguous matches; escalate on HIGH.
    - Outputs: risk.grade (e.g., LOW/MED/HIGH), risk.matches[], risk.explanation.
- **Decision** — Decision Agent
    - Goal: Draft clear decision message; call notification tool to send.
    - Backstory: Explains outcomes to humans kindly and clearly.
    - Outputs: message.draft, message.channel, message.status.

## Quick start

### Installation 

First, if you haven't already, install `ollama` and `uv`

```bash
    brew install ollama
    pip install uv
    uv --version
```

#### Start/Stop Ollama 
Next, go to `/script` directory

```bash
    #set executable permission: 
    #chmod +x start-ollama.sh / chmod +x stop-ollama.sh
    cd /script  

    # Start Ollama    
    ./start-ollama.sh

    # Stop Ollama
    ./stop-ollama.sh
```

#### Run LLM model
Next, once ollama is up, you can Run any LLM model, here we are using `llama3.2:1b`
```bash
    ollama run llama3.2:1b
```

Next, navigate to your project directory and install the dependencies:

```bash
    crewai install
```

or

```bash
    uv sync
```

### Customizing

**Update `.env` file**

- Rename `env.example` to `.env`
- Modify `OPENAI_API_KEY`

## :rocket: How To Run

To kickstart your crew of AI agents and begin task execution, run this from the root folder of your project:

```bash
    crewai run
```

## Workflow

### How the input flow into tasks
- `tasks.yaml` includes text like “Use OCR to extract KYC fields from `{s3_uri}`…”.
- CrewAI substitutes values from the inputs dict you pass to kickoff.
- Agents then use tools:
    - `ocr_extract(s3_uri)` (stub; replace with Textract),
    - `fetch_business_rules(doc_type)`,
    - `watchlist_search(...)`,
    - `send_decision_email(to_email, ...)`,
    - `persist_runlog(...)`.

## Builds & run locally
```bash

# Build
docker build -t kyc-pipeline:dev .

# Run (CLI)
docker run --rm \
  -e OPENAI_API_KEY=your_key_here 
  kyc-pipeline:dev


```

## Out-of-the-box Tools
https://docs.crewai.com/en/tools/overview

## Development
You can run unit tests via `pytest`. 

```bash
uv run -m pytest -q

# Verbose and filtered run
uv run -m pytest -vv tests/test_tools_ocr.py::test_ocr_extract_returns_expected_stub_text
```
