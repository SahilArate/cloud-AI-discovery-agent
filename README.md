# ai-discovery-agent

Finds AI usage across AWS, GCP and Azure, builds an AI inventory aligned with the ISO/IEC 42001
(AIMS) fields, flags potential shadow AI, and routes LLM work to the cheapest model that does the job.

| Document | What it covers |
|---|---|
| **README.md** (this file) | What it is, architecture, how to run it |
| [LOGIC.md](LOGIC.md) | Every decision rule: verdicts, evidence, approval, risk, routing |
| [TECHNICAL.md](TECHNICAL.md) | Modules, data model, API, security, testing, scaling |
| [docs/threat-model.md](docs/threat-model.md) | Threats and controls |
| [docs/aws-readonly-policy.json](docs/aws-readonly-policy.json) | Least-privilege IAM policy, generated from the catalog |

---

## 1. The problem

A large company has thousands of cloud resources and nobody knows which involve AI, who owns them,
whether they are used, or whether anyone approved them. This project answers that, and it keeps
three questions apart because mixing them is the usual mistake:

| Question | Field | Values |
|---|---|---|
| Is it AI? | `ai_verdict` | `ai_confirmed`, `ai_suspected`, `not_ai_evidenced`, `unknown` |
| Is it being used? | `activity_status` | `active_observed`, `dormant_observed`, `no_activity_observed`, `activity_unknown` |
| Is it approved? | `approval_status` | `approved`, `potential_shadow_ai`, `governance_exception`, `not_assessed` |

A second question from the assessment: when several agents share an application, how do you
use the right LLM for the best output at the least cost? The answer is a small router (section 6).

---

## 2. What is real and what is simulated

| Area | State |
|---|---|
| AWS collector (Lambda, SageMaker, EC2, Secrets Manager) | Built. Tested against **moto** (fake AWS). Never run on a live account. |
| AWS `--mode live` | Code path exists, **untested**. |
| GCP collector (Vertex AI, Cloud Run, Compute, Secret Manager) | Built behind an injected `GCPApi` interface. Runs on **fixture data**. No live adapter. |
| Azure collector (Cognitive Services, ML, AI Search, Web Apps, VMs, Key Vault) | Built behind an injected `AzureApi` interface. Runs on **fixture data**. No live adapter. |
| Detection, enrichment, governance | Built and unit tested. |
| LLM inspector and router | Built. Unit tested with a fake provider. Groq is the default provider. |
| Postgres, API, Next.js dashboard, review queue | Built and tested. |
| Eval harness | Built. Labels cover the demo estate only. |
| Network/DNS evidence, SBOM scanning, SaaS discovery, IAM-permission evidence | **Not built.** |

There are no live cloud accounts behind this project. The demo estate is invented.

---

## 3. Architecture

```
                         ┌───────────────────────────────────────────────┐
                         │  Next.js dashboard (TypeScript, Tailwind)     │
                         │  Inventory · Asset detail · Review queue ·    │
                         │  Coverage · Changes · LLM cost                │
                         └───────────────────────┬───────────────────────┘
                                                 │ HTTP (JSON)
                         ┌───────────────────────▼───────────────────────┐
                         │  FastAPI                                      │
                         │  /inventory /assets /coverage /changes        │
                         │  /reviews /llm/cost /health                   │
                         └───────────────────────┬───────────────────────┘
                                                 │ SQLAlchemy
┌────────────────────────────────────────────────▼─────────────────────────────────────────┐
│  PostgreSQL (append-only observations)                                                   │
│  scan_runs · ai_assets · asset_observations · evidence_records ·                         │
│  governance_reviews · scan_scope_results · llm_calls                                     │
└────────────────────────────────────────────────▲─────────────────────────────────────────┘
                                                 │ one transaction per scan
┌────────────────────────────────────────────────┴─────────────────────────────────────────┐
│  PIPELINE  (pipeline/scan.py)                                                            │
│                                                                                          │
│  Catalog (YAML) ──► COLLECT ──► CORRELATE ──► EVIDENCE ──► VERDICT ──► ENRICH ──► ASSESS │
│                     read-only    link secrets  rules        rules       owner,     vs    │
│                     no LLM       to consumers  (no LLM)     (no LLM)    usage      register│
│                                                                │                         │
│                                          ambiguous only        ▼                         │
│                                          ┌──────────────────────────────┐                │
│                                          │ INSPECTOR (LLM, optional)    │                │
│                                          │ via LLMRouter small → large  │                │
│                                          └──────────────────────────────┘                │
└───────┬───────────────────────┬───────────────────────────┬──────────────────────────────┘
        │                       │                           │
┌───────▼───────┐       ┌───────▼───────┐           ┌───────▼───────┐
│ AWS collector │       │ GCP collector │           │ Azure collector│
│ boto3 / moto  │       │ GCPApi        │           │ AzureApi       │
└───────────────┘       └───────────────┘           └────────────────┘
```

