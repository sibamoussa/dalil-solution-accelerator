# Dalil

Microsoft Fluent-inspired policy conversation accelerator using Microsoft Agent
Framework, Azure AI Search Foundry IQ, and Azure OpenAI. Public-source demonstration,
not an official Microsoft or government product or legal advice.

## Start Here

### Deploy end to end in a customer tenant

Use this path when the tenant does not already have Dalil's Azure services. The deployment
creates a dedicated Azure AI Search service with Foundry IQ, Azure OpenAI chat and
embedding deployments, Document Intelligence, managed identity and role assignments,
monitoring, Key Vault, a container registry, and the Container Apps app. You do **not**
need to create a separate Microsoft Foundry project or Search service first.

The deployment currently places the application stack in **UAE North**. Before starting,
confirm the tenant permits those services and model deployments in that region, has
available quota, and meets your data-residency and policy requirements. The deploying
identity needs permission to create subscription-scoped deployments/resources and role
assignments (typically Contributor plus User Access Administrator, or an equivalent
custom role). Review the cost section before provisioning. Source documents must be
approved for download and processing; public availability alone is not permission.

1. Install Python 3.13, Azure CLI, and PowerShell 7. From a PowerShell terminal, clone the
  repository and enter its folder:

  ```powershell
  git clone https://github.com/sibamoussa/dalil-solution-accelerator.git
  cd dalil-solution-accelerator
  ```

2. Create the Python environment, install the pinned dependencies, sign in, and select
  the customer subscription:

  ```powershell
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
  az login
  az account set --subscription <SUBSCRIPTION_ID>
  az account show --query "{name:name,id:id,state:state}" --output table
  ```

  Confirm that the displayed subscription is the intended customer tenant/subscription.
  Docker is not required; the deployment builds the image in the customer's Azure
  Container Registry.

