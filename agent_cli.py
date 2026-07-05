import asyncio
import sys
import os
import json
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Ollama exposes an OpenAI-compatible API on port 11434
# Adjust the model name to whatever you have pulled locally (e.g. 'llama3.1', 'gemma2')
OLLAMA_MODEL = "llama3.1"
OLLAMA_API_BASE = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama" # Required by the SDK, but ignored by Ollama

# Initialize OpenAI client pointing to Ollama
client = AsyncOpenAI(
    base_url=OLLAMA_API_BASE,
    api_key=OLLAMA_API_KEY
)

def mcp_tool_to_openai_tool(mcp_tool) -> dict:
    """Converts an MCP Tool schema to the OpenAI Tool schema format."""
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description,
            "parameters": mcp_tool.inputSchema
        }
    }

async def run_chat():
    print(f"Starting Kube-Whisperer Agent (Model: {OLLAMA_MODEL})...")
    
    server_params = StdioServerParameters(
        command="/home/vijay/projects/Anti-Gravity/kube_whisperer/.venv/bin/python",
        args=["/home/vijay/projects/Anti-Gravity/kube_whisperer/server.py"],
        env={"KUBECONFIG": "/home/vijay/.kube/config", **os.environ}
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Fetch tools from the MCP Server
            mcp_tools = await session.list_tools()
            def print_menu():
                print("\n" + "="*70)
                print("🚀 KUBE-WHISPERER MAIN MENU - Available Operations")
                print("="*70)
                for t in mcp_tools.tools:
                    print(f" • {t.name}: {t.description}")
                print("="*70)
                print("Type 'menu' or 'help' to see this list again.")
                print("Type 'quit' or 'exit' to end the session.")
                print("="*70 + "\n")
            
            print(f"Connected to MCP Server with {len(mcp_tools.tools)} tools.")
            print_menu()
            
            # Translate them for the LLM
            openai_tools = [mcp_tool_to_openai_tool(t) for t in mcp_tools.tools]
            
            system_prompt = (
                "You are Kube-Whisperer, an autonomous AI assistant specialized in Kubernetes triage. "
                "CRITICAL INSTRUCTIONS:\n"
                "1. ONLY use the tools provided to you. NEVER hallucinate or invent new tools.\n"
                "2. NEVER hallucinate CLI output. If a tool fails, tell the user it failed; do not invent a fake `kubectl` output.\n"
                "3. NEVER tell the user to manually run `kubectl` commands if you can use a tool to do it. Your tool calls ARE the actions. Just describe what you did.\n"
                "4. If a user makes a typo in a parameter (like 'boken-apps'), politely infer the correct spelling (e.g. 'broken-apps') and call the tool correctly. NEVER output a raw JSON tool call string to the user.\n"
                "5. You MUST ONLY respond in natural language conversational text. Never output raw JSON tool calls in your text response."
            )
            # Chat history
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            
            while True:
                try:
                    user_input = input("You: ")
                    if user_input.lower() in ['quit', 'exit']:
                        break
                    if user_input.lower() in ['menu', 'help']:
                        print_menu()
                        continue
                    if not user_input.strip():
                        continue
                        
                    messages.append({"role": "user", "content": user_input})
                    
                    # Call LLM
                    response = await client.chat.completions.create(
                        model=OLLAMA_MODEL,
                        messages=messages,
                        tools=openai_tools
                    )
                    
                    response_message = response.choices[0].message
                    messages.append(response_message)
                    
                    # Handle Tool Calls
                    if response_message.tool_calls:
                        for tool_call in response_message.tool_calls:
                            print(f"\n[Agent] Calling tool: {tool_call.function.name}({tool_call.function.arguments})")
                            
                            # Parse arguments and execute against MCP server
                            args = json.loads(tool_call.function.arguments)
                            try:
                                mcp_result = await session.call_tool(tool_call.function.name, args)
                                
                                # Extract text content from the MCP result
                                result_text = "\n".join([c.text for c in mcp_result.content if c.type == 'text'])
                                print(f"[Agent] Tool returned: {result_text}")
                                
                            except Exception as e:
                                result_text = f"Error executing tool: {str(e)}"
                                print(f"[Agent] {result_text}")
                            
                            # Append the tool result back to the LLM's context
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_call.function.name,
                                "content": result_text
                            })
                            
                        # Call LLM again with the tool results
                        final_response = await client.chat.completions.create(
                            model=OLLAMA_MODEL,
                            messages=messages,
                            tools=openai_tools
                        )
                        
                        final_message = final_response.choices[0].message
                        messages.append(final_message)
                        print(f"\nKube-Whisperer: {final_message.content}\n")
                        
                    else:
                        # Direct text response
                        print(f"\nKube-Whisperer: {response_message.content}\n")
                        
                except EOFError:
                    break
                except Exception as e:
                    print(f"\n[Error] {str(e)}\n")

if __name__ == "__main__":
    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        print("\nExiting...")
