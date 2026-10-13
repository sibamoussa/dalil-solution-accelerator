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
param runtimeSettings object = {}
param tags object

var chatEndpoint = '${openAIEndpoint}openai/deployments/${chatDeploymentName}/chat/completions?api-version=2024-10-21'
var isPlaceholder = startsWith(containerImage, 'mcr.microsoft.com/')
var defaultRuntimeSettings = {
  APP_TITLE: applicationTitle
  ORGANIZATION_SHORT_NAME: organizationShortName
  ORGANIZATION_NAME: organizationName
  LOGO_URL: logoUrl
  ALLOWED_AZURE_REGION: 'uaenorth'
  SEARCH_RESOURCE_REGION: 'uaenorth'
  SEARCH_ENDPOINT: searchEndpoint
  FOUNDRY_KNOWLEDGE_BASE: knowledgeBaseName
  COSMOS_ENDPOINT: cosmosEndpoint
  HISTORY_ENABLED: historyEnabled ? 'true' : 'false'
  AZURE_CLIENT_ID: identityClientId
  AOAI_CHAT_ENDPOINT: chatEndpoint
  AOAI_FAST_ENDPOINT: chatEndpoint
  AOAI_USE_GENERATIVE_SYNTHESIS: 'true'
  APPLICATIONINSIGHTS_CONNECTION_STRING: appInsightsConnectionString
}
var mergedRuntimeSettings = union(defaultRuntimeSettings, runtimeSettings)

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
          env: [for entry in items(mergedRuntimeSettings): {
            name: entry.key
            value: string(entry.value)
          }]
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