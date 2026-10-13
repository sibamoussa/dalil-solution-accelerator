targetScope = 'subscription'

param environmentName string
@minLength(2)
@maxLength(10)
param projectName string = 'dalil'
@allowed([
  'uaenorth'
])
param location string = 'uaenorth'
param sessionId string
param deployedBy string
param createdAt string
param deployerObjectId string
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param chatModelVersion string
param embeddingModelVersion string
param chatDeploymentName string = 'gpt-5-1'
param chatModelName string = 'gpt-5.1'
param chatModelCapacity int = 10
param chatModelSku string = 'GlobalStandard'
param embeddingDeploymentName string = 'text-embedding-3-large'
param embeddingModelName string = 'text-embedding-3-large'
param embeddingModelCapacity int = 100
param embeddingModelSku string = 'Standard'
param knowledgeBaseName string = 'dalil-policies-2026'
param applicationTitle string = 'Dalil'
param organizationName string = 'Dalil Solution Accelerator'
param organizationShortName string = 'Dalil'
param logoUrl string = '/assets/dalil-mark.svg'
param historyEnabled bool = false
param runtimeSettings object = {}
@allowed([
  'westcentralus'
  'northcentralus'
  'centralus'
  'brazilsouth'
  'canadacentral'
  'westus2'
  'eastus2'
  'francecentral'
  'japaneast'
  'southeastasia'
  'centralindia'
  'southafricanorth'
  'switzerlandnorth'
  'uaenorth'
  'ukwest'
  'northeurope'
  'westeurope'
  'uksouth'
  'norwayeast'
  'koreacentral'
  'australiaeast'
  'canadaeast'
  'eastasia'
  'germanywestcentral'
  'australiacentral'
  'australiasoutheast'
  'japanwest'
  'koreasouth'
  'southindia'
  'westindia'
  'westus'
  'southcentralus'
  'eastus'
  'westus3'
  'jioindiawest'
  'swedencentral'
  'qatarcentral'
  'polandcentral'
  'italynorth'
  'israelcentral'
  'spaincentral'
  'newzealandnorth'
  'mexicocentral'
  'indonesiacentral'
  'chilecentral'
  'malaysiawest'
  'austriaeast'
  'belgiumcentral'
  'denmarkeast'
  'indiasouthcentral'
])
param cosmosLocation string = 'uaenorth'
param historyDatabaseName string = 'dalil'
param historyContainerName string = 'conversations'
@minValue(1)
@maxValue(365)
param historyRetentionDays int = 30
param provisionStorage bool = true
param sourceDocumentsContainerName string = 'source-documents'

var suffix = take(uniqueString(subscription().id, projectName, environmentName), 8)
var resourceGroupName = 'rg-${projectName}-${environmentName}-${suffix}'
var resourceNames = {
  app: 'ca-${projectName}-${environmentName}-${suffix}'
  appInsights: 'appi-${projectName}-${environmentName}-${suffix}'
  containerEnvironment: 'cae-${projectName}-${environmentName}-${suffix}'
  cosmos: 'cosmos-${projectName}-${environmentName}-${take(uniqueString(cosmosLocation), 4)}-${suffix}'
  documentIntelligence: 'di-${projectName}-${environmentName}-${suffix}'
  identity: 'id-${projectName}-${environmentName}-${suffix}'
  keyVault: 'kv-${projectName}-${suffix}'
  logAnalytics: 'log-${projectName}-${environmentName}-${suffix}'
  openAI: 'oai-${projectName}-${environmentName}-${suffix}'
  registry: 'cr${replace(projectName, '-', '')}${suffix}'
  search: 'srch-${projectName}-${environmentName}-${suffix}'
  storage: 'st${replace(projectName, '-', '')}${suffix}'
}
var managedTags = {
  'app-onboard-skill': 'true'
  'app-onboard-session-id': sessionId
  'created-at': createdAt
  environment: environmentName
  'deployed-by': deployedBy
  project: projectName
}
// Preserve the legacy Dalil tag keys during updates while standardizing new deployments.
var tags = union(managedTags, {
  #disable-next-line prefer-unquoted-property-names
  'createdAt': createdAt
  #disable-next-line prefer-unquoted-property-names
  'deployedBy': deployedBy
  #disable-next-line prefer-unquoted-property-names
  'sessionId': sessionId
})

resource resourceGroup 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module observability 'modules/observability.bicep' = {
  scope: resourceGroup
  name: 'observability'
  params: {
    location: location
    logAnalyticsName: resourceNames.logAnalytics
    appInsightsName: resourceNames.appInsights
    tags: tags
  }
}

module identity 'modules/identity.bicep' = {
  scope: resourceGroup
  name: 'identity'
  params: {
    location: location
    identityName: resourceNames.identity
    tags: tags
  }
}

module registry 'modules/registry.bicep' = {
  scope: resourceGroup
  name: 'registry'
  params: {
    location: location
    registryName: resourceNames.registry
    tags: tags
  }
}

module keyVault 'modules/key-vault.bicep' = {
  scope: resourceGroup
  name: 'key-vault'
  params: {
    location: location
    keyVaultName: resourceNames.keyVault
    tenantId: tenant().tenantId
    tags: tags
  }
}

