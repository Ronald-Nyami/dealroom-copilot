# Security and data protection

There are two separate protections, because they cover different risks.

## Anonymisation before documents leave the machine

`Anonymiser.redact_pdf` rewrites a PDF before it is sent to Document Intelligence: names, emails, phone numbers, IBAN-like strings and addresses become placeholders such as `[PERSON_001]`. Image-only pages are OCR'd locally first, and the matching word boxes are blacked out in the image. Extracted text is masked again with the same vault, so the index and every model prompt only contain placeholders. Questions are masked the same way before search.

The vault (placeholder to original) stays on the server. The masking log stores the type, the placeholder and a SHA-256 prefix, never the value. `tests/test_ingestion.py` checks that a remote extractor only receives redacted bytes.

Person detection uses a first-name list plus a capitalised surname. It finds all ten personal-data strings in the synthetic data room, but it would miss names outside the list; for real documents it should be replaced by an NER model behind the same interface.

## Private endpoints and certificate authentication

In the Terraform configuration, Azure OpenAI and Document Intelligence have public network access and key authentication turned off, so they are reachable only through private endpoints. The backend signs in as an Entra ID service principal with a private key and an X.509 certificate (a signed JWT client assertion, no client secret). The certificate is generated inside Key Vault and mounted read-only into the pods by the Secrets Store CSI driver, using a workload identity that may read that one secret.

The certificate code (`ingestion/azure_auth.py`) is tested with a generated key and a mocked token endpoint. It has not been run against a real Entra ID tenant.

## Around them

- Roles: analysts read and record diligence items, associates also draft, partners also approve and export. Anything not listed is refused. The web API and the MCP server use the same guard.
- Tool arguments are validated with strict Pydantic models before anything runs.
- `export_memo` first returns an approval id and runs once, after a partner approves that id.
- Every call, refusal, approval and review decision is written to a JSONL log in which each line holds the hash of the previous one. `AuditLog.verify` reports the first edited line.
- In the cluster, the ingress authenticates users with Entra ID (oauth2-proxy) and sets the `X-User` and `X-Role` headers the backend trusts. Network policies deny ingress by default. Locally, the role comes from a dropdown in the UI.
