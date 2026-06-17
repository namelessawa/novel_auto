# Phase 6-A.3 — long-range memory fidelity verdict

- bench: `bench-phase6a2-longrange-500tick.json`
- completed ticks: 500
- narratives total: 271
- split mid tick: 305 (first half ≤ this, last half >)
- char pool size: 6

## Entity survival across halves

- early entities (mentioned in first half): 6
- late entities (mentioned in last half): 6
- **survived (in both halves): 6** — survival rate **100.0%**
- forgotten (early only): []
- new late (introduced after midpoint): []

## Mention counts in last half (engagement depth)

| character | mentions in last half |
| --- | ---: |
| 铁锤 | 119 |
| 灰钢 | 81 |
| 苏墨 | 67 |
| 林雪 | 50 |
| 九指 | 44 |
| 锈骨 | 1 |

## Open-loop reference check (first 5 current open loops)

- loops_closed_total during bench: **8**
- open_loops at end: 1

### Referenced in last half (keyword hit)

- `loop_t404_0`: '油池中存在被分成七块封入轴承的古代存在，已回收第三指骨，铁锤以协助寻找剩余六根轴承为条件换取对抗灰钢的援助'  (kw: ['油池中存在', '被分成七块', '封入轴承的', '古代存在', '已回收第三'])

### NOT referenced in last half

- (none — all current open loops actively referenced)

## Gate decision

- **GATE PASS** — entity survival 100% ≥ 60% threshold + 8 loops actively closed. Memory fidelity confirmed in long-range bench.
