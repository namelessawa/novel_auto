# Blind style classification

- Git: `2017dcebb1da8849a36493430d042e98ac827618`
- Model: `glm-5.2`
- Samples: `7/7` valid
- Top-1: `0.1429`
- Top-3: `0.4286`
- Execution: `COMPLETE`
- Judge tokens: `36061` / `50000`

## Samples

| scenario | theme | expected | top-1 | top-3 | hit |
| --- | --- | --- | --- | --- | --- |
| pressure | apocalypse_wasteland | literary | rough_grit_realism | rough_grit_realism, noir_cold, screenplay_visual | MISS |
| pressure | apocalypse_wasteland | first_person_immersive | rough_grit_realism | rough_grit_realism, first_person_immersive, xianxia_fast | TOP3 |
| pressure | apocalypse_wasteland | ensemble_epic | noir_cold | noir_cold, rough_grit_realism, literary | MISS |
| pressure | apocalypse_wasteland | warm_healing | noir_cold | noir_cold, rough_grit_realism, xianxia_fast | MISS |
| pressure | apocalypse_wasteland | philosophical_meditative | noir_cold | noir_cold, rough_grit_realism, literary | MISS |
| pressure | apocalypse_wasteland | noir_cold | rough_grit_realism | rough_grit_realism, noir_cold, xianxia_fast | TOP3 |
| pressure | apocalypse_wasteland | rough_grit_realism | rough_grit_realism | rough_grit_realism, noir_cold, literary | TOP1 |

## Top confusions

- `ensemble_epic` → `noir_cold`: 1
- `first_person_immersive` → `rough_grit_realism`: 1
- `literary` → `rough_grit_realism`: 1
- `noir_cold` → `rough_grit_realism`: 1
- `philosophical_meditative` → `noir_cold`: 1
- `warm_healing` → `noir_cold`: 1
