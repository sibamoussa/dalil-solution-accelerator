param location string
param accountName string
param tags object

resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

output name string = documentIntelligence.name
output endpoint string = documentIntelligence.properties.endpoint
