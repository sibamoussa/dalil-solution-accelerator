# Dalil

A policy knowledge assistant using Microsoft Agent Framework, Azure AI Search
Foundry IQ and Azure OpenAI. Ask Arabic or English questions and receive answers
grounded in reviewed policy documents with source citations.

Public-source demonstration, not an official Microsoft or government product or
legal advice. The default app has public HTTPS ingress and no user authentication.
Do not use confidential documents or sensitive questions without additional access
controls and governance.

## Start Here

| Task | Guide |
| --- | --- |
| Deploy in a new customer tenant | Follow the steps below |
| Run locally, update an app, enable history or use Compass | [Operations](docs/OPERATIONS.md) |
| Settings, demo ingestion, costs, limits and tests | [Reference](docs/REFERENCE.md) |
| Understand the Azure services | [Architecture](DALIL_AZURE_ARCHITECTURE.md) |

## Before You Begin

- Use **Windows, PowerShell 7.4+ and Python 3.13**, with [Git](https://git-scm.com/downloads/win)
  and [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli-windows) installed.
  Install [Python](https://www.python.org/downloads/windows/) and
  [PowerShell](https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-windows)
  if needed. Run commands in `pwsh`, not Windows PowerShell 5.1.
- Use an interactive customer-tenant user with subscription resource-creation and
  role-assignment permissions, typically **Contributor + User Access Administrator**.
  Service-principal onboarding is not supported by the deployment script.
- Confirm **UAE North** service/model availability, quota and tenant policy. This topology
  needs public Search access and local authentication for ingestion; runtime uses managed
  identity. GlobalStandard processing may occur outside UAE North.
- Approve the documents for download/processing and review [costs](docs/REFERENCE.md#costs).
  Search and ACR alone have an indicative fixed baseline of about **$79/month**, excluding
  model, OCR, app and other usage. This is not a full estimate or spending cap.

No existing Search service or Foundry project is needed. The script provisions a dedicated
stack, ingests reviewed documents and deploys the app. No local Docker or `azd` is required.

## Deploy in Your Tenant

Replace all `<...>` placeholders and the example website/name before running commands.
Keep the same website, name and profile throughout. Stop if any command fails.

### 1. Prepare the Workstation

```powershell
git clone https://github.com/sibamoussa/dalil-solution-accelerator.git
cd dalil-solution-accelerator
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
az login --tenant <CUSTOMER_TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
az account show --query "{name:name,id:id,tenantId:tenantId,state:state}" --output table
az bicep install
az extension add --name containerapp --upgrade
```

Confirm Python reports **3.13** and the displayed tenant/subscription are correct.
If another Python version is selected, use `py -3.13 -m venv .venv` instead. Run all
remaining commands from this repository root. Workstation and ACR dependency installs
need an approved package feed; do not bypass TLS verification for download errors.

Register required providers in that subscription. This changes subscription configuration
and requires permission, but does not provision the application resources:

```powershell
$providers = @('Microsoft.App', 'Microsoft.ContainerRegistry', 'Microsoft.CognitiveServices',
  'Microsoft.Search', 'Microsoft.KeyVault', 'Microsoft.OperationalInsights',
  'Microsoft.Insights', 'Microsoft.ManagedIdentity')
foreach ($provider in $providers) {
  az provider register --namespace $provider --wait
  if ($LASTEXITCODE -ne 0) { throw "Provider registration failed: $provider" }
}
```

### 2. Configure the Collection

```powershell
.\.venv\Scripts\python.exe configure_accelerator.py `
  --website https://policies.example.org/policies --name policies --output customer.json
```

Open `customer.json` before continuing:

- Narrow `source.pathPrefixes` from `["/"]` to approved policy/download paths, for example
  `["/policies", "/downloads/policies/"]`. Add approved file domains to `source.allowedHosts`
  only when needed.
- Keep `runtime.MODEL_PROVIDER` as `azure_openai` for initial provisioning. Review branding
  and [model defaults](docs/REFERENCE.md#configuration) against regional availability.
- Use a lowercase name of 2-10 letters/digits/hyphens, starting with a letter. It must match
  `resources.applicationName`. The default environment is `dev`; set
  `resources.environmentName` to `test` or `prod` before deploying if needed.

Never put secrets in the profile. Leave Azure endpoint overrides unset: deployment wires
the new stack. Do not edit the checked-in demo profile to create a customer collection.

### 3. Discover and Review Documents

```powershell
.\.venv\Scripts\python.exe policy_sources.py --config customer.json --output sources/policies.json
.\.venv\Scripts\python.exe configure_accelerator.py --check customer.json
```

The output path must match `source.manifest`. Open the manifest, verify every title/URL
and remove unapproved documents without changing hashes or filenames. Check `skipped`
and `truncated`; a truncated discovery is not a complete inventory. Discovery supports
public PDF, DOCX and HTML links, not authenticated or JavaScript-only sites. Profile
validation does not prove source completeness or Azure readiness.

### 4. Deploy

```powershell
.\deploy-customer.ps1 `
  -Subscription <SUBSCRIPTION_ID> `
  -Website https://policies.example.org/policies `
  -Name policies `
  -ConfigPath customer.json
```

Review the manifest and both what-if plans. Enter three approvals when prompted:
**`INGEST`**, **`DEPLOY`** for infrastructure, then **`DEPLOY`** for the image rollout.
The script provisions, ingests, builds in ACR and checks `/healthz`. No model/region
fallback is selected. A temporary sample page is replaced during the image rollout.

After a partial attempt, rerun with **`-UpdateExisting`**, the same profile/name/environment
and reviewed manifest. Cancellation does not roll back billable resources. If a missing
manifest or `-Rediscover` triggers discovery, review the result and rerun without
`-Rediscover`. See [troubleshooting](docs/OPERATIONS.md#troubleshooting) for failures.

### 5. Verify and Record

Open the printed HTTPS URL and verify before handover:

- `/healthz` returns HTTP 200.
- A question about a reviewed document gets a relevant answer and working source citation.
- An out-of-corpus question abstains. Test Arabic and English when both are required.

Health alone does not prove retrieval or answer quality. Save the printed resource names
and endpoints with the reviewed profile; the script does not write them into JSON.
[Deployment details](docs/OPERATIONS.md#deployment-details) explains output recovery.

## After Deployment

- [Update the app](docs/OPERATIONS.md#update-an-existing-app) or [run locally](docs/OPERATIONS.md#run-locally).
- [Enable optional Cosmos history](docs/OPERATIONS.md#conversation-history). It is not
  provisioned by default; each browser must opt in to saving after it is enabled.
- [Configure Compass](docs/OPERATIONS.md#compass-provider) on an existing app.
- Review [safety and privacy limits](docs/REFERENCE.md#safety-and-limits) before wider use.

Local tests do not certify fresh-tenant deployment success. Permissions, regional capacity
and preview APIs can vary; live deployment and acceptance checks remain required.