# cloudnet-draw-full-selfhost
IaC and Function code

## Deploy to Azure

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fkrhatland%2Fcloudnet-draw-full-selfhost%2Fmain%2Finfra%2Fmain.bicep)

### Parameters

| Parameter            | Description                                  |
|-----------------------|----------------------------------------------|
| `functionAppName`    | Name of the Function App                     |
| `storageAccountName` | Name of the Storage Account                  |
| `drawingStorageAccountName` | Name of the Storage Account for diagrams |
| `appServicePlanName` | Name of the App Service Plan (Consumption)   |
| `uamiName`           | User Assigned Managed Identity (Optional)    |

