# bench-compare

> 2 bench JSON 对比. analyzer = analyze_longrange_drift.py.

| metric | phase6a-500tick-seed1-retry-0625 | phase6a-500tick-republic-iterN |
| --- | ---: | ---: |
| 完成 tick | 500/500 | 500/500 |
| total tokens | 3,023,064 | 1,897,219 |
| LLM calls | 904 | 592 |
| avg dur (effective) | 60.2s | 54.8s |
| narratives | 241 | 162 |
| narrate% | 48.2% | 32.4% |
| top burner | narrator (1,215,168) | narrator (801,991) |
| drift findings | 2 | 1 |
| drift verdict | WARN | WARN |

## Drift verdict 汇总

* ⚠ **phase6a-500tick-seed1-retry-0625**: WARN (2 findings)
* ⚠ **phase6a-500tick-republic-iterN**: WARN (1 findings)
