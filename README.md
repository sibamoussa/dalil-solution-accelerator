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

## Choose the Model Provider

| Option | Setting | Application model calls |
| --- | --- | --- |
| Azure OpenAI (default) | `MODEL_PROVIDER=azure_openai` | Uses the configured Azure model deployments and managed identity/Azure CLI authentication. |
| Bring your own model through Compass APIM | `MODEL_PROVIDER=compass` | Uses one APIM deployment URL for synthesis, query rewriting and verification. |

This choice is server configuration, not a browser control. **Both options still require
Azure AI Search/Foundry IQ retrieval and Azure embedding deployments for ingestion and
retrieval.** The new-customer bootstrap still provisions those Azure resources, including
the Azure chat deployment used by Foundry IQ. Compass does not remove that dependency.

### Use Compass locally

Obtain the full deployment URL and subscription key from your Compass/APIM owner.
The URL must look like
`https://<APIM_HOST>/<API_PATH>/deployments/<DEPLOYMENT>/chat/completions?api-version=2024-10-21`.
Use the actual API version supplied by the owner. The deployment name in the URL selects
the model; no separate Compass model setting is required.

Set `COMPASS_API_KEY` in your process environment using a secure secret-injection tool
or a private terminal prompt. Do not put it in the customer profile, command-line
arguments, repository, or browser. In PowerShell 7.4+, set it privately with
`$env:COMPASS_API_KEY = Read-Host 'Compass APIM subscription key' -MaskInput`, then run:

```powershell
az login
.\run-local.ps1 -Config accelerator.json -SearchService <SEARCH_NAME> -ModelProvider compass -CompassEndpoint "https://<APIM_HOST>/<API_PATH>/deployments/<DEPLOYMENT>/chat/completions?api-version=2024-10-21" -CompassAuthHeader api-key
```

After stopping the local server, remove the process credential with
`Remove-Item Env:COMPASS_API_KEY`.

If your gateway expects `Ocp-Apim-Subscription-Key`, use that value for
`-CompassAuthHeader`. No bearer prefix is added. To return to Azure, run the local
command in section B with `-ModelProvider azure_openai` (or omit the option).

### Use Compass in an existing Container App

Build/deploy the updated code first. In the Azure portal, create a Container Apps secret
named `compass-api-key`, then set these environment variables on the application container:

| Environment variable | Value |
| --- | --- |
| `MODEL_PROVIDER` | `compass` |
| `COMPASS_ENDPOINT` | Your full HTTPS APIM deployment URL, including `api-version` |
| `COMPASS_AUTH_HEADER` | `api-key` or `Ocp-Apim-Subscription-Key` |
| `COMPASS_API_KEY` | Secret reference to `compass-api-key`, not a plain-text value |

Keep the existing Search and history settings. To switch back, set `MODEL_PROVIDER` to
`azure_openai` and ensure the `AOAI_*` endpoint settings are present. Use
[.env.example](.env.example) as the settings reference. **Do not use `deploy.ps1 -SyncEnv`
to upload a plain-text Compass key.** The local runner does not automatically load `.env`.

Compass must return OpenAI chat-completions responses and support Dalil's structured
JSON output requests (`json_schema` and `json_object`). Unsupported requests fail the
model stage without silently falling back to Azure or disabling groundedness verification.
This adapter has mocked HTTP coverage for routing and both key headers; live Compass
model capabilities are not yet verified. Confirm authorization to send policy excerpts
and questions to that external provider, including its residency and retention terms.

## What to Change

