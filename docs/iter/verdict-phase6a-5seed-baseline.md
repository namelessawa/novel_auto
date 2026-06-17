# Phase 5-J cross-seed long-range stress verdict

- seeds: 5 (['seed1', 'seed2', 'seed3', 'seed4', 'seed5'])
- gate: Phase 5-B stale-skip 在 cross-theme 长程不 drift?
- 标准: completion 100% + last-half narrative chars >= first-half × 0.7 + open_loops 无 collapse (-3+)

## Per-seed summary

| seed | label | completed | tokens | tpt | narr chars | rate | stale% | drift |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| seed1 | phase5j-longrange-200tick | 200/200 | 1062459 | 5312.3 | 84238 | 43.5% | 43.5% | PASS |
| seed2 | phase5j-longrange-seed2-republic | 100/100 | 423141 | 4231.4 | 50749 | 45.0% | 43.0% | PASS |
| seed3 | phase5j-longrange-seed3-apocalypse | 100/100 | 438843 | 4388.4 | 43444 | 45.0% | 43.0% | PASS |
| seed4 | phase6a-baseline-seed4-xianxia | 100/100 | 457166 | 4571.7 | 41970 | 43.0% | 43.0% | PASS |
| seed5 | phase6a-baseline-seed5-scifi | 100/100 | 478021 | 4780.2 | 46306 | 44.0% | 43.0% | PASS |

## Narrative growth (first vs last half)

Drift indicator: 后半 narrator 沉默 = WARN. PHASE5_PLAN J seed1 是 +37%.

| seed | first half chars | last half chars | delta |
| --- | ---: | ---: | ---: |
| seed1 | 38023 | 46215 | +21.5% |
| seed2 | 24578 | 26171 | +6.5% |
| seed3 | 21816 | 21628 | -0.9% |
| seed4 | 19699 | 22271 | +13.1% |
| seed5 | 21727 | 24579 | +13.1% |

## Open-loop progression

Drift indicator: open_loops 单调累积 = Stage 3 baseline 信号; Phase 5-B + Phase 4-E sideline 应该让其稳定. -3+ collapse = WARN.

### seed1
| tick | open | stale |
| ---: | ---: | ---: |
| 5 | 4 | 0 |
| 10 | 4 | 0 |
| 15 | 3 | 0 |
| … | … | … |
| 190 | 3 | 0 |
| 195 | 3 | 0 |
| 200 | 3 | 0 |

### seed2
| tick | open | stale |
| ---: | ---: | ---: |
| 5 | 5 | 0 |
| 10 | 5 | 0 |
| 15 | 5 | 0 |
| … | … | … |
| 90 | 5 | 0 |
| 95 | 5 | 0 |
| 100 | 5 | 0 |

### seed3
| tick | open | stale |
| ---: | ---: | ---: |
| 5 | 5 | 0 |
| 10 | 5 | 0 |
| 15 | 5 | 0 |
| … | … | … |
| 90 | 5 | 0 |
| 95 | 5 | 0 |
| 100 | 5 | 0 |

### seed4
| tick | open | stale |
| ---: | ---: | ---: |
| 5 | 5 | 0 |
| 10 | 5 | 0 |
| 15 | 5 | 0 |
| … | … | … |
| 90 | 5 | 0 |
| 95 | 5 | 0 |
| 100 | 5 | 0 |

### seed5
| tick | open | stale |
| ---: | ---: | ---: |
| 5 | 4 | 0 |
| 10 | 4 | 0 |
| 15 | 4 | 0 |
| … | … | … |
| 90 | 4 | 0 |
| 95 | 4 | 0 |
| 100 | 4 | 0 |

## Per-agent breakdown

| seed | top-5 agents (tokens) |
| --- | --- |
| seed1 | narrator=429286 / showrunner=155207 / world_simulator=131970 / event_injector=73577 / character_agent:char_linxue=53080 |
| seed2 | narrator=200876 / showrunner=53014 / world_simulator=44440 / event_injector=29919 / character_agent:char_zhaotianyou=22800 |
| seed3 | narrator=195770 / showrunner=53002 / world_simulator=47594 / event_injector=29609 / narrative_critic:critique=20980 |
| seed4 | narrator=197597 / showrunner=53419 / world_simulator=44666 / event_injector=30554 / character_agent:char_chenyan=21576 |
| seed5 | narrator=200964 / showrunner=53020 / world_simulator=47678 / event_injector=29758 / character_agent:char_qian=29191 |

## Gate decision

- PASS seeds: **5 / 5**
- **GATE PASS — SHIP confirmed**: Phase 5-B stale-skip 在 5 个 theme 上长程都不 drift.
