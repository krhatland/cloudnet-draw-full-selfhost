# cloudnet-draw-full-selfhost

Azure Function based network-topology exporter for Azure Marketplace Azure Application offers.

The solution deploys:

- an Azure Function on a daily timer
- an Azure Functions Flex Consumption hosting plan
- a system-assigned managed identity
- a storage account and blob container for topology output
- Application Insights and Log Analytics
- the RBAC needed for identity-based Azure Functions host storage and blob uploads

## Offer Variants

This repo is now organized around two free Azure Marketplace solution-template variants:

- `storage-only`: generate topology JSON plus HLD and MLD Draw.io files, then store them in Blob Storage
- `confluence-export`: do the same Blob Storage upload and also attach the generated files to a Confluence page

The function source is checked in under [`function`](/Users/kristoffer/cloudnet-draw-full-selfhost-2/function), the shared ARM template lives at [`infra/mainTemplate.json`](/Users/kristoffer/cloudnet-draw-full-selfhost-2/infra/mainTemplate.json), and the package-specific CreateUiDefinition files live under [`marketplace`](/Users/kristoffer/cloudnet-draw-full-selfhost-2/marketplace).

The UI definitions now use guided controls where Azure allows it:

- `StorageAccountSelector` for creating or reusing a storage account
- dropdowns for Flex Consumption memory, scale cap, and Python version
- step-based layout so deployment, scale, and Confluence settings are grouped logically

## Build Marketplace Packages

Run:

```bash
./scripts/build_marketplace_packages.sh
```

This produces:

- `dist/marketplace/storage-only.zip`
- `dist/marketplace/confluence-export.zip`

Each ZIP is structured the way Azure Application solution-template packaging expects:

- `mainTemplate.json`
- `createUiDefinition.json`
- `artifacts/function.zip`

## Deployment Parameters

Shared parameters:

- `functionAppName`
- `storageAccountName`
- `containerName`
- `location`
- `instanceMemoryMB`
- `maximumInstanceCount`
- `runtimeVersion`

Confluence-only parameters:

- `confluenceBaseUrl`
- `confluenceUsername`
- `confluenceApiToken`
- `confluencePageId`
- `confluenceAttachmentPrefix`

## Runtime Behavior

The function runs daily at midnight UTC (`0 0 0 * * *`).

For both variants it:

1. uses the managed identity to enumerate accessible subscriptions and collect VNet topology
2. stores the topology JSON and generated Draw.io files in the configured blob container

For the `confluence-export` variant it also:

3. uploads the JSON file and both diagrams to the configured Confluence page as attachments

## Notes

- This repo is prepared for free Azure Marketplace solution-template packaging, so the previous Marketplace metering flow has been removed.
- The deployment template now targets Azure Functions Flex Consumption where the selected region supports it.
- The Confluence implementation assumes attachment names based on the configured prefix:
  `prefix.json`, `prefix-mld.drawio`, and `prefix-hld.drawio`.
- The Confluence base URL can be provided with or without `/wiki`.
