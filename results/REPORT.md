# VoiceHCI-Bench results

Generated 2026-10-28T07:03:53.172736+00:00 on Windows-11-10.0.26300-SP0 (Python 3.14.3); 182 records; ASR profile {'ms_per_word': 380.0, 'asr_lag_ms': 120.0, 'final_lag_ms': 400.0}.

## Dictation systems

| system | n | TTFA p50 (ms) | TTFA p90 | tail latency p50 (ms) | COR | WER | drift | rewrite ratio | compute p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| verbatim-stream | 162 | 499 | 554 | 1200 | 1.103 | 0.870 | 1.00 | 1.85 | 0.01 |
| final-cleaned | 162 | 5444 | 7437 | 1600 | 0.929 | 0.808 | 1.00 | 1.84 | 0.02 |
| thought-stream | 162 | 1005 | 1453 | 1600 | 0.021 | 0.021 | 0.04 | 1.84 | 0.08 |
| thought-stream-final | 162 | 5444 | 7437 | 1600 | 0.021 | 0.021 | 0.04 | 1.01 | 0.07 |
| thought-stream-charaligned | 162 | 1005 | 1453 | 1600 | 0.021 | 0.021 | 0.04 | 1.84 | 0.10 |

## Action systems

| system | n | TTFA p50 (ms) | TTFA p90 | tail latency p50 (ms) | intent acc | slot acc | prewarm hit | drift |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| voice-action-speculative | 20 | 2061 | 3621 | 870 | 1.00 | 1.00 | 0.60 | 0.00 |
| voice-action-serial | 20 | 2308 | 4820 | 1030 | 1.00 | 1.00 | 0.00 | 0.00 |

## Drift and correction overhead by category

| system | action | clean | compound | filler | hard | meta | pivot_complement | pivot_restart | scratch |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| verbatim-stream | - | COR 0.08 | COR 2.04 / drift 1.00 | COR 0.27 | COR 0.93 / drift 1.00 | COR 1.46 | COR 1.06 / drift 1.00 | COR 1.46 / drift 1.00 | COR 1.82 / drift 1.00 |
| final-cleaned | - | COR 0.00 | COR 1.81 / drift 1.00 | COR 0.00 | COR 0.74 / drift 1.00 | COR 1.30 | COR 0.89 / drift 1.00 | COR 1.35 / drift 1.00 | COR 1.63 / drift 1.00 |
| thought-stream | - | COR 0.00 | COR 0.00 / drift 0.00 | COR 0.00 | COR 0.28 / drift 0.33 | COR 0.00 | COR 0.00 / drift 0.00 | COR 0.00 / drift 0.00 | COR 0.00 / drift 0.00 |
| thought-stream-final | - | COR 0.00 | COR 0.00 / drift 0.00 | COR 0.00 | COR 0.28 / drift 0.33 | COR 0.00 | COR 0.00 / drift 0.00 | COR 0.00 / drift 0.00 | COR 0.00 / drift 0.00 |
| thought-stream-charaligned | - | COR 0.00 | COR 0.00 / drift 0.00 | COR 0.00 | COR 0.28 / drift 0.33 | COR 0.00 | COR 0.00 / drift 0.00 | COR 0.00 / drift 0.00 | COR 0.00 / drift 0.00 |
| voice-action-speculative | COR 0.00 / drift 0.00 | - | - | - | - | - | - | - | - |
| voice-action-serial | COR 0.00 / drift 0.00 | - | - | - | - | - | - | - | - |

Definitions: TTFA = speech onset to first visible UI change. Tail latency = user stops talking to output stops changing. COR = keystrokes a human needs to fix the output per gold character. Drift = retracted thought leaked into output (or corrected one missing). Rewrite ratio = keystrokes the system itself dispatched per gold character.
