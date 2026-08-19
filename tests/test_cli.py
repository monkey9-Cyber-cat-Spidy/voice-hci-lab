from thought_stream import cli as ts_cli
from voice_action import cli as va_cli
from voicehci_bench import cli as vb_cli


def test_thought_stream_cli(capsys):
    assert ts_cli.main(["text", "meet at four I mean five", "--app", "Slack"]) == 0
    assert capsys.readouterr().out.strip() == "Meet at five"
    assert ts_cli.main(["demo", "-v"]) == 0
    out = capsys.readouterr().out
    assert "on screen:" in out and "prefix" in out


def test_voice_action_cli(capsys):
    assert va_cli.main(["say", "open slack and message john saying hi", "--json"]) == 0
    out = capsys.readouterr().out
    assert "TTFA" in out and '"prewarm_hits": 1' in out
    assert va_cli.main(["demo"]) == 0


def test_bench_cli_systems(capsys):
    assert vb_cli.main(["systems"]) == 0
    assert "thought-stream" in capsys.readouterr().out
