# Dalil

Microsoft Fluent-inspired policy conversation accelerator using Microsoft Agent
Framework, Azure AI Search Foundry IQ, and Azure OpenAI. Public-source demonstration,
not an official Microsoft or government product or legal advice.

## Start Here

Choose one run mode. Commands below are for Windows PowerShell and run from the Dalil
repository root. Python 3.13 is required.

### A. Open the UI locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\run-local.ps1
```

Open <http://127.0.0.1:8767>. The UI loads without Azure, but chat returns HTTP 503
until dedicated Azure Search and Azure OpenAI resource names are supplied. This is
intentional; Dalil does not generate mock answers or fall back to another project's data.

### B. Run locally with Azure-backed chat

You need an existing Dalil Search service and OpenAI account with the configured model
deployments. Sign in with Azure CLI; your identity needs Search Index Data Reader and
Cognitive Services OpenAI User on those resources.

```powershell
az login
.\run-local.ps1 -Config accelerator.json -SearchService <SEARCH_NAME> -OpenAIAccount <OPENAI_ACCOUNT_NAME> -Port 8769
```

Use `-Config customer.json` for a separate customer profile. Local Cosmos history is
optional: add `-CosmosEndpoint <COSMOS_ENDPOINT>` only when that account already exists
and your Azure CLI identity has Cosmos data-plane permission. The deployed app uses its
managed identity instead.

### C. Deploy a new customer collection

This provisions billable Azure resources, ingests reviewed documents, builds a container
in the customer's ACR, and deploys a Container App. It does not deploy into Dalil's
existing resource group.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
az login
.\.venv\Scripts\python.exe configure_accelerator.py --website https://policies.example.org/policies --name policies --output customer.json
.\.venv\Scripts\python.exe policy_sources.py --config customer.json --output sources/policies.json
```

Review `sources/policies.json`. Remove unrelated documents and check `skipped` and
`truncated`; public access is not permission to download or redistribute. Then deploy:

```powershell
.\deploy-customer.ps1 -Subscription <SUBSCRIPTION_ID> -Website https://policies.example.org/policies -Name policies -ConfigPath customer.json
```

The script requires you to type `INGEST`, previews a Bicep what-if, then requires
`DEPLOY`. Read the preview before approving. If a matching project resource group
already exists, deployment stops unless you explicitly add `-UpdateExisting` after
reviewing the preview. Model or regional capacity failures stop deployment; the script
does not silently choose another model or region.

Conversation history is a separate, billable Cosmos DB Serverless add-on. It is not
provisioned by the command above. To request it, explicitly choose a supported Cosmos
region:

```powershell
.\deploy-customer.ps1 -Subscription <SUBSCRIPTION_ID> -Website https://policies.example.org/policies -Name policies -ConfigPath customer.json -EnableConversationHistory -CosmosRegion swedencentral
```

The script asks for confirmation and an extra data-residency confirmation outside UAE
North. Supported-region listing is not a capacity guarantee; the generic Azure quota
CLI does not report Cosmos capacity. Check governance too: this Dalil subscription had
an inherited policy that disabled Cosmos public networking and required a resource-level
exception for its Container App to reach the database. Your subscription may differ.
Even after provisioning, each browser must enable **Save conversations** before chats
are persisted.

## What to Change

| Goal | Edit this | What it changes |
| --- | --- | --- |
| Use another policy website | Generate a new `customer.json` with `configure_accelerator.py` | Source URL, initial allowed host/path, resource collection names. The generator refuses to overwrite a profile. |
| Restrict crawling | `source.allowedHosts`, `source.pathPrefixes`, `maxDocuments`, `maxPages` in `customer.json` | Which public pages/files discovery may consider. Keep hosts and paths narrow. |
| Select documents | `sources/<collection>.json` after `policy_sources.py` | The reviewed `documents` list actually sent to ingestion. Check `skipped` and `truncated`. |
| Change branding | `branding.title`, `organization`, `shortName`, `accentColor`, `logo` in `customer.json` | Application title, organization, theme accent, and image. Put the image under `webapp/assets/`; use a path like `/assets/customer-logo.png`. |
| Change model deployments | `resources.chatModel*` and `embeddingModel*` in `customer.json` | Model, version, SKU, deployment name, and capacity. Confirm availability/quota in the target subscription and region first. |
| Change saved-history lifetime | `history.retentionDays` in `customer.json` | TTL/cookie lifetime. This does not provision Cosmos; use the explicit deployment switches above. |
| Change UI or answer behavior | `webapp/assets/` or `webapp/main.py` | Frontend appearance or chat behavior. Run tests, build a new image, and deploy it. |
| Change Azure resources | `infra/main.bicep`, `infra/modules/`, and deployment scripts | Infrastructure and regional placement. Preview a fresh what-if and review it before deploying. |

Do not edit `accelerator.json` to create a customer deployment: it is the checked-in
Dalil demo profile. Create a separate `customer.json` for each collection. Never put
credentials, access keys, tokens, or other secrets in either profile.

## Corpus

