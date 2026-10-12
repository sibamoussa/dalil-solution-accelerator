targetScope = 'resourceGroup'

param cosmosLocation string = 'swedencentral'
param accountName string
param databaseName string = 'dalil'
param containerName string = 'conversations'
@minValue(1)
@maxValue(365)
param retentionDays int = 30
param identityPrincipalId string
// This resource-scoped tag is the approved exception to the inherited Cosmos public-network modify policy.
param tags object = {
  SecurityControl: 'Ignore'
}

module cosmosHistory 'modules/cosmos-history.bicep' = {
  name: 'cosmos-history'
  params: {
    cosmosLocation: cosmosLocation
    accountName: accountName
    databaseName: databaseName
    containerName: containerName
    retentionDays: retentionDays
    identityPrincipalId: identityPrincipalId
    tags: tags
  }
}

output accountName string = cosmosHistory.outputs.name
output endpoint string = cosmosHistory.outputs.endpoint
output accountId string = cosmosHistory.outputs.accountId
output databaseName string = cosmosHistory.outputs.databaseName
output containerName string = cosmosHistory.outputs.containerName