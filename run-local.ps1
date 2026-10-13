<#
.SYNOPSIS
    Run Dalil with its local Python environment.

.DESCRIPTION
    Uses dedicated resources and the signed-in Azure CLI identity. No keys are read.
#>
[CmdletBinding()]
param(
    [string]$SearchService = "",
    [string]$OpenAIAccount = "",
    [string]$ChatDeployment = "",
    [string]$Config = "accelerator.json",
    [string]$CosmosEndpoint = "",
    [ValidateSet('azure_openai','compass')][string]$ModelProvider = 'azure_openai',
    [string]$CompassEndpoint = "",
    [ValidateSet('api-key','Ocp-Apim-Subscription-Key')][string]$CompassAuthHeader = 'api-key',
    [int]$Port = 8767,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$env:MODEL_PROVIDER = $ModelProvider
if ($ModelProvider -eq 'compass') {
    if (-not $CompassEndpoint -or -not $env:COMPASS_API_KEY) {
        throw 'Compass requires -CompassEndpoint and COMPASS_API_KEY in the process environment. Do not pass keys as command arguments.'
    }
    $env:COMPASS_ENDPOINT = $CompassEndpoint
    $env:COMPASS_AUTH_HEADER = $CompassAuthHeader
}

if (-not $PythonPath) {
    $PythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonPath)) {
    throw "Python interpreter not found at '$PythonPath'. Create it with 'python -m venv .venv' and install webapp/requirements.txt."
}

foreach ($setting in @("SEARCH_KEY", "SEARCH_BEARER_TOKEN", "AOAI_CHAT_API_KEY", "AOAI_CHAT_BEARER_TOKEN", "AOAI_FAST_API_KEY", "AOAI_FAST_BEARER_TOKEN", "AOAI_KEY", "AOAI_BEARER_TOKEN", "AZURE_CLIENT_ID")) {
    Remove-Item "Env:$setting" -ErrorAction SilentlyContinue
}

$env:ACCELERATOR_CONFIG = if ([IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $PSScriptRoot $Config }
$settings = Get-Content $env:ACCELERATOR_CONFIG -Raw | ConvertFrom-Json
if (-not $ChatDeployment) { $ChatDeployment = $settings.resources.chatDeployment }
$env:COSMOS_ENDPOINT = $CosmosEndpoint
$env:SEARCH_ENDPOINT = if ($SearchService) { "https://$SearchService.search.windows.net" } else { "" }
$env:FOUNDRY_KNOWLEDGE_BASE = $settings.resources.knowledgeBase
$env:SEARCH_RESOURCE_REGION = "uaenorth"
$env:ALLOWED_AZURE_REGION = "uaenorth"

$openAIEndpoint = "https://$OpenAIAccount.openai.azure.com"
$env:AOAI_CHAT_ENDPOINT = if ($OpenAIAccount) { "$openAIEndpoint/openai/deployments/$ChatDeployment/chat/completions?api-version=2024-12-01-preview" } else { "" }
$env:AOAI_FAST_ENDPOINT = $env:AOAI_CHAT_ENDPOINT
$env:AOAI_USE_GENERATIVE_SYNTHESIS = "true"
$env:APP_TITLE = $settings.branding.title
$env:ORGANIZATION_NAME = $settings.branding.organization
$env:ORGANIZATION_SHORT_NAME = $settings.branding.shortName

Write-Host "Dalil is starting at http://127.0.0.1:$Port" -ForegroundColor Cyan
& $PythonPath -m uvicorn main:app --app-dir (Join-Path $PSScriptRoot "webapp") --host 127.0.0.1 --port $Port