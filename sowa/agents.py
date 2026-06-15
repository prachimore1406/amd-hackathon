from langchain_core.prompts import PromptTemplate
from sowa.llm import llm
from sowa.metrics import LOCAL_NODE_NAME, get_cluster_snapshot, get_next_workload
from sowa.state import MultiAgentState

NODE_LABELS = {
    "AMD-EPYC-CPU": "cpu-epyc-milan",
    "AMD-Instinct-GPU": "gpu-instinct-mi350x",
    "General-VM": "general-purpose",
    LOCAL_NODE_NAME: "local-amd-mi350",
}

WORKLOAD_BASELINES = {
    "ml training": "AMD-Instinct-GPU",
    "web serving": "AMD-EPYC-CPU",
    "data processing": "General-VM",
}


def _workload_type(workload_request: str) -> str:
    if "|" not in workload_request:
        return "general"
    return workload_request.split("|", maxsplit=1)[1].replace("Type:", "").strip().lower()


def _normalize_decision(raw_decision: str) -> str:
    clean_text = raw_decision.strip().lower()
    aliases = {
        "amd-epyc-cpu": "AMD-EPYC-CPU",
        "epyc": "AMD-EPYC-CPU",
        "amd-instinct-gpu": "AMD-Instinct-GPU",
        "instinct": "AMD-Instinct-GPU",
        "gpu": "AMD-Instinct-GPU",
        "general-vm": "General-VM",
        "general": "General-VM",
        "local-notebook-node": LOCAL_NODE_NAME,
        "local amd node": LOCAL_NODE_NAME,
        "local node": LOCAL_NODE_NAME,
    }
    for alias, canonical_name in aliases.items():
        if alias in clean_text:
            return canonical_name
    return "General-VM"


def _baseline_decision(workload_request: str) -> str:
    return WORKLOAD_BASELINES.get(_workload_type(workload_request), "General-VM")


def _performance_summary(state: MultiAgentState, decision: str) -> tuple[str, str]:
    baseline = _baseline_decision(state["current_workload"])
    node_loads = state.get("node_loads", {})
    baseline_load = node_loads.get(baseline, 100)
    selected_load = node_loads.get(decision, 100)
    baseline_headroom = max(0, 100 - baseline_load)
    selected_headroom = max(0, 100 - selected_load)
    headroom_delta = selected_headroom - baseline_headroom

    if decision == baseline:
        impact_line = "Matches the baseline policy while preserving the best raw-fit hardware."
    elif headroom_delta >= 15:
        impact_line = "Improves startup responsiveness by steering the workload to a node with more available headroom."
    elif headroom_delta >= 0:
        impact_line = "Reduces contention risk while keeping expected throughput close to the default placement."
    else:
        impact_line = "Trades some raw speed for a safer placement because the preferred node is already under pressure."

    summary = (
        f"Baseline policy: {baseline}\n"
        f"SOWA placement: {decision}\n"
        f"Baseline headroom: {baseline_headroom}%\n"
        f"Selected headroom: {selected_headroom}%\n"
        f"Performance impact: {impact_line}"
    )
    return baseline, summary


def _build_manifest(workload_name: str, decision: str) -> str:
    app_label = workload_name
    k8s_node_label = NODE_LABELS.get(decision, NODE_LABELS["General-VM"])
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {workload_name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {app_label}
  template:
    metadata:
      labels:
        app: {app_label}
    spec:
      containers:
      - name: workload-container
        image: {workload_name}:latest
      nodeSelector:
        amd.com/hardware-type: {k8s_node_label}
"""


def simulator_agent(state: MultiAgentState) -> MultiAgentState:
    """Agent 1: mixes real local telemetry with simulated cluster nodes."""
    snapshot = get_cluster_snapshot(state.get("last_decision", "None"))
    workload = get_next_workload(state.get("current_workload", ""))
    return {
        **state,
        "cluster_status_text": snapshot["cluster_status_text"],
        "local_telemetry_text": snapshot["local_telemetry_text"],
        "telemetry_source": snapshot["telemetry_source"],
        "current_workload": workload,
    }


def devops_agent(state: MultiAgentState) -> MultiAgentState:
    """Agent 2: uses the hybrid cluster snapshot for placement decisions."""
    prompt = PromptTemplate.from_template("""
    You are an AI DevOps Orchestrator managing an AMD cluster.
    Cluster Status: {status}
    Local Telemetry Source: {telemetry_source}
    Local Telemetry Details: {local_telemetry}
    Incoming Workload: {workload}

    Rules:
    - ML Training prefers AMD-Instinct-GPU.
    - Web Serving prefers AMD-EPYC-CPU.
    - If a physical node load is above 80%, avoid it and choose another node.
    - You may choose Local-Notebook-Node for ML only when the local telemetry looks healthy.
    - If local telemetry reports an active or recent real GPU spike, avoid Local-Notebook-Node for new ML work unless it is the only viable option.
    - Your decision must be exactly one of: AMD-EPYC-CPU, AMD-Instinct-GPU, General-VM, Local-Notebook-Node.

    Format:
    REASONING: <logic>
    DECISION: <Node Name>
    """)
    response = (prompt | llm).invoke({
        "status": state["cluster_status_text"],
        "telemetry_source": state.get("telemetry_source", "simulated"),
        "local_telemetry": state.get("local_telemetry_text", "Unavailable"),
        "workload": state["current_workload"],
    })

    reasoning, decision = "Could not parse.", "General-VM"
    for line in response.split("\n"):
        if line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()
        elif line.startswith("DECISION:"):
            decision = _normalize_decision(line.replace("DECISION:", "").strip())

    workload_name = state["current_workload"].split("|")[0].replace("Name:", "").strip().lower().replace(" ", "-")
    baseline, performance_summary = _performance_summary(state, decision)
    yaml_content = _build_manifest(workload_name, decision)
    return {
        **state,
        "devops_reasoning": reasoning,
        "last_decision": decision,
        "performance_summary": performance_summary,
        "yaml_output": yaml_content,
    }
