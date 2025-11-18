import os
import json
import logging
import requests
from datetime import datetime

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError

# Import CloudNetDraw library modules
import cloudnetdraw.azure_client as azure_client
from cloudnetdraw.config import Config
from cloudnetdraw.diagram_generator import generate_mld_diagram, generate_hld_diagram


def main(mytimer: func.TimerRequest) -> None:
    """Azure Function entrypoint for generating network diagrams.

    This timer-triggered function collects Azure networking topology using
    Managed Identity authentication, saves the topology as JSON, and
    generates both mid-level (MLD) and high-level (HLD) Draw.io diagrams
    using the CloudNetDraw library. The resulting files are uploaded
    to a specified Blob Storage container.
    """
    logging.info("DrawTrigger function triggered")

    # Create a timestamp for file naming
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

    # Initialize credentials for CloudNetDraw using Managed Identity.
    azure_client._credentials = DefaultAzureCredential()

    # Discover all subscriptions available to this identity
    try:
        subscription_ids = azure_client.get_all_subscription_ids()
        logging.info(f"Found {len(subscription_ids)} subscriptions: {subscription_ids}")
    except Exception as e:
        logging.error(f"Failed to list subscriptions: {e}")
        return

    # Build the full VNet topology across the subscriptions
    try:
        topology = azure_client.get_vnet_topology_for_selected_subscriptions(subscription_ids)
    except Exception as e:
        logging.error(f"Failed to retrieve VNet topology: {e}")
        return

    # Persist topology to a temporary JSON file in /tmp
    json_file_name = f"{timestamp}_network_topology.json"
    json_file_path = f"/tmp/{json_file_name}"
    try:
        with open(json_file_path, "w") as json_file:
            json.dump(topology, json_file, indent=2)
        logging.info(f"Saved topology JSON to {json_file_path}")
    except Exception as e:
        logging.error(f"Failed to write topology JSON: {e}")
        return

    # Prepare diagram file paths
    diagram_file_name_mld = f"{timestamp}_network_diagram_MLD.drawio"
    diagram_file_path_mld = f"/tmp/{diagram_file_name_mld}"
    diagram_file_name_hld = f"{timestamp}_network_diagram_HLD.drawio"
    diagram_file_path_hld = f"/tmp/{diagram_file_name_hld}"

    # Load default configuration for diagram styling and thresholds
    config = Config()

    # Generate diagrams using CloudNetDraw
    try:
        generate_mld_diagram(diagram_file_path_mld, json_file_path, config)
        logging.info(f"Generated MLD diagram at {diagram_file_path_mld}")
        generate_hld_diagram(diagram_file_path_hld, json_file_path, config)
        logging.info(f"Generated HLD diagram at {diagram_file_path_hld}")
    except Exception as e:
        logging.error(f"Failed to generate diagrams: {e}")
        return

    # Upload the JSON and diagrams to Blob Storage
    account_url = os.environ.get("DRAWING_STORAGE_URL")
    container_name = os.environ.get("DRAWING_CONTAINER_NAME")
    if not account_url or not container_name:
        logging.error("Storage configuration missing: DRAWING_STORAGE_URL and DRAWING_CONTAINER_NAME must be set")
        return

    # Use Managed Identity to authenticate with Blob Storage
    blob_service_client = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())

    def upload_file(blob_name: str, file_path: str) -> None:
        """Helper to upload a local file to the configured blob container."""
        try:
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            with open(file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            logging.info(f"Uploaded {blob_name} to Blob Storage")
        except Exception as upload_error:
            logging.error(f"Failed to upload {blob_name}: {upload_error}")

    # Upload the JSON topology and both diagrams
    upload_file(json_file_name, json_file_path)
    upload_file(diagram_file_name_mld, diagram_file_path_mld)
    upload_file(diagram_file_name_hld, diagram_file_path_hld)

    # === Metered billing logic (1 charge per day max) ===
    try:
        if has_billed_today(blob_service_client, container_name):
            logging.info("Already billed for today, skipping metering event.")
        else:
            msi_token = get_msi_token()

            subscription_id = os.environ.get("SUBSCRIPTION_ID")
            rg_name = os.environ.get("RESOURCE_GROUP_NAME")
            plan_id = os.environ.get("PLAN_ID")

            if not subscription_id or not rg_name or not plan_id:
                logging.error(
                    "Missing metering configuration (SUBSCRIPTION_ID, RESOURCE_GROUP_NAME, PLAN_ID). "
                    "Skipping metering event."
                )
            else:
                resource_id = get_managed_app_resource_id(subscription_id, rg_name, msi_token)
                emit_meter_event(resource_id, plan_id, msi_token)
                mark_billed_today(blob_service_client, container_name)
                logging.info("Marketplace metering event submitted (1 unit).")
    except Exception as e:
        # Don't fail the whole function if metering breaks
        logging.error(f"Failed to submit metering event: {e}")

    logging.info("DrawTrigger function execution completed successfully")


def get_msi_token() -> str:
    url = (
        "http://169.254.169.254/metadata/identity/oauth2/token"
        "?api-version=2018-02-01"
        "&resource=00001111-aaaa-2222-bbbb-3333cccc4444"
    )
    headers = {"Metadata": "true"}
    r = requests.get(url, headers=headers, timeout=5)
    r.raise_for_status()
    return r.json()["access_token"]


def get_managed_app_resource_id(subscription_id: str, resource_group_name: str, token: str) -> str:
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourcegroups/{resource_group_name}?api-version=2021-04-01"
    )
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()["managedBy"]


def emit_meter_event(resource_id: str, plan_id: str, token: str) -> dict:
    url = "https://marketplaceapi.microsoft.com/api/usageEvent?api-version=2018-08-31"
    body = {
        "resourceId": resource_id,
        "dimension": "dailyRun",   # your dimension ID
        "quantity": 1,             # always 1 per day
        "effectiveStartTime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "planId": plan_id,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    r = requests.post(url, headers=headers, json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def has_billed_today(blob_service_client: BlobServiceClient, container_name: str) -> bool:
    """Check if we've already submitted a metering event for today."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    blob_name = f"billing/dailyRun_{today}.marker"
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    try:
        blob_client.get_blob_properties()
        return True
    except ResourceNotFoundError:
        return False


def mark_billed_today(blob_service_client: BlobServiceClient, container_name: str) -> None:
    """Write a small marker blob indicating we've billed for today."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    blob_name = f"billing/dailyRun_{today}.marker"
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    blob_client.upload_blob(b"", overwrite=True)
