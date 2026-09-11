"""Additional agent tools over the shared, path-checked domain services."""
import anyio
from typing import Annotated
from pydantic import Field
from .schemas import RunCreate,CreativeCreate
from . import services
from .comparison import compare_evaluations
from .agent_bridge import AgentOperator, AgentSource

def register(mcp):
    @mcp.tool()
    def get_external_receipts() -> dict:
        """Read durable Weave delivery IDs, URLs and errors; does not publish new data."""
        from .delivery import receipts
        return {'receipts':receipts()}

    @mcp.tool()
    def inspect_project(project_id: Annotated[str, Field(min_length=1, max_length=120)]) -> dict:
        """Read a bounded project brief, constraints, managed assets and run summaries."""
        return services.project_context(project_id)

    @mcp.tool()
    def propose_agent_experiment(
        base_run_id: Annotated[str, Field(min_length=1, max_length=120)],
        operator: AgentOperator,
        hypothesis: Annotated[str, Field(min_length=1, max_length=1000)],
        source: AgentSource = 'local agent',
    ) -> dict:
        """Prepare one typed intervention under a prior run's frozen objective, budget, operators and constraints. Does not execute; review the returned digest."""
        from .agent_bridge import propose,Proposal
        return propose(Proposal(base_run_id=base_run_id,operator=operator,hypothesis=hypothesis,source=source))

    @mcp.tool()
    def get_agent_proposal(proposal_id: Annotated[str, Field(min_length=1, max_length=120)]) -> dict:
        """Read a proposal's exact typed specification, digest, state and recovery guidance."""
        from .agent_bridge import get_proposal
        return get_proposal(proposal_id)

    @mcp.tool()
    def execute_agent_proposal(
        proposal_id: Annotated[str, Field(min_length=1, max_length=120)],
        approval_digest: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')],
    ) -> dict:
        """Queue an explicitly reviewed proposal using its exact digest. The shared guard, queue, renderer, evaluator and ledger remain authoritative."""
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
    def run_experiment(project_id: Annotated[str, Field(min_length=1, max_length=120)], operator: AgentOperator, max_evaluations: Annotated[int, Field(ge=1, le=4)]=4, max_seconds: Annotated[int, Field(ge=30, le=900)]=900, min_gain: Annotated[float, Field(ge=0.0001, le=0.25)]=.005, no_speech:bool=False, allow_static_presentation:bool=False, idempotency_key:Annotated[str|None, Field(max_length=100)]=None) -> dict:
        """Queue one permitted edit through the shared bounded run service; no external code or provider call is accepted."""
        request=RunCreate(project_id=project_id,mode='optimize',operators=[operator],max_evaluations=max_evaluations,max_seconds=max_seconds,min_gain=min_gain,allow_static_presentation=allow_static_presentation,no_speech=no_speech,target_score=1.0)
        return services.create_run(request,idempotency_key)
