# Customer Setup and Branding

## Status

Application configuration, discovery, ingestion, branding, browser opt-in history,
optional Cosmos Bicep and the customer deployment bootstrap are implemented. Each
deployment is customer-owned and must be validated against its own subscription,
regional capacity, governance policies, data-residency obligations and billing approval.
Conversation history is opt-in at deployment and per browser. Cosmos accounts use
managed identity with key-based authentication disabled. The generic Azure quota CLI
does not expose Cosmos DB capacity; a `BadRequest` from that API is not a capacity result.

## Configure a Collection

Use Python 3.13 and install the complete, committed development lock from a clean
environment. The container uses the narrower runtime lock, so test-only dependencies
are not shipped in the image:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.venv\Scripts\python.exe configure_accelerator.py --website https://policies.example.org/policies --name policies --output customer.json
.venv\Scripts\python.exe policy_sources.py --config customer.json --output sources/policies.json
```

The checked-in lockfiles pin the resolved transitive versions for Python 3.13. If a
direct dependency changes, regenerate both locks from the root after installing the
tool pinned in [requirements-lock-tools.txt](requirements-lock-tools.txt):

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-lock-tools.txt
.venv\Scripts\python.exe -m piptools compile --resolver=backtracking --strip-extras --no-emit-index-url --no-header --output-file webapp/requirements.lock webapp/requirements.txt
.venv\Scripts\python.exe -m piptools compile --resolver=backtracking --strip-extras --no-emit-index-url --no-header --output-file requirements-dev.lock requirements-dev.txt
```

Review lock changes and run the suite before committing. The locks pin versions but
do not currently enforce artifact hashes; this is deterministic dependency selection,
not a complete hash-verified supply-chain policy.

The generator refuses to overwrite an existing profile. The default profile remains
[accelerator.json](accelerator.json), and the existing reviewed gazettes remain in
[sources/gazettes-2026.json](sources/gazettes-2026.json). Choose a distinct `--name`
(2-10 lowercase letters/digits/hyphens, starting with a letter) for another collection.
Review `resources.chatModel`, `chatModelVersion`, `chatModelSku` and `chatModelCapacity`
plus the corresponding embedding fields in the generated JSON against the target
subscription's regional model availability and quota before deploying. These defaults
preserve Dalil's current deployments; availability is not guaranteed in another tenant.

The generated profile initially allows HTTPS documents on the website's hostname.
Add specific CDN/document hostnames to `source.allowedHosts` if required; redirects
are checked too. Narrow `source.pathPrefixes` to the policy and document paths where
possible. DNS destinations must be public, robots.txt is respected, and downloads
are limited to 50 MiB. Discovery is bounded by `maxDocuments` and `maxPages`.

Supported inputs are linked PDFs, DOCX files, and static HTML pages. Scanned PDFs
use Document Intelligence OCR during ingestion. HTML and DOCX become UTF-8 text;
images, complex layout and some table structure may be lost. Authenticated sites,
JavaScript-only content, and recursive unrestricted crawling are not supported.
Discovery extracts text but does not decide whether a page is an authoritative policy.

Review the manifest's `documents`, `skipped`, and `truncated` fields. Remove unrelated
documents, correct titles/languages, and keep the reviewed URLs, filenames and hashes.
The output path must match `source.manifest` in the profile. The manifest path is
relative to the repository root, even when the profile is elsewhere. Obtain appropriate
permission to download/process the source; public accessibility is not a reuse license.

## Ingest Into Prepared Resources

This standalone command requires existing dedicated Search, OpenAI and Document
Intelligence services, model deployments, and data-plane permissions. It does not
create Azure resources. For a new collection and isolated stack, use
[deploy-customer.ps1](deploy-customer.ps1), which provisions the resources before
running ingestion.

```powershell
python ingest_policies.py --config customer.json --search-endpoint https://SEARCH.search.windows.net --openai-endpoint https://OPENAI.openai.azure.com --document-intelligence-endpoint https://DOCUMENTINTELLIGENCE.cognitiveservices.azure.com
```

Without `--apply`, this validates downloads and remote compatibility without uploading
files or running billable OCR. Add `--apply` only after reviewing the manifest and costs.
The script refuses mixed collections, changed hashes, and incompatible extraction
versions rather than silently replacing existing data. Rediscover and review updates;
source replacement/removal requires an explicit migration, not an automatic prune.
The Foundry IQ file-source API is preview. PDF ingestion is live-tested; generic
HTML/DOCX uploads are unit-tested but not yet verified against the live preview service.

## Replace Branding

Edit the `branding` object in your profile:

```json
{
  "title": "Policy Desk",
  "organization": "Your organization",
  "shortName": "Policies",
  "logo": "/assets/customer-logo.png",
  "accentColor": "#0078d4"
}
```

