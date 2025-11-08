import pytest

from thought_stream.disfluency import resolve_pivots, strip_fillers


def test_strip_fillers():
    assert strip_fillers("um the uh build is, er, green") == "the build is, green"
    assert strip_fillers("hummus and umbrella") == "hummus and umbrella"  # no partial-word hits


@pytest.mark.parametrize("spoken,expected,strategy", [
    ("the deployment is ready actually wait make that delayed until 4 PM",
     "the deployment is delayed until 4 PM", "complement"),
    ("send it to john at four no wait to jane at four", "send it to jane at four", "anchor"),
    ("meet at four I mean five", "meet at five", "complement"),
    ("the meeting is at four actually five", "the meeting is at five", "complement"),
    ("the demo is on hold I mean merged", "the demo is merged", "complement"),
    ("send the report to marketing no send it to finance", "send it to finance", "restart"),
    ("let's ship on friday actually monday", "let's ship on monday", "complement"),
    ("open spotify no wait open slack", "open slack", "restart"),
])
def test_replace_pivots(spoken, expected, strategy):
    out, events = resolve_pivots(spoken)
    assert out == expected
    assert events[-1].kind == "replace" and events[-1].strategy == strategy


@pytest.mark.parametrize("spoken,expected", [
    ("the meeting is on tuesday scratch that", ""),
    ("let's meet on monday scratch that let's meet on friday", "let's meet on friday"),
    ("first point, second point, never mind", "first point"),
])
def test_delete_pivots(spoken, expected):
    out, events = resolve_pivots(spoken)
    assert out == expected
    assert events[0].kind == "delete"


@pytest.mark.parametrize("text", [
    "there is no way we ship friday",
    "it's actually fine to wait for the build",
    "sorry for the delay",
    "we would rather not",
    "please wait for me",
])
def test_soft_pivots_left_alone_when_not_structural(text):
    out, events = resolve_pivots(text)
    assert out == text
    assert events == []


def test_no_does_not_match_inside_words():
    out, events = resolve_pivots("notify the team and note the risk")
    assert out == "notify the team and note the risk"
    assert events == []


def test_streaming_deferral_hides_forming_correction():
    # on a partial, a trailing hard pivot with a 1-word correction is hidden
    out, ev = resolve_pivots("send it to john at four no wait to", final=False)
    assert out == "send it to john at four" and ev == []
    out, ev = resolve_pivots("send it to john at four no wait to jane", final=False)
    assert out == "send it to jane" and ev
    # on final it is applied regardless
    out, _ = resolve_pivots("meet at four I mean five", final=True)
    assert out == "meet at five"


def test_multiple_pivots_in_sequence():
    out, ev = resolve_pivots("send it to john no wait to jane actually to omar")
    assert out == "send it to omar"
    assert len(ev) == 2
