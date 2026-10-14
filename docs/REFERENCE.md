# Dalil Reference

[Back to README](../README.md) | [Operations](OPERATIONS.md)

## Configuration

Keep [accelerator.json](../accelerator.json) as the demo profile. Generate a separate
`customer.json` per collection. Never include keys, tokens or credentials. Validate with:

```powershell
.\.venv\Scripts\python.exe configure_accelerator.py --check customer.json
```

| Goal | Setting or file |
| --- | --- |
| Website/collection | Generate with `configure_accelerator.py`; existing profiles are never overwritten |
| Discovery scope | `source.allowedHosts`, `pathPrefixes`, `maxDocuments`, `maxPages` |
| Approved documents | Reviewed `source.manifest`, usually `sources/<collection>.json` |
| Branding | `branding.title`, `organization`, `shortName`, `accentColor`, `logo`; images under `webapp/assets/` |
| Azure models | `resources.chatModel*`, `embeddingModel*`, `chatDeployment`, `embeddingDeployment` |
| Provider | `runtime.MODEL_PROVIDER`; [Compass](OPERATIONS.md#compass-provider) is for local/existing apps |
| Runtime behavior | Supported `runtime` entries, including `SEARCH_TOP_K`, `MATCH_RESPONSE_LANGUAGE_TO_QUESTION`, `GROUNDEDNESS_CHECK_ENABLED` |
| History lifetime | `history.retentionDays`; provisioning needs the explicit [history switch](OPERATIONS.md#conversation-history) |
| Deployment targets | `deployment.subscription`, `resourceGroup`, `containerApp`, `registry`, `localPort`, `cosmosRegion` |
| Infrastructure | [infra/main.bicep](../infra/main.bicep), modules and deployment scripts; review a fresh what-if |

`runtime` is a top-level object beside `source`, `resources`, `branding`, `history` and
`deployment`. Edit inside it rather than replacing the whole profile with an example.
Unknown/secret runtime fields are rejected. Environment values override profile defaults.
Local changes require a restart; deployed changes require rebuild/rollout and review of
app environment settings. Source changes need rediscovery, review and ingestion. Profiles
do not implement arbitrary region migrations, private networking or new API behavior.

The generator initially allows the starting host with `pathPrefixes: ["/"]`; narrow it
before discovery and add other approved download hosts/paths explicitly. Discovery follows
ordinary HTML links and robots rules, not sign-in or JavaScript. Check skipped/truncated
results; bounded discovery is not proof of completeness.

Default models are `gpt-5.1` version `2025-11-13`, GlobalStandard capacity 10, and
`text-embedding-3-large` version `1`, Standard capacity 100. Verify both in the customer's
subscription and UAE North. Quota is not a reservation or model-availability guarantee.
GlobalStandard processing may occur outside UAE North.

## Bundled Corpus

Eight Arabic 2026 Abu Dhabi Official Gazette PDFs, issues 1-8, are pinned in
[sources/gazettes-2026.json](../sources/gazettes-2026.json). Arabic and English questions
use Arabic evidence; English answers are not official translations. Documents download
independently from the government's [policy page](https://www.abudhabi.gov.ae/ar/policies-and-legislations).
No private corpus, older publications or another project's Search data is reused. Public
availability is not a redistribution license: this repository ships URLs, not PDFs.

### Manual Ingestion

Advanced path for services that already exist; normal customer deployment runs ingestion
for you. The operator needs Search management/content access and Document Intelligence OCR
permission. Runtime uses managed identity. Optional `SEARCH_KEY` must not be printed or committed.

```powershell
python -m venv .venv-ingestion
.\.venv-ingestion\Scripts\python.exe -m pip install -r requirements-foundry-ingestion.txt
az login --tenant <CUSTOMER_TENANT_ID>
az account set --subscription <SUBSCRIPTION_ID>
```

Validate/download without uploads or billable OCR:

```powershell
.\.venv-ingestion\Scripts\python.exe ingest_gazettes_foundry.py `
  --manifest sources/gazettes-2026.json `
  --search-endpoint https://<SEARCH_NAME>.search.windows.net `
  --openai-endpoint https://<OPENAI_ACCOUNT>.openai.azure.com `
  --document-intelligence-endpoint https://<DOCUMENT_INTELLIGENCE_ACCOUNT>.cognitiveservices.azure.com
```

After reviewing rights, sources and costs, repeat with `--apply`. This creates/uses source
`dalil-gazettes-2026` and knowledge base `dalil-policies-2026`. SHA checks and an OCR-version
marker skip unchanged files; changed, duplicate, failed or unexpected files stop for review.
Do not assume every error resumes automatically. Inspect Arabic text and citations: the
Foundry IQ file-source API is preview. For a customer collection, use `ingest_policies.py
--config customer.json` with the same endpoint arguments; add `--apply` only after review.

## Costs

UAE North retail snapshot checked 2026-10-09, not a quote or spending cap:

| Item | Indicative cost |
| --- | --- |
| Search Basic | $0.101/hour, about $73.73 for 730 hours |
| ACR Basic | $0.1666/day, about $5.00 per 30 days, plus $0.10/GB-month storage |
| Container Apps active Consumption | $0.000024/vCPU-second and $0.000003/GiB-second |
| Optional Cosmos Serverless | $0.311/million RU plus $0.33/GB-month |

Search plus ACR is a **partial fixed baseline of about $78.73/month**. An app at 0.5 vCPU/
1 GiB for eight hours daily is about $12.96 per 30 days before free grants. Model tokens,
OCR, logs, storage transactions, egress, taxes and regional differences are excluded.
Check current prices, estimate usage, set a budget and monitor charges. Failed/stopped
deployments can incur costs until resources are removed.

## Safety and Limits

- Public ingress and anonymous history are not enterprise authentication. Sensitive data
  requires appropriate access controls and governance.
- Per-process limits: 12 combined chat/history requests/minute, two concurrent requests,
  32 KiB bodies, 4,000-character questions and ten history messages. One worker/replica is
  configured by default. These are not a distributed security perimeter.
- Citations must match the reviewed manifest. Invalid citations abstain; failed enabled
  verification degrades to evidence excerpts rather than accepting claims.
- OCR may be inaccurate. Publication date does not prove current legal validity or
  applicability. Review sources and obtain download/processing permission.
- History uses an anonymous browser cookie, not a user account. Shared browsers share
  history; losing the cookie loses access. Turning saving off stops new writes, not old
  data. Use the delete action.
- Cosmos TTL applies to the browser record and resets on change, not exact physical
  per-conversation deletion. Backups have separate retention.
- Questions still reach Search and the model when saving is off. History failures do not
  discard successful answers. Compass requires approval for external processing.
- Locks pin package versions, not wheel hashes. Regenerate/test on dependency changes;
  do not call these hash-verified supply-chain locks.

## Development

With README dependencies installed, run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\tests\test_deployment_scripts.ps1
```

PowerShell tests mock Azure and do not provision. Local tests are not proof of fresh-tenant
success; live deployment and answer/citation checks remain required. Preview APIs, tenant
policy, regional capacity and networking can change independently of this repository.

| Area | Source |
| --- | --- |
| UI | [webapp/assets/](../webapp/assets/) |
| API/workflow | [main.py](../webapp/main.py), [agent_runtime.py](../webapp/agent_runtime.py), [grounded_workflow.py](../webapp/grounded_workflow.py) |
| History | [conversation_history.py](../webapp/conversation_history.py) |
| Configuration | [accelerator_config.py](../webapp/accelerator_config.py) |
| Discovery | [policy_sources.py](../policy_sources.py) |
| Ingestion | [ingest_policies.py](../ingest_policies.py), [ingest_gazettes_foundry.py](../ingest_gazettes_foundry.py) |
| Infrastructure | [main.bicep](../infra/main.bicep), [modules](../infra/modules/) |
| Run/deploy | [run-local.ps1](../run-local.ps1), [deploy-customer.ps1](../deploy-customer.ps1), [deploy.ps1](../deploy.ps1) |

See [architecture](../DALIL_AZURE_ARCHITECTURE.md) for service relationships.