from hci_common.clock import FakeClock
from voice_action.actions import (
    ActionContext,
    ClickElement,
    MockOSBackend,
    MoveFile,
    PressSend,
    TrustPolicy,
    TypeText,
    UndoStack,
)
from voice_action.agent import VoiceActionAgent
from voice_action.grounding import MockUIProvider, UINode, UITree
from voice_action.transcribers import ScriptedTranscriber


def make_ctx(running=()):
    clock = FakeClock()
    os_b = MockOSBackend(clock=clock, running=set(running))
    tree = UITree("slack", "Slack", [
        UINode("treeitem", "john", (0, 0, 10, 10)),
        UINode("edit", "Message", (0, 0, 10, 10), focused=True),
        UINode("edit", "Address and search bar", (0, 0, 10, 10)),
    ])
    return ActionContext(os=os_b, ui=MockUIProvider(tree), clock=clock), os_b, clock


def test_move_file_executes_and_undoes_on_real_filesystem(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x")
    dest = tmp_path / "archive"
    ctx, _, _ = make_ctx()
    act = MoveFile(str(src), str(dest))
    r = act.execute(ctx)
    assert r.ok and (dest / "a.txt").exists() and not src.exists()
    assert act.undo(ctx, r) and src.exists()


def test_undo_stack_and_type_text():
    ctx, os_b, _ = make_ctx()
    stack = UndoStack(ctx)
    r = TypeText("hello").execute(ctx)
    stack.push(r)
    assert stack.undo_last() is r
    assert os_b.typed[-1].kind == "backspace" and os_b.typed[-1].count == 5


def test_trust_policy_is_earned_and_lost():
    t = TrustPolicy()
    send = PressSend("john")
    assert t.decide(send) == "confirm"
    for _ in range(7):
        t.record_success(send)
    assert t.decide(send) == "preview"
    t.record_undo(send)
    assert t.decide(send) == "confirm"
    assert t.decide(TypeText("x")) == "auto"
    # clicking an input is reversible; clicking an arbitrary button is not
    assert ClickElement("address bar", roles=("edit", "combobox")).reversible
    assert not ClickElement("delete button").reversible


def run(text, speculation, running=("vscode",), confirm=False):
    ctx, os_b, clock = make_ctx(running)
    agent = VoiceActionAgent(ctx, enable_speculation=speculation)
    trace = agent.run(ScriptedTranscriber(text, clock=clock), speech_onset_ms=0.0, confirm=confirm)
    return trace, os_b, agent


def test_speculation_prewarms_and_commit_reuses_it():
    spec, os_spec, _ = run("open slack and message john saying running late", True)
    serial, os_ser, _ = run("open slack and message john saying running late", False)
    assert spec.prewarm_ms is not None and spec.prewarm_ms < spec.final_transcript_ms
    assert ("prewarm", "slack") in os_spec.calls and ("prewarm", "slack") not in os_ser.calls
    assert spec.prewarm_hits == 1
    # the window is on screen while the user is still talking
    assert spec.ttfa_ms < spec.final_transcript_ms < serial.ttfa_ms
    assert spec.commit_latency_ms < serial.commit_latency_ms
    # both typed the body; neither sent (PressSend needs earned trust)
    assert spec.pending_confirm == ["send to john"] == serial.pending_confirm


def test_wrong_speculation_is_rolled_back():
    trace, os_b, _ = run("open spotify no wait open slack", True)
    assert ("prewarm", "spotify") in os_b.calls
    assert ("close", "spotify") in os_b.calls
    assert trace.prewarm_aborts == 1
    assert trace.actions == ["open slack"] and trace.ok
    assert "spotify" not in os_b.running and os_b.foreground == "slack"


def test_cancel_aborts_speculation():
    ctx, os_b, clock = make_ctx()
    agent = VoiceActionAgent(ctx, enable_speculation=True)
    chunks = list(ScriptedTranscriber("open slack", clock=clock))
    agent.run(iter(chunks[:-1]), speech_onset_ms=0.0)  # partials only -> prewarm started
    assert ("prewarm", "slack") in os_b.calls
    agent.executor.abort()
    assert ("close", "slack") in os_b.calls


def test_undo_last_commit_and_voice_undo():
    ctx, os_b, clock = make_ctx()
    agent = VoiceActionAgent(ctx)
    agent.run(ScriptedTranscriber("open notepad", clock=clock), speech_onset_ms=0.0)
    assert "notepad" in os_b.running
    t2 = agent.run(ScriptedTranscriber("undo that", clock=clock), speech_onset_ms=clock.now_ms())
    assert "notepad" not in os_b.running
    assert any(e[0] == "undo" for e in t2.events)


def test_confirmed_run_sends_message():
    trace, os_b, _ = run("message john saying hi", True, running=("slack",), confirm=True)
    assert trace.ok and not trace.pending_confirm
    assert any(o.kind == "key" and o.text == "enter" for o in os_b.typed)


def test_asr_revision_in_transcriber():
    clock = FakeClock()
    chunks = list(ScriptedTranscriber("open crome", clock=clock, revisions={"crome": "chrome"}))
    assert chunks[1].text == "open crome"
    assert chunks[-1].final and chunks[-1].text == "open chrome"
