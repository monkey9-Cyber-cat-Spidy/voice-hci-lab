import random

import pytest

from hci_common.keystrokes import apply_ops
from thought_stream.patcher import compute_patch


def test_noop():
    assert compute_patch("same", "same").is_noop


def test_append_is_pure_typing():
    plan = compute_patch("send it", "send it to jane")
    assert plan.strategy == "prefix"
    assert [o.kind for o in plan.ops] == ["type"]
    assert plan.cost == len(" to jane")


def test_mid_sentence_swap_uses_suffix_strategy():
    old, new = "send it to john at four tomorrow", "send it to jane at four tomorrow"
    plan = compute_patch(old, new)
    assert plan.strategy == "prefix+suffix"
    assert apply_ops(old, plan.ops) == new
    # far cheaper than retyping the tail
    assert plan.cost < compute_patch(old, new, allow_caret_moves=False).cost


def test_word_alignment_never_splits_a_word():
    old, new = "the deployment is ready", "the deployment is really late"
    plan = compute_patch(old, new, word_aligned=True)
    assert plan.ops[0].kind == "backspace" and plan.ops[0].count == len("ready")
    char = compute_patch(old, new, word_aligned=False)
    assert char.cost <= plan.cost  # char alignment is cheaper but flickers mid-word


@pytest.mark.parametrize("seed", range(200))
def test_property_both_strategies_reach_target(seed):
    rng = random.Random(seed)
    alphabet = "ab c"
    old = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 25)))
    new = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 25)))
    for wa in (True, False):
        for cm in (True, False):
            plan = compute_patch(old, new, word_aligned=wa, allow_caret_moves=cm)
            assert apply_ops(old, plan.ops) == new
