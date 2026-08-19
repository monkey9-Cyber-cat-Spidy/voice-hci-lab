import pytest

from hci_common.keystrokes import (
    KeyOp,
    apply_ops,
    backspace,
    end,
    keystroke_cost,
    move_left,
    type_text,
)
from hci_common.text import levenshtein, word_error_rate


def test_apply_type_and_backspace():
    assert apply_ops("hello", [backspace(2), type_text("p me")]) == "help me"


def test_apply_caret_moves():
    ops = [move_left(5), backspace(4), type_text("jane"), end(), type_text("!")]
    assert apply_ops("to john at 4", ops) == "to jane at 4!"


def test_backspace_clamps_at_start():
    assert apply_ops("ab", [backspace(10)]) == ""


def test_cost():
    assert keystroke_cost([type_text("abc"), backspace(2), move_left(3)]) == 8


def test_invalid_ops():
    with pytest.raises(ValueError):
        KeyOp("backspace", count=-1)
    with pytest.raises(ValueError):
        KeyOp("type", text="x", count=2)


def test_levenshtein_and_wer():
    assert levenshtein("kitten", "sitting") == 3
    assert word_error_rate("the build is green", "The build is green.") == 0.0
    assert word_error_rate("", "a b") == 1.0
