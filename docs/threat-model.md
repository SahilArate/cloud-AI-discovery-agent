# Threat model

## What we protect

- Client cloud accounts (we only read them).
- Secret values, which must never enter this system.
- Client resource metadata (names, tag keys, env var names), which goes to an LLM only
  when a finding is ambiguous.

## How access works

The client creates a read-only role from `docs/aws-readonly-policy.json` and lets the scanner
assume it. The policy is generated from the discovery catalog, so permissions match code.
The role should trust only the scanner's principal and require an **external ID** on
`sts:AssumeRole`, to prevent confused-deputy use. An explicit Deny blocks
`secretsmanager:GetSecretValue` and SSM parameter reads.

## Threats and controls

| Threat | Control | Residual risk |
|---|---|---|
| Scanner writes to or changes a client account | Read-only policy; collectors only list and describe | Moto does not enforce IAM, so this is untested against real AWS |
| Secret values leak into storage or logs | Collectors keep only names; values are dropped in-process; tests search outputs and the database for planted values | See next row |
| `lambda:ListFunctions` returns env var values | Cannot be avoided: the API returns them. They are dropped immediately inside the collector and never stored or logged | Values exist briefly in scanner memory |
| Prompt injection through resource names or tags | Inspector has no tools; untrusted text sits in the data message only; tag values are not sent; verdict set is capped (never `ai_confirmed`); cited evidence IDs are checked | A model could still mislead a reviewer, so every LLM verdict stays `review_required` |
| Resource metadata sent to an LLM provider | Only ambiguous findings go out; payload is names, tag keys, env var names and evidence text | Names can be sensitive. A regulated client needs an approved provider |
| LLM outage or overspend | LLM is optional; budget cap; provider errors fall back to the rules result | None significant |
| Tampering with history | Observations are append-only by design | The database role used by the app can still modify rows. Production needs DB-level controls |
| Credentials committed to git | `.env` is ignored; `.env.example` holds blanks | Developer error |

## Out of scope for this proof of concept

GCP and Azure live adapters (they run from fixtures), authentication on the API, multi-tenant
isolation, encryption at rest, and network or DNS evidence.