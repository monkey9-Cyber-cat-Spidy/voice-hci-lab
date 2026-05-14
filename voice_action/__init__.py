"""Speculative Voice-to-Action: sub-second voice commands for the desktop.

The latency budget of a voice command is dominated by *waiting*: for the
speaker to finish, for the transcript to finalise, for an LLM round trip.
This package attacks each wait:

* ``intent``       - a streaming prefix classifier emits a hypothesis after
                     the first verb, long before the sentence ends.
* ``speculation``  - cheap, reversible preparation (resolve + pre-warm the
                     target app) runs on the hypothesis; the commit on the
                     final transcript reuses it or rolls it back.
* ``grounding``    - the focused window's accessibility tree, not a
                     screenshot, answers "where is the message box?".
* ``actions``      - every action carries its own undo; a trust policy
                     decides which ones may run without confirmation.
* ``agent``        - wires the above and records a millisecond timeline that
                     VoiceHCI-Bench consumes.
"""

from .actions import (
    Action,
    ActionContext,
    ClickElement,
    FocusWindow,
    MoveFile,
    OpenApp,
    SendMessage,
    TrustPolicy,
    TypeText,
    UndoStack,
)
from .agent import SessionTrace, VoiceActionAgent
from .events import TranscriptChunk
from .grounding import MockUIProvider, UINode, UITree, find_element
from .intent import Intent, IntentHypothesis, StreamingIntentClassifier
from .speculation import SpeculativeExecutor
from .transcribers import ScriptedTranscriber

__all__ = [
    "Action",
    "ActionContext",
    "ClickElement",
    "FocusWindow",
    "Intent",
    "IntentHypothesis",
    "MockUIProvider",
    "MoveFile",
    "OpenApp",
    "ScriptedTranscriber",
    "SendMessage",
    "SessionTrace",
    "SpeculativeExecutor",
    "StreamingIntentClassifier",
    "TranscriptChunk",
    "TrustPolicy",
    "TypeText",
    "UINode",
    "UITree",
    "UndoStack",
    "VoiceActionAgent",
    "find_element",
]
