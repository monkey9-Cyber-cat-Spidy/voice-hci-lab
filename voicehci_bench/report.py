"""Markdown report from a benchmark payload."""

from __future__ import annotations


def _f(v, unit="", nd=0) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}{unit}"
    return f"{v}{unit}"


def render_markdown(payload: dict) -> str:
    meta = payload["meta"]
    lines = [
        "# VoiceHCI-Bench results",
        "",
        f"Generated {meta['generated_at']} on {meta['platform']} (Python {meta['python']}); "
        f"{meta['n_records']} records; ASR profile {meta['asr_profile']}.",
        "",
        "## Dictation systems",
        "",
        "| system | n | TTFA p50 (ms) | TTFA p90 | tail latency p50 (ms) | COR | WER | drift | rewrite ratio | compute p95 (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    dict_rows = [s for s in payload["summaries"] if s["intent_accuracy"] is None]
    act_rows = [s for s in payload["summaries"] if s["intent_accuracy"] is not None]
    for s in dict_rows:
        lines.append(
            f"| {s['system']} | {s['n']} | {_f(s['ttfa_ms_median'])} | {_f(s['ttfa_ms_p90'])} | "
            f"{_f(s['tail_latency_ms_median'])} | {_f(s['cor_mean'], nd=3)} | {_f(s['wer_mean'], nd=3)} | "
            f"{_f(s['drift_rate'], nd=2)} | {_f(s['rewrite_ratio_mean'], nd=2)} | {_f(s['compute_ms_p95'], nd=2)} |")
    if act_rows:
        lines += [
            "",
            "## Action systems",
            "",
            "| system | n | TTFA p50 (ms) | TTFA p90 | tail latency p50 (ms) | intent acc | slot acc | prewarm hit | drift |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for s in act_rows:
            lines.append(
                f"| {s['system']} | {s['n']} | {_f(s['ttfa_ms_median'])} | {_f(s['ttfa_ms_p90'])} | "
                f"{_f(s['tail_latency_ms_median'])} | {_f(s['intent_accuracy'], nd=2)} | "
                f"{_f(s['slot_accuracy'], nd=2)} | {_f(s['prewarm_hit_rate'], nd=2)} | {_f(s['drift_rate'], nd=2)} |")
    lines += ["", "## Drift and correction overhead by category", ""]
    cats = sorted({c for s in payload["summaries"] for c in s["by_category"]})
    lines.append("| system | " + " | ".join(cats) + " |")
    lines.append("|---|" + "---:|" * len(cats))
    for s in payload["summaries"]:
        cells = []
        for c in cats:
            b = s["by_category"].get(c)
            if not b:
                cells.append("-")
            elif b["drift_rate"] is not None:
                cells.append(f"COR {b['cor_mean']:.2f} / drift {b['drift_rate']:.2f}")
            elif b["intent_accuracy"] is not None:
                cells.append(f"intent {b['intent_accuracy']:.2f}")
            else:
                cells.append(f"COR {b['cor_mean']:.2f}")
        lines.append(f"| {s['system']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Definitions: TTFA = speech onset to first visible UI change. Tail latency = user stops "
        "talking to output stops changing. COR = keystrokes a human needs to fix the output per "
        "gold character. Drift = retracted thought leaked into output (or corrected one missing). "
        "Rewrite ratio = keystrokes the system itself dispatched per gold character.",
        "",
    ]
    return "\n".join(lines)
