# ai-discovery-agent

Discovers AI usage across cloud accounts, builds an AI inventory aligned with
ISO/IEC 42001 (AIMS) fields, and flags potential shadow AI.

## What it answers

1. **What AI exists in our cloud?** Owner, hosting, usage, evidence, one-line reasoning.
2. **Is it approved?** Compared against an approved register, with reason codes.
3. **Which LLM should do the work, at least cost?** A small router with escalation and a budget cap.

## Status (read this first)

| Area | State |
|---|---|
| AWS collector (Lambda, SageMaker, EC2, Secrets Manager) | Built, tested against **moto** (fake AWS). Never run against a live account. |
| AWS live mode | Code path exists (`--mode live`), **untested**. |
| GCP and Azure collectors | Not built yet. Same `BaseCollector` interface. |
| Detection, enrichment, governance | Built and unit tested. |
| LLM inspector and router | Built. Tested with a fake provider. Groq is the default provider. |
| Postgres storage, API | Built and tested against a real Postgres. |
| Dashboard | Not built. API docs at `/docs`. |

## How it works

```
Catalog (YAML) -> Collector (read-only, no LLM)
  -> Evidence rules -> Verdict rules
  -> [ambiguous only] LLM inspector via router
  -> Owner + usage enrichment -> Approval check vs register
  -> Postgres (append-only observations) -> API
```

Key decisions:

- **Discovery, classification and approval are separate questions.** Each has its own field.
- **Verdicts are `ai_confirmed`, `ai_suspected`, `not_ai_evidenced`, `unknown`.** Rules, not scores:
  a managed AI service is strong evidence; an `OPENAI_API_KEY` name is only a lead.
- **Activity is separate from the verdict.** An idle endpoint is still AI.
- **The LLM is optional.** Without a key, or if the provider fails, the rules result stands
  and the item stays in review. The inspector can never return `ai_confirmed`.
- **No secret values, ever.** Only env var and secret *names* are collected. Tested down to the database.
- **Owner is an explicit tag or unknown.** A creator is never passed off as the owner.
- **Coverage is recorded.** Denied calls and failed scopes are stored, so a scan can show what it could not see.
- **History is append-only.** Each scan adds observations, which gives new and missing assets.

## AIMS field mapping

| Group | Fields stored |
|---|---|
| Identity | asset_key (provider + native id), name, provider, account |
| Technical | service, region, hosting_type |
| Ownership | owner, owner_source |
| Usage | usage_count with usage_window_days, activity_status |
| Governance | approval_status, risk_tier, reason codes, review_required |
| Discovery | evidence records, decided_by, reasoning, first_seen, last_seen |

Not captured yet: data sensitivity, linked policies, review dates.

## Shadow AI

`potential_shadow_ai` means AI was found and is not in the approved register. Matching uses
provider, native resource id, account, region and owner, not the name. Registered but
drifted assets (for example an unapproved region) are `governance_exception`. The risk
policy is a short rule table in `governance/shadow.py`, never decided by the LLM.

Not covered: AI SaaS used outside the cloud account, and network or DNS evidence.

## LLM routing and cost

Every request starts on the small model and escalates to the large one only when the output
fails validation. Provider outages do not escalate. A budget cap blocks calls, and every call
is logged without prompt text. The CLI prints calls per tier, escalations and cost, plus an
estimate of the all-large cost. Prices are configurable and the defaults are unverified
placeholders, so check them before quoting any numbers.

## Run it

Needs Python 3.11 and Docker.

```bash
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e ".[dev]"
copy .env.example .env
docker compose up -d
alembic upgrade head
python -m ai_discovery scan --mode mock --register data/approved_register.yaml --no-llm
python -m uvicorn ai_discovery.api.main:app --reload
pytest
```

Mock mode builds a fake messy AWS account in moto. Drop `--no-llm` and set `GROQ_API_KEY`
in `.env` to enable the inspector.

API: `/health`, `/inventory`, `/assets/{asset_key}`, `/coverage/latest`, `/changes`, `/docs`.

Windows note: if SQLAlchemy fails with an Application Control DLL error, set
`DISABLE_SQLALCHEMY_CEXT_RUNTIME=1`. If `ai_discovery` is not importable, set `PYTHONPATH=src`.

## Limitations

- Tested against moto, not a real account. Rate limits and pagination at scale are untested.
- Hidden AI in compute is found by env var names, GPU types and name hints only. There is no
  dependency, SBOM, IAM or network evidence yet.
- The AWS catalog lists the API calls we use, but the IAM policy is not generated from it yet.
- Fusion rules are hand-set and not calibrated against labelled data.
- A crashed scan leaves no `scan_runs` row.
- Secret resources appear as their own assets rather than being linked to the resources that use them.

## Next

GCP and Azure collectors, a dashboard, an evaluation harness with precision and recall,
IAM policy generation, CloudTrail owner hints.