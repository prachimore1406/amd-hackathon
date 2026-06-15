from langgraph.graph import StateGraph, END
from sowa.state import MultiAgentState
from sowa.agents import simulator_agent, devops_agent

def build_graph():
    workflow = StateGraph(MultiAgentState)
    workflow.add_node("simulator", simulator_agent)
    workflow.add_node("devops", devops_agent)
    
    workflow.set_entry_point("simulator")
    workflow.add_edge("simulator", "devops")
    workflow.add_edge("devops", END)
    
    return workflow.compile()

agent_app = build_graph()
