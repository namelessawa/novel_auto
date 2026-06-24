# Long-range drift analysis

* label: `phase6a-500tick-seed1-retry-0625` · ticks 500/500 · 10 buckets

* **verdict: WARN**


## Findings

* [D1] avg_dur drift: t 201– 250 avg_dur 51.9s = 2.25× start (23.1s) — slow drift
* [D1] avg_dur drift: t 451– 500 avg_dur 88.0s = 3.81× start (23.1s) — slow drift

## Per-bucket

| bucket | n | avg_dur | cum_tok end | clean% | OL avg | OL@cap% | memC | contradictions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| t   1–  50 | 50 | — | —
| t  51– 100 | 50 | — | —
| t 101– 150 | 50 | — | —
| t 151– 200 | 50 | — | —
| t 201– 250 | 50 | — | —
| t 251– 300 | 50 | — | —
| t 301– 350 | 50 | — | —
| t 351– 400 | 50 | — | —
| t 401– 450 | 50 | — | —
| t 451– 500 | 50 | — | —
