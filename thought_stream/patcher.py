"""Minimal in-place keystroke patching.

Given the text currently rendered in a text field (caret at the end, as in
dictation) and the text we now believe should be there, produce the cheapest
sequence of keystrokes that rewrites only the affected span.

Two strategies are evaluated and the cheaper one wins:

* **prefix** - keep the common prefix, backspace the rest, retype the tail.
  Zero caret movement, always correct.
* **prefix+suffix** - additionally keep the common suffix: move the caret
  left over the suffix, backspace the differing middle, type the new middle,
  press End. Wins when a correction lands mid-sentence and a long tail
  follows ("send it to john at 4 pm" -> "send it to jane at 4 pm").

Both strategies touch only the span between the first and last differing
character, which is what keeps the rewrite visually quiet: unchanged text
never flickers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hci_common.keystrokes import (
    KeyOp,
    apply_ops,
    backspace,
    end,
    keystroke_cost,
    move_left,
    type_text,
)


@dataclass(frozen=True)
class PatchPlan:
    ops: list[KeyOp] = field(default_factory=list)
    strategy: str = "noop"
    chars_deleted: int = 0
    chars_typed: int = 0

    @property
    def cost(self) -> int:
        return keystroke_cost(self.ops)

    @property
    def is_noop(self) -> bool:
        return not self.ops


def _common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _common_suffix_len(a: str, b: str, limit: int) -> int:
    n = min(len(a), len(b), limit)
    i = 0
    while i < n and a[-1 - i] == b[-1 - i]:
        i += 1
    return i


def _word_aligned_prefix(a: str, b: str, p: int) -> int:
    """Pull the split point back to a word boundary so the user never sees a
    half-word get deleted and retyped from its middle ("deplo|yed").

    Costs a few extra keystrokes but is far less visually jarring; the bench
    measures both so the trade-off is explicit.
    """
    if p == 0 or p >= len(a) or p >= len(b):
        return p
    if a[p - 1].isspace():
        return p
    while p > 0 and not a[p - 1].isspace():
        p -= 1
    return p


def compute_patch(rendered: str, target: str, *, word_aligned: bool = True,
                  allow_caret_moves: bool = True) -> PatchPlan:
    if rendered == target:
        return PatchPlan()

    p = _common_prefix_len(rendered, target)
    if word_aligned:
        p = _word_aligned_prefix(rendered, target, p)

    # Strategy A: prefix only.
    del_a = len(rendered) - p
    tail_a = target[p:]
    ops_a: list[KeyOp] = []
    if del_a:
        ops_a.append(backspace(del_a))
    if tail_a:
        ops_a.append(type_text(tail_a))
    plan_a = PatchPlan(ops_a, "prefix", del_a, len(tail_a))

    if not allow_caret_moves:
        return plan_a

    # Strategy B: prefix + suffix with caret moves.
    s = _common_suffix_len(rendered, target, limit=min(len(rendered), len(target)) - p)
    if s == 0:
        return plan_a
    mid_old = rendered[p : len(rendered) - s]
    mid_new = target[p : len(target) - s]
    ops_b: list[KeyOp] = [move_left(s)]
    if mid_old:
        ops_b.append(backspace(len(mid_old)))
    if mid_new:
        ops_b.append(type_text(mid_new))
    ops_b.append(end())
    plan_b = PatchPlan(ops_b, "prefix+suffix", len(mid_old), len(mid_new))

    # Sanity: both must produce the target. (Cheap, and it has caught bugs.)
    assert apply_ops(rendered, plan_a.ops) == target
    assert apply_ops(rendered, plan_b.ops) == target

    return plan_b if plan_b.cost < plan_a.cost else plan_a
