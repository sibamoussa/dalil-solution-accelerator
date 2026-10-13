<#
.SYNOPSIS
    Build the Dalil image in Azure Container Registry and
    roll it out to an Azure Container App.

.DESCRIPTION
    Reproduces the full redeploy in one command:
      1. Reads deployment target + app settings from a .env file.
      2. Builds the image server-side with `az acr build` (no local Docker needed).
      3. Updates the Container App to the new image, creating a new revision.
      4. Optionally pushes the app's environment variables from .env.

    Fill in the unknowns in .env (copy from .env.example) before running.

.PARAMETER EnvFile
    Path to the environment file. Default: .env

.PARAMETER ResourceGroup / ContainerApp / Registry / ImageName
    Azure targets. If omitted, they are read from the .env keys
    AZURE_RESOURCE_GROUP, AZURE_CONTAINER_APP, AZURE_CONTAINER_REGISTRY,
    AZURE_IMAGE_NAME.

.PARAMETER SyncEnv
    Also push all app settings (SEARCH_*, AOAI_*, etc.) from .env to the
    Container App as environment variables.

.EXAMPLE
    ./deploy.ps1
.EXAMPLE
    ./deploy.ps1 -SyncEnv
#>
[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [string]$ResourceGroup,
    [string]$ContainerApp,
    [string]$Registry,
    [string]$ImageName,
    [string]$Dockerfile = "Dockerfile",
    [switch]$SyncEnv
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
# Azure CLI streams UTF-8 build logs; avoid cp1252 console crashes on Windows.
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# --- Load .env ---------------------------------------------------------------
if (-not (Test-Path $EnvFile)) {
    throw "Env file '$EnvFile' not found. Copy .env.example to .env and fill it in."
}

$settings = @{}
foreach ($line in Get-Content $EnvFile) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
    $idx = $trimmed.IndexOf("=")
    if ($idx -lt 1) { continue }
    $key = $trimmed.Substring(0, $idx).Trim()
    $val = $trimmed.Substring($idx + 1).Trim()
    $settings[$key] = $val
}

# Deployment target: explicit params win, otherwise fall back to .env keys.
if ($SyncEnv -and $settings["COMPASS_API_KEY"]) {
    throw 'Do not sync COMPASS_API_KEY as plain text. Configure a Container Apps secret reference and leave this .env value blank.'
}
if (-not $ResourceGroup) { $ResourceGroup = $settings["AZURE_RESOURCE_GROUP"] }
if (-not $ContainerApp)  { $ContainerApp  = $settings["AZURE_CONTAINER_APP"] }
if (-not $Registry)      { $Registry      = $settings["AZURE_CONTAINER_REGISTRY"] }
if (-not $ImageName)     { $ImageName     = $settings["AZURE_IMAGE_NAME"] }
if (-not $ImageName)     { $ImageName     = "dalil-knowledge-assistant" }

foreach ($pair in @{ ResourceGroup = $ResourceGroup; ContainerApp = $ContainerApp; Registry = $Registry }.GetEnumerator()) {
    if (-not $pair.Value -or $pair.Value -like "*<*>*") {
        throw "Missing deployment target '$($pair.Name)'. Set it in $EnvFile (AZURE_* keys) or pass -$($pair.Name)."
    }
}

# --- Build -------------------------------------------------------------------
$tag = "${ImageName}:release-$(Get-Date -Format yyyyMMddHHmmss)"
$fullImage = "$Registry.azurecr.io/$tag"
Write-Host "Building $fullImage ..." -ForegroundColor Cyan
az acr build --registry $Registry --image $tag --file $Dockerfile .

# --- Deploy ------------------------------------------------------------------
Write-Host "Updating container app '$ContainerApp' to new image ..." -ForegroundColor Cyan
az containerapp update `
    --name $ContainerApp `
    --resource-group $ResourceGroup `
    --image $fullImage `
    --output table

az containerapp ingress update `
    --name $ContainerApp `
    --resource-group $ResourceGroup `
    --target-port 8000 `
    --output none

# --- Optionally sync app settings from .env ----------------------------------
if ($SyncEnv) {
    $deploymentKeys = @("AZURE_RESOURCE_GROUP", "AZURE_CONTAINER_APP", "AZURE_CONTAINER_REGISTRY", "AZURE_IMAGE_NAME")
    $envArgs = @()
    foreach ($kv in $settings.GetEnumerator()) {
        if ($kv.Key -in $deploymentKeys) { continue }
        if (-not $kv.Value -or $kv.Value -like "*<*>*") { continue }
        $envArgs += "$($kv.Key)=$($kv.Value)"
    }
    if ($envArgs.Count -gt 0) {
        Write-Host "Syncing $($envArgs.Count) app settings from $EnvFile ..." -ForegroundColor Cyan
        az containerapp update --name $ContainerApp --resource-group $ResourceGroup --set-env-vars @envArgs --output none
    }
}

Write-Host "Done. Deployed $fullImage" -ForegroundColor Green
