import json
from typing import Any, Dict, List, Literal, Optional, Sequence, Union, Annotated
from pydantic import BaseModel, Field

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage
)
from langchain_core.tools import tool, BaseTool, StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .backends import BaseBackend, StateBackend

class TodoItem(BaseModel):
    task: str = Field(description="Action item to complete")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", 
        description="Status of the todo item"
    )

class DeepAgentState(BaseModel):
    messages: Annotated[List[BaseMessage], add_messages] = Field(default_factory=list)
    todos: List[Dict[str, Any]] = Field(default_factory=list)
    files: Dict[str, str] = Field(default_factory=dict)
    session_data: Dict[str, Any] = Field(default_factory=dict)

class DeepAgentRunner:
    def __init__(self, graph, backend: BaseBackend, tools_map: Dict[str, Any]):
        self.graph = graph
        self.backend = backend
        self.tools_map = tools_map

    def invoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Runs the Deep Agent graph and syncs files from backend."""
        # Convert dictionary messages to BaseMessage if needed
        raw_msgs = input_data.get("messages", [])
        converted_msgs = []
        for m in raw_msgs:
            if isinstance(m, BaseMessage):
                converted_msgs.append(m)
            elif isinstance(m, dict):
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "user":
                    converted_msgs.append(HumanMessage(content=content))
                elif role == "assistant":
                    converted_msgs.append(AIMessage(content=content))
                elif role == "system":
                    converted_msgs.append(SystemMessage(content=content))
                elif role == "tool":
                    converted_msgs.append(ToolMessage(
                        content=content, 
                        tool_call_id=m.get("tool_call_id", "tool_call_default")
                    ))
            else:
                converted_msgs.append(HumanMessage(content=str(m)))

        graph_input = {
            "messages": converted_msgs,
            "todos": input_data.get("todos", []),
            "files": self.backend.get_files(),
            "session_data": input_data.get("session_data", {})
        }

        result = self.graph.invoke(graph_input, config=config)
        result["files"] = self.backend.get_files()
        return result


def create_deep_agent(
    model: Any,
    tools: Optional[Sequence[Union[BaseTool, Any]]] = None,
    system_prompt: str = "You are an autonomous Deep Agent.",
    backend: Optional[BaseBackend] = None,
    checkpointer: Optional[Any] = None,
    subagents: Optional[Sequence[Any]] = None
):
    """
    Creates a Deep Agent with:
    1. Planning Tool (`write_todos`)
    2. Virtual File System tools (backed by backend)
    3. Custom domain tools and sub-agents
    4. LangGraph cyclical execution
    """
    active_backend = backend or StateBackend()
    tools_list = list(tools) if tools else []

    # 1. Virtual File System Tools for Deep Agent
    @tool
    def write_file(filename: str, content: str) -> str:
        """Write or overwrite content to a file in the virtual file system."""
        return active_backend.write_file(filename, content)

    @tool
    def read_file(filename: str) -> str:
        """Read content from a file in the virtual file system."""
        return active_backend.read_file(filename)

    @tool
    def list_files() -> str:
        """List all available files in the virtual file system."""
        files = active_backend.list_files()
        if not files:
            return "No files currently exist in the virtual file system."
        return f"Files: {', '.join(files)}"

    # 2. Planning Tool for Deep Agent
    @tool
    def write_todos(todos: List[Dict[str, str]]) -> str:
        """
        Record or update the agent's step-by-step action plan.
        Each item should have: 'task' (description) and 'status' ('pending', 'in_progress', 'completed').
        """
        todo_summary = [f"[{item.get('status', 'pending').upper()}] {item.get('task', '')}" for item in todos]
        return "Updated Todo Plan:\n" + "\n".join(todo_summary)

    agent_tools = [write_todos, write_file, read_file, list_files] + tools_list
    tools_by_name = {t.name: t for t in agent_tools if hasattr(t, "name")}

    # Bind tools to Model
    model_with_tools = model.bind_tools(agent_tools)

    # Define Graph Nodes
    def agent_node(state: DeepAgentState) -> Dict[str, Any]:
        messages = state.messages
        # Ensure system prompt is present at the beginning
        if not messages or not isinstance(messages[0], SystemMessage):
            full_system_text = (
                f"{system_prompt}\n\n"
                "DEEP AGENT RULES:\n"
                "- When dealing with complex, multi-step actions (like verifying reseller, deducting credits, or processing payment), "
                "use `write_todos` to track your progress.\n"
                "- Always execute tool calls to query live prices, check inventory, verify reseller codes, or claim links."
            )
            messages = [SystemMessage(content=full_system_text)] + list(messages)

        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(agent_tools)

    def should_continue(state: DeepAgentState) -> Literal["tools", "__end__"]:
        messages = state.messages
        last_message = messages[-1] if messages else None
        if last_message and getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    # Build Graph
    workflow = StateGraph(DeepAgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, ["tools", END])
    workflow.add_edge("tools", "agent")

    compiled_graph = workflow.compile(checkpointer=checkpointer)

    return DeepAgentRunner(
        graph=compiled_graph,
        backend=active_backend,
        tools_map=tools_by_name
    )
