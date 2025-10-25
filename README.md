
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

- 🧾 **Bizrules** (Business-Rule Agent)
  - Goal: Apply organization rules, produce violations list, and decision hints.
  - Backstory: The "policy nerd" who love citations.
  - Outputs: `rules.violations[]`, `rules.hint`, `rules.citations[]`.

- ⚖️ **Judge** (Judgement Agent)
  - Goal: Validate completeness and accuracy, produce pass/fail with rationale and confidence, request rework if needed.
  - Backstory: Structured QA with reflection.
  - Outputs: `judge.verdict`, `judge.rationale`, `judge.confidence`.

- **Risk** (Fraud-Risk Agent)
  - Goal: Perform Watchlist checks with fuzzy matching, produce risk grading and explanation.
  - Backstory: Escalates suspicious  matches with care.
  - Outputs: `risk.grade` (`LOW`, `MED`, `HIGH`), `risk.matches[]`, `risk.explanation`.
- **Decision** (Decision Agent)
  - Goal: Draft clear decision messages and send notification.
  - Backstory: Explains outcomes to humans in plain language.
  - Outputs: `message.draft`, `message.channel`, `message.status`.

## 🧰 Quick start

### 1. Installation

Install `uv` if not alrelady installed.

```bash

    pip install uv
    uv --version

```

Then, install dependencies:

```bash

    crewai install
    # or
    uv sync
```

### 2. Environment Setup

- Rename `env.example` to `.env`
- Update your `OPENAI_API_KEY` in `.env`.

## 🏃 How To Run

Run your Crew of AI agents from the project root:

```bash

    crewai run

```

## 🧭 Workflow Details

- `tasks.yaml` contains instruction like:
   “Use OCR to extract KYC fields from `{s3_uri}`…”.
- CrewAI injects values from the inputs dictionary into task templates.
- Agents then use tools such as:
  - `ocr_extract(s3_uri)`,
  - `fetch_business_rules(doc_type)`,
  - `watchlist_search(...)`,
  - `send_decision_email(to_email, ...)`,
  - `persist_runlog(...)`
  - `persist(...)`

## 🐳 Builds & Run locally (Docker)

```bash

# Build image
docker build -t kyc-pipeline:dev .

# Run container
docker run --rm -e OPENAI_API_KEY=<your_key_here>  kyc-pipeline:dev

```

## 🧪 Development & Testing

### Run Unit Tests

```bash

uv run pytest

```

### Run API Server

```bash

uv run uvicorn kyc_pipeline.api:app --host 0.0.0.0 --port 8000

```

Ping test:

```bash
curl http://localhost:8000/ping

```

Trigger KYC Pipeline:

```bash

curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{
        "doc_id":"KYC-1",
        "s3_uri":"s3://bucket/file.pdf",
        "doc_type":"KYC",
        "to_email":"user@example.com"
      }'

```

Local file test:

```bash

  curl -X POST http://localhost:8000/run \
    -H "Content-Type: application/json" \
    -d '{
          "doc_id":"KYC-1",
          "s3_uri":"./data/file.pdf",
          "doc_type":"KYC",
          "to_email":"user@example.com"
        }'

```

### 📊 KYC Status API

Below are common use cases and example commands to query KYC statuses:

| 🧭 **Use Case**              | 💻 **Example Command**                                                                                           |
|-----------------------------|------------------------------------------------------------------------------------------------------------------|
| All records                 | `curl http://localhost:8000/kyc_status`                                                                          |
| Filter by status            | `curl http://localhost:8000/kyc_status?final_decision=PROCESSED`                                                 |
| Search by name              | `curl http://localhost:8000/kyc_status?customer_name=Patel`                                                      |
| Search by ID number         | `curl http://localhost:8000/kyc_status?identification_no=S1234567A`                                              |
| Date range filter           | `curl http://localhost:8000/kyc_status?from_date=2025-09-15&to_date=2025-09-15`                                  |
| Combine filters             | `curl http://localhost:8000/kyc_status?customer_name=Lee&final_decision=INPROCESS`                               |
| Pagination                  | `curl http://localhost:8000/kyc_status?limit=5&offset=0`                                                         |
| Complex queries             | `curl http://localhost:8000/kyc_status?final_decision=PROCESSED&from_date=2025-09-15&limit=10`                   |

### 🧪 Promptfoo Testing

```bash

promptfoo eval --no-cache

# Display Promptfoo report
promptfoo view

```

## 📈 Monitoring

For LLM usage metrics and observability:

👉  https://app.agentops.ai/overview

## 🐋 Docker Compose

To run with Docker Compose:

```bash
  # First time or after dependencies changes 
  # (replace `<user-profile>` on `docker-compose.yml`)
docker compose up -d --build kyc-api

```

Subsequent runs:

```bash

docker compose up -d kyc-api

```

Stop container:

```bash

docker compose down

```
