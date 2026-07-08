"""VoiceHCI-Bench: an evaluation harness for speech-driven interaction.

Word error rate tells you whether a recogniser heard the words. It says
nothing about whether the *interaction* felt instant, whether the user had to
fix the result, or whether the system executed the thought they retracted.
This harness measures those:

* **TTFA**  - time-to-first-action: speech onset -> first visible UI change.
* **COR**   - correction overhead rate: keystrokes a human needs to turn the
              system's output into the intended text, per intended character.
* **Drift** - intent drift under mid-sentence disfluency: did the retracted
              thought leak into the output / the executed action?
* **Rewrite ratio** - keystrokes the system itself dispatched per final
              character (a flicker proxy for streaming systems).
* plus WER, compute latency percentiles and intent accuracy for actions.

Any system that can consume a stream of transcript partials can be plugged
in (``systems.DictationSystem`` / ``systems.ActionSystem``).
"""

from .dataset import generate_dataset, load_dataset
from .metrics import correction_overhead, intent_drift
from .runner import run_benchmark
from .schema import BenchRecord, RecordResult, SystemSummary

__all__ = [
    "BenchRecord", "RecordResult", "SystemSummary", "correction_overhead", "generate_dataset",
    "intent_drift", "load_dataset", "run_benchmark",
]
