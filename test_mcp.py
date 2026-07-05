import asyncio
import sys
import os
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run():
    tool_name = sys.argv[1]
    args_json = sys.argv[2] if len(sys.argv) > 2 else "{}"
    arguments = json.loads(args_json)
    
    server_params = StdioServerParameters(
        command="/home/vijay/projects/Anti-Gravity/kube_whisperer/.venv/bin/python",
        args=["/home/vijay/projects/Anti-Gravity/kube_whisperer/server.py"],
        env={"KUBECONFIG": "/home/vijay/.kube/config", **os.environ}
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List tools
            tools = await session.list_tools()
            print("Tools available:", [t.name for t in tools.tools])
            
            # Call tool
            print(f"Calling {tool_name} with args {arguments}...")
            result = await session.call_tool(tool_name, arguments)
            print("\nResult from MCP Server:")
            for content in result.content:
                if content.type == 'text':
                    print(content.text)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_mcp.py <tool_name> [args_json]")
        sys.exit(1)
    asyncio.run(run())