module openAI 'modules/openai.bicep' = {
  scope: resourceGroup
  name: 'openai'
  params: {
    location: location
    accountName: resourceNames.openAI
    chatModelVersion: chatModelVersion
    embeddingModelVersion: embeddingModelVersion
    chatDeploymentName: chatDeploymentName
    chatModelName: chatModelName
    chatModelCapacity: chatModelCapacity
    chatModelSku: chatModelSku
    embeddingDeploymentName: embeddingDeploymentName
    embeddingModelName: embeddingModelName
    embeddingModelCapacity: embeddingModelCapacity
    embeddingModelSku: embeddingModelSku
    tags: tags
  }
}

module search 'modules/search.bicep' = {
  scope: resourceGroup
  name: 'search'
  params: {
    location: location
    serviceName: resourceNames.search
    tags: tags
  }
}

module storage 'modules/storage.bicep' = if (provisionStorage) {
  scope: resourceGroup
  name: 'storage'
  params: {
    location: location
    accountName: resourceNames.storage
    containerName: sourceDocumentsContainerName
    tags: tags
  }
}

module cosmosHistory 'modules/cosmos-history.bicep' = if (historyEnabled) {
  scope: resourceGroup
  name: 'cosmos-history'
  params: {
    cosmosLocation: cosmosLocation
    accountName: resourceNames.cosmos
    databaseName: historyDatabaseName
    containerName: historyContainerName
    retentionDays: historyRetentionDays
    identityPrincipalId: identity.outputs.principalId
    tags: tags
  }
}

module documentIntelligence 'modules/document-intelligence.bicep' = {
  scope: resourceGroup
  name: 'document-intelligence'
  params: {
    location: location
    accountName: resourceNames.documentIntelligence
    tags: tags
  }
}

module containerEnvironment 'modules/container-environment.bicep' = {
  scope: resourceGroup
  name: 'container-environment'
  params: {
    location: location
    environmentName: resourceNames.containerEnvironment
    logAnalyticsCustomerId: observability.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: observability.outputs.logAnalyticsSharedKey
    tags: tags
  }
}

module roleAssignments 'modules/role-assignments.bicep' = {
  scope: resourceGroup
  name: 'role-assignments'
  params: {
    identityPrincipalId: identity.outputs.principalId
    deployerObjectId: deployerObjectId
    registryName: resourceNames.registry
    keyVaultName: resourceNames.keyVault
    openAIAccountName: resourceNames.openAI
    searchServiceName: resourceNames.search
    searchPrincipalId: search.outputs.principalId
    documentIntelligenceAccountName: resourceNames.documentIntelligence
  }
  dependsOn: [
    registry
    keyVault
    documentIntelligence
  ]
}

module secrets 'modules/secrets.bicep' = {
  scope: resourceGroup
  name: 'secrets'
  params: {
    keyVaultName: resourceNames.keyVault
    searchServiceName: resourceNames.search
  }
  dependsOn: [
    openAI
    search
    roleAssignments
  ]
}

module containerApp 'modules/container-app.bicep' = {
  scope: resourceGroup
  name: 'container-app'
  params: {
    location: location
    appName: resourceNames.app
    environmentId: containerEnvironment.outputs.id
    identityResourceId: identity.outputs.id
    identityClientId: identity.outputs.clientId
    registryServer: registry.outputs.loginServer
    containerImage: containerImage
    searchEndpoint: search.outputs.endpoint
    openAIEndpoint: openAI.outputs.endpoint
    chatDeploymentName: chatDeploymentName
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    projectName: projectName
    knowledgeBaseName: knowledgeBaseName
    applicationTitle: applicationTitle
    organizationName: organizationName
    organizationShortName: organizationShortName
    logoUrl: logoUrl
    cosmosEndpoint: cosmosHistory.?outputs.endpoint ?? ''
    historyEnabled: historyEnabled
    runtimeSettings: runtimeSettings
    tags: tags
  }
  dependsOn: [
    roleAssignments
    secrets
  ]
}

output resourceGroupName string = resourceGroup.name
output containerAppName string = containerApp.outputs.name
output containerAppUrl string = containerApp.outputs.url
output containerRegistryName string = registry.outputs.name
output openAIAccountName string = openAI.outputs.name
output keyVaultName string = keyVault.outputs.name
output searchServiceName string = search.outputs.name
output searchEndpoint string = search.outputs.endpoint
output searchIndexName string = projectName == 'dalil' ? 'dalil-gazettes-2026-index' : ''
output storageAccountName string = storage.?outputs.name ?? ''
output sourceDocumentsContainerName string = storage.?outputs.containerName ?? ''
output sourceDocumentsBaseUrl string = storage.?outputs.containerUrl ?? ''
output documentIntelligenceName string = documentIntelligence.outputs.name
output documentIntelligenceEndpoint string = documentIntelligence.outputs.endpoint
output cosmosAccountName string = cosmosHistory.?outputs.name ?? ''
output cosmosEndpoint string = cosmosHistory.?outputs.endpoint ?? ''
output cosmosDatabaseName string = cosmosHistory.?outputs.databaseName ?? ''
output cosmosContainerName string = cosmosHistory.?outputs.containerName ?? ''