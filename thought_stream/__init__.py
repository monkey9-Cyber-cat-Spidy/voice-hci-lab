"""Thought-Stream: a real-time disfluency and in-place text patch engine.

Pipeline (per streaming transcript update):

    raw partial transcript
      -> strip fillers                 (disfluency.strip_fillers)
      -> split meta-commands           (commands.extract_commands)
      -> resolve pivots/corrections    (disfluency.resolve_pivots)
      -> apply meta-commands           (commands.apply_commands)
      -> style for the active app      (style.format_for)
      -> minimal keystroke patch       (patcher.compute_patch)
      -> dispatch to a KeystrokeSink   (sinks.*)

The same patcher that handles the user saying "no wait, make that 4 PM"
also handles the ASR engine revising its own earlier words, which is why
streaming partials and human corrections cost the same code path.
"""

from .commands import Command, apply_commands, extract_commands
from .disfluency import resolve_pivots, strip_fillers
from .engine import PatchResult, ThoughtStreamEngine
from .patcher import PatchPlan, compute_patch
from .style import AppContext, StyleProfile, format_for, resolve_style

__all__ = [
    "AppContext",
    "Command",
    "PatchPlan",
    "PatchResult",
    "StyleProfile",
    "ThoughtStreamEngine",
    "apply_commands",
    "compute_patch",
    "extract_commands",
    "format_for",
    "resolve_pivots",
    "resolve_style",
    "strip_fillers",
]
