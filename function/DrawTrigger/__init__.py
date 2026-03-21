import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import azure.functions as func
import requests
from requests.auth import HTTPBasicAuth

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

import cloudnetdraw.azure_client as azure_client
from cloudnetdraw.config import Config
from cloudnetdraw.diagram_generator import generate_hld_diagram, generate_mld_diagram


def main(mytimer: func.TimerRequest) -> None:
    """Generate topology output and store it in Blob Storage and optionally Confluence."""
    del mytimer
    logging.info("DrawTrigger function triggered")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    credential = DefaultAzureCredential()
    azure_client._credentials = credential

    try:
        subscription_ids = azure_client.get_all_subscription_ids()
        logging.info("Found %s subscriptions", len(subscription_ids))
    except Exception as exc:
        logging.exception("Failed to list subscriptions: %s", exc)
        return

    try:
        topology = azure_client.get_vnet_topology_for_selected_subscriptions(subscription_ids)
    except Exception as exc:
        logging.exception("Failed to retrieve VNet topology: %s", exc)
        return

    output_files = create_output_files(timestamp, topology)
    if not output_files:
        return

    blob_service_client = create_blob_service_client(credential)
    if blob_service_client is None:
        return

    upload_outputs_to_blob(blob_service_client, output_files)

    output_mode = os.environ.get("OUTPUT_MODE", "storage").strip().lower()
    if output_mode == "confluence":
        upload_outputs_to_confluence(output_files)
    elif output_mode != "storage":
        logging.warning("Unsupported OUTPUT_MODE '%s'. Falling back to storage-only behavior.", output_mode)

    logging.info("DrawTrigger function execution completed successfully")


def create_output_files(timestamp: str, topology: Dict[str, object]) -> Dict[str, Path]:
    """Persist topology and generated diagrams to temporary files."""
    json_file_path = Path("/tmp") / f"{timestamp}_network_topology.json"
    diagram_file_path_mld = Path("/tmp") / f"{timestamp}_network_diagram_MLD.drawio"
    diagram_file_path_hld = Path("/tmp") / f"{timestamp}_network_diagram_HLD.drawio"

    try:
        json_file_path.write_text(json.dumps(topology, indent=2), encoding="utf-8")
        logging.info("Saved topology JSON to %s", json_file_path)
    except Exception as exc:
        logging.exception("Failed to write topology JSON: %s", exc)
        return {}

    config = Config()
    try:
        generate_mld_diagram(str(diagram_file_path_mld), str(json_file_path), config)
        logging.info("Generated MLD diagram at %s", diagram_file_path_mld)
        generate_hld_diagram(str(diagram_file_path_hld), str(json_file_path), config)
        logging.info("Generated HLD diagram at %s", diagram_file_path_hld)
    except Exception as exc:
        logging.exception("Failed to generate diagrams: %s", exc)
        return {}

    return {
        "topology_json": json_file_path,
        "diagram_mld": diagram_file_path_mld,
        "diagram_hld": diagram_file_path_hld,
    }


def create_blob_service_client(credential: DefaultAzureCredential) -> BlobServiceClient | None:
    account_url = os.environ.get("DRAWING_STORAGE_URL")
    container_name = os.environ.get("DRAWING_CONTAINER_NAME")

    if not account_url or not container_name:
        logging.error("Storage configuration missing: DRAWING_STORAGE_URL and DRAWING_CONTAINER_NAME must be set")
        return None

    return BlobServiceClient(account_url=account_url, credential=credential)