### Scan workflow

```mermaid
flowchart TD
    A["CLI or API starts a scan"] --> B["Create scan_runs row"]
    B --> C["For each target: collector lists resources"]
    C --> D["Record coverage per scope: complete, partial or failed"]
    D --> E["Link AI-named secrets to consumers"]
    E --> F["Gather evidence with rules"]
    F --> G["Classify with deterministic verdict rules"]
    G --> H{"Verdict is suspected or unknown?"}
    H -- "yes and LLM configured" --> I["Inspector via router"]
    H -- "no" --> J
    I --> J{"Verdict is not_ai_evidenced?"}
    J -- "yes" --> K["Count it, do not store as an asset"]
    J -- "no" --> L["Resolve owner, read usage"]
    L --> M["Match against approved register"]
    M --> N["Assess approval, reason codes, risk tier"]
    N --> O["Append observation and evidence rows"]
    O --> P["Save LLM call log"]
    K --> P
    P --> Q["Commit one transaction"]
```

### Request flow for the dashboard

```mermaid
sequenceDiagram
    participant U as Reviewer
    participant W as Next.js
    participant A as FastAPI
    participant D as Postgres
    U->>W: open Review queue
    W->>A: GET /reviews/queue
    A->>D: latest observations and reviews
    D-->>A: rows
    A-->>W: queue sorted by risk
    U->>W: Approve with name and reason
    W->>A: POST /reviews
    A->>D: INSERT governance_reviews
    A-->>W: 201 created
    W->>A: GET /reviews/queue
    A-->>W: asset has left the queue
```

---

## 4. Key design decisions

| Decision | Why |
|---|---|
| Rules decide first, the LLM only sees ambiguous findings | Free, repeatable and explainable. A model is used where rules cannot settle it. |
| The LLM can never return `ai_confirmed` | A manipulated or overconfident model cannot promote an asset. |
| `unknown` is a real answer | A GPU instance alone is weak evidence. We do not guess. |
| Activity is separate from the verdict | An idle endpoint is still AI. |
| Owner is an explicit tag or unknown | A creator seen in CloudTrail is labelled `inferred_creator` and never counts as verified. |
| Coverage is stored for every scope | A scan that finds 5 assets means little unless you know what it could not inspect. |
| Observations are append-only | Gives history, new assets and missing assets for free. |
| Collectors never see secret values | Names only. Tests search outputs and the database for planted values. |
| Collectors sit behind interfaces | Detection, governance and the API never learn which cloud a resource came from. |

---

## 5. Repository layout

```
src/ai_discovery/
  catalog/      versioned per-cloud discovery catalogs (YAML) and a typed loader
  collectors/   base contract; AWS, GCP, Azure; CloudWatch usage; CloudTrail owner hints
  models/       Resource, Evidence, Finding, coverage models, shared enums
  detection/    rules (evidence), classifier (verdict), correlate (secret linking)
  enrichment/   owner resolution, usage summary
  governance/   approved register matching, shadow AI policy
  llm/          types, Groq provider, router, factory, cost report
  agents/       inspector (LLM second opinion)
  pipeline/     scan orchestration
  db/           SQLAlchemy base, session, tables
  api/          FastAPI app
  evals/        hand-labelled ground truth and scoring
  security/     IAM policy generator
  demo/         fake AWS account and GCP/Azure fixtures
  cli.py        command line entry point
frontend/       Next.js dashboard
migrations/     Alembic migrations
data/           approved register (YAML)
docs/           threat model, generated IAM policy
tests/          pytest suite
```

