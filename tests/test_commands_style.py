from thought_stream.commands import MARK, apply_commands, extract_commands, strip_markers
from thought_stream.engine import render_target
from thought_stream.style import (
    CASUAL,
    CODE,
    PROFESSIONAL,
    SEARCH,
    AppContext,
    format_for,
    resolve_style,
)


def test_extract_produces_markers_and_keeps_content():
    marked = extract_commands("hi team period new line bullet ship it")
    assert marked.count(MARK) == 6
    assert strip_markers(marked) == "hi team ship it"


def test_commands_only_match_at_word_start():
    assert MARK not in extract_commands("a periodic bulletin")


def test_apply_commands_layout():
    marked = extract_commands("action items new line bullet ship the patch new line bullet write tests period")
    out = apply_commands(marked, newline="\n", bullet_prefix="- ")
    assert out == "action items\n- ship the patch\n- write tests."


def test_delete_last_word_and_sentence():
    assert apply_commands(extract_commands("send it today delete the last word tomorrow")) == "send it tomorrow"
    out = apply_commands(extract_commands("this is wrong period delete the last sentence this is right period"))
    assert out == "this is right."


def test_scratch_that_retracts_only_the_last_bullet():
    spoken = ("action items new line bullet ship the patch new line bullet notify the on call "
              "scratch that notify support period")
    text, pivots = render_target(spoken, PROFESSIONAL)
    assert text == "Action items\n- Ship the patch\n- Notify support."
    assert pivots[0].retracted == "notify the on call"


def test_style_resolution():
    assert resolve_style(AppContext("Slack")) is CASUAL
    assert resolve_style(AppContext("Notion")) is PROFESSIONAL
    assert resolve_style(AppContext("Code")) is CODE
    assert resolve_style(AppContext("Chrome", control_kind="url")) is SEARCH
    assert resolve_style(AppContext("", "Windows PowerShell")) is CODE


def test_format_for_profiles():
    assert format_for("the build is green", PROFESSIONAL) == "The build is green."
    assert format_for("the build is green", CASUAL) == "The build is green"
    assert format_for("the build is green", CODE) == "the build is green"
    assert format_for("Faster Whisper Latency", SEARCH) == "faster whisper latency"
    assert format_for("hi. how are you", PROFESSIONAL) == "Hi. How are you."
    # idempotent
    s = format_for("notes\n- one\n- two", PROFESSIONAL)
    assert format_for(s, PROFESSIONAL) == s
