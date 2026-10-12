param location string
param appName string
param environmentId string
param identityResourceId string
param identityClientId string
param registryServer string
param containerImage string
param searchEndpoint string
param openAIEndpoint string
param chatDeploymentName string
param appInsightsConnectionString string
param projectName string
param knowledgeBaseName string
param applicationTitle string
param organizationName string
param organizationShortName string
param logoUrl string
param cosmosEndpoint string
param historyEnabled bool
param tags object

var chatEndpoint = '${openAIEndpoint}openai/deployments/${chatDeploymentName}/chat/completions?api-version=2024-10-21'
var isPlaceholder = startsWith(containerImage, 'mcr.microsoft.com/')

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityResourceId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: isPlaceholder ? 80 : 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: isPlaceholder ? [] : [
        {
          server: registryServer
          identity: identityResourceId
        }
      ]
    }
    template: {
      containers: [
        {
          name: '${projectName}-knowledge-assistant'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'APP_TITLE', value: applicationTitle }
            { name: 'ORGANIZATION_SHORT_NAME', value: organizationShortName }
            { name: 'ORGANIZATION_NAME', value: organizationName }
            { name: 'LOGO_URL', value: logoUrl }
            { name: 'ALLOWED_AZURE_REGION', value: 'uaenorth' }
            { name: 'SEARCH_RESOURCE_REGION', value: 'uaenorth' }
            { name: 'SEARCH_ENDPOINT', value: searchEndpoint }
            { name: 'FOUNDRY_KNOWLEDGE_BASE', value: knowledgeBaseName }
            { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
            { name: 'HISTORY_ENABLED', value: historyEnabled ? 'true' : 'false' }
            { name: 'AZURE_CLIENT_ID', value: identityClientId }
            { name: 'AOAI_CHAT_ENDPOINT', value: chatEndpoint }
            { name: 'AOAI_FAST_ENDPOINT', value: chatEndpoint }
            { name: 'AOAI_USE_GENERATIVE_SYNTHESIS', value: 'true' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
          ]
          probes: isPlaceholder ? [] : [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

output name string = app.name
output url string = 'https://${app.properties.configuration.ingress.fqdn}'