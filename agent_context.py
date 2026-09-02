"""
Per-request session context for Deep Agent tools.

The LLM never sees session identifiers, so tools cannot receive them as arguments.
Instead `run_deep_agent_chat` sets a ContextVar before invoking the graph; tools read
it to scope orders, remember a verified reseller, and pick up a WhatsApp sender's phone.
ContextVars are thread-safe, so concurrent chats never leak into each other.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionContext:
    session_id: str
    platform: str = "web"               # "web" | "whatsapp"
    owner_id: Optional[str] = None      # browser client id / WhatsApp phone
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None
    user_type_hint: str = "customer"
    tool_calls: list = field(default_factory=list)  # audit trail of tools executed this turn


_current: ContextVar[Optional[SessionContext]] = ContextVar("deep_agent_session_ctx", default=None)


def set_session_context(ctx: Optional[SessionContext]):
    """Bind a context for the current execution; returns a token for `reset_session_context`."""
    return _current.set(ctx)


def reset_session_context(token) -> None:
    _current.reset(token)


def get_session_context() -> Optional[SessionContext]:
    return _current.get()


def record_tool_call(name: str, ok: bool, detail: str = "") -> None:
    ctx = _current.get()
    if ctx is not None:
        ctx.tool_calls.append({"tool": name, "ok": ok, "detail": detail[:200]})
