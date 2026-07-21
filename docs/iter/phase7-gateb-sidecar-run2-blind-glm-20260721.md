# Blind style classification

- Git: `2017dcebb1da8849a36493430d042e98ac827618`
- Model: `glm-5.2`
- Samples: `6/6` valid
- Top-1: `0.1667`
- Top-3: `0.3333`
- Execution: `COMPLETE`
- Judge tokens: `30429` / `50000`

## Samples

| scenario | theme | expected | top-1 | top-3 | hit |
| --- | --- | --- | --- | --- | --- |
| pressure | apocalypse_wasteland | first_person_immersive | rough_grit_realism | rough_grit_realism, noir_cold, xianxia_fast | MISS |
| pressure | apocalypse_wasteland | ensemble_epic | noir_cold | noir_cold, rough_grit_realism, literary | MISS |
| pressure | apocalypse_wasteland | warm_healing | noir_cold | noir_cold, rough_grit_realism, literary | MISS |
| pressure | apocalypse_wasteland | philosophical_meditative | rough_grit_realism | rough_grit_realism, first_person_immersive, noir_cold | MISS |
| pressure | apocalypse_wasteland | noir_cold | rough_grit_realism | rough_grit_realism, noir_cold, xianxia_fast | TOP3 |
| pressure | apocalypse_wasteland | rough_grit_realism | rough_grit_realism | rough_grit_realism, noir_cold, xianxia_fast | TOP1 |

## Top confusions

- `ensemble_epic` → `noir_cold`: 1
- `first_person_immersive` → `rough_grit_realism`: 1
- `noir_cold` → `rough_grit_realism`: 1
- `philosophical_meditative` → `rough_grit_realism`: 1
- `warm_healing` → `noir_cold`: 1
