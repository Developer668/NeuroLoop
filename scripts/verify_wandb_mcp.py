"""Verify the official W&B MCP transport and project/trace queries, without logging secrets."""
import asyncio,json
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
async def main():
    parameters=StdioServerParameters(command=str(ROOT/'.runtimes/wandb-mcp/Scripts/python.exe'),args=[str(ROOT/'scripts/wandb_mcp.py')])
    async with stdio_client(parameters) as (reader,writer),ClientSession(reader,writer) as session:
        await session.initialize()
        listed=await session.list_tools()
        report={'tools':{t.name:t.inputSchema for t in listed.tools}}
        report['queries']={}
        for name,params in [('query_weave_traces_tool',{'entity_name':'jerry-wen0616-santa-clara-university','project_name':'neuroloop','limit':3,'include_costs':False,'include_feedback':False})]:
            result=await session.call_tool(name,params)
            report['queries'][name]=result.model_dump(mode='json')
            if result.isError:raise RuntimeError('W&B MCP query failed')
        target=ROOT/'data/verification/release'
        target.mkdir(parents=True,exist_ok=True)
        (target/'wandb-mcp-schema.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps({'tools':list(report['tools'])}))
if __name__=='__main__':asyncio.run(main())