3. Generate a separate customer profile for the policy website:

  ```powershell
  .\.venv\Scripts\python.exe configure_accelerator.py `
    --website https://policies.example.org/policies `
    --name policies `
    --output customer.json
  ```

  Replace the example website and collection name with the customer's values. Edit
  `customer.json` for supported branding and model settings; see [Configure Once](#configure-once).
  Keep credentials and keys out of this file.

4. Discover candidate documents and review the generated manifest:

  ```powershell
  .\.venv\Scripts\python.exe policy_sources.py `
    --config customer.json `
    --output sources/policies.json
  ```

  Open `sources/policies.json`. Verify every title and URL, remove documents that should
  not be included, and check `skipped` and `truncated`. The deployment will ingest the
  reviewed manifest to the new Foundry IQ knowledge source and knowledge base.

5. Run the customer deployment:

  ```powershell
  .\deploy-customer.ps1 `
    -Subscription <SUBSCRIPTION_ID> `
    -Website https://policies.example.org/policies `
    -Name policies `
    -ConfigPath customer.json
  ```

  The script checks quota/model capacity, shows the exact manifest and asks you to type
  `INGEST` to approve OCR and upload. It then previews the Bicep deployment with
  `what-if`; inspect the resources and type `DEPLOY` to authorize billable provisioning.
  It provisions the stack, ingests and verifies the files, builds the app image in ACR,
  deploys the Container App, and checks its `/healthz` endpoint. If the project resource
  group already exists, deployment stops unless you explicitly pass `-UpdateExisting`
  after reviewing the what-if. It does not silently change region or model when quota or
  capacity is unavailable.

6. Open the HTTPS URL printed at completion. Ask a question answerable from a reviewed
  document and verify the cited source. The browser's **Save conversations** option is
  disabled until Cosmos history is separately provisioned and explicitly enabled.

This flow removes the need to manually create Foundry IQ, Search, OpenAI, or app resources,
but intentionally retains source-review, cost, and deployment approval gates. A tenant
administrator may need to grant permissions or resolve quota, policy, and model availability
before deployment can succeed.

## Configure Once

Use one JSON profile for supported customer settings: [accelerator.json](accelerator.json)
for the bundled demo, or generate `customer.json` for your own collection. You do not
need to edit Python files, PowerShell scripts, or Bicep for ordinary configuration.

| Profile section | Change here |
| --- | --- |
| `source` | Website, allowed hosts/paths, document limits and manifest path |
| `branding` | Name, organization, logo path and accent color |
| `resources` | Collection names, environment and Azure model/deployment settings |
| `history` | Capability flag, database/container names and retention days |
| `deployment` | Subscription, existing resource group/app/registry, local port and optional Cosmos region |
| `runtime` | Model provider, Compass endpoint/header, existing service endpoints, response-language and quality/retrieval settings |

For example, open `customer.json` and find its top-level `runtime` object. Change or add
the entries below **inside that object**. This is only the `runtime` section; keep the
rest of the profile (`source`, `branding`, `resources`, `history`, and `deployment`) as it
is. Preserve any other runtime entries you already use.

```json
{
  "runtime": {
    "MODEL_PROVIDER": "compass",
    "COMPASS_ENDPOINT": "https://gateway.example/openai/deployments/my-model/chat/completions?api-version=2024-10-21",
    "COMPASS_AUTH_HEADER": "api-key",
    "SEARCH_ENDPOINT": "https://<search-service>.search.windows.net",
    "MATCH_RESPONSE_LANGUAGE_TO_QUESTION": true,
    "SEARCH_TOP_K": 8,
    "GROUNDEDNESS_CHECK_ENABLED": true
  }
}
```

In the actual profile, `runtime` sits alongside the other top-level sections; do not
replace the full profile with the example above. Replace the example Search host with
your Search service endpoint. Compass handles model calls, but retrieval still needs
Azure AI Search and a configured Foundry IQ knowledge base.

Never put credentials in JSON. Supply `COMPASS_API_KEY` separately through a secure
local process/secret manager, or configure it as a Container Apps secret reference for
a deployed app. The profile validator rejects unknown settings and secret fields.

For local use, sign in to Azure CLI (the signed-in identity needs access to Search),
provide `COMPASS_API_KEY` securely in the process environment, then validate and start
the same profile:

```powershell
az login
.\.venv\Scripts\python.exe configure_accelerator.py --check customer.json
.\run-local.ps1 -Config customer.json -Port 8769
```

The validation command checks the profile and prints normalized non-secret settings; it
does not deploy resources. The runner loads `customer.json` and starts the app locally.
After stopping the app, remove the process key with `Remove-Item Env:COMPASS_API_KEY`.

For local chat, set `runtime.SEARCH_ENDPOINT` and, for Azure, `runtime.AOAI_CHAT_ENDPOINT`
to your existing services. Compass reads `runtime.COMPASS_ENDPOINT` instead. Explicit
process environment settings take precedence over profile defaults; local command
arguments override the corresponding runner setting. Restart after changing the profile.

For a new stack, set `deployment.subscription`, then run
`deploy-customer.ps1 -ConfigPath customer.json`; names, website and environment are read
from the profile. Cosmos creation still requires `-EnableConversationHistory` and consent.
For an existing stack, fill `deployment.resourceGroup`, `containerApp` and `registry`,
then run `deploy.ps1 -Config customer.json -SyncEnv` to rebuild and apply runtime settings.
An optional private `.env` supplies explicit overrides, but is no longer required.
Review the target subscription before deploying; these commands incur charges.

Changes are not live edits: local changes require a restart; deployed changes require
an image rebuild/rollout. Source changes also require rediscovery, document review and
ingestion. This profile does not support arbitrary region migrations, network topology,
new API behavior or other code/infrastructure redesigns.

## Run the Solution

Choose one run mode. Commands below are for Windows PowerShell and run from the Dalil
repository root. Python 3.13 is required.

### A. Run locally with Azure-backed chat

You need an existing Dalil Search service with a populated Foundry IQ knowledge base,
and an OpenAI account with the configured model deployments. Sign in with Azure CLI;
your identity needs Search Index Data Reader and Cognitive Services OpenAI User on those
resources. The app and local runner refuse to start until both endpoints are configured.

```powershell
az login
.\run-local.ps1 -Config accelerator.json -SearchService <SEARCH_NAME> -OpenAIAccount <OPENAI_ACCOUNT_NAME> -Port 8769
```

Use `-Config customer.json` for a separate customer profile. Local Cosmos history is
optional: add `-CosmosEndpoint <COSMOS_ENDPOINT>` only when that account already exists
and your Azure CLI identity has Cosmos data-plane permission. The deployed app uses its
managed identity instead.

### B. Deploy a new customer collection

For a tenant without existing Dalil services, follow the numbered [end-to-end customer
deployment steps](#deploy-end-to-end-in-a-customer-tenant) above. This provisions billable
Azure resources, ingests the reviewed manifest, builds the app image in the customer's
registry, and deploys an isolated Container App stack.

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

The primary choice is now `runtime.MODEL_PROVIDER` in your single JSON profile. Set
`runtime.COMPASS_ENDPOINT` and `runtime.COMPASS_AUTH_HEADER` there for Compass; the
environment variables and runner flags below are optional explicit overrides.

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
command in section A with `-ModelProvider azure_openai` (or omit the option).

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
| Choose Azure or Compass | `runtime.MODEL_PROVIDER` in the selected JSON profile (`azure_openai` or `compass`) | Selects the provider for synthesis, query rewriting, and verification. Environment/runner overrides remain optional. |
| Change Azure model deployments | `resources.chatModel*` and `resources.embeddingModel*` in `customer.json` | Azure model, version, SKU, deployment name, and capacity. These fields do not select the Compass model. Azure retrieval/embedding dependencies remain required with Compass. |
| Choose a Compass model | `runtime.COMPASS_ENDPOINT` and `runtime.COMPASS_AUTH_HEADER` in the selected JSON profile | The full APIM URL selects the model. Choose `api-key` or `Ocp-Apim-Subscription-Key`. Only the secret `COMPASS_API_KEY` stays outside JSON, as a process secret or Container Apps secret reference. |
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

The command for a new customer collection is in the [end-to-end customer deployment steps](#deploy-end-to-end-in-a-customer-tenant).
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

`.env` is an optional override file for `deploy.ps1`; it may contain secrets and must
never be committed. Prefer the JSON profile for non-secret settings. It is not required
when deployment targets are populated in that profile, and is not read by
`run-local.ps1` or `deploy-customer.ps1`.

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