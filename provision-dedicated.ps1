<#
.SYNOPSIS
    Provision a fully isolated Dalil Knowledge Agent stack in UAE North.

.DESCRIPTION
    Creates new project-owned Azure resources, optionally ingests the
    2026 gazettes, builds in the new ACR, and
    deploys the image. Public gazette citations require no Storage SAS.
    It never reads from or updates ADMO resources.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Subscription,
    [string]$EnvironmentName = "dev",
    [string]$Location = "uaenorth",
    [switch]$IngestGazettes,
    [switch]$EnableConversationHistory,
    [ValidateSet('westcentralus','northcentralus','centralus','brazilsouth','canadacentral','westus2','eastus2','francecentral','japaneast','southeastasia','centralindia','southafricanorth','switzerlandnorth','uaenorth','ukwest','northeurope','westeurope','norwayeast','koreacentral','australiaeast','canadaeast','eastasia','germanywestcentral','uksouth','australiacentral','australiasoutheast','japanwest','koreasouth','southindia','westindia','westus','southcentralus','eastus','westus3','jioindiawest','swedencentral','qatarcentral','polandcentral','italynorth','israelcentral','spaincentral','newzealandnorth','mexicocentral','indonesiacentral','chilecentral','malaysiawest','austriaeast','belgiumcentral','denmarkeast','indiasouthcentral')]
    [string]$CosmosRegion,
    [string]$PackageIndexUrl = $(if ($env:PIP_INDEX_URL) { $env:PIP_INDEX_URL } else { "https://pypi.org/simple" })
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
if ($Location -ne "uaenorth") {
    throw "This project is restricted to uaenorth."
}

$account = az account show --subscription $Subscription --output json | ConvertFrom-Json
if (-not $account) {
    throw "Azure subscription '$Subscription' is unavailable. Run 'az login' and retry."
}

$signedIn = az ad signed-in-user show --query "{id:id,name:displayName}" --output json | ConvertFrom-Json
$sessionId = [guid]::NewGuid().ToString()
$createdAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$deploymentName = "dalil-$EnvironmentName-$(Get-Date -Format yyyyMMddHHmmss)"

$historyEnabled = $EnableConversationHistory.IsPresent
if ($historyEnabled) {
    if (-not $CosmosRegion) { throw "Conversation history requires an explicit -CosmosRegion; capacity is not verified by the Cosmos quota API." }
    $cosmosRegions = @(az provider show --namespace Microsoft.DocumentDB --query "resourceTypes[?resourceType=='databaseAccounts'].locations[]" --output tsv)
    if ($LASTEXITCODE -ne 0 -or -not ($cosmosRegions | Where-Object { $_.Replace(' ', '').ToLowerInvariant() -eq $CosmosRegion })) {
        throw "Cosmos DB account resources are not listed for region '$CosmosRegion'. No resources were changed."
    }
    Write-Host "Cosmos DB quota API is unsupported for this subscription/provider; capacity in $CosmosRegion is unverified. The base application remains in UAE North." -ForegroundColor Yellow
    if ((Read-Host "Type COSMOS to add billable conversation history in $CosmosRegion, or anything else to stop") -cne "COSMOS") {
        Write-Host "Stopped before deployment. No Azure resources were changed."
        return
    }
    if ($CosmosRegion -ne "uaenorth" -and (Read-Host "Cosmos history will be stored in $CosmosRegion, outside UAE North. Type RESIDENCY to accept this data-residency choice") -cne "RESIDENCY") {
        Write-Host "Stopped before deployment. No Azure resources were changed."
        return
    }
}
$deploymentCosmosRegion = if ($historyEnabled) { $CosmosRegion } else { "uaenorth" }