Eight Arabic 2026 Abu Dhabi Official Gazette PDFs, issues 1-8, are pinned in
[sources/gazettes-2026.json](sources/gazettes-2026.json). Arabic and English questions
are supported over the Arabic evidence. Answers follow the question's language;
English answers are not official translations of the Arabic source documents.
Documents are independently downloaded from the government's
[policy page](https://www.abudhabi.gov.ae/ar/policies-and-legislations).
No private corpus, older publications, or existing project's Search data is reused.

Public availability does not establish a redistribution license: the accelerator ships
URLs and code, not repackaged PDFs.

### Ingest the bundled gazettes

The eight-file manifest is `sources/gazettes-2026.json`. This ingestion path uses
Foundry IQ file knowledge sources, Azure AI Search, Azure OpenAI embeddings, and
Document Intelligence Read OCR. It is separate from the customer website discovery
flow above.

Install the ingestion-only dependencies in a clean environment and sign in with an
identity that can use the target services. The operator needs Document Intelligence
OCR permission and permission to manage the Search knowledge source/index. `SEARCH_KEY`
is optional for ingestion and must not be committed or printed; the running app uses
managed identity.

```powershell
python -m venv .venv-ingestion
.\.venv-ingestion\Scripts\python.exe -m pip install -r requirements-foundry-ingestion.txt
az login
```

First validate and download the pinned source files without uploading or running
billable OCR:

```powershell
.\.venv-ingestion\Scripts\python.exe ingest_gazettes_foundry.py --manifest sources/gazettes-2026.json --search-endpoint https://<SEARCH_NAME>.search.windows.net --openai-endpoint https://<OPENAI_ACCOUNT>.openai.azure.com --document-intelligence-endpoint https://<DOCUMENT_INTELLIGENCE_ACCOUNT>.cognitiveservices.azure.com
```

Only after reviewing the source manifest, costs, and permissions, repeat the command
with `--apply` to create/update the Foundry IQ file source and ingest. The command uses
the independent Dalil corpus; it never reads another project's Search index or storage.
SHA checks and an OCR-version marker skip unchanged remote files. Changed, duplicate,
failed, or unexpected files stop for review. Re-run the same command to resume and
verify idempotence. The Foundry IQ file-source API is preview; OCR and ingestion quality
must be verified against the resulting documents.

For a generated customer collection instead, use `ingest_policies.py --config
customer.json --search-endpoint ... --openai-endpoint ... --document-intelligence-endpoint
...` to validate without applying, then add `--apply` only after review. This direct
command requires already-provisioned services; `deploy-customer.ps1` runs ingestion as
part of its guided deployment flow.

## Azure Deployment Notes

The Dalil application is hosted on Azure Container Apps. This repository is a
customer-ready accelerator; it does not include customer credentials, deployment
records, or production resource identifiers. Browser conversation history is an
optional Cosmos DB Serverless add-on and is off for standard deployments. For a
deployment, choose a supported region that meets your data-residency requirements and
review the governance policies that apply to your subscription. The generic Azure quota
CLI does not expose Cosmos DB capacity. GlobalStandard model processing may occur
outside the resource region; confirm model data-residency requirements separately.

The customer deployment flow is in [Start Here](#c-deploy-a-new-customer-collection).
It creates an isolated UAE North app stack, with Cosmos in a separately chosen region.
The current Dalil deployment has been validated, but each customer must independently
check quota, model availability, governance, network policy, residency and costs. For
the service map, see [DALIL_AZURE_ARCHITECTURE.md](DALIL_AZURE_ARCHITECTURE.md).
For later releases of an existing deployment, review [deploy.ps1](deploy.ps1) and
[.env.example](.env.example); never commit the populated private environment file.

### Cost Snapshot

UAE North Retail Prices API rates checked 2026-10-09: Azure AI Search Basic is
$0.101/hour ($73.73 for 730 hours); ACR Basic is $0.1666/day ($5.00 for 30 days),
plus $0.10/GB-month of registry storage. That is a **partial fixed baseline of about
$78.73/month** for a continuously provisioned Search service and ACR, before any
usage. Container Apps Consumption is $0.000024/vCPU-second and $0.000003/GiB-second
active; at 0.5 vCPU and 1 GiB for 8 hours/day, the gross usage estimate is $12.96
for a 30-day month, before subscription free grants. Cosmos Serverless is $0.311 per
million request units plus $0.33/GB-month stored. OpenAI tokens, OCR pages, logs,
Storage transactions and content are variable and are not included. Actual regional
prices, free grants, taxes, quota and model availability can differ; this is not a
complete estimate or a spending cap.

## Safety and Limits

- Demo limits are per process: 12 combined chat/history requests per minute and 2
  concurrent requests. They are not a distributed security perimeter.
- Request bodies are limited to 32 KiB, questions to 4,000 characters, and history to
  10 messages. One worker and one Container App replica are configured by default.
- Citations must match the reviewed source manifest. Invalid citations abstain; failed
  enabled verification degrades to evidence excerpts rather than accepting claims.
- OCR may be inaccurate. Publication in 2026 does not prove current legal validity or
  applicability. Review sources and obtain permission to download/process them.
- History is tied to an anonymous browser cookie, not a user account. Shared browsers
  share that browser's history; losing the cookie loses access. Do not use for sensitive
  data without an appropriate authentication and access-control design.
- Turning saving off stops future writes but does not delete prior history. Use the
  delete action. Cosmos TTL applies to the browser record and resets when it changes;
  it does not guarantee physical per-conversation deletion at an exact age. Backups
  have separate retention.
- Questions still go to Search and the model when saving is off. History failures do
  not discard a successful answer.
- Lock files pin dependency versions but do not pin wheel hashes. Regenerate and test
  runtime/development locks when dependencies change; do not describe them as
  hash-verified supply-chain locks.

## Code Map

- UI: `webapp/assets/index.html`, `webapp/assets/dalil.css`, `webapp/assets/dalil.js`
- API and grounded response pipeline: `webapp/main.py`, `webapp/agent_runtime.py`,
  `webapp/grounded_workflow.py`
- Browser history: `webapp/conversation_history.py`
- Customer profile validation: `webapp/accelerator_config.py`
- Website discovery and document review: `policy_sources.py`
- Customer and pinned-gazette ingestion: `ingest_policies.py`, `ingest_gazettes_foundry.py`
- Infrastructure: `infra/main.bicep`, `infra/modules/`
- Local and Azure startup: `run-local.ps1`, `deploy-customer.ps1`