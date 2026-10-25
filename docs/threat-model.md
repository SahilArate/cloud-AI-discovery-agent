# Threat model

## What we protect

- Client cloud accounts (we only read them).
- Secret values, which must never enter this system.
- Client resource metadata (names, tag keys, env var names), which goes to an LLM only
  when a finding is ambiguous.

## How access works

**Target design:** the client creates a read-only role from `docs/aws-readonly-policy.json` and lets the
scanner assume it. The role trusts only the scanner's principal and requires an **external ID** on
`sts:AssumeRole`, to prevent confused-deputy use. An explicit Deny blocks
`secretsmanager:GetSecretValue` and SSM parameter reads.

**What the code does today:** it uses whatever AWS credentials the environment provides (for example a
named profile for a read-only user). Role assumption with an external ID is **not implemented**. Before
any scan, live mode calls `sts:GetCallerIdentity` and refuses to run if the account differs from `--account-id`.
The policy is generated from the discovery catalog, so permissions match code, but it has never been
enforced by a real account.

## Threats and controls

| Threat | Control | Residual risk |
|---|---|---|
| Scanner writes to or changes a client account | Read-only policy; collectors only list and describe | Moto does not enforce IAM, so this is untested against real AWS |
| Scanner runs against the wrong account | STS identity check before a live scan | None known |
| Secret values leak into storage or logs | Collectors keep only names; values are dropped in-process; tests search outputs and the database for planted values | See next row |
| `lambda:ListFunctions` returns env var values | Cannot be avoided: the API returns them. They are dropped immediately inside the collector and never stored or logged | Values exist briefly in scanner memory |
| Prompt injection through resource names or tags | Inspector has no tools; untrusted text sits in the data message only; tag values are not sent; verdict set is capped (never `ai_confirmed`); cited evidence IDs are checked | A model could still mislead a reviewer, so every LLM verdict stays `review_required` |
| Resource metadata sent to an LLM provider | Only ambiguous findings go out; payload is names, tag keys, env var names and evidence text | Names can be sensitive. A regulated client needs an approved provider |
| LLM outage or overspend | LLM is optional; budget cap; provider errors fall back to the rules result | None significant |
| Tampering with history | Observations are append-only by design | The database role used by the app can still modify rows. Production needs DB-level controls |
| Public demo is written to or abused | `DEMO_READ_ONLY=true` rejects review writes; CORS allow-list; the server holds no cloud or LLM keys | The read endpoints are public and unauthenticated, so the data must stay simulated |
| Credentials committed to git | `.env` and `.env.*` are ignored; `.env.example` holds blanks | Developer error. A connection string pasted into chat or a ticket must be rotated |

## Out of scope for this proof of concept

GCP and Azure live adapters (they run from fixtures), authentication on the API, multi-tenant
isolation, encryption at rest, role assumption with external ID, and network or DNS evidence.
