# Dalil

Microsoft Fluent-inspired policy conversation accelerator using Microsoft Agent
Framework, Azure AI Search Foundry IQ, and Azure OpenAI. Public-source demonstration,
not an official Microsoft or government product or legal advice.

## Start Here

The supported deployment workstation is **Windows with PowerShell 7.4+ and Python
3.13**. Run commands from the repository root. No local Docker or Azure Developer CLI
(`azd`) is required. This is a public-source demonstration with public HTTPS ingress,
not an authenticated enterprise production service. Do not load confidential policies
or collect sensitive questions without first designing authentication, access controls,
networking and data governance.

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

1. Install [Git](https://git-scm.com/downloads/win),
  [Python 3.13](https://www.python.org/downloads/windows/),
  [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli-windows), and
  [PowerShell 7.4+](https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-windows).
  Open **PowerShell 7** (`pwsh`, not Windows PowerShell 5.1). Check `python --version`
  reports 3.13 and `$PSVersionTable.PSVersion` reports at least 7.4. Clone the
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
  az login --tenant <CUSTOMER_TENANT_ID>
  az account set --subscription <SUBSCRIPTION_ID>
  az account show --query "{name:name,id:id,tenantId:tenantId,state:state}" --output table
  az bicep install
  az extension add --name containerapp --upgrade
  ```

  Replace every `<...>` placeholder before running a command. Use an interactive user
  account in the customer tenant, not a service principal: the script resolves the
  signed-in Entra user for scoped permissions. Confirm the displayed tenant and
  subscription IDs. Stop on any failed command; do not proceed with a partial install.
  If `python` resolves to another version, use `py -3.13 -m venv .venv` instead.
  Docker is not required; the deployment builds the image in the customer's Azure
  Container Registry. Dependency installation and ACR builds need access to an approved
  package feed. Do not bypass TLS validation for proxy, mirror or certificate errors;
  configure the approved feed/trust chain instead.

  Register required resource providers in the selected subscription. Registration is a
  subscription configuration change, not resource provisioning; it needs permission.

  ```powershell
  $providers = @('Microsoft.App', 'Microsoft.ContainerRegistry', 'Microsoft.CognitiveServices',
    'Microsoft.Search', 'Microsoft.KeyVault', 'Microsoft.OperationalInsights',
    'Microsoft.Insights', 'Microsoft.ManagedIdentity')
  foreach ($provider in $providers) {
    az provider register --namespace $provider --wait
    if ($LASTEXITCODE -ne 0) { throw "Provider registration failed: $provider" }
  }
  ```

  Before provisioning, verify the model/version/SKU pairs in the profile generated in
  step 3 are available in UAE North and approved in the subscription. Defaults are
  `gpt-5.1`, version `2025-11-13`, GlobalStandard capacity 10, and
  `text-embedding-3-large`, version `1`, Standard capacity 100. Quota checks are not a
  reservation or an availability guarantee. GlobalStandard processing may occur outside
  UAE North. Tenant policy must permit public Search access and Search local authentication
  for operator ingestion; runtime Azure access uses managed identity. Azure Policy can
  prevent this demonstration topology from deploying.

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
  Use a lowercase collection name of 2-10 letters/digits/hyphens, starting with a letter.
  Keep the same website, name and profile for all later steps. `-Name` must match
  `resources.applicationName`; the default environment is `dev`. For a separate environment,
  set `resources.environmentName` to `test` or `prod` before provisioning. Names and the
  subscription determine resource names; changing them is not a migration.

  Keep `runtime.MODEL_PROVIDER` as `azure_openai` for this workflow. The customer script
  does not wire Compass secrets and rejects Compass profiles. Use the existing-app Compass
  instructions after verifying Azure. Leave Azure endpoint overrides out of `runtime`:
  this script always wires the newly provisioned stack, not existing services.
  The generator initially allows the website's host with `source.pathPrefixes: ["/"]`.
  Before discovery, replace that broad path with the approved policy-page and download
  paths, for example `["/policies", "/downloads/policies/"]`. Discovery may otherwise
  include unrelated pages from the same host. Add other approved file hosts explicitly;
  the generator does not infer a complete allowlist from the website URL.

4. Discover candidate documents and review the generated manifest:

  ```powershell
  .\.venv\Scripts\python.exe policy_sources.py `
    --config customer.json `
    --output sources/policies.json
  ```

  Open `sources/policies.json`. Verify every title and URL, remove documents that should
  not be included, and check `skipped` and `truncated`. The deployment will ingest the
  reviewed manifest to the new Foundry IQ knowledge source and knowledge base.
  `--output` must match `source.manifest` in the profile (the `policies` example uses
  `sources/policies.json`). Discovery follows ordinary HTML links and respects `robots.txt`;
  it does not sign in or execute JavaScript. PDF, DOCX and HTML are supported. For documents
  on another public domain/path, add only the approved hosts and paths to `source.allowedHosts`
  and `source.pathPrefixes`, then rediscover and review again. `truncated: true` means
  discovery hit a limit, not a complete inventory. Decide whether to increase bounded limits
  or narrow the source. Keep hashes and filenames intact when removing unwanted entries.

  Validate the profile before continuing:

  ```powershell
  .\.venv\Scripts\python.exe configure_accelerator.py --check customer.json
  ```

  Success prints non-secret runtime settings. This does not check Azure permissions,
  source completeness, model availability or retrieval readiness.

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
  There are **three required approvals**: `INGEST`, `DEPLOY` for infrastructure, and
  a second `DEPLOY` after the image-phase what-if to roll out the app. Enter each word
  exactly as shown. Stopping at the second deployment prompt leaves billable resources
  and an image in ACR; it is not a rollback. A first deployment may show a temporary
  Microsoft sample page until the app image is rolled out.
  If the manifest is missing, or you pass `-Rediscover`, the script writes a new manifest
  and stops for review. Review it, then rerun without `-Rediscover`.

6. Open the HTTPS URL printed at completion. Ask a question answerable from a reviewed
  document and verify the cited source. Without Cosmos history, conversation saving is
  unavailable. After provisioning Cosmos, each browser must turn on **Save conversations**
  before its chats are persisted.

  **Acceptance check:** `/healthz` must return HTTP 200, a question about a reviewed
  document must return a relevant answer with a working citation to that document, and
  a question outside the corpus must abstain rather than invent a policy. Test Arabic
  and English when both are required. A healthy process alone does not prove Search
  indexing, model access, citations or answer quality. Do not hand over the app until
  these checks pass. See [Troubleshooting](#troubleshooting) for failures.

### Keep the Deployment Details

Completion prints the URL, subscription, resource group, Container App, registry, Search
service/endpoint, OpenAI account, chat deployment and knowledge-base name. Keep those
non-secret details with the reviewed profile and manifest in your deployment records.
The script does not write them back into `customer.json`. For later image updates, fill
`deployment.subscription`, `resourceGroup`, `containerApp` and `registry` in that profile
using the printed values. Never use the original Dalil demo's endpoints for a customer.

Recover outputs in **Azure portal > Subscriptions > your subscription > Deployments**,
select the successful `<name>-<environment>-<timestamp>-image` deployment, and open
**Outputs**. From the selected subscription:

```powershell
az deployment sub show --name <DEPLOYMENT_NAME> --query properties.outputs --output json
```

For local development, use those names with
`run-local.ps1 -Config customer.json -SearchService <SEARCH_NAME> -OpenAIAccount <OPENAI_ACCOUNT_NAME>`.
The deployer's automatic permissions support ingestion, not necessarily local chat:
grant that user **Search Index Data Reader** and **Cognitive Services OpenAI User** on
the respective resources before running locally. Do not copy access keys into the profile.

### Optional: conversation history

Cosmos DB history is a separate billable add-on. To add it after the main app is deployed,
rerun the customer deployment for the existing stack, explicitly enable history, and pick
a supported Cosmos region.

The profile's `history.enabled` value alone never authorizes Cosmos provisioning;
`-EnableConversationHistory` controls the deployed app and the billable add-on. The profile
still supplies database/container names and retention days.

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
Register `Microsoft.DocumentDB` with `az provider register --namespace Microsoft.DocumentDB --wait`
before enabling history. On later customer-script updates, keep `-EnableConversationHistory`
and the same Cosmos region if history must remain enabled. Omitting the switch disables
the app's history integration; it does not delete Cosmos data or stop account charges.
Do not change Cosmos region as an update shortcut.

This flow removes the need to manually create Foundry IQ, Search, OpenAI, or app resources,
but intentionally retains source-review, cost, and deployment approval gates. A tenant
administrator may need to grant permissions or resolve quota, policy, and model availability
before deployment can succeed.

### Troubleshooting

| Symptom | Action |
| --- | --- |
| Script execution is blocked | Use PowerShell 7 and your organization's approved signing/execution-policy process. Do not disable machine-wide security policy. |
| Wrong tenant, missing subscription, or user cannot be resolved | Repeat tenant-specific login, select the subscription, and check `az account show`. Guest-user/Graph restrictions may require an administrator. Service-principal onboarding is not supported. |
| Provider registration, role assignment or policy denial | Check the error's provider/action/scope. Obtain subscription resource-creation and role-assignment permissions plus required tenant approvals. Login alone does not grant them. |
| Quota/model/region check stops | Verify both model/version/SKU combinations and regional quota. Request capacity or choose an approved compatible configuration. No automatic model/region fallback occurs. |
| No documents, missing PDFs, skipped or truncated results | Check accessibility, robots rules and host/path allowlists. JavaScript-only or authenticated sites need a different ingestion design. Rediscovery overwrites the manifest; preserve the reviewed copy first. |
| Failure after resources were created | Keep the same profile, subscription, name, environment and reviewed manifest. Rerun step 5 with `-UpdateExisting`, plus the same history switches if enabled. Review every what-if again. This repeats orchestration, not a rollback. |
| OCR/upload fails, or changed/duplicate/failed/unexpected files are reported | Inspect the named file and source. Matching unchanged files can be reused, but conflicting/failed remote files intentionally stop for review. Do not edit hashes to force acceptance, delete data blindly, or assume every error resumes automatically. |
| New role assignment gives 403 | Confirm principal and scope, allow RBAC propagation, then retry with `-UpdateExisting`. Persistent 403 requires fixing the reported permission, not replacing identity with committed keys. |
| ACR build fails | Inspect the failed run in the registry's task/run history. Check package-feed, network, quota and Dockerfile errors. Resolve the cause, then retry with `-UpdateExisting`. |
| Sample page, unhealthy revision, or health failure | Ensure you approved the second `DEPLOY`. Check Container App revisions, system logs and console logs. A one-time health probe can fail during startup; recheck the final URL and revision before redeploying. |
| App opens but answers fail or lack citations | Check Search file-source/indexing status, knowledge-base name, model deployment and managed-identity roles. Repeat acceptance checks after indexing completes. `/healthz` is not end-to-end readiness. |
| Image update reports missing targets | Fill the profile's deployment targets from the saved outputs, or pass explicit targets. Run from the repository root. |

Failed/cancelled deployments may leave billable resources. Inspect the dedicated project
resource group, tags and contents before keeping it for a retry or deleting it. Deleting
the group removes its app, Search content, logs and Cosmos history, subject to each
service's retention rules. Never delete a group merely because its name resembles this
project's name.

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
This example selects Compass for local development or an **existing** Container App;
do not apply it before running the Azure-only customer-provisioning workflow.

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
Install the tools and `.venv` dependencies from steps 1-2 first. Use a new PowerShell
terminal when changing profiles/providers: process environment overrides profile defaults,
and values from an earlier local run can remain in that terminal.

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
For new customer infrastructure, first deploy with `azure_openai`. Switching an existing
app to Compass does not remove the Azure chat deployment or reduce its allocated quota.

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
Omit it only when the profile and process both select Azure; otherwise pass
`-ModelProvider azure_openai` explicitly or use a clean PowerShell terminal.

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
Use `deploy.ps1` below for code/branding/runtime-only changes. It does not provision
services, change infrastructure, rediscover sources or ingest new documents. For reviewed
source or infrastructure changes, rerun `deploy-customer.ps1 -UpdateExisting` instead;
keep the same history switches and region when history is enabled. That orchestrator
requires the Azure provider, so do not use it to update a Compass-configured app without
first planning how its external settings and secret references will be preserved.

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
  Blank and `<PLACEHOLDER>` template values are ignored, so they do not erase profile
  defaults. Existing Container App environment values are not removed when absent here.
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
  The script does not migrate data or run acceptance checks. Repeat the answer/citation
  and out-of-corpus checks after each rollout. Existing app environment variables override
  values baked into the image; use reviewed `-SyncEnv` settings to change those values too.

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

### Local Regression Checks

With the step-2 dependencies installed, run these from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\tests\test_deployment_scripts.ps1
```

The PowerShell regression script mocks Azure calls and approvals; it does not provision
resources. These checks verify local behavior, not fresh-tenant deployment success. A
release handover still requires the customer's live deployment and acceptance checks.
Preview Search APIs, tenant policy, regional model availability and network conditions
can change independently of this repository. No guide can pre-grant tenant permissions
or guarantee regional capacity.

### Source Files

- UI: `webapp/assets/index.html`, `webapp/assets/dalil.css`, `webapp/assets/dalil.js`
- API and grounded response pipeline: `webapp/main.py`, `webapp/agent_runtime.py`,
  `webapp/grounded_workflow.py`
- Browser history: `webapp/conversation_history.py`
- Customer profile validation: `webapp/accelerator_config.py`
- Website discovery and document review: `policy_sources.py`
- Customer and pinned-gazette ingestion: `ingest_policies.py`, `ingest_gazettes_foundry.py`
- Infrastructure: `infra/main.bicep`, `infra/modules/`
- Local and Azure startup: `run-local.ps1`, `deploy-customer.ps1`