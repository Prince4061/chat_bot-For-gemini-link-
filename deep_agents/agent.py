"""
Minimal Deep Agent built on LangGraph.

    START -> agent -> (tool calls?) -> tools -> agent ... -> END

Extras over a plain ReAct loop:
* `write_todos` planning tool whose output is persisted in graph state (not just echoed).
* Virtual file system tools backed by a pluggable backend.
* A per-turn "session context" block injected into the system prompt so the model
  knows who it is talking to (verified reseller, pending order, platform...).
* Bounded execution (recursion limit) with partial-state recovery when the model
  errors mid-run, so callers can tell whether any tools already executed.
"""
from typing import Any, Dict, List, Literal, Optional, Sequence, Union, Annotated

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool, BaseTool, InjectedToolCallId
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from langgraph.errors import GraphRecursionError

from .backends import BaseBackend, StateBackend


class TodoItem(BaseModel):
    task: str = Field(description="Action item to complete")
    status: Literal["pending", "in_progress", "completed"] = Field(default="pending")


class DeepAgentState(BaseModel):
    messages: Annotated[List[BaseMessage], add_messages] = Field(default_factory=list)
    todos: List[Dict[str, Any]] = Field(default_factory=list)
    files: Dict[str, str] = Field(default_factory=dict)
    session_data: Dict[str, Any] = Field(default_factory=dict)


class DeepAgentError(RuntimeError):
    """Raised when the graph fails; carries the last good state so the caller can
    see whether tools already ran (and therefore must not re-run business logic)."""

    def __init__(self, original: Exception, partial_state: Optional[Dict[str, Any]]):
        super().__init__(str(original))
        self.original = original
        self.partial_state = partial_state or {}

    @property
    def tools_executed(self) -> List[str]:
        names = []
        for m in self.partial_state.get("messages", []):
            if isinstance(m, ToolMessage):
                names.append(getattr(m, "name", "") or "tool")
        return names


def extract_text(message: Any) -> str:
    """Normalise an AI message's content (str or content-block list) to plain text."""
    if message is None:
        return ""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


class DeepAgentRunner:
    def __init__(self, graph, backend: BaseBackend, tools_map: Dict[str, Any], recursion_limit: int = 30):
        self.graph = graph
        self.backend = backend
        self.tools_map = tools_map
        self.recursion_limit = recursion_limit

    @staticmethod
    def _coerce_messages(raw_msgs: Sequence[Any]) -> List[BaseMessage]:
        converted: List[BaseMessage] = []
        for m in raw_msgs:
            if isinstance(m, BaseMessage):
                converted.append(m)
            elif isinstance(m, dict):
                role, content = m.get("role", "user"), m.get("content", "")
                if role == "assistant":
                    converted.append(AIMessage(content=content))
                elif role == "system":
                    converted.append(SystemMessage(content=content))
                elif role == "tool":
                    converted.append(ToolMessage(content=content, tool_call_id=m.get("tool_call_id", "tool_call")))
                else:
                    converted.append(HumanMessage(content=content))
            else:
                converted.append(HumanMessage(content=str(m)))
        return converted

    def invoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        graph_input = {
            "messages": self._coerce_messages(input_data.get("messages", [])),
            "todos": input_data.get("todos", []),
            "files": self.backend.get_files(),
            "session_data": input_data.get("session_data", {}),
        }
        run_config = {"recursion_limit": self.recursion_limit}
        if config:
            run_config.update(config)

        last_state: Optional[Dict[str, Any]] = None
        try:
            # Streaming state snapshots lets us keep the last good state if a later step fails.
            for state in self.graph.stream(graph_input, config=run_config, stream_mode="values"):
                last_state = state
        except GraphRecursionError as exc:
            raise DeepAgentError(exc, last_state) from exc
        except Exception as exc:
            raise DeepAgentError(exc, last_state) from exc

        result = dict(last_state or graph_input)
        result["files"] = self.backend.get_files()
        return result


def create_deep_agent(
    model: Any,
    tools: Optional[Sequence[Union[BaseTool, Any]]] = None,
    system_prompt: str = "You are an autonomous Deep Agent.",
    backend: Optional[BaseBackend] = None,
    checkpointer: Optional[Any] = None,
    recursion_limit: int = 30,
    enable_file_tools: bool = False,
) -> DeepAgentRunner:
    active_backend = backend or StateBackend()
    tools_list = list(tools) if tools else []

    # --- Planning tool: updates graph state so the UI can render the plan ------
    @tool
    def write_todos(todos: List[TodoItem], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        """
        Record or update your step-by-step plan for a multi-step task.
        Each item: {"task": "...", "status": "pending" | "in_progress" | "completed"}.
        Call again with updated statuses as steps complete.
        """
        items = [t.model_dump() if isinstance(t, TodoItem) else dict(t) for t in todos]
        summary = "\n".join(f"[{i.get('status', 'pending').upper()}] {i.get('task', '')}" for i in items)
        return Command(update={
            "todos": items,
            "messages": [ToolMessage(content="Plan updated:\n" + summary, tool_call_id=tool_call_id)],
        })

    # --- Optional virtual file system tools -----------------------------------
    @tool
    def write_file(filename: str, content: str) -> str:
        """Write or overwrite a file in the agent workspace."""
        return active_backend.write_file(filename, content)

    @tool
    def read_file(filename: str) -> str:
        """Read a file from the agent workspace."""
        return active_backend.read_file(filename)

    @tool
    def list_files() -> str:
        """List files in the agent workspace."""
        files = active_backend.list_files()
        return "Files: " + ", ".join(files) if files else "No files in the workspace."

    agent_tools: List[Any] = [write_todos]
    if enable_file_tools:
        agent_tools += [write_file, read_file, list_files]
    agent_tools += tools_list
    tools_by_name = {t.name: t for t in agent_tools if hasattr(t, "name")}

    model_with_tools = model.bind_tools(agent_tools)

    def build_system_message(session_data: Dict[str, Any]) -> SystemMessage:
        parts = [system_prompt.strip()]
        context_text = (session_data or {}).get("context_text")
        if context_text:
            parts.append("## Live Session Context (authoritative, refreshed every turn)\n" + context_text.strip())
        parts.append(
            "## Execution Rules\n"
            "- Your tools return INSTANTLY. NEVER tell the user to wait, and never say you will 'check', "
            "'look up', 'fetch' or 'get back to them'. If you need data, CALL THE TOOL RIGHT NOW in this same "
            "turn, then answer. Do not end your turn with a promise to do something - do it.\n"
            "- Use `write_todos` for multi-step work (verify -> check credits -> claim -> confirm).\n"
            "- Never state a price, stock count, balance, order id or link that did not come from a tool result.\n"
            "- After tools finish, reply to the user with the complete, friendly final answer in one message."
        )
        return SystemMessage(content="\n\n".join(parts))

    def agent_node(state: DeepAgentState) -> Dict[str, Any]:
        messages = list(state.messages)
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [build_system_message(state.session_data)] + messages
        else:
            messages[0] = build_system_message(state.session_data)
        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(agent_tools, handle_tool_errors=True)

    def should_continue(state: DeepAgentState) -> Literal["tools", "__end__"]:
        last = state.messages[-1] if state.messages else None
        return "tools" if last is not None and getattr(last, "tool_calls", None) else END

    workflow = StateGraph(DeepAgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, ["tools", END])
    workflow.add_edge("tools", "agent")

    compiled = workflow.compile(checkpointer=checkpointer)
    return DeepAgentRunner(graph=compiled, backend=active_backend, tools_map=tools_by_name, recursion_limit=recursion_limit)
