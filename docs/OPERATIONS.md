# Dalil Operations

[Back to README](../README.md) | [Reference](REFERENCE.md)

Use this guide after the [first deployment](../README.md#deploy-in-your-tenant), or
when setup fails. Run commands from the repository root in PowerShell 7.4+.

## Deployment Details

Completion prints the URL, subscription, resource group, Container App, registry,
Search service/endpoint, OpenAI account, chat deployment and knowledge-base name.
Keep these non-secret values with the reviewed profile and manifest. The script does
not write them into `customer.json`. For later image updates, fill that profile's
`deployment.subscription`, `resourceGroup`, `containerApp` and `registry` from the outputs.
Never reuse the original demo's endpoints for a customer.

Recover outputs in **Azure portal > Subscriptions > your subscription > Deployments**.
Select `<name>-<environment>-<timestamp>-image` and open **Outputs**, or run:

```powershell
az deployment sub show --name <DEPLOYMENT_NAME> --query properties.outputs --output json
```

## Update an Existing App

For code, branding or runtime-only changes, use `deploy.ps1`. It builds in ACR and
updates an existing app; it does not provision services, discover or ingest documents.
Set the profile's deployment targets first:

```powershell
az login --tenant <CUSTOMER_TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
.\deploy.ps1 -Config customer.json -SyncEnv
```

Existing app environment values override values baked into the image. Review `-SyncEnv`
when changing runtime values; absent settings are not removed from the app. Repeat the
README acceptance checks after each rollout. The update script does not run them.

For source/infrastructure changes, rerun the original customer deployment command with
`-UpdateExisting`, the same profile/name/environment and reviewed manifest. Keep the same
history switches and region if enabled. Source changes need rediscovery, review and
ingestion. This orchestrator requires `azure_openai`; do not use it for a Compass app
without planning preservation of its external settings and secret references.

### Optional Environment File

Only `deploy.ps1` reads `.env`; the customer deployment and local runner do not. Skip
it when the profile already supplies the targets and runtime settings.

```powershell
Copy-Item .env.example .env
```

Fill `AZURE_RESOURCE_GROUP`, `AZURE_CONTAINER_APP` and `AZURE_CONTAINER_REGISTRY` if not
in the profile. `AZURE_IMAGE_NAME` is optional. Explicit target parameters override `.env`,
then profile targets. Non-empty `.env` runtime values override profile values; blank and
`<PLACEHOLDER>` entries are ignored. `-SyncEnv` applies those values to the app.

Leave credential fields blank: `SEARCH_KEY`, `AOAI_*_API_KEY`, bearer tokens and
`COMPASS_API_KEY`. Azure uses managed identity; Compass uses a Container Apps secret
reference configured separately. `.env` is git-ignored, but must never contain committed
credentials or be used to sync a plain-text Compass key.

## Conversation History

Cosmos is an optional billable add-on. `history.enabled` in the profile does not authorize
provisioning: `-EnableConversationHistory` controls the deployed integration. The profile
supplies database/container names and retention days. Check capacity and governance first:

```powershell
az provider register --namespace Microsoft.DocumentDB --wait
.\deploy-customer.ps1 `
  -Subscription <SUBSCRIPTION_ID> `
  -Website https://policies.example.org/policies `
  -Name policies `
  -ConfigPath customer.json `
  -UpdateExisting `
  -EnableConversationHistory `
  -CosmosRegion <COSMOS_REGION>
```

Additional approvals are `COSMOS` and, outside UAE North, `RESIDENCY`, followed by the
normal ingestion/deployment approvals. Region listing is not a capacity guarantee; the
generic quota API does not report Cosmos capacity. Keep the switch and same region on
subsequent customer-script runs. Omitting it disables integration, not account charges
or stored data. Do not change region as an update shortcut. Each browser must turn on
**Save conversations** before chats persist. Read the [privacy limits](REFERENCE.md#safety-and-limits).

## Run Locally

This needs existing, populated Search/Foundry IQ and Azure OpenAI resources; it does not
provision or ingest. Install the README tools/dependencies first. The signed-in user
needs **Search Index Data Reader** and **Cognitive Services OpenAI User** on those resources.
Automatic deployment ingestion permissions do not necessarily grant local-chat access.

```powershell
az login --tenant <CUSTOMER_TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
.\.venv\Scripts\python.exe configure_accelerator.py --check customer.json
.\run-local.ps1 -Config customer.json -SearchService <SEARCH_NAME> -OpenAIAccount <OPENAI_ACCOUNT_NAME> -Port 8769
```

Open `http://127.0.0.1:8769`. Use `accelerator.json` only for the demo collection.
Optionally pass `-CosmosEndpoint` for an existing account with data-plane permission.
Use a clean terminal when changing profiles/providers: process environment overrides
profile defaults and can retain earlier values. Stop with Ctrl+C.

## Compass Provider

Fresh provisioning requires `azure_openai`. After verifying Azure, Compass can replace
synthesis, query rewriting and verification. Search/Foundry IQ and Azure embeddings
remain required. Switching does not remove Azure chat resources or release their quota.

Obtain the full HTTPS deployment URL, API version and key from the Compass/APIM owner.
It must support OpenAI chat-completions responses and `json_schema`/`json_object` output.
Unsupported calls fail without silent Azure fallback or disabling verification. Routing
and headers have mocked HTTP coverage; live Compass capabilities remain unverified.
Approve external transfer, residency and retention of questions/excerpts first.

### Local Compass

Edit the profile's existing top-level `runtime` object. This example is only that section;
preserve the other sections and any existing runtime settings:

```json
{
  "runtime": {
    "MODEL_PROVIDER": "compass",
    "COMPASS_ENDPOINT": "https://gateway.example/openai/deployments/my-model/chat/completions?api-version=2024-10-21",
    "COMPASS_AUTH_HEADER": "api-key",
    "SEARCH_ENDPOINT": "https://<search-service>.search.windows.net"
  }
}
```

Use the actual URL/version; the URL selects the model. The header is `api-key` or
`Ocp-Apim-Subscription-Key`, with no bearer prefix. Secrets are rejected from JSON.
Enter the key at a masked prompt in the same terminal that starts the app:

```powershell
$env:COMPASS_API_KEY = Read-Host 'Compass APIM subscription key' -MaskInput
az login --tenant <CUSTOMER_TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
.\run-local.ps1 -Config customer.json -SearchService <SEARCH_NAME> -ModelProvider compass
```

After Ctrl+C, clear it with `Remove-Item Env:COMPASS_API_KEY`. Do not save it as a
persistent user/system variable or type the literal key into a command. A trusted
secret manager can inject it instead; the local runner does not read `.env`.
To return to Azure, use a clean terminal and pass `-ModelProvider azure_openai` explicitly.

### Container Apps Compass

Deploy the updated code first. In the existing Container App's Azure portal configuration:

1. Under **Settings > Secrets**, add `compass-api-key` with the APIM key in its secret
   value field, never directly in an environment-variable value.
2. Under **Application > Containers**, edit the container and set the variables below.
3. Save and verify the new revision is healthy before sending traffic.

| Variable | Value |
| --- | --- |
| `MODEL_PROVIDER` | `compass` |
| `COMPASS_ENDPOINT` | Full HTTPS deployment URL including `api-version` |
| `COMPASS_AUTH_HEADER` | `api-key` or `Ocp-Apim-Subscription-Key` |
| `COMPASS_API_KEY` | Secret reference to `compass-api-key`, not the literal key |

Keep Search/history settings. For rotation, update the secret and create/restart a revision
as needed. To return to Azure, set `MODEL_PROVIDER=azure_openai` and ensure `AOAI_*` endpoints
are present. `deploy.ps1 -SyncEnv` refuses non-empty Compass keys; leave that `.env` entry
blank and manage the secret reference separately.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Script blocked | Use PowerShell 7 and the approved signing/execution-policy process. Do not disable machine-wide security. |
| Wrong tenant, missing subscription, unresolved user | Repeat tenant-specific login and subscription selection; check `az account show`. Guest/Graph restrictions may require an administrator. |
| Provider, role or policy denial | Check the error's action/scope and obtain deployment plus role-assignment permissions and tenant approvals. Login alone is insufficient. |
| Quota/model/region failure | Verify model/version/SKU pairs and regional quota. Request approved capacity; no automatic fallback occurs. |
| Package/TLS failure | Configure approved feeds, proxy and trust chain for workstation and ACR builds. Do not disable TLS verification. |
| Missing/skipped/truncated documents | Check accessibility, robots and allowlists. Authenticated/JavaScript-only sites need another ingestion design. Preserve reviewed manifests before rediscovery overwrites them. |
| Partial deployment | Keep the same profile/subscription/name/environment/manifest. Rerun with `-UpdateExisting` and the same history switches; review both what-if plans. |
| OCR/upload conflict or failed file | Inspect the named file. Unchanged matches can be reused; changed, duplicate, failed or unexpected files stop for review. Do not alter hashes or blindly delete data. |
| 403 after role assignment | Confirm principal/scope, allow RBAC propagation and retry. Persistent errors need permission fixes, not committed keys. |
| ACR build fails | Inspect registry task/run history. Fix feed, network, quota or Dockerfile errors before retrying with `-UpdateExisting`. |
| Sample page/unhealthy revision | Confirm the second `DEPLOY`. Inspect app revisions and system/console logs. Recheck after startup; the one-time health probe may be early. |
| App opens, answers fail | Check indexing, knowledge-base name, model deployment and identity roles. Repeat acceptance checks after indexing; `/healthz` alone is insufficient. |
| Missing update targets | Fill profile targets from saved outputs or pass explicit targets. Run from the repository root. |

### Cleanup

Failed/cancelled deployments can leave billable resources. Inspect the dedicated group,
tags and contents before retaining it for retry or deleting it. Group deletion removes
the app, Search data, logs and Cosmos history, subject to service retention rules. Never
delete a group merely because its name resembles this project's name.