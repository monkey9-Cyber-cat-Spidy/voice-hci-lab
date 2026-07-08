"""Benchmark runner: dataset x systems -> per-record results + summaries -> JSON."""

from __future__ import annotations

import json
import platform
import sys
import time
import zlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from hci_common.clock import FakeClock
from voice_action.transcribers import ScriptedTranscriber

from .dataset import load_dataset
from .metrics import correction_overhead, intent_drift, mean, median, percentile, wer
from .schema import BenchRecord, RecordResult, SystemSummary
from .systems import ACTION_SYSTEMS, DICTATION_SYSTEMS

ASR_PROFILE = {"ms_per_word": 380.0, "asr_lag_ms": 120.0, "final_lag_ms": 400.0}


def _chunks(record: BenchRecord, clock: FakeClock):
    revisions = record.asr_revisions or None
    return ScriptedTranscriber(record.spoken, clock=clock, revisions=revisions,
                               seed=zlib.crc32(record.id.encode()) & 0xFFFF, **ASR_PROFILE)


def _speech_end_ms(record: BenchRecord) -> float:
    # deterministic given seed; recompute by running a transcriber on a scratch clock
    c = FakeClock()
    last = 0.0
    for ch in _chunks(record, c):
        if not ch.final:
            last = ch.t_ms - ASR_PROFILE["asr_lag_ms"]
    return last


def run_record_dictation(system, record: BenchRecord) -> RecordResult:
    clock = FakeClock()
    out = system.run(record, _chunks(record, clock), clock)
    ks, cor = correction_overhead(out.text, record.expected_text)
    speech_end = _speech_end_ms(record)
    return RecordResult(
        record_id=record.id, system=system.name, category=record.category, kind="dictation",
        output_text=out.text, ttfa_ms=out.first_output_ms, final_ms=out.final_ms,
        speech_end_ms=speech_end,
        tail_latency_ms=(out.final_ms - speech_end) if out.final_ms is not None else None,
        correction_keystrokes=ks, cor=cor, wer=wer(out.text, record.expected_text),
        drift=intent_drift(out.text, record.retracted_terms, record.required_terms),
        system_keystrokes=out.system_keystrokes,
        rewrite_ratio=round(out.system_keystrokes / max(1, len(record.expected_text)), 3),
        updates=out.updates, compute_ms_p50=percentile(out.compute_ms, 0.5),
        compute_ms_p95=percentile(out.compute_ms, 0.95),
    )


def run_record_action(system, record: BenchRecord) -> RecordResult:
    clock = FakeClock()
    out = system.run(record, _chunks(record, clock), clock)
    tr = out.trace
    slots_ok = all(out.slots.get(k) == v for k, v in record.expected_slots.items())
    speech_end = _speech_end_ms(record)
    drift = None
    if record.retracted_terms:
        acted_apps = {e[2].get("app") for e in tr.events if e[0] == "ui_change"}
        drift = any(t in acted_apps for t in record.retracted_terms)
    return RecordResult(
        record_id=record.id, system=system.name, category=record.category, kind="action",
        output_text="; ".join(tr.actions), ttfa_ms=tr.ttfa_ms, final_ms=tr.commit_end_ms,
        speech_end_ms=speech_end,
        tail_latency_ms=(tr.commit_end_ms - speech_end) if tr.commit_end_ms is not None else None,
        drift=drift, updates=len(tr.hypotheses), compute_ms_p50=percentile(out.compute_ms, 0.5),
        compute_ms_p95=percentile(out.compute_ms, 0.95),
        intent_correct=(out.intent == record.expected_intent), slots_correct=slots_ok,
        prewarm_hit=out.prewarm_hit, pending_confirm=out.pending_confirm,
    )


def summarize(system: str, rows: list[RecordResult]) -> SystemSummary:
    def _cat(rs: list[RecordResult]) -> dict:
        ttfa = [r.ttfa_ms for r in rs if r.ttfa_ms is not None]
        tail = [r.tail_latency_ms for r in rs if r.tail_latency_ms is not None]
        drift = [r.drift for r in rs if r.drift is not None]
        intents = [r.intent_correct for r in rs if r.intent_correct is not None]
        slots = [r.slots_correct for r in rs if r.slots_correct is not None]
        pre = [r.prewarm_hit for r in rs if r.prewarm_hit is not None]
        return {
            "n": len(rs),
            "ttfa_ms_median": median(ttfa),
            "ttfa_ms_p90": percentile(ttfa, 0.9) if ttfa else None,
            "tail_latency_ms_median": median(tail),
            "cor_mean": mean([r.cor for r in rs]),
            "wer_mean": mean([r.wer for r in rs]),
            "drift_rate": mean([1.0 if d else 0.0 for d in drift]) if drift else None,
            "rewrite_ratio_mean": mean([r.rewrite_ratio for r in rs]),
            "compute_ms_p95": percentile([r.compute_ms_p95 for r in rs], 0.95),
            "intent_accuracy": mean([1.0 if x else 0.0 for x in intents]) if intents else None,
            "slot_accuracy": mean([1.0 if x else 0.0 for x in slots]) if slots else None,
            "prewarm_hit_rate": mean([1.0 if x else 0.0 for x in pre]) if pre else None,
        }

    overall = _cat(rows)
    by_cat: dict[str, list[RecordResult]] = defaultdict(list)
    for r in rows:
        by_cat[r.category].append(r)
    return SystemSummary(system=system, **overall, by_category={c: _cat(rs) for c, rs in sorted(by_cat.items())})


def run_benchmark(systems: list[str] | None = None, records: list[BenchRecord] | None = None,
                  out_dir: Path | None = None) -> dict:
    records = records or load_dataset()
    systems = systems or (list(DICTATION_SYSTEMS) + list(ACTION_SYSTEMS))
    results: list[RecordResult] = []
    t0 = time.perf_counter()
    for name in systems:
        if name in DICTATION_SYSTEMS:
            sysm = DICTATION_SYSTEMS[name]
            for r in records:
                if r.kind == "dictation":
                    results.append(run_record_dictation(sysm, r))
        elif name in ACTION_SYSTEMS:
            sysm = ACTION_SYSTEMS[name]
            for r in records:
                if r.kind == "action":
                    results.append(run_record_action(sysm, r))
        else:
            raise KeyError(f"unknown system {name!r}; known: {list(DICTATION_SYSTEMS) + list(ACTION_SYSTEMS)}")
    by_sys: dict[str, list[RecordResult]] = defaultdict(list)
    for r in results:
        by_sys[r.system].append(r)
    summaries = [summarize(s, rs) for s, rs in by_sys.items()]
    payload = {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "asr_profile": ASR_PROFILE,
            "n_records": len(records),
            "wall_seconds": round(time.perf_counter() - t0, 3),
            "dataset": "voicehci_bench_v1",
        },
        "summaries": [s.to_dict() for s in summaries],
        "results": [r.to_dict() for r in results],
        "records": {r.id: {"spoken": r.spoken, "expected_text": r.expected_text,
                           "expected_intent": r.expected_intent, "app": r.app,
                           "category": r.category, "difficulty": r.difficulty} for r in records},
    }
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (out_dir / f"run-{stamp}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        (out_dir / "latest.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return payload
