from hci_common.clock import FakeClock
from thought_stream.engine import ThoughtStreamEngine, render_target
from thought_stream.sinks import RecordingSink
from thought_stream.style import AppContext, resolve_style


def stream(engine, utterance):
    words = utterance.split()
    out = []
    for i in range(1, len(words) + 1):
        out.append(engine.feed(" ".join(words[:i]), final=(i == len(words))))
    return out


def test_streaming_converges_to_final_render():
    utt = "hey team um the deployment is ready actually wait make that delayed until 4 PM"
    sink = RecordingSink()
    eng = ThoughtStreamEngine(sink, context=AppContext("Slack"), clock=FakeClock())
    stream(eng, utt)
    final, _ = render_target(utt, resolve_style(AppContext("Slack")))
    assert sink.text == final == "Hey team the deployment is delayed until 4 PM"
    assert eng.rendered == sink.text


def test_streaming_types_early_and_patches_surgically():
    utt = "send it to john at four no wait to jane at four"
    sink = RecordingSink()
    eng = ThoughtStreamEngine(sink, context=AppContext("Slack"))
    results = stream(eng, utt)
    # first keystrokes went out on the second partial (first word held back as unstable)
    assert results[1].ops and results[1].ops[0].kind == "type"
    assert sink.text == "Send it to jane at four"
    # the correction never retyped the prefix "Send it"
    assert all(not (o.kind == "backspace" and o.count > len("to john at four")) for o in sink.log)


def test_asr_revision_is_just_another_patch():
    sink = RecordingSink()
    eng = ThoughtStreamEngine(sink, context=AppContext("Notion"))
    eng.feed("open slag and", final=False)
    assert sink.text == "Open slag"  # trailing partial word is held back
    eng.feed("open slack and message", final=False)
    assert sink.text == "Open slack and"
    # word-aligned: only "slag" was deleted, never the stable prefix
    assert sink.log[-2].kind == "backspace" and sink.log[-2].count == len("slag")


def test_final_only_mode_dispatches_once():
    sink = RecordingSink()
    eng = ThoughtStreamEngine(sink, context=AppContext("Notion"), commit_partials=False)
    stream(eng, "the build is green and tests pass")
    assert sink.dispatch_count == 1
    assert sink.text == "The build is green and tests pass."


def test_stats_and_reset():
    clock = FakeClock()
    eng = ThoughtStreamEngine(RecordingSink(), context=AppContext("Notion"), clock=clock)
    eng.mark_speech_onset()
    clock.advance(500)
    eng.feed("hello world", final=False)
    assert eng.stats.first_dispatch_at_ms == 500
    assert eng.stats.updates == 1
    eng.reset()
    assert eng.rendered == "" and eng.stats.updates == 0
