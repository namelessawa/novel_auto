# Blind style classification

- Git: `41d363270836f50f9c03448f62e405217f4683f8`
- Model: `glm-5.2`
- Samples: `2/2` valid
- Top-1: `0.0`
- Top-3: `0.0`
- Execution: `COMPLETE`
- Judge tokens: `10105` / `50000`

## Samples

| scenario | theme | expected | top-1 | top-3 | hit |
| --- | --- | --- | --- | --- | --- |
| pressure | apocalypse_wasteland | philosophical_meditative | noir_cold | noir_cold, rough_grit_realism, xianxia_fast | MISS |
| compatible | scifi_soft_lit | philosophical_meditative | noir_cold | noir_cold, literary, melancholic | MISS |

## Top confusions

- `philosophical_meditative` → `noir_cold`: 2