def upload_outputs_to_blob(blob_service_client: BlobServiceClient, output_files: Dict[str, Path]) -> None:
    container_name = os.environ["DRAWING_CONTAINER_NAME"]

    for _, file_path in output_files.items():
        try:
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_path.name)
            with file_path.open("rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            logging.info("Uploaded %s to Blob Storage", file_path.name)
        except Exception as exc:
            logging.exception("Failed to upload %s to Blob Storage: %s", file_path.name, exc)


def upload_outputs_to_confluence(output_files: Dict[str, Path]) -> None:
    settings = get_confluence_settings()
    if settings is None:
        return

    session = requests.Session()
    session.auth = HTTPBasicAuth(settings["username"], settings["api_token"])
    session.headers.update({"Accept": "application/json", "X-Atlassian-Token": "no-check"})

    for attachment_name, file_path in iter_confluence_attachments(output_files, settings["attachment_prefix"]):
        try:
            upload_confluence_attachment(
                session=session,
                base_url=settings["base_url"],
                page_id=settings["page_id"],
                attachment_name=attachment_name,
                file_path=file_path,
            )
            logging.info("Uploaded %s to Confluence page %s", attachment_name, settings["page_id"])
        except Exception as exc:
            logging.exception("Failed to upload %s to Confluence: %s", attachment_name, exc)


def get_confluence_settings() -> Dict[str, str] | None:
    required_settings = {
        "base_url": os.environ.get("CONFLUENCE_BASE_URL", "").strip(),
        "username": os.environ.get("CONFLUENCE_USERNAME", "").strip(),
        "api_token": os.environ.get("CONFLUENCE_API_TOKEN", "").strip(),
        "page_id": os.environ.get("CONFLUENCE_PAGE_ID", "").strip(),
        "attachment_prefix": os.environ.get("CONFLUENCE_ATTACHMENT_PREFIX", "cloudnetdraw-topology").strip(),
    }

    missing_settings = [name for name, value in required_settings.items() if not value]
    if missing_settings:
        logging.error(
            "Confluence export is enabled but required settings are missing: %s",
            ", ".join(sorted(missing_settings)),
        )
        return None

    return required_settings


def iter_confluence_attachments(
    output_files: Dict[str, Path],
    attachment_prefix: str,
) -> Iterable[Tuple[str, Path]]:
    yield f"{attachment_prefix}.json", output_files["topology_json"]
    yield f"{attachment_prefix}-mld.drawio", output_files["diagram_mld"]
    yield f"{attachment_prefix}-hld.drawio", output_files["diagram_hld"]


def upload_confluence_attachment(
    session: requests.Session,
    base_url: str,
    page_id: str,
    attachment_name: str,
    file_path: Path,
) -> None:
    create_url, update_url = resolve_confluence_attachment_urls(session, base_url, page_id, attachment_name)

    attachment_id = find_existing_attachment_id(session, create_url, attachment_name)
    upload_url = update_url.format(attachment_id=attachment_id) if attachment_id else create_url

    with file_path.open("rb") as file_handle:
        response = session.post(
            upload_url,
            files={"file": (attachment_name, file_handle, guess_content_type(file_path))},
            timeout=30,
        )

    response.raise_for_status()


def resolve_confluence_attachment_urls(
    session: requests.Session,
    base_url: str,
    page_id: str,
    attachment_name: str,
) -> Tuple[str, str]:
    candidate_roots = build_confluence_api_roots(base_url)
    for root in candidate_roots:
        create_url = f"{root}/content/{page_id}/child/attachment"
        try:
            response = session.get(
                create_url,
                params={"filename": attachment_name, "limit": 1},
                timeout=15,
            )
        except requests.RequestException:
            continue

        if response.status_code not in (404, 401, 403):
            return create_url, f"{root}/content/{page_id}/child/attachment/{{attachment_id}}/data"

    root = candidate_roots[0]
    return f"{root}/content/{page_id}/child/attachment", f"{root}/content/{page_id}/child/attachment/{{attachment_id}}/data"


def build_confluence_api_roots(base_url: str) -> List[str]:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/wiki"):
        return [f"{normalized}/rest/api", f"{normalized[:-5]}/rest/api"]
    return [f"{normalized}/wiki/rest/api", f"{normalized}/rest/api"]


def find_existing_attachment_id(
    session: requests.Session,
    attachment_collection_url: str,
    attachment_name: str,
) -> str | None:
    response = session.get(
        attachment_collection_url,
        params={"filename": attachment_name, "limit": 1},
        timeout=15,
    )
    response.raise_for_status()

    results = response.json().get("results", [])
    if not results:
        return None

    attachment = results[0]
    return attachment.get("id")


def guess_content_type(file_path: Path) -> str:
    if file_path.suffix == ".json":
        return "application/json"
    return "application/octet-stream"
