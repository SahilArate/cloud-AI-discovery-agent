# ai-discovery-agent

Discovers AI usage across AWS, GCP and Azure, builds an AI inventory aligned with the
ISO/IEC 42001 (AIMS) fields, flags potential shadow AI, and routes LLM work to the cheapest
model that does the job.

![Inventory](docs/screenshots/inventory.png)

## The three questions it keeps separate

1. **Is it AI?** Verdict: `ai_confirmed`, `ai_suspected`, `not_ai_evidenced`, `unknown`.
2. **Is it being used?** Activity: observed, dormant, none observed, unknown.
3. **Is it approved?** Approved, potential shadow AI, governance exception, not assessed.

## Status: what is real and what is simulated

| Area | State |
|---|---|
| AWS collector (Lambda, SageMaker, EC2, Secrets Manager) | Built. Tested against **moto** (fake AWS). Never run on a live account. |
| AWS `--mode live` | Code path exists, **untested**. |
| GCP and Azure collectors | Built behind injected API interfaces. Run on **fixture data** only. No live adapters. |
| Detection, enrichment, governance | Built and unit tested. |
| Evidence: managed services, secret and env var names, GPU types, name hints, AI-named Lambda layers | Built. |
| Secret to consumer linking | Name match only, not proof of use. |
| CloudTrail owner hints | Built, tested with fakes. Moto does not implement `LookupEvents`. |
| CloudWatch usage (Lambda, SageMaker endpoints) | Built. Tested against moto metrics. |
| LLM inspector and router | Built. Tested with a fake provider. Real Groq calls verified by hand. |
| Postgres, API, Next.js dashboard, review queue | Built and tested. |
| Eval harness | Built. Labels cover the demo estate only. |
| Network/DNS evidence, SBOM scanning, SaaS discovery | Not built. |

## Architecture

```
Catalog (YAML) -> Collector (read-only, no LLM) -> Evidence rules -> Verdict rules
   -> [ambiguous only] LLM inspector via router -> Owner + usage enrichment
   -> Approval check vs register -> Postgres (append-only) -> FastAPI -> Next.js
```

Key decisions:

- **Rules decide first.** The LLM only sees ambiguous findings and can never return `ai_confirmed`.
  Without a key, or if the provider fails, the rules result stands and stays in review.
- **No secret values.** Only names are collected. Tests search outputs and the database for planted values.
- **Owner is an explicit tag or unknown.** A CloudTrail creator is labelled `inferred_creator`.
- **Coverage is recorded** for every scope, so a scan shows what it could not see.
- **History is append-only**, which gives new and missing assets between scans.
- **Least privilege.** `docs/aws-readonly-policy.json` is generated from the catalog, with an explicit
  deny on secret values. See `docs/threat-model.md`.

## LLM routing and cost

Requests start on the small model and escalate to the large one only when output fails
validation. Provider outages do not escalate. A budget cap blocks calls, and the call log
(no prompt text) is stored per scan. The `/costs` page shows calls per tier, escalations, actual
cost and an estimated all-large cost. Prices in `.env` are placeholders: verify them before
quoting any figure.

![LLM cost](docs/screenshots/costs.png)

## Evaluation

`python -m ai_discovery.evals.scoring` scores the latest three-cloud scan against hand-written
labels (`evals/ground_truth.py`): detection precision and recall, verdict and approval accuracy,
shadow AI precision and recall, and coverage. Labels were written before scoring.
Replace this line with your real numbers: detection P=__, R=__; shadow P=__, R=__.
The estate is small and invented, so 100% here says the pipeline is consistent, not that it
would score that on a real account.

## Run it

Needs Python 3.11, Docker and Node 18.18+.

```bash
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e ".[dev]"
copy .env.example .env
docker compose up -d
alembic upgrade head
python -m ai_discovery scan --mode mock --clouds aws gcp azure --register data/approved_register.yaml --no-llm
python -m uvicorn ai_discovery.api.main:app --reload
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. Drop `--no-llm` and set `GROQ_API_KEY` to enable the inspector.
Tests: `pytest` (needs the `ai_discovery_test` database, see below).

```bash
docker exec -it ai-discovery-db psql -U discovery -d ai_discovery -c "CREATE DATABASE ai_discovery_test;"
```

Windows notes: if SQLAlchemy fails with an Application Control DLL error, set
`DISABLE_SQLALCHEMY_CEXT_RUNTIME=1`.

## Limitations

- Everything is tested on mocks and fixtures. Rate limits, pagination at scale and real IAM
  enforcement are untested.
- Hidden AI is found from names, tags, layer names, GPU types and secret names. There is no code,
  SBOM, IAM-permission or network evidence, so quiet or well-named AI will be missed.
- Rules are hand-set, not calibrated against labelled real data.
- The inventory shows assets from the latest scan only. A partial scan hides other clouds' assets.
- The review API has no authentication, and reviewer names are self-declared. A later scan that
  changes a verdict does not reopen an earlier approval.
- A crashed scan leaves no `scan_runs` row.
- Not multi-tenant. No encryption at rest.
- The all-large cost is an estimate from the small model's token counts.

## Next

Live GCP and Azure adapters, a Bedrock collector, dependency and SBOM scanning, network evidence,
authentication and tenancy, generated API types for the frontend, reopening reviews on change.