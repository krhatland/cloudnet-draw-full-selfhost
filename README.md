# cloudnet-draw-full-selfhost
IaC and Function code

## Deploy to Azure

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/main.bicep)

### Parameters

| Parameter            | Description                                  |
|-----------------------|----------------------------------------------|
| `functionAppName`    | Name of the Function App                     |
| `storageAccountName` | Name of the Storage Account                  |
| `appServicePlanName` | Name of the App Service Plan (Consumption)   |
| `uamiName`           | User Assigned Managed Identity (Optional)    |

