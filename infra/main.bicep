@description('Location for all resources')
param location string = resourceGroup().location

@description('Name for the Function App')
param functionAppName string

@description('Name for the Storage Account')
param storageAccountName string

@description('Name for the Storage Account used to store drawings')
param drawingStorageAccountName string

@description('Name for the App Service Plan')
param appServicePlanName string

resource storage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
    encryption: {
      keySource: 'Microsoft.Storage'
      services: {
        blob: { enabled: true }
        file: { enabled: true }
      }
    }
    accessTier: 'Hot'
  }
}

resource drawingStorage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: drawingStorageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
    encryption: {
      keySource: 'Microsoft.Storage'
      services: {
        blob: { enabled: true }
        file: { enabled: true }
      }
    }
    accessTier: 'Hot'
  }
}

resource drawingContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2022-09-01' = {
  name: '${drawingStorage.name}/default/drawfunc'
  properties: {
    publicAccess: 'None'
  }
}

resource appServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
}

resource functionApp 'Microsoft.Web/sites@2022-03-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.10'
      appSettings: [
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${listKeys(storage.id, '2022-09-01').keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
        }
        {
          name: 'DRAWING_STORAGE_URL'
          value: drawingStorage.properties.primaryEndpoints.blob
        }
        {
          name: 'DRAWING_CONTAINER_NAME'
          value: 'drawfunc'
        }
      ]
    }
    httpsOnly: true
  }
}

resource drawingStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(functionApp.name, drawingStorage.id, 'blobcontrib')
  scope: drawingStorage
  properties: {
    principalId: functionApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}

output functionAppEndpoint string = 'https://${functionApp.properties.defaultHostName}'

