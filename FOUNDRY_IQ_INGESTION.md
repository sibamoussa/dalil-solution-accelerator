# Reproduce the 2026 Gazette Corpus

The pinned manifest contains eight Arabic PDFs from
https://www.abudhabi.gov.ae/ar/policies-and-legislations. The script validates the
government host, 2026 Arabic path, PDF content, redirects and file size before any
upload. It never crawls other years. Review the publisher's terms before redistribution.

## Prerequisites

Use Python 3.13 and install [requirements-foundry-ingestion.txt](requirements-foundry-ingestion.txt).
Provision independent Dalil Search, OpenAI chat/embedding deployments and Document
Intelligence in UAE North first. Authenticate with `az login`; operator needs OCR
access and permission to manage Search knowledge sources and indexed content.
`SEARCH_KEY` is an optional operator credential; never print it or save it in code.
The application runtime uses managed identity, not the ingestion credential.

## Preflight and Apply

```powershell
.\.venv\Scripts\python.exe .\ingest_gazettes_foundry.py `
  --search-endpoint https://<DALIL_SEARCH>.search.windows.net `
  --openai-endpoint https://<DALIL_OPENAI>.openai.azure.com `
  --document-intelligence-endpoint https://<DALIL_DI>.cognitiveservices.azure.com
```

Without `--apply`, the command validates/downloads source documents without uploading
or changing Azure state. Repeat with `--apply` to OCR and ingest. Downloads occur
directly from government URLs, not from the original application's index or storage.

The source is `dalil-gazettes-2026`, the knowledge base is `dalil-policies-2026`,
and Foundry manages the source's backing index. The API is `2026-08-01-preview`.
OCR uses Document Intelligence Read and searchable-PDF output before minimal Search
extraction. Original government PDF URLs remain the citation targets.

SHA checks and an OCR-version marker skip unchanged remote files. Changed, duplicate,
failed, or unexpected files stop the run for review rather than silently replacing
the corpus. Run the same command again to resume safely and verify idempotence.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

After ingestion, confirm all eight files succeeded and produced searchable Arabic
text. Independently test cited Arabic and English questions on the new app. Unit
tests with mocks do not establish live Azure integration or OCR accuracy.

## Caveats

This is a preview Search feature and a public-source demonstration. OCR may be
inaccurate; 2026 publication does not establish current legal validity. The new
corpus has not yet been ingested. OCR, embeddings, Search and chat incur charges.