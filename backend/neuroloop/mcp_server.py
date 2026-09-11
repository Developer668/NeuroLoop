"""Agent interface over the same services as the website. Long jobs return run IDs."""
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from . import services
from .config import settings
from .schemas import ProjectCreate,RunCreate

mcp=FastMCP('NeuroLoop',instructions='Evaluate and improve managed creative assets under a fixed budget. TRIBE predicts cortical responses, not thoughts or purchases. Query capabilities before acting. Upload media through the authenticated HTTP asset endpoint. Long-running tools return a run ID; poll get_run. Never invent missing model outputs.',stateless_http=True,json_response=True,streamable_http_path='/',transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,allowed_hosts=settings().mcp_allowed_hosts,allowed_origins=settings().mcp_allowed_origins))

@mcp.tool()
def get_capabilities() -> dict:
    """Return actual installed capabilities, licensing gates and integration status."""
    return services.capabilities()

@mcp.tool()
def list_workspace() -> dict:
    """List this authenticated workspace's projects, managed assets and real runs."""
    data=services.dashboard()
    return {key:data[key] for key in ['projects','assets','runs','counts']}

@mcp.tool()
def create_project(name: str,brief: str='',asset_id: str | None=None,reference_ids: list[str] | None=None) -> dict:
    """Create a project from already uploaded managed asset IDs."""
    return services.create_project(ProjectCreate(name=name,brief=brief,asset_id=asset_id,reference_ids=reference_ids or []))

@mcp.tool()
def evaluate_creative(project_id: str,max_evaluations: int=4,no_speech: bool=False,allow_static_presentation: bool=False,idempotency_key: str | None=None,include_tsam:bool=False,tsam_research_acknowledged:bool=False,include_kragel:bool=True) -> dict:
    """Queue real TRIBE evaluation with optional independent TSAM and experimental Kragel readouts."""
    return services.create_run(RunCreate(project_id=project_id,max_evaluations=max_evaluations,no_speech=no_speech,allow_static_presentation=allow_static_presentation,include_tsam=include_tsam,tsam_research_acknowledged=tsam_research_acknowledged,include_kragel=include_kragel),idempotency_key)

@mcp.tool()
def optimize_creative(project_id: str,max_evaluations: int=4,max_seconds: int=1800,min_gain: float=0.005,no_speech: bool=False,allow_static_presentation: bool=False,idempotency_key: str | None=None) -> dict:
    """Run bounded controlled edits against supplied reference responses; returns immediately with a job ID."""
    return services.create_run(RunCreate(project_id=project_id,mode='optimize',max_evaluations=max_evaluations,max_seconds=max_seconds,min_gain=min_gain,no_speech=no_speech,allow_static_presentation=allow_static_presentation),idempotency_key)

@mcp.tool()
def optimize_response(project_id: str, emotion_targets: dict[str,float], max_evaluations: int=6, max_seconds: int=1800, min_gain: float=0.005, no_speech: bool=False, allow_static_presentation: bool=False, include_tsam: bool=False, tsam_research_acknowledged: bool=False, include_kragel: bool=True, idempotency_key: str | None=None) -> dict:
    """Optimize local controlled edits toward declared relative emotion targets. Values are 0..1 model-evidence targets, not human-response probabilities."""
    target={'emotions':{name:{'desired':value,'weight':1.0} for name,value in emotion_targets.items()}}
    request=RunCreate(project_id=project_id,mode='optimize',objective='response_target',target=target,max_evaluations=max_evaluations,max_seconds=max_seconds,min_gain=min_gain,no_speech=no_speech,allow_static_presentation=allow_static_presentation,include_tsam=include_tsam,tsam_research_acknowledged=tsam_research_acknowledged,include_kragel=include_kragel)
    return services.create_run(request,idempotency_key)

@mcp.tool()
def get_run(run_id: str) -> dict:
    """Read real progress, experiment lineage, model evidence and stopping reason."""
    return services.get_run(run_id)

@mcp.tool()
def cancel_run(run_id: str) -> dict:
    """Prevent further work; any in-flight model operation completes at a safe checkpoint."""
    return services.cancel_run(run_id)

@mcp.tool()
def get_evidence(evaluation_id: str) -> dict:
    """Return numerical evidence and provenance; large tensors remain in authenticated storage."""
    return services.get_evidence(evaluation_id)

@mcp.tool()
def export_result(run_id: str) -> dict:
    """Return authenticated API paths for the selected artifact and evidence archive."""
    run=services.get_run(run_id);asset_id=run['result'].get('best_asset_id')
    if not asset_id: raise ValueError('This run has no completed result to export')
    return {'run_id':run_id,'asset_id':asset_id,'asset_path':f'/api/assets/{asset_id}/content','archive_path':f'/api/runs/{run_id}/export','requires_authentication':True,'scope':run['result'].get('scope')}

from .mcp_extensions import register
register(mcp)
