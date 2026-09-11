"""Additional agent tools over the shared, path-checked domain services."""
import anyio
from .schemas import RunCreate,CreativeCreate
from . import services
from .comparison import compare_evaluations

def register(mcp):
    @mcp.tool()
    def get_external_receipts() -> dict:
        """Read durable Weave delivery IDs, URLs and errors; does not publish new data."""
        from .delivery import receipts
        return {'receipts':receipts()}

    @mcp.tool()
    def propose_agent_experiment(base_run_id:str,operator:str,hypothesis:str,source:str='local agent') -> dict:
        """Prepare a version-1 proposal under a prior run's frozen objective/constraints. Does not execute. Review the returned contract and digest."""
        from .agent_bridge import propose,Proposal
        return propose(Proposal(base_run_id=base_run_id,operator=operator,hypothesis=hypothesis,source=source))

    @mcp.tool()
    def execute_agent_proposal(proposal_id:str,approval_digest:str) -> dict:
        """Execute an explicitly reviewed proposal using its exact digest. Same bounded domain queue, GPU lock and keep/revert rules as the UI."""
        from .agent_bridge import execute
        return execute(proposal_id,approval_digest)

    @mcp.tool()
    def get_research_ledger() -> dict:
        """Read recorded timelines, interventions and costs, including clearly marked archived history. No inference is started."""
        from .research import ledger
        return ledger()

    @mcp.tool()
    def get_system_status() -> dict:
        """Read local GPU temperature, free memory and RAM telemetry; use get_capabilities for asset readiness."""
        from .hardware import hardware_status
        return hardware_status()

    @mcp.tool()
    def list_evaluations() -> dict:
        """List active saved evaluations and their model profiles so an agent can select compatible comparison IDs."""
        return {'evaluations':services.dashboard()['evaluations']}

    @mcp.tool()
    async def compare_creatives(evaluation_ids:list[str]) -> dict:
        """Compare 2–12 saved cortical arrays without another GPU inference; profiles must match."""
        return await anyio.to_thread.run_sync(compare_evaluations,evaluation_ids)

    @mcp.tool()
    async def render_creative(asset_id:str,headline:str,subline:str='',duration:int=8,headline_start:float=1,aspect:str='landscape') -> dict:
        """Render an editable, silent composition from a managed image/video and exact copy. No AI imagery generation."""
        spec=CreativeCreate(asset_id=asset_id,headline=headline,subline=subline,duration=duration,headline_start=headline_start,aspect=aspect)
        return await anyio.to_thread.run_sync(services.create_creative,spec)

    @mcp.tool()
    def run_experiment(project_id:str,operator:str,max_evaluations:int=4,max_seconds:int=900,min_gain:float=.005,no_speech:bool=False,allow_static_presentation:bool=False,idempotency_key:str|None=None) -> dict:
        """Queue one permitted edit, preserving the fixed goal and budget. No speech may be asserted only for genuinely speech-free media."""
        request=RunCreate(project_id=project_id,mode='optimize',operators=[operator],max_evaluations=max_evaluations,max_seconds=max_seconds,min_gain=min_gain,no_speech=no_speech,allow_static_presentation=allow_static_presentation,target_score=1.0)
        return services.create_run(request,idempotency_key)
