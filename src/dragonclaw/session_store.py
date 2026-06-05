"""Persistent session with probe-based checklist."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChecklistItem:
    id: str
    label: str
    done: bool = False
    detail: str = ""

    def render(self) -> str:
        mark = "✓" if self.done else "○"
        line = f"  {mark} {self.label}"
        if self.detail:
            line += f" — {self.detail}"
        return line


@dataclass
class SessionState:
    active_flow_id: str | None = None
    flow_step_index: int = 0
    checklist: list[ChecklistItem] = field(default_factory=list)
    flow_vars: dict[str, str] = field(default_factory=dict)
    history: list[dict[str, str]] = field(default_factory=list)

    def render_checklist(self) -> str:
        if not self.checklist:
            return ""
        lines = ["Checklist:"] + [item.render() for item in self.checklist]
        return "\n".join(lines)


DEFAULT_SESSION_ID = "default"


def _session_file(workspace_dir: Path, session_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in session_id)
    return workspace_dir / ".dragonclaw" / "sessions" / f"{safe}.json"


def load_session(workspace_dir: Path, session_id: str = DEFAULT_SESSION_ID) -> SessionState:
    workspace_dir = workspace_dir.expanduser().resolve()
    path = _session_file(workspace_dir, session_id)
    if not path.is_file():
        return SessionState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return SessionState()
    if not isinstance(raw, dict):
        return SessionState()
    checklist = [
        ChecklistItem(
            id=str(item.get("id", "")),
            label=str(item.get("label", "")),
            done=bool(item.get("done", False)),
            detail=str(item.get("detail", "")),
        )
        for item in raw.get("checklist") or []
        if isinstance(item, dict)
    ]
    return SessionState(
        active_flow_id=raw.get("active_flow_id"),
        flow_step_index=int(raw.get("flow_step_index", 0)),
        checklist=checklist,
        flow_vars={str(k): str(v) for k, v in (raw.get("flow_vars") or {}).items()},
        history=list(raw.get("history") or []),
    )


def save_session(
    workspace_dir: Path,
    state: SessionState,
    session_id: str = DEFAULT_SESSION_ID,
) -> None:
    workspace_dir = workspace_dir.expanduser().resolve()
    path = _session_file(workspace_dir, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_flow_id": state.active_flow_id,
        "flow_step_index": state.flow_step_index,
        "checklist": [
            {
                "id": item.id,
                "label": item.label,
                "done": item.done,
                "detail": item.detail,
            }
            for item in state.checklist
        ],
        "flow_vars": state.flow_vars,
        "history": state.history,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def mark_checklist_item(
    state: SessionState,
    item_id: str,
    *,
    done: bool,
    detail: str = "",
) -> None:
    for item in state.checklist:
        if item.id == item_id:
            item.done = done
            if detail:
                item.detail = detail
            return
    state.checklist.append(ChecklistItem(id=item_id, label=item_id, done=done, detail=detail))
