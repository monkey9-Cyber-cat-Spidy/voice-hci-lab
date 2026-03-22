"""Windows keystroke injection via user32.SendInput (ctypes only).

Why SendInput and not clipboard-paste: paste is one visible chunk, which is
fine for first insertion but destroys the in-place edit illusion (a flicker
of selection + replace), clobbers the user's clipboard, and is blocked by
some apps. SendInput with KEYEVENTF_UNICODE types any BMP character into
any focused control without needing keyboard-layout gymnastics.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from hci_common.keystrokes import KeyOp

if sys.platform != "win32":  # pragma: no cover
    raise ImportError("WindowsSendInputSink is Windows-only")

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "end": 0x23, "home": 0x24, "left": 0x25,
    "up": 0x26, "right": 0x27, "down": 0x28, "delete": 0x2E, "win": 0x5B,
    "a": 0x41, "c": 0x43, "v": 0x56, "x": 0x58, "z": 0x5A, "y": 0x59,
}

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(inputs: list[INPUT]) -> None:
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


def _vk_input(vk: int, up: bool = False) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    return inp


def _unicode_input(ch: str, up: bool = False) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    inp.u.ki = KEYBDINPUT(0, ord(ch), flags, 0, 0)
    return inp


class WindowsSendInputSink:
    def __init__(self, inter_key_delay_s: float = 0.0, batch: int = 64) -> None:
        self.delay = inter_key_delay_s
        self.batch = batch

    def _tap(self, vk: int, times: int = 1) -> None:
        inputs: list[INPUT] = []
        for _ in range(times):
            inputs += [_vk_input(vk), _vk_input(vk, up=True)]
        _send(inputs)

    def _type(self, text: str) -> None:
        inputs: list[INPUT] = []
        for ch in text:
            if ch == "\n":
                inputs += [_vk_input(VK["enter"]), _vk_input(VK["enter"], up=True)]
            else:
                inputs += [_unicode_input(ch), _unicode_input(ch, up=True)]
            if len(inputs) >= self.batch * 2:
                _send(inputs)
                inputs = []
                if self.delay:
                    time.sleep(self.delay)
        _send(inputs)

    def _chord(self, chord: str) -> None:
        parts = [p.strip().lower() for p in chord.split("+")]
        vks = [VK[p] for p in parts]
        _send([_vk_input(v) for v in vks] + [_vk_input(v, up=True) for v in reversed(vks)])

    def dispatch(self, ops: list[KeyOp]) -> None:
        for op in ops:
            if op.kind == "type":
                self._type(op.text)
            elif op.kind == "backspace":
                self._tap(VK["backspace"], op.count)
            elif op.kind == "left":
                self._tap(VK["left"], op.count)
            elif op.kind == "right":
                self._tap(VK["right"], op.count)
            elif op.kind == "end":
                self._tap(VK["end"])
            elif op.kind == "key":
                self._chord(op.text)
