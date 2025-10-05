
# Agentic KYC Document Processor 
An event-driven KYC pipeline that starts when a document lands in S3. A ManagerCrew kicks off a sequence of YAML-defined tasks handled by five focused agents: Planner, Extractor,Judge, BizRule, Risk, Notifier

## How it runs (end-to-end)

1. **Trigger**: New KYC file uploaded to **S3**
2. **Process**: The S3 event invokes the **CrewAI endpoint**.
3. **Execution**: ManagerCrew(hierarchical) orchestrates YAML-defined tasks. Agents rely on deterministic tools and constrained LLM checks.
4. **Outputs**: Final Decision + explaination are produced and stored to persistent.

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

Next, once ollama is up, you can Run any LLM model, here we are using `llama3.2:3b`

```bash
    ollama run llama3.2:3b
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

## Development

You can run unit tests via `pytest`.

```bash
uv run -m pytest -q

# Verbose and filtered run
uv run -m pytest -vv tests/test_tools_ocr.py::test_ocr_extract_returns_expected_stub_text
```

You can run server process via `uvicorn`.

```bash
uv run uvicorn kyc_pipeline.api:app --host 0.0.0.0 --port 8000

# ping test
curl http://localhost:8000/ping

# run crewAI KYC
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"doc_id":"KYC-1","s3_uri":"s3://bucket/file.jpg","doc_type":"KYC","to_email":"user@example.com"}'

# To get KYC Status
1. Get all records:
curl http://localhost:8000/kyc_status

2. Filter by status:
curl http://localhost:8000/kyc_status?final_decision=PROCESSED
curl http://localhost:8000/kyc_status?final_decision=FAILED

3. Search by customer name:
curl http://localhost:8000/kyc_status?customer_name=Patel
curl http://localhost:8000/kyc_status?customer_name=Sarah

4. Filter by identification number:
curl http://localhost:8000/kyc_status?identification_no=S1234567A

5. Filter by date range:
curl http://localhost:8000/kyc_status?from_date=2025-09-15&to_date=2025-09-15

6. Combine multiple filters:
curl http://localhost:8000/kyc_status?final_decision=PROCESSED&from_date=2025-09-15
curl http://localhost:8000/kyc_status?customer_name=Lee&final_decision=INPROCESS

7. Pagination:
curl http://localhost:8000/kyc_status?limit=5&offset=0    # First 5 records
curl http://localhost:8000/kyc_status?limit=5&offset=5    # Next 5 records

8. Complex query:
curl http://localhost:8000/kyc_status?final_decision=PROCESSED&from_date=2025-09-15&limit=10
```

## Docker

You can run it on `docker`.

- First time or after changing Dockerfile/deps.
  Replace `<user-profile>` on `docker-compose.yml` to a valid path

```bash
docker compose up -d --build kyc-api
```

- Subsequent runs (just restart container)

```bash
docker compose up -d kyc-api
```

- Stop container

```bash
docker compose down

```
