import json
import re

from langchain_core.prompts import PromptTemplate
from sowa.llm import llm
from sowa.metrics import (
    LOCAL_NODE_NAME,
    get_cluster_snapshot,
    get_live_telemetry,
    get_next_workload,
    get_recent_gpu_event,
)
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


def _parse_structured_response(response: str) -> dict:
    # Look for the last JSON-like block to avoid issues with conversational prefix/suffix
    matches = list(re.finditer(r"\{.*\}", response, re.DOTALL))
    if not matches:
        return {
            "reasoning": "Could not parse LLM response.",
            "decision": "General-VM",
            "risk_level": "Medium",
            "performance_explanation": "Fallback decision used.",
            "tool_trace_summary": "Structured output missing."
        }
    
    # Try the last match as it's most likely the intended JSON block
    last_match = matches[-1].group(0)
    try:
        payload = json.loads(last_match)
    except json.JSONDecodeError:
        # If last match fails, try the first one as a backup
        try:
            payload = json.loads(matches[0].group(0))
        except json.JSONDecodeError:
            return {
                "reasoning": "Invalid JSON format in LLM response.",
                "decision": "General-VM",
                "risk_level": "Medium",
                "performance_explanation": "Fallback decision used.",
                "tool_trace_summary": "Invalid JSON response."
            }
    
    return {
        "reasoning": str(payload.get("reasoning", "No reasoning provided.")),
        "decision": _normalize_decision(str(payload.get("decision", "General-VM"))),
        "risk_level": str(payload.get("risk_level", "Medium")).title(),
        "performance_explanation": str(payload.get("performance_explanation", "")),
        "tool_trace_summary": str(payload.get("tool_trace_summary", "None")),
    }


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
        "tool_trace": state.get("tool_trace", ""),
        "risk_level": state.get("risk_level", "Medium"),
    }


def devops_agent(state: MultiAgentState) -> MultiAgentState:
    """Agent 2: uses explicit tools plus structured output for placement decisions."""
    live_snapshot = get_live_telemetry(state.get("last_decision", "None"), advance_simulation=False)
    recent_gpu_event = get_recent_gpu_event()
    tool_trace = (
        "Tool 1: get_live_telemetry() -> refreshed local telemetry without advancing simulator\n"
        f"Tool 2: get_recent_gpu_event() -> {recent_gpu_event}"
    )
    prompt = PromptTemplate.from_template("""
    You are an AI DevOps Orchestrator managing an AMD cluster.
    Cluster Status: {status}
    Local Telemetry Source: {telemetry_source}
    Local Telemetry Details: {local_telemetry}
    Recent GPU Event Tool: {recent_gpu_event}
    Incoming Workload: {workload}

    Rules:
    - ML Training prefers AMD-Instinct-GPU.
    - Web Serving prefers AMD-EPYC-CPU.
    - If a physical node load is above 80%, avoid it and choose another node.
    - Avoid Local-Notebook-Node for new ML work when the recent GPU event reports an active or recent spike.
    - decision must be exactly one of: AMD-EPYC-CPU, AMD-Instinct-GPU, General-VM, Local-Notebook-Node.

    Return exactly one JSON object with keys:
    reasoning, decision, risk_level, performance_explanation, tool_trace_summary
    """)
    response = (prompt | llm).invoke({
        "status": live_snapshot["cluster_status_text"],
        "telemetry_source": live_snapshot.get("telemetry_source", state.get("telemetry_source", "simulated")),
        "local_telemetry": live_snapshot.get("local_telemetry_text", state.get("local_telemetry_text", "Unavailable")),
        "recent_gpu_event": recent_gpu_event,
        "workload": state["current_workload"],
    })
    parsed = _parse_structured_response(response)
    decision = parsed["decision"]
    workload_name = state["current_workload"].split("|")[0].replace("Name:", "").strip().lower().replace(" ", "-")
    _, performance_summary = _performance_summary({**state, **live_snapshot}, decision)
    if parsed["performance_explanation"]:
        performance_summary = f"{performance_summary}\nAgent note: {parsed['performance_explanation']}\nRisk level: {parsed['risk_level']}"
    yaml_content = _build_manifest(workload_name, decision)
    return {
        **state,
        **live_snapshot,
        "devops_reasoning": parsed["reasoning"],
        "last_decision": decision,
        "performance_summary": performance_summary,
        "yaml_output": yaml_content,
        "tool_trace": f"{tool_trace}\nLLM tool summary: {parsed['tool_trace_summary']}",
        "risk_level": parsed["risk_level"],
    }
