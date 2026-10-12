# Dalil

Microsoft Fluent-inspired policy conversation accelerator using Microsoft Agent
Framework, Azure AI Search Foundry IQ, and Azure OpenAI. Public-source demonstration,
not an official Microsoft or government product or legal advice.

## Customer Configuration

The checked-in [accelerator.json](accelerator.json) preserves the current Dalil
branding and eight-gazette collection. Create a separate profile from a public URL:

```powershell
python configure_accelerator.py --website https://policies.example.org/policies --output customer.json
python policy_sources.py --config customer.json --output sources/policies.json
```

Install the dependencies below first. Review the discovered document list before
ingestion: a website may include unrelated pages. See
[ACCELERATOR_SETUP.md](ACCELERATOR_SETUP.md) for formats, branding, history privacy,
and the deployment boundary.

## Local Development

Python 3.13 and PowerShell 7.4+ are required. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\run-local.ps1
```

Open http://127.0.0.1:8767. Without explicit cloud resource names the UI runs, but
chat returns an honest HTTP 503 configuration message. No mock answers or shared
resource fallback are used. After provisioning and `az login`:

```powershell
.\run-local.ps1 -SearchService <DALIL_SEARCH_NAME> -OpenAIAccount <DALIL_OPENAI_NAME>
```

Local CLI identity needs Search Index Data Reader and Cognitive Services OpenAI
User on the new services. The deployed app uses its own managed identity.

## Corpus

Eight Arabic 2026 Abu Dhabi Official Gazette PDFs, issues 1-8, are pinned in
[sources/gazettes-2026.json](sources/gazettes-2026.json). Arabic and English questions
are supported over the Arabic evidence; English answers are not official translations.
Documents are independently downloaded from the government's
[policy page](https://www.abudhabi.gov.ae/ar/policies-and-legislations).
No private corpus, older publications, or existing project's Search data is reused.

See [FOUNDRY_IQ_INGESTION.md](FOUNDRY_IQ_INGESTION.md) for reproducible download,
OCR, upload, and idempotent resumption. Public availability does not establish a
redistribution license: the accelerator ships URLs and code, not repackaged PDFs.

## Deployment

The Dalil application is hosted on Azure Container Apps. This repository is a
customer-ready accelerator; it does not include customer credentials, deployment
records, or production resource identifiers. Browser conversation history is an
optional Cosmos DB Serverless add-on and is off for standard deployments. For a
deployment, choose a supported region that meets your data-residency requirements and
review the governance policies that apply to your subscription. The generic Azure quota
CLI does not expose Cosmos DB capacity. GlobalStandard model processing may occur
outside the resource region; confirm model data-residency requirements separately.

### New Customer Deployment

1. Install Python 3.13 dependencies using `requirements-dev.lock`, install Azure CLI,
  sign in with `az login`, and select a subscription you are authorized to use.
2. Create a profile from the website. Use a distinct short lowercase name per
  collection:

  ```powershell
  .\.venv\Scripts\python.exe configure_accelerator.py --website https://policies.example.org/policies --name policies --output customer.json
  ```

3. Add permitted document/CDN hosts and narrow `pathPrefixes` in `customer.json` as
  needed. Put your logo under `webapp/assets/`, then set `branding.logo`, title,
  organization, short name and accent color. The Dalil profile and logo remain unchanged.
4. Discover and review the bounded document manifest before any resources are created:

  ```powershell
  .\.venv\Scripts\python.exe policy_sources.py --config customer.json --output sources/policies.json
  ```

  Edit `documents` to remove irrelevant entries; check `skipped` and `truncated` too.
  Public accessibility does not grant rights to download or redistribute.
5. Run the bootstrap with the same website/name. It reuses an existing profile and
  reviewed manifest. It refuses to reuse an existing project resource group unless
  you explicitly pass `-UpdateExisting` after reviewing its what-if. It will show the
  manifest, require `INGEST`, run a Bicep
  `what-if`, and separately require `DEPLOY` before creating billable resources:

  ```powershell
  .\deploy-customer.ps1 -Subscription <SUBSCRIPTION_ID> -Website https://policies.example.org/policies -Name policies -ConfigPath customer.json
  ```

  It creates an isolated resource group and UAE North Container Apps, ACR, Search,
  OpenAI, Document Intelligence, Key Vault, managed identity and monitoring; then
  ingests the reviewed source, builds in that customer's ACR, deploys the image and
  probes `/healthz`. Cosmos and the history API are not provisioned/enabled by default.
  To opt into the add-on, pass `-EnableConversationHistory -CosmosRegion <region>`.
  The script checks that Azure lists the region for Cosmos accounts and asks for typed
  billing and, outside UAE North, data-residency confirmation. The Cosmos quota API is
  unsupported for the tested regions, so the script cannot verify capacity; a successful
  region-list check is not a capacity guarantee. History saving also remains off in each
  browser until that browser opts in. For UAE North, use `-CosmosRegion uaenorth` only
  after obtaining capacity approval. `-UpdateExisting` does not delete an already
  provisioned Cosmos account; it disables runtime history but the account may continue
  billing until separately reviewed and removed.
  If model quota/capacity is unavailable, provisioning stops rather than silently
  changing region or model. Pass `-Rediscover` only when intentionally replacing the
  saved manifest from website discovery.

The subscription owner must provide Azure login, role-assignment permission, model
availability/quota and billing approval. A website URL alone cannot supply them.
The bootstrap has not yet been exercised against a newly provisioned customer stack;
the currently running Dalil deployment remains unchanged.

```powershell
.\provision-dedicated.ps1 -Subscription <SUBSCRIPTION_ID> -EnvironmentName dev -IngestGazettes
```

This legacy command creates billable resources, ingests the checked-in gazette corpus,
builds in the new ACR and deploys the container. Use [deploy-customer.ps1](deploy-customer.ps1)
for a customer profile and reviewed website manifest.
For later releases use [deploy.ps1](deploy.ps1) with a private environment file based
on [.env.example](.env.example). Keep secrets out of source control.

See [DALIL_AZURE_ARCHITECTURE.md](DALIL_AZURE_ARCHITECTURE.md) for the service map.

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

## Demo Boundaries

- Public endpoint with global per-process limits: 12 combined chat/history requests/minute and 2
  concurrent requests; excess requests return HTTP 429 and Retry-After.
- Maximum request body 32 KiB, question 4,000 characters, history 10 messages with
  user/assistant roles only; request body read timeout 10 seconds.
- One Uvicorn worker and one Container App replica. Limits reset on restart and are
  not a distributed security perimeter. Add a gateway/distributed limiter before scaling.
- Model/retrieval timeouts and token budgets are bounded. Quota and billing alerts
  are not hard spending caps. Set a budget and monitor usage before public sharing.
- Citations allow only URLs in the reviewed source manifest. Invalid citations abstain; unavailable
  enabled verification degrades to excerpts rather than accepting generated claims.
- Foundry IQ file sources use a preview API. OCR can contain errors. Publication in
  2026 does not prove current legal validity or applicability.
- Website discovery is bounded by allowed hosts, paths, document/page limits and file
  size, but does not determine whether a page is authoritative policy. Review the
  generated manifest before ingestion. Public access is not a redistribution license.
- Conversation saving is off by default, even after Cosmos is provisioned. History
  belongs to an anonymous browser cookie, not an authenticated account. Shared browsers
  share history; clearing or losing the cookie loses access. Do not use for confidential
  content without authentication and an appropriate access-control design.
- Turning saving off stops future writes; it does not delete prior history. Use the
  explicit delete action. Cosmos TTL applies to a browser's whole record and resets when
  it changes, so it does not guarantee physical per-conversation deletion exactly at
  the configured age. Backups have separate retention settings.
- The history toggle controls Cosmos persistence only: questions and recent context
  still go to Search and the model. History failures do not discard successful answers.
- New customers need their own Azure subscription, permissions, quota and billing
  authorization. A policy website link cannot grant these. Model quota/availability
  must be checked per subscription; the template will not silently switch model/region.
- Direct package requirements are pinned and deployment installs use a transitive
  version lock. Updating dependencies requires regenerating and testing both runtime
  and development locks. These locks pin versions but do not pin wheel hashes; enable
  hash-checking mode before treating this as a supply-chain-locked production build.

UI sources live in [webapp/assets/index.html](webapp/assets/index.html),
[webapp/assets/dalil.css](webapp/assets/dalil.css), and
[webapp/assets/dalil.js](webapp/assets/dalil.js). Framework execution is in
[webapp/agent_runtime.py](webapp/agent_runtime.py) and
[webapp/grounded_workflow.py](webapp/grounded_workflow.py).