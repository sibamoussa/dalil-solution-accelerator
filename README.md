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
custom role). Review [costs](#cost-snapshot) before provisioning. Source documents must be
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
  document and verify the cited source. Without Cosmos history, conversation saving is
  unavailable. After provisioning Cosmos, each browser must turn on **Save conversations**
  before its chats are persisted.

#### Optional: conversation history

Cosmos DB history is a separate billable add-on. To add it after the main app is deployed,
rerun the customer deployment for the existing stack, explicitly enable history, and pick
a supported Cosmos region:

```powershell
.\deploy-customer.ps1 `
  -Subscription <SUBSCRIPTION_ID> `
  -Website https://policies.example.org/policies `
  -Name policies `
  -ConfigPath customer.json `
  -UpdateExisting `
  -EnableConversationHistory `
  -CosmosRegion <COSMOS_REGION>
```

The script asks for extra confirmation, including a residency confirmation when Cosmos is
outside UAE North. Region listing is not a capacity guarantee; the generic Azure quota CLI
does not report Cosmos capacity. Check regional capacity and governance before proceeding.

This flow removes the need to manually create Foundry IQ, Search, OpenAI, or app resources,
but intentionally retains source-review, cost, and deployment approval gates. A tenant
administrator may need to grant permissions or resolve quota, policy, and model availability
before deployment can succeed.

## Configure Once

Use [accelerator.json](accelerator.json) as the bundled demo profile, or generate a
separate `customer.json` for your collection. The profile groups source, branding,
resource, history, deployment, and runtime settings so normal setup does not require
editing application code or Bicep. See the [configuration reference](#configuration-reference)
for supported settings.

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

Never put credentials in JSON. Supply `COMPASS_API_KEY` through a local process or
secret manager, or as a Container Apps secret reference. The profile validator rejects
unknown settings and secret fields. For execution, follow either [the local run steps](#run-locally-with-existing-azure-services)
or the [new-customer deployment steps](#deploy-end-to-end-in-a-customer-tenant).

Changes are not live edits: local changes require a restart; deployed changes require
an image rebuild/rollout. Source changes also require rediscovery, document review and
ingestion. This profile does not support arbitrary region migrations, network topology,
new API behavior or other code/infrastructure redesigns.

## Run locally with existing Azure services

This is for development when you already have a populated Azure AI Search Foundry IQ
knowledge base and Azure OpenAI deployment. It does not create resources or ingest
documents. Use the end-to-end customer deployment above if those services do not exist.
Commands are for Windows PowerShell from the repository root; Python 3.13 is required.
The signed-in Azure CLI identity needs Search Index Data Reader and Cognitive Services
OpenAI User on those resources. The app and local runner refuse to start until both
endpoints are configured.

```powershell
az login
.\.venv\Scripts\python.exe configure_accelerator.py --check accelerator.json
.\run-local.ps1 -Config accelerator.json -SearchService <SEARCH_NAME> -OpenAIAccount <OPENAI_ACCOUNT_NAME> -Port 8769
```

Use `-Config customer.json` for a separate customer profile. Local Cosmos history is
optional: add `-CosmosEndpoint <COSMOS_ENDPOINT>` only when that account already exists
and your Azure CLI identity has Cosmos data-plane permission. The deployed app uses its
managed identity instead.


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
retrieval.** The customer deployment provisions Azure OpenAI chat for answers and an
embedding deployment for Foundry IQ ingestion/retrieval. Compass replaces the chat model;
it does not remove the Search or embedding dependency.

### Use Compass locally

Obtain the full deployment URL and subscription key from your Compass/APIM owner.
The URL must look like
`https://<APIM_HOST>/<API_PATH>/deployments/<DEPLOYMENT>/chat/completions?api-version=2024-10-21`.
Use the actual API version supplied by the owner. The deployment name in the URL selects
the model; no separate Compass model setting is required.

`COMPASS_API_KEY` is a secret, not a profile setting. Do not add it under `runtime`:
the profile validator intentionally rejects secret and unknown keys. The profile stores
only non-secret values such as `MODEL_PROVIDER`, `COMPASS_ENDPOINT`,
`COMPASS_AUTH_HEADER`, and `SEARCH_ENDPOINT`.

For a local run, open PowerShell 7.4+ in the repository. Enter the key at the masked
prompt; it is assigned only to that PowerShell process and inherited by the local app.
Then sign in to Azure CLI for Search access and start the app in the same terminal:

```powershell
$env:COMPASS_API_KEY = Read-Host 'Compass APIM subscription key' -MaskInput
az login
.\run-local.ps1 -Config accelerator.json -SearchService <SEARCH_NAME> -ModelProvider compass -CompassEndpoint "https://<APIM_HOST>/<API_PATH>/deployments/<DEPLOYMENT>/chat/completions?api-version=2024-10-21" -CompassAuthHeader api-key
```

The key is not echoed, saved to JSON, or placed in the command line. Keep the terminal
open while the server runs. After stopping the server with Ctrl+C, clear it from that
process with `Remove-Item Env:COMPASS_API_KEY`. This is an environment variable, scoped
to the current PowerShell process and inherited by the app it starts. You may instead
configure a trusted local secret manager to inject `COMPASS_API_KEY` into that process
before starting the runner. Avoid saving the key in a persistent Windows user/system
environment variable or writing it literally in a PowerShell assignment; those approaches
can leave it stored unprotected or in shell history. The local runner does not load `.env`.
In CI or another hosted environment, use the platform's secret store to inject
`COMPASS_API_KEY` as a process environment variable.

If your gateway expects `Ocp-Apim-Subscription-Key`, use that value for
`-CompassAuthHeader`. No bearer prefix is added. To return to Azure, run the local
command in [the Azure OpenAI local-run section](#run-locally-with-existing-azure-services)
with `-ModelProvider azure_openai` (or omit the option).

### Use Compass in an existing Container App

Build/deploy the updated code first. In the Azure portal, configure an existing Container
App as follows:

1. Open the Container App, go to **Settings > Secrets**, choose **Add**, enter
  `compass-api-key` as the secret name, paste the APIM key into the secret value field,
  and save. The key belongs in the secret value field, not an environment-variable value.
2. Go to **Application > Containers**, edit the app container, and add these environment
  variables. For `COMPASS_API_KEY`, select the secret-reference option and choose
  `compass-api-key`; do not type the key itself into the environment variable.
3. Save the container configuration to create a new revision, then wait until that
  revision is healthy before sending traffic to it.

Configure the variables as follows:

| Environment variable | Value |
| --- | --- |
| `MODEL_PROVIDER` | `compass` |
| `COMPASS_ENDPOINT` | Your full HTTPS APIM deployment URL, including `api-version` |
| `COMPASS_AUTH_HEADER` | `api-key` or `Ocp-Apim-Subscription-Key` |
| `COMPASS_API_KEY` | Secret reference to `compass-api-key`, not a plain-text value |

Keep the existing Search and history settings. To rotate the key, update the Container Apps
secret value and create/restart a revision if the portal does not do so automatically. To
switch back to Azure OpenAI, set `MODEL_PROVIDER` to
`azure_openai` and ensure the `AOAI_*` endpoint settings are present. Use
the [existing-app deployment instructions](#update-an-existing-deployment) for
`.env` usage. **Do not use `deploy.ps1 -SyncEnv` to upload a plain-text Compass key.**

Compass must return OpenAI chat-completions responses and support Dalil's structured
JSON output requests (`json_schema` and `json_object`). Unsupported requests fail the
model stage without silently falling back to Azure or disabling groundedness verification.
This adapter has mocked HTTP coverage for routing and both key headers; live Compass
model capabilities are not yet verified. Confirm authorization to send policy excerpts
and questions to that external provider, including its residency and retention terms.

## Configuration reference

Use the customer profile for supported non-secret settings. Compass keys belong in a
secret store, never in the profile. See [Model Provider](#choose-the-model-provider)
for provider details.

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

## Architecture

The current Dalil demo is an example, not a subscription or resource set for customers
to reuse. See [DALIL_AZURE_ARCHITECTURE.md](DALIL_AZURE_ARCHITECTURE.md) for the service
map. The first-time deployment region and customer prerequisites are documented in
[Start Here](#deploy-end-to-end-in-a-customer-tenant). GlobalStandard model processing
may occur outside the resource region; verify residency requirements separately.

## Update an existing deployment

This path is only for an already provisioned Container App. New customer provisioning is
covered in [Start Here](#deploy-end-to-end-in-a-customer-tenant).

### Optional .env file

Use this only to rebuild/update an **already provisioned** Container App with
`deploy.ps1`. Skip it for a new tenant deployment (`deploy-customer.ps1`) and for local
development (`run-local.ps1`); neither of those commands reads `.env`.

1. Copy the template from the repository root:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Open `.env` and fill the existing deployment target values if they are not already
   set in the selected profile: `AZURE_RESOURCE_GROUP`, `AZURE_CONTAINER_APP`, and
   `AZURE_CONTAINER_REGISTRY`. `AZURE_IMAGE_NAME` is optional. Keep non-secret runtime
   settings in `customer.json` where possible; non-empty `.env` values override profile
   values when `deploy.ps1` reads them.
3. Leave credential fields such as `SEARCH_KEY`, `AOAI_*_API_KEY`, bearer tokens, and
   `COMPASS_API_KEY` blank. `deploy.ps1 -SyncEnv` sends non-empty `.env` settings to the
   Container App. For Azure services, use managed identity; for Compass, configure the
   key in **Container Apps > Settings > Secrets** and set `COMPASS_API_KEY` to the
   `secretref:compass-api-key` reference as described above. Never put real credentials
   in `.env` or commit it; `.env` is git-ignored.
4. Sign in to the intended Azure subscription and update the existing app:

   ```powershell
   az login
   .\deploy.ps1 -Config customer.json -SyncEnv
   ```

   `deploy.ps1` builds the image in the configured registry and rolls it out to the
   existing Container App. `-SyncEnv` also applies non-empty, non-secret `.env` overrides.
   The JSON profile can provide the deployment targets instead of `.env`; explicit
   `deploy.ps1` parameters take precedence over both.

## Cost snapshot

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