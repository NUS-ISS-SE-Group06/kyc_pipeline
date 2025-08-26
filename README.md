
# Agentic KYC Document Processor 
An event-driven KYC pipeline that starts when a document lands in S3. A ManagerCrew kicks off a sequence of YAML-defined tasks handled by five focused agents: Planner, Extractor,Judge, BizRule, Risk, Notifier


## How it runs (end-to-end)
1. Trigger: New file in S3 → Lambda invokes crew.kickoff(inputs={...}).
2. Process: ManagerCrew (hierarchical) delegates YAML tasks to agents; each agent uses a deterministic tool (OCR, rules engine, vector search) or a constrained LLM check.
3. Outputs: Decision + explanation sent via email.

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

- **Judge** — LLM Judge Agent
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
- **Notifier** — Notifier Agent
    - Goal: Draft clear decision message; call notification tool to send.
    - Backstory: Explains outcomes to humans kindly and clearly.
    - Outputs: message.draft, message.channel, message.status.

## Quick start

### Install Ollama 
```bash
    brew install ollama
```

### Start Ollama 
```bash
    cd /script
    chmod +x start-ollama.sh
    ./start-ollama.sh
```

### Run LLM model llama3.2:1b 
```bash
    ollama run llama3.2:1b
```


### Install Python Version Manager

```bash
    cd /kyc_pipeline

    brew update
    brew install pyenv
    # Enable in your shell (Bash/Zsh); add these lines to ~/.zshrc or ~/.bashrc:
    echo 'eval "$(pyenv init -)"' >> ~/.zshrc
    exec $SHELL -l  # restart shell
```

### Install Python 3.13.2

```bash
    pyenv install 3.13.2          # builds and installs into ~/.pyenv/versions/3.13.2
    pyenv local 3.13.2            # writes .python-version in the current project
    python -V                     # should show Python 3.13.2
```

### Create Virtual Environnment

```bash
    python -m venv .venv
    source .venv/bin/activate    
    pip install --upgrade pip  
    pip install -U pip setuptools wheel    # python package chain tools
```

### Install Dependencies

```bash
    pip install -r requirements.txt
```

### Set .env for your keys Dependencies

```bash

    cp .env.example .env
    vi .env  # Set OPENAI_API_KEY and save
```

### Run as script

```bash
    cd /src/

    python -m kyc_pipeline.main
```

## Workflow

### How the input flow into tasks
- `tasks.yaml` includes text like “Use OCR to extract KYC fields from `{s3_uri}`…”.
- CrewAI substitutes values from the inputs dict you pass to kickoff.
- Agents then use tools:
    - `ocr_extract(s3_uri)` (stub; replace with Textract),
    - `fetch_business_rules(org_id)`,
    - `watchlist_search(...)`,
    - `send_decision_email(to_email, ...)`,
    - `persist_runlog(...)`.

## Out-of-the-box Tools
https://docs.crewai.com/en/tools/overview

## SDK
https://docs.crewai.com/en/examples/example#flows

## OpenAI Platform
https://platform.openai.com/docs/api-reference/introduction