Write-Host "Provisioning isolated resources in UAE North..." -ForegroundColor Cyan
$deployment = az deployment sub create `
    --name $deploymentName `
    --location $Location `
    --subscription $Subscription `
    --template-file "infra/main.bicep" `
    --parameters "infra/main.parameters.json" `
    --parameters `
        environmentName=$EnvironmentName `
        location=$Location `
        sessionId=$sessionId `
        createdAt=$createdAt `
        deployedBy=$($signedIn.name) `
        deployerObjectId=$($signedIn.id) `
        containerImage="mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" `
        historyEnabled=$($historyEnabled.ToString().ToLowerInvariant()) `
        cosmosLocation=$deploymentCosmosRegion `
    --output json | ConvertFrom-Json

$outputs = $deployment.properties.outputs
$resourceGroup = $outputs.resourceGroupName.value
$containerApp = $outputs.containerAppName.value
$registry = $outputs.containerRegistryName.value
$searchService = $outputs.searchServiceName.value
$storageAccount = $outputs.storageAccountName.value
$sourceContainer = $outputs.sourceDocumentsContainerName.value

if ($IngestGazettes) {
    $env:SEARCH_KEY = az search admin-key show `
        --service-name $searchService `
        --resource-group $resourceGroup `
        --subscription $Subscription `
        --query primaryKey `
        --output tsv
    try {
        & ".\.venv\Scripts\python.exe" ".\ingest_gazettes_foundry.py" `
            --search-endpoint $outputs.searchEndpoint.value `
            --openai-endpoint "https://$($outputs.openAIAccountName.value).openai.azure.com" `
            --document-intelligence-endpoint $outputs.documentIntelligenceEndpoint.value `
            --apply
        if ($LASTEXITCODE -ne 0) { throw "Gazette ingestion failed; resume before deploying the application" }
    }
    finally {
        Remove-Item Env:SEARCH_KEY -ErrorAction SilentlyContinue
    }
}

$imageTag = "dalil-knowledge-assistant:release-$(Get-Date -Format yyyyMMddHHmmss)"
$fullImage = "$registry.azurecr.io/$imageTag"
Write-Host "Building $fullImage..." -ForegroundColor Cyan
az acr build `
    --registry $registry `
    --subscription $Subscription `
    --image $imageTag `
    --file Dockerfile `
    --build-arg "PIP_INDEX_URL=$PackageIndexUrl" `
    .

Write-Host "Deploying the application image..." -ForegroundColor Cyan
az containerapp update `
    --name $containerApp `
    --resource-group $resourceGroup `
    --subscription $Subscription `
    --image $fullImage `
    --output none
az containerapp ingress update `
    --name $containerApp `
    --resource-group $resourceGroup `
    --subscription $Subscription `
    --target-port 8000 `
    --output none

$storageAccess = az storage account show `
    --name $storageAccount `
    --resource-group $resourceGroup `
    --subscription $Subscription `
    --query "{publicNetworkAccess:publicNetworkAccess,allowSharedKeyAccess:allowSharedKeyAccess}" `
    --output json | ConvertFrom-Json
if ($storageAccess.publicNetworkAccess -eq "Disabled") {
    Write-Host "Storage remains network-isolated. Gazette citations use original government PDF URLs."
}

$nonRegionalTypes = @(
    "Microsoft.Authorization/roleAssignments"
)
$wrongRegion = @(az resource list `
    --resource-group $resourceGroup `
    --subscription $Subscription `
    --output json | ConvertFrom-Json | Where-Object {
        $_.type -notin $nonRegionalTypes -and
        $_.location -and
        $_.location.ToLowerInvariant() -ne "uaenorth"
    })
if ($wrongRegion.Count -gt 0) {
    throw "Regional verification failed: $($wrongRegion.name -join ', ')"
}

$appUrl = "https://$(az containerapp show --name $containerApp --resource-group $resourceGroup --subscription $Subscription --query properties.configuration.ingress.fqdn --output tsv)"
Write-Host "Deployment complete: $appUrl" -ForegroundColor Green
Write-Host "Resource group: $resourceGroup" -ForegroundColor Green
Write-Host "Source container: $($outputs.sourceDocumentsBaseUrl.value)" -ForegroundColor Green