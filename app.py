import gradio as gr
from sowa.metrics import get_cluster_snapshot
from sowa.workflow import agent_app
from sowa.workloads import launch_workload_for_request, trigger_real_gpu_spike

current_app_state = {
    "cluster_status_text": "", "current_workload": "",
    "last_decision": "None", "devops_reasoning": "", "performance_summary": "",
    "yaml_output": "", "local_telemetry_text": "", "telemetry_source": "",
    "node_loads": {}, "tool_trace": "", "risk_level": "Medium"
}

def _view_tuple(result, job_status=""):
    return (
        result["current_workload"], result["cluster_status_text"], result["local_telemetry_text"],
        result["telemetry_source"], result["devops_reasoning"], result["last_decision"],
        result["performance_summary"], result["tool_trace"], result["yaml_output"], job_status
    )


def run_simulation_turn():
    global current_app_state
    result = agent_app.invoke(current_app_state)
    current_app_state = result
    return _view_tuple(result)


def run_current_workload():
    global current_app_state
    job_status = launch_workload_for_request(current_app_state.get("current_workload", ""))
    snapshot = get_cluster_snapshot(current_app_state.get("last_decision", "None"), advance_simulation=False)
    current_app_state.update(snapshot)
    return _view_tuple(current_app_state, job_status)


def refresh_telemetry():
    global current_app_state
    snapshot = get_cluster_snapshot(current_app_state.get("last_decision", "None"), advance_simulation=False)
    current_app_state.update(snapshot)
    return _view_tuple(current_app_state)


def run_real_gpu_spike():
    global current_app_state
    job_status = trigger_real_gpu_spike()
    snapshot = get_cluster_snapshot(current_app_state.get("last_decision", "None"), advance_simulation=False)
    current_app_state.update(snapshot)
    return _view_tuple(current_app_state, job_status)


def reset_simulation():
    global current_app_state
    current_app_state = {
        "cluster_status_text": "", "current_workload": "", "last_decision": "None",
        "devops_reasoning": "", "performance_summary": "", "yaml_output": "",
        "local_telemetry_text": "", "telemetry_source": "", "node_loads": {},
        "tool_trace": "", "risk_level": "Medium"
    }
    return "", "", "", "", "", "", "", "", "", ""

def main():
    with gr.Blocks(theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🚀 SOWA: AMD Multi-Agent Workload Optimizer")
        gr.Markdown("Watch the app combine **real local telemetry** with **simulated cluster nodes** so the DevOps agent can make hardware-aware placement decisions.")
        
        with gr.Row():
            with gr.Column():
                gr.Markdown("### 🌍 Environment (Simulator Agent)")
                in_workload = gr.Textbox(label="Incoming Workload Request", lines=2)
                in_status = gr.Textbox(label="Cluster Node Status", lines=4)
                local_telemetry = gr.Textbox(label="Local CPU / GPU Telemetry", lines=4)
                telemetry_source = gr.Textbox(label="Telemetry Source", lines=1)
                job_status = gr.Textbox(label="Local Notebook Execution", lines=2)
                btn_run = gr.Button("▶️ Run Next Simulation Turn", variant="primary")
                btn_execute = gr.Button("⚙️ Run Current Workload On Notebook")
                btn_gpu_spike = gr.Button("🔥 Trigger Real GPU Spike")
                btn_refresh = gr.Button("🔄 Refresh Telemetry")
                btn_reset = gr.Button("🧹 Reset")
                
            with gr.Column():
                gr.Markdown("### 🧠 DevOps Orchestrator (Decision & Action)")
                out_reasoning = gr.Textbox(label="Explainable AI Reasoning", lines=4)
                out_decision = gr.Textbox(label="Target Physical Node")
                out_performance = gr.Textbox(label="Performance Impact", lines=5)
                out_tool_trace = gr.Textbox(label="Tool Execution Trace", lines=4)
                out_yaml = gr.Code(label="Generated Kubernetes Manifest", language="yaml")

        btn_run.click(fn=run_simulation_turn, inputs=[], outputs=[in_workload, in_status, local_telemetry, telemetry_source, out_reasoning, out_decision, out_performance, out_tool_trace, out_yaml, job_status])
        btn_execute.click(fn=run_current_workload, inputs=[], outputs=[in_workload, in_status, local_telemetry, telemetry_source, out_reasoning, out_decision, out_performance, out_tool_trace, out_yaml, job_status])
        btn_gpu_spike.click(fn=run_real_gpu_spike, inputs=[], outputs=[in_workload, in_status, local_telemetry, telemetry_source, out_reasoning, out_decision, out_performance, out_tool_trace, out_yaml, job_status])
        btn_refresh.click(fn=refresh_telemetry, inputs=[], outputs=[in_workload, in_status, local_telemetry, telemetry_source, out_reasoning, out_decision, out_performance, out_tool_trace, out_yaml, job_status])
        btn_reset.click(fn=reset_simulation, inputs=[], outputs=[in_workload, in_status, local_telemetry, telemetry_source, out_reasoning, out_decision, out_performance, out_tool_trace, out_yaml, job_status])

    demo.launch(server_name="0.0.0.0", share=True)

if __name__ == "__main__":
    main()