Put your image under [webapp/assets](webapp/assets), for example `customer-logo.png`.
PNG, JPG, WebP and trusted SVG artwork are supported. Use branding you have permission
to distribute; review SVG content before publishing it. Dalil artwork stays the default.
The built-in Arabic Dalil wordmark is hidden when the configured title is not `Dalil`.
`shortName` is reserved configuration; the current UI uses `title` as its display name.
Use [webapp/assets/dalil.css](webapp/assets/dalil.css) for further theme changes.

For local testing after Azure CLI login and scoped role assignment:

```powershell
.\run-local.ps1 -Config customer.json -SearchService SEARCH -OpenAIAccount OPENAI -Port 8769
```

Local users need Search Index Data Reader and Cognitive Services OpenAI User.
Ingestion additionally needs Search management/data access and Document Intelligence
OCR permissions. The deployed runtime uses managed identity, not the developer's login.
Container builds use the repository root and `--build-arg ACCELERATOR_CONFIG=customer.json`.
The reviewed manifest and branding assets must be in the build context. Never store
secrets in the profile. Model/version changes must match provisioned deployments.

## Conversation History

Saving is off by default. `history.enabled` in the profile configures the application,
but infrastructure is opt-in separately. Normal deployments set `historyEnabled=false`
and do not create a Cosmos account or enable history endpoints. To provision the add-on,
pass `-EnableConversationHistory -CosmosRegion <region>` to the bootstrap. The script
validates that Azure lists the selected region for Cosmos accounts and requires typed
confirmation for the billable add-on and for any region outside UAE North. Its Cosmos
quota API checks return `BadRequest` for all regions tested, so region support does not
mean capacity is available. The Dalil account was created successfully in Sweden
Central, though this does not guarantee future regional capacity. For UAE North, pass
`-CosmosRegion uaenorth` only after obtaining capacity approval at
https://aka.ms/cosmosdbquota. The account is Serverless with a database/container,
partition key `/owner`, TTL, local auth disabled and a Cosmos-native data role scoped to
that container. Its region is independent of the UAE North app stack. Local runs still
require a pre-provisioned endpoint and matching managed identity or Azure CLI data access;
the UI cannot create billable resources.

The Save conversations switch applies only to that browser's anonymous cookie. There
is no sign-in, user account, or cross-device synchronization. A random HttpOnly,
SameSite=Strict cookie is Secure on HTTPS; localhost HTTP is allowed for development.
Possession of the cookie grants access to its history. A shared browser shares history;
clearing/losing the cookie loses access. Do not use this mode for confidential policies
or sensitive personal data without an appropriate authentication/security design.

Turning saving off stops future writes but does not delete existing history. Delete
saved history explicitly removes it. Enabling saving does not backfill earlier turns.
At most 10 conversations with 20 messages each are retained per browser; messages are
bounded to 4,000 characters and the combined record to approximately 900 KB. Older data
is dropped when limits are reached. Reopened answers use plain text, not the original
rich citation links.

`retentionDays` defaults to 30. Old conversations are hidden by their last update time.
Cosmos TTL applies to the entire browser record and resets when that record changes;
it is not a guarantee of physical per-conversation deletion exactly 30 days later.
Cookie expiry can also precede record expiry after later chats. Cosmos backups follow
their separately configured retention policy. Delete history and turning saving off
block stale in-flight responses from recreating deleted/saved content.

Chat still sends the current question and recent context to Search/OpenAI when saving
is off. The toggle controls Cosmos persistence, not model processing. GlobalStandard
model processing may occur outside UAE even though regional resources and the planned
Cosmos history account is in Sweden Central. History failures do not discard a successful answer;
the UI reports that it was not saved.

## Deployment and Production Boundaries

[infra/main.bicep](infra/main.bicep) is the existing central infrastructure entrypoint,
with modules for Container Apps, ACR, identity, Key Vault, observability, Search,
OpenAI, Document Intelligence and Storage. Cosmos is an optional module with a separate
region parameter. Existing resource names must be preserved when updating Dalil.
No Azure account, subscription, role permissions, quota or billing entitlement can be
created by supplying a website alone; customers must provide their own Azure context.

The public demo is not a production security perimeter. Combined chat/history rate
limits are in-process and apply globally, with one worker/replica. Add authentication,
distributed abuse protection, spending monitoring and appropriate network controls
before production use. Browser isolation is not enterprise multi-tenant authentication.
Set budgets and monitor model, Search, OCR, Container Apps, Cosmos and logging costs.

Run `python -m unittest discover -s tests -v` and `node --check webapp/assets/dalil.js`
before publishing changes. Real Cosmos persistence and a fresh customer deployment
require separate cloud validation; unit tests do not substitute for those checks.