from typing import Dict, TypedDict

class MultiAgentState(TypedDict):
    cluster_status_text: str
    current_workload: str
    last_decision: str
    devops_reasoning: str
    performance_summary: str
    yaml_output: str
    local_telemetry_text: str
    telemetry_source: str
    node_loads: Dict[str, int]
