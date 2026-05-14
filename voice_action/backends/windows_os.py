"""Windows OS backend: launch, focus, click, type - ctypes + stdlib only.

Launching uses ``os.startfile``/``subprocess`` with a small alias table; the
``prewarm`` path only *resolves* the launch target (which is the slow,
cacheable part: Start-Menu/PATH lookup) and optionally spawns it minimised.
"""

from __future__ import annotations

import ctypes
import os
import shlex
import shutil
import subprocess
import sys
from ctypes import wintypes

from hci_common.keystrokes import KeyOp

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("WindowsOSBackend is Windows-only")

user32 = ctypes.WinDLL("user32", use_last_error=True)

LAUNCH_TARGETS: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "terminal": ["wt.exe", "powershell.exe"],
    "chrome": ["chrome.exe", r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"],
    "edge": ["msedge.exe", r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"],
    "vscode": ["code.cmd", "Code.exe", r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe"],
    "slack": [r"%LocalAppData%\slack\slack.exe"],
    "discord": [r"%LocalAppData%\Discord\Update.exe --processStart Discord.exe"],
    "spotify": ["spotify.exe", r"%AppData%\Spotify\Spotify.exe"],
    "outlook": ["outlook.exe"],
    "excel": ["excel.exe"],
    "word": ["winword.exe"],
    "teams": ["ms-teams.exe"],
    "notion": [r"%LocalAppData%\Programs\Notion\Notion.exe"],
    "figma": [r"%LocalAppData%\Figma\Figma.exe"],
    "whatsapp": ["whatsapp:"],
}

WINDOW_TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "slack": ("slack",), "chrome": ("google chrome",), "edge": ("microsoft edge",),
    "vscode": ("visual studio code",), "terminal": ("powershell", "terminal", "cmd"),
    "notepad": ("notepad",), "calculator": ("calculator",), "explorer": ("file explorer",),
    "spotify": ("spotify",), "outlook": ("outlook",), "excel": ("excel",), "word": ("word",),
    "teams": ("teams",), "notion": ("notion",), "figma": ("figma",), "discord": ("discord",),
    "whatsapp": ("whatsapp",),
}


class WindowsOSBackend:  # pragma: no cover - exercised manually
    def __init__(self) -> None:
        self._resolved: dict[str, str] = {}
        self._launched: dict[str, subprocess.Popen] = {}

    # -- resolution (cheap, speculative-safe) --------------------------------
    def resolve_app(self, app: str) -> str | None:
        if app in self._resolved:
            return self._resolved[app]
        for cand in LAUNCH_TARGETS.get(app, [app + ".exe"]):
            expanded = os.path.expandvars(cand)
            exe = expanded.split(" ")[0]
            if exe.endswith(":") or os.path.exists(exe) or shutil.which(exe):
                self._resolved[app] = expanded
                return expanded
        return None

    # -- launch / focus --------------------------------------------------------
    def open_app(self, app: str, *, prewarm: bool = False) -> str | None:
        target = self.resolve_app(app)
        if not target:
            return None
        if prewarm:
            return target  # resolution is the warm part; spawning stays visible
        if self.focus_app(app):
            return target
        if target.endswith(":"):
            os.startfile(target)
        else:
            self._launched[app] = subprocess.Popen(shlex.split(target, posix=False))
        return target

    def close_app(self, app: str) -> bool:
        p = self._launched.pop(app, None)
        if p and p.poll() is None:
            p.terminate()
            return True
        return False

    def _enum_windows(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    out.append((hwnd, buf.value))
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return out

    def focus_app(self, app: str) -> bool:
        hints = WINDOW_TITLE_HINTS.get(app, (app,))
        for hwnd, title in self._enum_windows():
            if any(h in title.lower() for h in hints):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return True
        return False

    def foreground_title(self) -> str:
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    # -- input ---------------------------------------------------------------
    def click(self, x: int, y: int) -> None:
        user32.SetCursorPos(int(x), int(y))
        MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def dispatch_keys(self, ops: list[KeyOp]) -> None:
        from thought_stream.backends.windows_input import WindowsSendInputSink

        WindowsSendInputSink().dispatch(ops)

    def move_file(self, src: str, dst: str) -> str:
        return shutil.move(src, dst)
