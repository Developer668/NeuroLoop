"""Restricted, high-level MCP facade. It cannot approve or activate advertising."""
import os
from uuid import UUID
import httpx
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("NeuroLoop")

def request(method, path, body=None, *, idempotency_key=None):
    from .config import Settings
    settings=Settings()
    token=settings.agent_token.get_secret_value()
    if not token:
        raise RuntimeError("NOT_CONFIGURED: set the restricted NEUROLOOP_AGENT_TOKEN, not the human operator key")
    headers={"Authorization":"Bearer "+token}
    if idempotency_key: headers["Idempotency-Key"]=idempotency_key
    with httpx.Client(base_url=settings.public_api_url, headers=headers, timeout=30) as client:
        response=client.request(method,"/api/v2"+path,json=body)
        response.raise_for_status()
        return response.json()

@mcp.tool()
def get_capabilities() -> dict:
    """Read actual model and sponsor availability; configured is not verified."""
    return request("GET","/capabilities")

@mcp.tool()
def create_campaign(spec: dict) -> dict:
    """Persist a source-grounded campaign brief; does not spend or generate."""
    from .domain import CampaignSpec
    return request("POST","/campaigns",CampaignSpec.model_validate(spec).model_dump())

@mcp.tool()
def optimize(campaign_id: str, idempotency_key: str, config: dict, reference_asset_ids: list[str]) -> dict:
    """Queue a bounded optimization run using previously uploaded asset IDs."""
    from .domain import StartRun
    body=StartRun.model_validate({"config":config,"reference_asset_ids":reference_asset_ids})
    return request("POST",f"/campaigns/{UUID(campaign_id)}/runs",body.model_dump(),idempotency_key=idempotency_key)

@mcp.tool()
def get_run(run_id: str) -> dict:
    """Read run state, immutable creative lineage and current evidence."""
    return request("GET",f"/runs/{UUID(run_id)}")

@mcp.tool()
def get_lineage(run_id: str) -> list[dict]:
    """Get every creative, including failed and rejected branches."""
    return get_run(run_id)["creatives"]

@mcp.tool()
def get_evidence(run_id: str, creative_id: str) -> dict:
    """Get provenance-tagged evidence, not unverified outcome claims."""
    return next(c for c in get_lineage(run_id) if c["id"]==str(UUID(creative_id)))

@mcp.tool()
def cancel_run(run_id: str) -> dict:
    """Persist cancellation and reject late notebook success callbacks."""
    return request("POST",f"/runs/{UUID(run_id)}/cancel",{})

@mcp.tool()
def export_result(run_id: str) -> dict:
    """Export actual trajectory evidence for NeuroLab/ARIA review."""
    return request("GET",f"/runs/{UUID(run_id)}/export")

if __name__ == "__main__":
    mcp.run(transport="stdio")
