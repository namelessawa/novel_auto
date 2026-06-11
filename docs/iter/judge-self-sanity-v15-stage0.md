# Quality Judge Self-Sanity

- source: `docs/iter/bench-v15-final-iter29.json`
- rounds: 4
- elapsed: 99.02s
- judge_model: `mimo-v2.5-pro`

## Outcome

- x_wins: 0
- y_wins: 0
- tie: 3
- parse_error: 1
- valid_total: 3
- bias_score: 0.0 (OK)

> bias_score = (x_wins - y_wins) / valid. 同 text 两侧应 ≈ 0. |bias| ≥ 0.34 视作 judge 流程有偏, 必须先修.
