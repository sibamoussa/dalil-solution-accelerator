<#
.SYNOPSIS
    Review a public policy source, provision an isolated stack, ingest reviewed files, and deploy.
.DESCRIPTION
    Requires explicit Azure subscription, source-review confirmation, and deployment confirmation.
    All regional Azure resources are created in UAE North. No existing customer stack is reused.
#>
[CmdletBinding()]
param(
    [string]$Subscription,
    [string]$Website,
    [ValidatePattern('^[a-z][a-z0-9-]{1,9}$')][string]$Name = 'policies',
    [ValidateSet('dev','test','prod')][string]$EnvironmentName = 'dev',
    [string]$ConfigPath = '.\customer.json',
    [string]$PythonPath = '.\.venv\Scripts\python.exe',
    [switch]$Rediscover,
    [switch]$UpdateExisting,
    [switch]$EnableConversationHistory,
    [ValidateSet('westcentralus','northcentralus','centralus','brazilsouth','canadacentral','westus2','eastus2','francecentral','japaneast','southeastasia','centralindia','southafricanorth','switzerlandnorth','uaenorth','ukwest','northeurope','westeurope','norwayeast','koreacentral','australiaeast','canadaeast','eastasia','germanywestcentral','uksouth','australiacentral','australiasoutheast','japanwest','koreasouth','southindia','westindia','westus','southcentralus','eastus','westus3','jioindiawest','swedencentral','qatarcentral','polandcentral','italynorth','israelcentral','spaincentral','newzealandnorth','mexicocentral','indonesiacentral','chilecentral','malaysiawest','austriaeast','belgiumcentral','denmarkeast','indiasouthcentral')]
    [string]$CosmosRegion,
    [string]$PackageIndexUrl = $(if ($env:PIP_INDEX_URL) { $env:PIP_INDEX_URL } else { 'https://pypi.org/simple' })
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$root = $PSScriptRoot
Push-Location $root
try {
    $python = if ([IO.Path]::IsPathRooted($PythonPath)) { $PythonPath } else { Join-Path $root $PythonPath }
    $configFile = if ([IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $root $ConfigPath }
    if (Test-Path $configFile) {
        $profile = Get-Content $configFile -Raw | ConvertFrom-Json
        if (-not $Subscription) { $Subscription = $profile.deployment.subscription }
        if (-not $Website) { $Website = $profile.source.website }
        if (-not $PSBoundParameters.ContainsKey('Name')) { $Name = $profile.resources.applicationName }
        if (-not $PSBoundParameters.ContainsKey('EnvironmentName')) { $EnvironmentName = $profile.resources.environmentName }
        if (-not $CosmosRegion) { $CosmosRegion = $profile.deployment.cosmosRegion }
    }
    if (-not $Subscription -or -not $Website) { throw 'Set deployment.subscription and source.website in the selected profile or pass -Subscription and -Website.' }
    if (-not (Test-Path $python)) { throw "Python environment not found: $python. Install from requirements-dev.lock first." }
    $relativeConfig = [IO.Path]::GetRelativePath($root, $configFile)
    if ($relativeConfig -eq '..' -or $relativeConfig.StartsWith("..$([IO.Path]::DirectorySeparatorChar)") -or [IO.Path]::IsPathRooted($relativeConfig)) {
        throw 'Customer profile must be inside the repository build context. Place customer.json at the repository root.'
    }
    $account = az account show --subscription $Subscription --output json | ConvertFrom-Json
    if (-not $account -or $account.state -ne 'Enabled') { throw "Subscription '$Subscription' is unavailable. Run az login and retry." }
    $signedIn = az ad signed-in-user show --query '{id:id,name:displayName}' --output json | ConvertFrom-Json
    if (-not $signedIn.id) { throw 'Could not resolve the signed-in Entra user needed for scoped deployer permissions.' }

    $acaUsage = az rest --method get --url "https://management.azure.com/subscriptions/$Subscription/providers/Microsoft.App/locations/uaenorth/usages?api-version=2024-03-01" --query "value[?name.value=='ManagedEnvironmentCount'] | [0].{used:currentValue,limit:limit}" --output json | ConvertFrom-Json
    if (-not $acaUsage -or ($acaUsage.limit - $acaUsage.used) -lt 1) { throw 'No confirmed Container Apps managed-environment quota remains in UAE North. Request capacity or choose another subscription; this script will not change region.' }
    $searchUsage = az rest --method get --url "https://management.azure.com/subscriptions/$Subscription/providers/Microsoft.Search/locations/uaenorth/usages?api-version=2025-05-01" --query "value[?name.value=='basic'] | [0].{used:currentValue,limit:limit}" --output json | ConvertFrom-Json
    if (-not $searchUsage -or ($searchUsage.limit - $searchUsage.used) -lt 1) { throw 'No confirmed Azure AI Search Basic service quota remains in UAE North. Request capacity or choose another subscription; this script will not change region or SKU.' }

    $newProfile = -not (Test-Path $configFile)
    if ($newProfile) {
        & $python (Join-Path $root 'configure_accelerator.py') --website $Website --name $Name --output $configFile
        if ($LASTEXITCODE -ne 0) { throw 'Customer configuration creation failed.' }
    }
    $config = Get-Content $configFile -Raw | ConvertFrom-Json
    $runtimeJson = & $python (Join-Path $root 'configure_accelerator.py') --check $configFile
    if ($LASTEXITCODE -ne 0) { throw 'Configuration validation failed before deployment.' }
    if ($config.source.website -ne $Website) { throw "The saved profile points to '$($config.source.website)', not '$Website'. Review ConfigPath instead of silently replacing it." }
    if ($config.resources.applicationName -ne $Name) { throw "Profile name is '$($config.resources.applicationName)'; rerun with -Name $($config.resources.applicationName)." }
    $validateConfig = "import sys; from pathlib import Path; sys.path.insert(0, str(Path('webapp'))); from accelerator_config import load_config; from source_manifest import documents; config=load_config(Path(sys.argv[1])); documents(config)"
    & $python -c $validateConfig $configFile
    if ($LASTEXITCODE -ne 0) { throw 'Customer profile or reviewed source manifest failed validation; no Azure resources were changed.' }
    if ($config.branding.logo.StartsWith('/assets/')) {
        $logoPath = Join-Path (Join-Path $root 'webapp\assets') $config.branding.logo.Substring('/assets/'.Length)
        if (-not (Test-Path $logoPath)) { throw "Configured branding image not found at '$logoPath'; no Azure resources were changed." }
    }
    $manifest = Join-Path $root $config.source.manifest
    if (-not (Test-Path $manifest)) { throw "Reviewed manifest not found at '$manifest'; no Azure resources were changed." }
    if ($newProfile -or $Rediscover -or -not (Test-Path $manifest)) {
        & $python (Join-Path $root 'policy_sources.py') --config $configFile --output $manifest
        if ($LASTEXITCODE -ne 0) { throw 'Bounded source discovery failed; no Azure resources were changed.' }
    }
    $review = Get-Content $manifest -Raw | ConvertFrom-Json

    $modelUsages = az rest --method get --url "https://management.azure.com/subscriptions/$Subscription/providers/Microsoft.CognitiveServices/locations/uaenorth/usages?api-version=2023-05-01" --query "value[?name.value=='OpenAI.$($config.resources.chatModelSku).$($config.resources.chatModel)'] | [0].{used:currentValue,limit:limit}" --output json | ConvertFrom-Json
    if (-not $modelUsages -or ($modelUsages.limit - $modelUsages.used) -lt $config.resources.chatModelCapacity) { throw "Insufficient or unverified UAE North quota for $($config.resources.chatModelSku)/$($config.resources.chatModel). Check the subscription/model capacity before provisioning; no fallback model or region is selected." }
    $embeddingUsages = az rest --method get --url "https://management.azure.com/subscriptions/$Subscription/providers/Microsoft.CognitiveServices/locations/uaenorth/usages?api-version=2023-05-01" --query "value[?name.value=='OpenAI.$($config.resources.embeddingModelSku).$($config.resources.embeddingModel)'] | [0].{used:currentValue,limit:limit}" --output json | ConvertFrom-Json
    if (-not $embeddingUsages -or ($embeddingUsages.limit - $embeddingUsages.used) -lt $config.resources.embeddingModelCapacity) { throw "Insufficient or unverified UAE North quota for $($config.resources.embeddingModelSku)/$($config.resources.embeddingModel). Check the subscription/model capacity before provisioning; no fallback model or region is selected." }

    $historyEnabled = $EnableConversationHistory.IsPresent
    if ($historyEnabled) {
        if (-not $CosmosRegion) { throw 'Conversation history requires an explicit -CosmosRegion; capacity is not verified by the Cosmos quota API.' }
        $cosmosRegions = @(az provider show --namespace Microsoft.DocumentDB --query "resourceTypes[?resourceType=='databaseAccounts'].locations[]" --output tsv)
        if ($LASTEXITCODE -ne 0 -or -not ($cosmosRegions | Where-Object { $_.Replace(' ', '').ToLowerInvariant() -eq $CosmosRegion })) {
            throw "Cosmos DB account resources are not listed for region '$CosmosRegion'. No resources were changed."
        }
        Write-Host "Cosmos DB quota API is unsupported for this subscription/provider; capacity in $CosmosRegion is unverified. The base application remains in UAE North." -ForegroundColor Yellow
        if ((Read-Host "Type COSMOS to add billable conversation history in $CosmosRegion, or anything else to stop") -cne 'COSMOS') {
            Write-Host 'Stopped before provisioning. No Azure resources were changed.'
            return
        }
        if ($CosmosRegion -ne 'uaenorth' -and (Read-Host "Cosmos history will be stored in $CosmosRegion, outside UAE North. Type RESIDENCY to accept this data-residency choice") -cne 'RESIDENCY') {
            Write-Host 'Stopped before provisioning. No Azure resources were changed.'
            return
        }
    }

    Write-Host "`nReviewed source preview: $($review.documents.Count) document(s); skipped $($review.skipped.Count); truncated=$($review.truncated)" -ForegroundColor Cyan
    $review.documents | Select-Object title,format,url | Format-Table -Wrap -AutoSize
    Write-Host 'Review titles and URLs above and edit the manifest if needed.' -ForegroundColor Yellow
    if ((Read-Host 'Type INGEST to approve this exact manifest for OCR/upload, or anything else to stop') -cne 'INGEST') {
        Write-Host "Stopped before provisioning. Your reviewed profile and manifest remain at $configFile and $manifest."
        return
    }

    $createdAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $sessionId = [guid]::NewGuid().ToString()
    $deploymentName = "$Name-$EnvironmentName-$(Get-Date -Format yyyyMMddHHmmss)"
    $phase1Image = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    $existingGroups = @(az group list --subscription $Subscription --output json | ConvertFrom-Json | Where-Object {
        $_.tags.project -eq $Name -and $_.tags.environment -in @($EnvironmentName, "$Name-$EnvironmentName")
    })
    if ($existingGroups.Count -gt 1) { throw "Multiple resource groups match project '$Name' and environment '$EnvironmentName'; resolve the target explicitly before continuing." }
    if ($existingGroups.Count -eq 1) {
        if (-not $UpdateExisting) { throw "Resource group '$($existingGroups[0].name)' already exists for this project. Refusing to reuse it; pass -UpdateExisting only after reviewing the what-if plan." }
        $existingApps = @(az containerapp list --resource-group $existingGroups[0].name --subscription $Subscription --output json | ConvertFrom-Json)
        if ($existingApps.Count -gt 1) { throw "More than one Container App exists in $($existingGroups[0].name); refusing an ambiguous update." }
        if ($existingApps.Count -eq 1) {
            $phase1Image = $existingApps[0].properties.template.containers[0].image
            if (-not $phase1Image) { throw 'Could not read the current Container App image; refusing a placeholder downgrade.' }
        }
    }
    elseif ($UpdateExisting) { throw "-UpdateExisting was specified, but no existing resource group was found for '$Name' / '$EnvironmentName'. Remove the switch for a fresh stack." }
    $common = @(
        "environmentName=$EnvironmentName", "projectName=$Name", 'location=uaenorth',
        "sessionId=$sessionId", "createdAt=$createdAt", "deployedBy=$($signedIn.name)",
        "deployerObjectId=$($signedIn.id)",
        "chatDeploymentName=$($config.resources.chatDeployment)", "chatModelName=$($config.resources.chatModel)",
        "chatModelVersion=$($config.resources.chatModelVersion)", "chatModelSku=$($config.resources.chatModelSku)",
        "chatModelCapacity=$($config.resources.chatModelCapacity)", "embeddingDeploymentName=$($config.resources.embeddingDeployment)",
        "embeddingModelName=$($config.resources.embeddingModel)", "embeddingModelVersion=$($config.resources.embeddingModelVersion)",
        "embeddingModelSku=$($config.resources.embeddingModelSku)", "embeddingModelCapacity=$($config.resources.embeddingModelCapacity)",
        "knowledgeBaseName=$($config.resources.knowledgeBase)", "applicationTitle=$($config.branding.title)",
        "organizationName=$($config.branding.organization)", "organizationShortName=$($config.branding.shortName)",
        "logoUrl=$($config.branding.logo)", "historyEnabled=$($historyEnabled.ToString().ToLowerInvariant())",
        "historyDatabaseName=$($config.history.database)", "historyContainerName=$($config.history.container)",
        "historyRetentionDays=$($config.history.retentionDays)", 'provisionStorage=false'
    )
    $runtimeParameterFile = Join-Path ([IO.Path]::GetTempPath()) "$deploymentName-runtime.parameters.json"
    $deploymentRuntime = $runtimeJson | ConvertFrom-Json -AsHashtable
    $deploymentRuntime.Remove('HISTORY_ENABLED')
    if (-not $historyEnabled) { $deploymentRuntime.Remove('COSMOS_ENDPOINT') }
    $runtimeParameters = @{ parameters = @{ runtimeSettings = @{ value = $deploymentRuntime } } }
    $runtimeParameters | ConvertTo-Json -Depth 10 | Set-Content $runtimeParameterFile -Encoding utf8
    $common += "@$runtimeParameterFile"
    if ($historyEnabled) { $common += "cosmosLocation=$CosmosRegion" }
    $phase1Params = $common + "containerImage=$phase1Image"
    Write-Host "`nValidating isolated $Name deployment in $($account.name) ($Subscription), UAE North..." -ForegroundColor Cyan
    az deployment sub what-if --name $deploymentName --location uaenorth --subscription $Subscription --template-file (Join-Path $root 'infra\main.bicep') --parameters (Join-Path $root 'infra\main.parameters.json') --parameters $phase1Params --output json
    if ($LASTEXITCODE -ne 0) { throw 'Bicep what-if failed. No deployment was started.' }
    if ((Read-Host "Type DEPLOY to provision the listed $Name resources in UAE North, or anything else to stop") -cne 'DEPLOY') {
        Write-Host 'Stopped before provisioning. No Azure resources were changed.'
        return
    }

    $deployment = az deployment sub create --name $deploymentName --location uaenorth --subscription $Subscription --template-file (Join-Path $root 'infra\main.bicep') --parameters (Join-Path $root 'infra\main.parameters.json') --parameters $phase1Params --output json | ConvertFrom-Json
    $outputs = $deployment.properties.outputs
    $rg = $outputs.resourceGroupName.value
    $search = $outputs.searchServiceName.value
    $acr = $outputs.containerRegistryName.value
    $openAi = $outputs.openAIAccountName.value

    $env:SEARCH_KEY = az search admin-key show --service-name $search --resource-group $rg --subscription $Subscription --query primaryKey --output tsv
    try {
        & $python (Join-Path $root 'ingest_policies.py') --config $configFile --search-endpoint $outputs.searchEndpoint.value --openai-endpoint "https://$openAi.openai.azure.com" --document-intelligence-endpoint $outputs.documentIntelligenceEndpoint.value --apply
        if ($LASTEXITCODE -ne 0) { throw 'Policy ingestion failed. The reviewed manifest and deployment are retained for safe resumption.' }
    }
    finally { Remove-Item Env:SEARCH_KEY -ErrorAction SilentlyContinue }

    $imageTag = "$Name-assistant:release-$(Get-Date -Format yyyyMMddHHmmss)"
    $image = "$acr.azurecr.io/$imageTag"
    az acr build --registry $acr --subscription $Subscription --image $imageTag --file (Join-Path $root 'Dockerfile') --build-arg "ACCELERATOR_CONFIG=$($relativeConfig.Replace('\','/'))" --build-arg "PIP_INDEX_URL=$PackageIndexUrl" --no-logs $root
    if ($LASTEXITCODE -ne 0) { throw 'ACR image build failed. Infrastructure and ingestion are retained; retry image build after resolving the error.' }

    $imageDeploymentName = "$deploymentName-image"
    $imageParams = $common + "containerImage=$image"
    az deployment sub what-if --name $imageDeploymentName --location uaenorth --subscription $Subscription --template-file (Join-Path $root 'infra\main.bicep') --parameters (Join-Path $root 'infra\main.parameters.json') --parameters $imageParams --output json
    if ($LASTEXITCODE -ne 0) { throw 'Image-phase what-if failed; the placeholder revision remains running.' }
    if ((Read-Host "Type DEPLOY to roll out $image, or anything else to keep the placeholder revision") -cne 'DEPLOY') {
        Write-Host "Image remains in ACR; placeholder revision is unchanged. Image: $image"
        return
    }
    az deployment sub create --name $imageDeploymentName --location uaenorth --subscription $Subscription --template-file (Join-Path $root 'infra\main.bicep') --parameters (Join-Path $root 'infra\main.parameters.json') --parameters $imageParams --output none
    if ($LASTEXITCODE -ne 0) { throw 'Image-phase infrastructure update failed.' }

    $app = $outputs.containerAppName.value
    $fqdn = az containerapp show --name $app --resource-group $rg --subscription $Subscription --query properties.configuration.ingress.fqdn --output tsv
    $url = "https://$fqdn"
    $health = Invoke-WebRequest -Uri "$url/healthz" -MaximumRedirection 3 -TimeoutSec 30
    if ($health.StatusCode -ne 200) { throw "Health probe failed for $url/healthz" }
    Write-Host "Deployment complete: $url" -ForegroundColor Green
    $historySummary = if ($historyEnabled) { "Cosmos ($CosmosRegion): $($outputs.cosmosEndpoint.value)" } else { 'Cosmos conversation history: not provisioned' }
    Write-Host "Resource group: $rg | $historySummary" -ForegroundColor Green
}
finally {
    if ($runtimeParameterFile -and (Test-Path $runtimeParameterFile)) { Remove-Item $runtimeParameterFile }
    Pop-Location
}