---

## 6. LLM routing and cost

```mermaid
flowchart TD
    R["Ambiguous finding"] --> S{"Budget left?"}
    S -- "no" --> X["Log budget_blocked, keep rules result"]
    S -- "yes" --> T["Small model"]
    T --> U{"Output valid JSON, allowed verdict, real evidence ids?"}
    U -- "yes" --> Z["Accept, mark review_required"]
    U -- "no, unusable output" --> V["Large model"]
    T -- "provider error" --> Y["Log provider_error, keep rules result"]
    V --> W{"Valid?"}
    W -- "yes" --> Z
    W -- "no" --> Y2["Keep rules result"]
```

- Every request starts on the small model. Only unusable output escalates. A provider outage does not.
- A per-scan budget caps spend. Blocked calls are logged.
- Each call stores tier, tokens, cost, latency and outcome, never prompt text.
- The cost page shows calls per tier, escalations, actual cost and an estimated all-large cost.
  The estimate reuses the small model's token counts, and prices in `.env` are placeholders: verify them before quoting any figure.

---

## 7. Run it

Needs Python 3.11, Docker and Node 18.18 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e ".[dev]"
copy .env.example .env
docker compose up -d
alembic upgrade head

# scan all three clouds (AWS on moto, GCP and Azure on fixtures), rules only
python -m ai_discovery scan --mode mock --clouds aws gcp azure --register data/approved_register.yaml --no-llm

# API on :8000
python -m uvicorn ai_discovery.api.main:app --reload

# dashboard on :3000 (second terminal)
cd frontend
npm install
npm run dev
```

Drop `--no-llm` and set `GROQ_API_KEY` in `.env` to enable the inspector. Check Groq's console for
current model names and override `SMALL_MODEL_NAME` and `LARGE_MODEL_NAME` if needed.

Evaluation and tests:

```bash
python -m ai_discovery.evals.scoring
docker exec -it ai-discovery-db psql -U discovery -d ai_discovery -c "CREATE DATABASE ai_discovery_test;"
pytest
```

Windows notes: if SQLAlchemy fails with an Application Control DLL error, set
`DISABLE_SQLALCHEMY_CEXT_RUNTIME=1`. If `ai_discovery` cannot be imported, set `PYTHONPATH=src`.

---

## 8. API

| Method and path | Purpose |
|---|---|
| `GET /health` | Database reachable |
| `GET /inventory` | AI assets seen in the latest scan (`?include_missing=true` adds older ones) |
| `GET /assets/{asset_key}` | One asset: observation history and evidence per observation |
| `GET /coverage/latest` | What the latest scan inspected and what failed |
| `GET /changes` | New and missing assets between the last two scans |
| `GET /reviews/queue` | Assets waiting for a person, highest risk first |
| `POST /reviews` | Approve or escalate with reviewer and reason |
| `GET /reviews/history?asset_key=` | Every decision for one asset |
| `GET /llm/cost` | LLM routing and cost report for the latest scan |

Interactive docs at `/docs`.

---

## 9. Limitations

- Everything is tested on mocks and fixtures. Rate limits, pagination at scale and IAM enforcement are untested.
- Hidden AI is found from names, tags, layer names, GPU types and secret names. There is no code, SBOM,
  IAM-permission or network evidence, so quiet or well-named AI will be missed.
- Rules are hand-set, not calibrated on labelled real data.
- The inventory shows the latest scan only. A scan of one cloud hides the others' assets.
- The review API has no authentication, and reviewer names are self-declared.
  A later scan that changes a verdict does not reopen an earlier approval.
- A crashed scan leaves no `scan_runs` row.
- Not multi-tenant, no encryption at rest.
- Secret-to-consumer linking is a name match, not proof of use.

## 10. Next

Live GCP and Azure adapters, a Bedrock collector, dependency and SBOM scanning, network evidence,
authentication and tenancy, parallel scanning, generated API types for the frontend, and reopening
reviews when a verdict changes.