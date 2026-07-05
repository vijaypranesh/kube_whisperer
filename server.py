import asyncio
import sys
import datetime
from typing import Any
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
from kubernetes import client, config, utils
from kubernetes.client.rest import ApiException
import subprocess

# Initialize MCP server
server = Server("kube-whisperer")

# Authenticate with local kubeconfig
try:
    config.load_kube_config()
except Exception as e:
    print(f"Error loading kubeconfig: {e}", file=sys.stderr)

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    """
    return [
        types.Tool(
            name="get_pod_status",
            description="Get the status, restart counts, and container conditions of a specific pod.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"},
                    "pod_name": {"type": "string", "description": "The name of the pod"}
                },
                "required": ["namespace", "pod_name"]
            }
        ),
        types.Tool(
            name="list_pods",
            description="List all pods in a given namespace and get their current status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"}
                },
                "required": ["namespace"]
            }
        ),
        types.Tool(
            name="get_pod_logs",
            description="Fetch logs from a specific pod.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"},
                    "pod_name": {"type": "string", "description": "The name of the pod"}
                },
                "required": ["namespace", "pod_name"]
            }
        ),
        types.Tool(
            name="delete_pod",
            description="Delete a specific pod.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"},
                    "pod_name": {"type": "string", "description": "The name of the pod"}
                },
                "required": ["namespace", "pod_name"]
            }
        ),
        types.Tool(
            name="list_deployments",
            description="List all deployments in a given namespace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"}
                },
                "required": ["namespace"]
            }
        ),
        types.Tool(
            name="scale_deployment",
            description="Scale a deployment to a specific number of replicas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"},
                    "deployment_name": {"type": "string", "description": "The deployment name"},
                    "replicas": {"type": "integer", "description": "Target number of replicas"}
                },
                "required": ["namespace", "deployment_name", "replicas"]
            }
        ),
        types.Tool(
            name="restart_deployment",
            description="Trigger a rolling restart of a deployment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"},
                    "deployment_name": {"type": "string", "description": "The deployment name"}
                },
                "required": ["namespace", "deployment_name"]
            }
        ),
        types.Tool(
            name="delete_deployment",
            description="Delete a deployment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"},
                    "deployment_name": {"type": "string", "description": "The deployment name"}
                },
                "required": ["namespace", "deployment_name"]
            }
        ),
        types.Tool(
            name="list_services",
            description="List all services in a given namespace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "The Kubernetes namespace"}
                },
                "required": ["namespace"]
            }
        ),
        types.Tool(
            name="list_namespaces",
            description="List all namespaces in the cluster.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="create_namespace",
            description="Create a new namespace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace_name": {"type": "string", "description": "The name of the new namespace"}
                },
                "required": ["namespace_name"]
            }
        ),
        types.Tool(
            name="deploy_yaml",
            description="Deploy resources to the cluster from a YAML file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "yaml_path": {"type": "string", "description": "The absolute path to the YAML file"},
                    "namespace": {"type": "string", "description": "Optional. The namespace to deploy the resources into."}
                },
                "required": ["yaml_path"]
            }
        ),
        types.Tool(
            name="create_cluster",
            description="Create a new local Kubernetes cluster.",
            inputSchema={
                "type": "object",
                "properties": {
                    "engine": {"type": "string", "description": "The engine to use (e.g. minikube, kind)"},
                    "cluster_name": {"type": "string", "description": "The name of the new cluster"}
                },
                "required": ["engine", "cluster_name"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    """
    valid_tools = [
        "get_pod_status", "list_pods", "get_pod_logs", "delete_pod",
        "list_deployments", "scale_deployment", "restart_deployment",
        "delete_deployment", "list_services", "list_namespaces",
        "create_namespace", "deploy_yaml", "create_cluster"
    ]
    if name not in valid_tools:
        raise ValueError(f"Unknown tool: {name}")

    namespace_required_tools = [
        "get_pod_status", "list_pods", "get_pod_logs", "delete_pod",
        "list_deployments", "scale_deployment", "restart_deployment",
        "delete_deployment", "list_services"
    ]
    if name in namespace_required_tools:
        if not arguments or "namespace" not in arguments:
            raise ValueError("Missing required arguments: namespace")
        namespace = arguments["namespace"]
    else:
        namespace = None

    try:
        core_v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        
        if name == "list_pods":
            pods = core_v1.list_namespaced_pod(namespace=namespace)
            result = f"Pods in namespace '{namespace}':\n"
            if not pods.items:
                result += "No pods found."
            else:
                for pod in pods.items:
                    status = pod.status.phase
                    result += f"- {pod.metadata.name} (Status: {status})\n"
            return [types.TextContent(type="text", text=result)]
            
        elif name == "get_pod_status":
            if not arguments.get("pod_name"):
                raise ValueError("Missing or empty pod_name. If you don't know the pod name, run list_pods first.")
            pod = core_v1.read_namespaced_pod(name=arguments["pod_name"], namespace=namespace)
            status = pod.status.phase
            restarts = sum(container.restart_count for container in (pod.status.container_statuses or []))
            conditions = []
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    conditions.append(f"{condition.type}: {condition.status}")
            result = f"Pod Phase: {status}\nTotal Restarts: {restarts}\nConditions:\n" + "\n".join(conditions)
            return [types.TextContent(type="text", text=result)]

        elif name == "get_pod_logs":
            if not arguments.get("pod_name"):
                raise ValueError("Missing or empty pod_name. If you don't know the pod name, run list_pods first.")
            logs = core_v1.read_namespaced_pod_log(name=arguments["pod_name"], namespace=namespace, tail_lines=50)
            return [types.TextContent(type="text", text=logs if logs else "No logs found.")]

        elif name == "delete_pod":
            if not arguments.get("pod_name"):
                raise ValueError("Missing or empty pod_name. If you don't know the pod name, run list_pods first.")
            core_v1.delete_namespaced_pod(name=arguments["pod_name"], namespace=namespace)
            return [types.TextContent(type="text", text=f"Pod {arguments['pod_name']} deleted successfully.")]

        elif name == "list_deployments":
            deps = apps_v1.list_namespaced_deployment(namespace=namespace)
            result = f"Deployments in namespace '{namespace}':\n"
            if not deps.items:
                result += "No deployments found."
            else:
                for dep in deps.items:
                    result += f"- {dep.metadata.name} (Ready: {dep.status.ready_replicas or 0}/{dep.status.replicas or 0})\n"
            return [types.TextContent(type="text", text=result)]

        elif name == "scale_deployment":
            if not arguments.get("deployment_name") or "replicas" not in arguments:
                raise ValueError("Missing or empty deployment_name or replicas. If you don't know the deployment name, run list_deployments first.")
            patch = {"spec": {"replicas": int(arguments["replicas"])}}
            apps_v1.patch_namespaced_deployment(name=arguments["deployment_name"], namespace=namespace, body=patch)
            return [types.TextContent(type="text", text=f"Deployment {arguments['deployment_name']} scaled to {arguments['replicas']} replicas.")]

        elif name == "restart_deployment":
            if not arguments.get("deployment_name"):
                raise ValueError("Missing or empty deployment_name. If you don't know the deployment name, run list_deployments first.")
            patch = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": datetime.datetime.utcnow().isoformat() + "Z"
                            }
                        }
                    }
                }
            }
            apps_v1.patch_namespaced_deployment(name=arguments["deployment_name"], namespace=namespace, body=patch)
            return [types.TextContent(type="text", text=f"Deployment {arguments['deployment_name']} successfully restarted.")]

        elif name == "delete_deployment":
            if not arguments.get("deployment_name"):
                raise ValueError("Missing or empty deployment_name. If you don't know the deployment name, run list_deployments first.")
            apps_v1.delete_namespaced_deployment(name=arguments["deployment_name"], namespace=namespace)
            return [types.TextContent(type="text", text=f"Deployment {arguments['deployment_name']} deleted successfully.")]

        elif name == "list_services":
            svcs = core_v1.list_namespaced_service(namespace=namespace)
            result = f"Services in namespace '{namespace}':\n"
            if not svcs.items:
                result += "No services found."
            else:
                for svc in svcs.items:
                    result += f"- {svc.metadata.name} (Type: {svc.spec.type})\n"
            return [types.TextContent(type="text", text=result)]

        elif name == "list_namespaces":
            ns_list = core_v1.list_namespace()
            result = "Namespaces in cluster:\n"
            for ns in ns_list.items:
                result += f"- {ns.metadata.name} (Status: {ns.status.phase})\n"
            return [types.TextContent(type="text", text=result)]

        elif name == "create_namespace":
            if not arguments.get("namespace_name"):
                raise ValueError("Missing or empty namespace_name.")
            ns_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=arguments["namespace_name"]))
            core_v1.create_namespace(body=ns_body)
            return [types.TextContent(type="text", text=f"Namespace '{arguments['namespace_name']}' created successfully.")]

        elif name == "deploy_yaml":
            if not arguments.get("yaml_path"):
                raise ValueError("Missing or empty yaml_path.")
            
            target_ns = arguments.get("namespace")
            cmd = ["kubectl", "apply", "-f", arguments["yaml_path"]]
            if target_ns:
                cmd.extend(["-n", target_ns])
                
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return [types.TextContent(type="text", text=f"Resources from {arguments['yaml_path']} deployed successfully.\n{proc.stdout}")]
            except subprocess.CalledProcessError as e:
                return [types.TextContent(type="text", text=f"Failed to deploy resources from {arguments['yaml_path']}.\nExit Code: {e.returncode}\nStdout: {e.stdout}\nStderr: {e.stderr}")]

        elif name == "create_cluster":
            if not arguments.get("engine") or not arguments.get("cluster_name"):
                raise ValueError("Missing engine or cluster_name.")
            engine = arguments["engine"].lower()
            cname = arguments["cluster_name"]
            if engine not in ["minikube", "kind"]:
                raise ValueError(f"Unsupported engine: {engine}. Only minikube or kind are supported.")
            
            cmd = []
            if engine == "minikube":
                cmd = ["minikube", "start", "-p", cname]
            elif engine == "kind":
                cmd = ["kind", "create", "cluster", "--name", cname]
                
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return [types.TextContent(type="text", text=f"Cluster '{cname}' created successfully using {engine}.\n{proc.stdout}")]
            except subprocess.CalledProcessError as e:
                return [types.TextContent(type="text", text=f"Failed to create cluster '{cname}'.\nExit Code: {e.returncode}\nStdout: {e.stdout}\nStderr: {e.stderr}")]

    except ApiException as e:
        return [types.TextContent(type="text", text=f"Kubernetes API Error: {e.reason} ({e.status})\n{e.body}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="kube-whisperer",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
