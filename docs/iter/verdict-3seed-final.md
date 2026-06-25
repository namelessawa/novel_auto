# bench-compare

> 3 bench JSON 对比. analyzer = analyze_longrange_drift.py.

| metric | phase6a-500tick-seed1-retry-0625 | phase6a-500tick-republic-iterN | phase6a-500tick-apocalypse-iterN |
| --- | ---: | ---: | ---: |
| 完成 tick | 500/500 | 500/500 | 290/500 |
| total tokens | 3,023,064 | 1,897,219 | 3,006,585 |
| LLM calls | 904 | 592 | 773 |
| avg dur (effective) | 60.2s | 54.8s | 68.8s |
| narratives | 241 | 162 | 174 |
| narrate% | 48.2% | 32.4% | 60.0% |
| top burner | narrator (1,215,168) | narrator (801,991) | narrator (898,927) |
| drift findings | 2 | 2 | 4 |
| drift verdict | WARN | WARN | FAIL |

## Drift verdict 汇总

* ⚠ **phase6a-500tick-seed1-retry-0625**: WARN (2 findings)
* ⚠ **phase6a-500tick-republic-iterN**: WARN (2 findings)
* ❌ **phase6a-500tick-apocalypse-iterN**: FAIL (4 findings)
