
# :brain: Agentic KYC Document Processor 
An **event-driven KYC pipeline** that starts when a document lands in S3. A **ManagerCrew** kicks off a sequence of YAML-defined tasks handled by six specialized agents: `Planner`, `Extractor`, `Judge`, `BizRule`, `Risk`, `Decision`.

## :rocket: End-to-End Flow

1. **Trigger**: A New KYC document is uploaded to **S3**
2. **Process**: The S3 event invokes the **CrewAI** endpoint.
3. **Execution**: `ManagerCrew` orchestrates YAML-defined tasks using deterministic tools and constrained LLM checks.
4. **Outputs**: A final Decision and explaination are persisted in storage.

## 🧑‍💼 Agents Overview

- 🧭 **Planner** — Planner Agent (Manager Agent)
  - Goal: Plan & route KYC flows, request rework if confidence is low, maintain provenance.
  - Backstory: Keeps the process accountable with logs and decision trails.
  - Notes: Acts as the hierarchical manager in CrewAI, delegating tasks and aggregating results.

- 📄 **Extractor** (Extraction Agent)
  - Goal: Extract `name`, `dob`, `address`, `id_number`, `email`, `face_photo`.
  - Backstory: Uses OCR tool and heuristics.
  - Tools: `ocr_extract`
  - Outputs: `extracted_fields`, raw OCR text, confidence scores.

- ⚖️ **Judge** — Judgement Agent
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

First, if you haven't already, install `uv`

```bash
    pip install uv
    uv --version
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

```

You can run server process via `uvicorn`.

```bash
uv run uvicorn kyc_pipeline.api:app --host 0.0.0.0 --port 8000

# ping test
curl http://localhost:8000/ping

# run crewAI KYC
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
        "doc_id":"KYC-1",
        "s3_uri":"s3://bucket/file.jpg",
        "doc_type":"KYC",
        "to_email":"user@example.com"
      }'

curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
        "doc_id":"KYC-1",
        "s3_uri":"./test/idcard_john_doe.jpg",
        "doc_type":"KYC",
        "to_email":"user@example.com"
      }'

# To get KYC Status
#1. Get all records:
curl http://localhost:8000/kyc_status

#2. Filter by status:
curl http://localhost:8000/kyc_status?final_decision=PROCESSED
curl http://localhost:8000/kyc_status?final_decision=FAILED

#3. Search by customer name:
curl http://localhost:8000/kyc_status?customer_name=Patel
curl http://localhost:8000/kyc_status?customer_name=Sarah

#4. Filter by identification number:
curl http://localhost:8000/kyc_status?identification_no=S1234567A

#5. Filter by date range:
curl http://localhost:8000/kyc_status?from_date=2025-09-15&to_date=2025-09-15

#6. Combine multiple filters:
curl http://localhost:8000/kyc_status?final_decision=PROCESSED&from_date=2025-09-15
curl http://localhost:8000/kyc_status?customer_name=Lee&final_decision=INPROCESS

#7. Pagination:
curl http://localhost:8000/kyc_status?limit=5&offset=0    # First 5 records
curl http://localhost:8000/kyc_status?limit=5&offset=5    # Next 5 records

#8. Complex query:
curl http://localhost:8000/kyc_status?final_decision=PROCESSED&from_date=2025-09-15&limit=10
```

You can run promptfoo tests.

```bash

promptfoo eval --no-cache

# Display Promptfoo report
promptfoo view

```

## Monitoring

You can display LLM Monitoring dashboard
  https://app.agentops.ai/overview

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
