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
    [ValidateSet('azure_openai','compass')][string]$ModelProvider,
    [string]$CompassEndpoint = "",
    [ValidateSet('api-key','Ocp-Apim-Subscription-Key')][string]$CompassAuthHeader,
    [int]$Port = 8767,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

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
$runtimeJson = & $PythonPath (Join-Path $PSScriptRoot 'configure_accelerator.py') --check $env:ACCELERATOR_CONFIG
if ($LASTEXITCODE -ne 0) { throw 'Configuration validation failed.' }
$runtime = $runtimeJson | ConvertFrom-Json
foreach ($entry in $runtime.PSObject.Properties) {
    if (-not [Environment]::GetEnvironmentVariable($entry.Name, 'Process')) {
        [Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, 'Process')
    }
}
if ($ModelProvider) { $env:MODEL_PROVIDER = $ModelProvider }
if ($CompassEndpoint) { $env:COMPASS_ENDPOINT = $CompassEndpoint }
if ($CompassAuthHeader) { $env:COMPASS_AUTH_HEADER = $CompassAuthHeader }
if ($env:MODEL_PROVIDER -eq 'compass' -and (-not $env:COMPASS_ENDPOINT -or -not $env:COMPASS_API_KEY)) {
    throw 'Compass requires runtime.COMPASS_ENDPOINT in the profile and COMPASS_API_KEY in the process environment.'
}
$settings = Get-Content $env:ACCELERATOR_CONFIG -Raw | ConvertFrom-Json
if (-not $PSBoundParameters.ContainsKey('Port') -and $settings.deployment.localPort) { $Port = $settings.deployment.localPort }
if (-not $ChatDeployment) { $ChatDeployment = $settings.resources.chatDeployment }
if ($CosmosEndpoint) { $env:COSMOS_ENDPOINT = $CosmosEndpoint }
if ($SearchService) { $env:SEARCH_ENDPOINT = "https://$SearchService.search.windows.net" }
$env:FOUNDRY_KNOWLEDGE_BASE = $settings.resources.knowledgeBase
$env:SEARCH_RESOURCE_REGION = "uaenorth"
$env:ALLOWED_AZURE_REGION = "uaenorth"

$openAIEndpoint = "https://$OpenAIAccount.openai.azure.com"
if ($OpenAIAccount) { $env:AOAI_CHAT_ENDPOINT = "$openAIEndpoint/openai/deployments/$ChatDeployment/chat/completions?api-version=2024-12-01-preview" }
if (-not $env:AOAI_FAST_ENDPOINT) { $env:AOAI_FAST_ENDPOINT = $env:AOAI_CHAT_ENDPOINT }
if (-not $env:AOAI_USE_GENERATIVE_SYNTHESIS) { $env:AOAI_USE_GENERATIVE_SYNTHESIS = "true" }
$env:APP_TITLE = $settings.branding.title
$env:ORGANIZATION_NAME = $settings.branding.organization
$env:ORGANIZATION_SHORT_NAME = $settings.branding.shortName

Write-Host "Dalil is starting at http://127.0.0.1:$Port" -ForegroundColor Cyan
& $PythonPath -m uvicorn main:app --app-dir (Join-Path $PSScriptRoot "webapp") --host 127.0.0.1 --port $Port