**For model changes, choose the provider first.** Azure deployment settings belong in
the customer profile; Compass settings belong in the server environment or local-runner
options. See [Choose the Model Provider](#choose-the-model-provider) for the commands.

| Goal | Edit this | What it changes |
| --- | --- | --- |
| Use another policy website | Generate a new `customer.json` with `configure_accelerator.py` | Source URL, initial allowed host/path, resource collection names. The generator refuses to overwrite a profile. |
| Restrict crawling | `source.allowedHosts`, `source.pathPrefixes`, `maxDocuments`, `maxPages` in `customer.json` | Which public pages/files discovery may consider. Keep hosts and paths narrow. |
| Select documents | `sources/<collection>.json` after `policy_sources.py` | The reviewed `documents` list actually sent to ingestion. Check `skipped` and `truncated`. |
| Change branding | `branding.title`, `organization`, `shortName`, `accentColor`, `logo` in `customer.json` | Application title, organization, theme accent, and image. Put the image under `webapp/assets/`; use a path like `/assets/customer-logo.png`. |
| Choose Azure or Compass | `MODEL_PROVIDER=azure_openai` or `MODEL_PROVIDER=compass` in the server environment; locally use `-ModelProvider` | Selects the provider for synthesis, query rewriting, and verification. Azure is the default. |
| Change Azure model deployments | `resources.chatModel*` and `resources.embeddingModel*` in `customer.json` | Azure model, version, SKU, deployment name, and capacity. These fields do not select the Compass model. Azure retrieval/embedding dependencies remain required with Compass. |
| Choose a Compass model | `COMPASS_ENDPOINT` and `COMPASS_AUTH_HEADER` in the server environment; locally use `-CompassEndpoint` and `-CompassAuthHeader` | The deployment name in the full APIM URL selects the Compass model. Choose `api-key` or `Ocp-Apim-Subscription-Key`; provide `COMPASS_API_KEY` securely as a process secret or Container Apps secret reference. Do not put these settings or the key in `customer.json`. |
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

The eight-file manifest is `sources/gazettes-2026.json`. This path uses Foundry IQ
file knowledge sources, Azure AI Search, Azure OpenAI embeddings, and Document
Intelligence Read OCR. It is separate from customer website discovery. Public
availability is not a redistribution license; the repository stores the source URLs,
not repackaged PDFs.

Use a clean Python 3.13 environment. The operator needs Azure CLI access, Document
Intelligence OCR permission, and permission to manage the Search knowledge source and
indexed content. The running application uses managed identity; ingestion can use the
operator's `az login`. `SEARCH_KEY` is optional and must never be committed or printed.

```powershell
python -m venv .venv-ingestion
.\.venv-ingestion\Scripts\python.exe -m pip install -r requirements-foundry-ingestion.txt
az login
```

Validate/download the pinned files first. This does not upload or run billable OCR:

```powershell
.\.venv-ingestion\Scripts\python.exe ingest_gazettes_foundry.py --manifest sources/gazettes-2026.json --search-endpoint https://<SEARCH_NAME>.search.windows.net --openai-endpoint https://<OPENAI_ACCOUNT>.openai.azure.com --document-intelligence-endpoint https://<DOCUMENT_INTELLIGENCE_ACCOUNT>.cognitiveservices.azure.com
```

After reviewing the manifest, URLs, rights, and costs, repeat with `--apply` to ingest.
The script creates/uses source `dalil-gazettes-2026` and knowledge base
`dalil-policies-2026`. SHA checks and an OCR-version marker skip unchanged remote files;
changed, duplicate, failed, or unexpected files stop for review. Rerun to resume and
verify idempotence. The Foundry IQ file-source API is preview, so inspect the resulting
Arabic text and citations after ingestion.

For a generated customer collection, `ingest_policies.py --config customer.json
--search-endpoint ... --openai-endpoint ... --document-intelligence-endpoint ...` validates
without applying. Add `--apply` only after reviewing the manifest. It requires the
services to exist already; `deploy-customer.ps1` invokes this flow during deployment.

## Azure Deployment Notes

The command for a new customer collection is in [Start Here](#c-deploy-a-new-customer-collection).
It targets an isolated UAE North application stack; Cosmos has its own optional region.
Each customer must check model availability, service capacity, governance, data residency,
permissions, and cost in their own subscription. The generic Azure quota CLI does not
report Cosmos capacity. GlobalStandard model processing may occur outside the resource
region; verify model residency requirements separately.

The current Dalil demo has been deployed and verified, including optional browser
history in Sweden Central. It is an example, not a subscription or resource set for
customers to reuse. See [DALIL_AZURE_ARCHITECTURE.md](DALIL_AZURE_ARCHITECTURE.md) for
the service map. For updates to an existing deployment, review [deploy.ps1](deploy.ps1)
and the [`.env.example` template](.env.example). To use `deploy.ps1`, copy the template to a local `.env` and fill in its placeholders:

```powershell
Copy-Item .env.example .env
```

`.env` contains deployment-specific settings and may contain secrets; it is git-ignored and must never be committed. The `.env` file is for `deploy.ps1` (updating an existing deployment). It is not required for `run-local.ps1` or the new-customer `deploy-customer.ps1` workflow above.

### Cost Snapshot

UAE North retail rates checked 2026-10-09: Azure AI Search Basic is $0.101/hour
($73.73 for 730 hours); ACR Basic is $0.1666/day (about $5.00 for 30 days), plus
$0.10/GB-month of registry storage. This partial fixed baseline is about $78.73/month
for continuously provisioned Search and ACR, before usage. Container Apps Consumption
is $0.000024/vCPU-second and $0.000003/GiB-second active; 0.5 vCPU/1 GiB for 8 hours
per day is about $12.96 per 30-day month before free grants. Cosmos Serverless is
$0.311 per million request units plus $0.33/GB-month stored. Model tokens, OCR, logs,
storage transactions, egress, taxes, and regional price differences are excluded. This
is not a complete estimate or spending cap; monitor usage and set a budget.

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