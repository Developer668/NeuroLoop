"""Official W&B MCP with private local credential loading and read-only remote tools."""
from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=False)
if '/' in os.environ.get('WANDB_PROJECT',''):
    os.environ['WANDB_ENTITY'],os.environ['WANDB_PROJECT']=os.environ['WANDB_PROJECT'].split('/',1)
os.environ['WANDB_MCP_READ_ONLY']='true'
os.environ['WANDB_MCP_ENABLE_WEAVE_AGENT_TOOLS']='false'
os.environ['WANDB_MCP_PROXY_DOCS']='false'
os.environ['MCP_ANALYTICS_LOG_STREAM']='stderr'
os.environ['MCP_LOG_PRIVACY_LEVEL']='strict'
from wandb_mcp_server.server import cli
if __name__=='__main__':cli()
