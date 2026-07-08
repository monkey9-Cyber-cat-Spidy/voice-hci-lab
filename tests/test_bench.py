import json
from collections import Counter

from voicehci_bench.dataset import generate_dataset, load_dataset, save_dataset
from voicehci_bench.metrics import correction_overhead, intent_drift, percentile
from voicehci_bench.report import render_markdown
from voicehci_bench.runner import run_benchmark


def test_dataset_shape_and_determinism(tmp_path):
    recs = generate_dataset()
    assert len(recs) >= 150
    cats = Counter(r.category for r in recs)
    assert set(cats) == {"clean", "filler", "pivot_restart", "pivot_complement", "scratch", "meta",
                         "compound", "hard", "action"}
    assert cats["hard"] >= 10
    assert recs == generate_dataset()
    p = save_dataset(recs, tmp_path / "d.jsonl")
    assert load_dataset(p) == recs
    for r in recs:
        if r.kind == "dictation":
            assert r.expected_text
        else:
            assert r.expected_intent


def test_correction_overhead_human_model():
    assert correction_overhead("same", "same") == (0, 0.0)
    ks, _ = correction_overhead("the build is green", "The build is green.")
    assert ks == 3 + 2  # capitalise (nav+del+ins) and add period (nav+ins)
    ks_full, _ = correction_overhead("", "abc")
    assert ks_full == 4


def test_intent_drift():
    assert intent_drift("send it to jane", ["john"], ["jane"]) is False
    assert intent_drift("send it to john jane", ["john"], ["jane"]) is True
    assert intent_drift("send it", ["john"], ["jane"]) is True
    assert intent_drift("anything", [], []) is None
    assert percentile([1, 2, 3, 4], 0.5) == 2.5


def test_benchmark_subset_runs_and_reports(tmp_path):
    recs = [r for r in generate_dataset() if r.id in {"vhb-001", "vhb-050", "vhb-080", "vhb-151", "vhb-170"}]
    payload = run_benchmark(systems=["thought-stream", "final-cleaned", "voice-action-speculative"],
                            records=recs, out_dir=tmp_path)
    assert (tmp_path / "latest.json").exists()
    assert {s["system"] for s in payload["summaries"]} == {"thought-stream", "final-cleaned",
                                                           "voice-action-speculative"}
    ts = next(s for s in payload["summaries"] if s["system"] == "thought-stream")
    fc = next(s for s in payload["summaries"] if s["system"] == "final-cleaned")
    assert ts["cor_mean"] <= fc["cor_mean"]
    assert ts["ttfa_ms_median"] < fc["ttfa_ms_median"]
    md = render_markdown(payload)
    assert "| thought-stream |" in md and "Action systems" in md
    json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))


def test_full_benchmark_quality_gates():
    """The numbers in the README come from here; keep them honest."""
    payload = run_benchmark()
    s = {x["system"]: x for x in payload["summaries"]}
    ts = s["thought-stream"]["by_category"]
    for cat in ("clean", "filler", "pivot_restart", "pivot_complement", "scratch", "meta", "compound"):
        assert ts[cat]["cor_mean"] == 0.0, cat
        assert ts[cat]["drift_rate"] in (None, 0.0), cat
    assert s["thought-stream"]["cor_mean"] < 0.1
    assert s["thought-stream"]["drift_rate"] < 0.1
    assert s["final-cleaned"]["drift_rate"] > 0.9  # baseline leaks every retracted thought
    assert s["thought-stream"]["ttfa_ms_median"] < s["final-cleaned"]["ttfa_ms_median"] / 3
    assert s["voice-action-speculative"]["intent_accuracy"] == 1.0
    assert s["voice-action-speculative"]["slot_accuracy"] == 1.0
    assert s["voice-action-speculative"]["ttfa_ms_median"] < s["voice-action-serial"]["ttfa_ms_median"]
    assert s["voice-action-speculative"]["drift_rate"] == 0.0
