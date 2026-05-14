"""Windows UI Automation provider (requires the ``uiautomation`` package).

Walks the *focused top-level window* only, breadth-first, with a hard time
budget. Deep trees (Electron apps expose thousands of nodes) are cut off at
the budget: a partial tree in 15 ms beats a complete one in 400 ms, because
the elements a user names are almost always near the top (toolbars, inputs,
visible list items).
"""

from __future__ import annotations

import contextlib
from collections import deque

from hci_common.clock import Clock

from ..grounding import UINode, UITree

try:  # pragma: no cover - needs Windows + package
    import uiautomation as auto
except ImportError as exc:  # pragma: no cover
    raise ImportError("pip install 'wispr-hci-lab[windows]' for the UIA provider") from exc

_ROLE_MAP = {
    "EditControl": "edit",
    "DocumentControl": "document",
    "ButtonControl": "button",
    "SplitButtonControl": "splitbutton",
    "HyperlinkControl": "hyperlink",
    "ListItemControl": "listitem",
    "TreeItemControl": "treeitem",
    "MenuItemControl": "menuitem",
    "TabItemControl": "tabitem",
    "ComboBoxControl": "combobox",
    "CheckBoxControl": "checkbox",
    "TextControl": "text",
}
_INTERESTING = set(_ROLE_MAP)


class WindowsUIAProvider:  # pragma: no cover - exercised manually
    def __init__(self, clock: Clock, budget_ms: float = 15.0, max_nodes: int = 400) -> None:
        self.clock = clock
        self.budget_ms = budget_ms
        self.max_nodes = max_nodes

    def snapshot(self) -> UITree:
        t0 = self.clock.now_ms()
        focused = auto.GetFocusedControl()
        top = focused.GetTopLevelControl() if focused else auto.GetForegroundControl()
        app_name = ""
        with contextlib.suppress(Exception):
            app_name = auto.GetProcessName(top.ProcessId) if hasattr(auto, "GetProcessName") else ""
        nodes: list[UINode] = []
        focused_rt = focused.GetRuntimeId() if focused else None
        q: deque = deque([top])
        while q and len(nodes) < self.max_nodes and self.clock.now_ms() - t0 < self.budget_ms:
            ctrl = q.popleft()
            try:
                ctype = ctrl.ControlTypeName
                if ctype in _INTERESTING and (ctrl.Name or ctrl.AutomationId):
                    r = ctrl.BoundingRectangle
                    value = ""
                    try:
                        vp = ctrl.GetValuePattern() if ctype in ("EditControl", "ComboBoxControl") else None
                        value = vp.Value if vp else ""
                    except Exception:
                        pass
                    nodes.append(UINode(
                        role=_ROLE_MAP.get(ctype, ctype.lower()),
                        name=ctrl.Name or "",
                        rect=(r.left, r.top, r.right, r.bottom),
                        focused=(focused_rt is not None and ctrl.GetRuntimeId() == focused_rt),
                        value=value or "",
                        automation_id=ctrl.AutomationId or "",
                    ))
                q.extend(ctrl.GetChildren())
            except Exception:
                continue
        return UITree(app_name=app_name, window_title=top.Name or "", nodes=nodes,
                      latency_ms=self.clock.now_ms() - t0)
