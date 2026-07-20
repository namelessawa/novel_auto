# Blind style classification

- Git: `c38fc7c69f329964d270c2da067849c91b67cde2`
- Model: `glm-5.2`
- Samples: `12/12` valid
- Top-1: `0.5`
- Top-3: `0.5833`
- Execution: `COMPLETE`
- Judge tokens: `56874` / `60000`

## Samples

| scenario | theme | expected | top-1 | top-3 | hit |
| --- | --- | --- | --- | --- | --- |
| pressure | apocalypse_wasteland | xianxia_fast | noir_cold | noir_cold, xianxia_fast, rough_grit_realism | TOP3 |
| pressure | apocalypse_wasteland | noir_cold | noir_cold | noir_cold, literary, rough_grit_realism | TOP1 |
| pressure | apocalypse_wasteland | warm_healing | rough_grit_realism | rough_grit_realism, noir_cold, literary | MISS |
| pressure | apocalypse_wasteland | ensemble_epic | xianxia_fast | xianxia_fast, rough_grit_realism, noir_cold | MISS |
| pressure | apocalypse_wasteland | philosophical_meditative | noir_cold | noir_cold, rough_grit_realism, melancholic | MISS |
| pressure | apocalypse_wasteland | rough_grit_realism | rough_grit_realism | rough_grit_realism, noir_cold, xianxia_fast | TOP1 |
| compatible | xianxia_cultivation | xianxia_fast | xianxia_fast | xianxia_fast, noir_cold, hot_blooded | TOP1 |
| compatible | republic_spy | noir_cold | noir_cold | noir_cold, literary, somber | TOP1 |
| compatible | gourmet_culinary | warm_healing | warm_healing | warm_healing, literary, noir_cold | TOP1 |
| compatible | history_military | ensemble_epic | noir_cold | noir_cold, literary, melancholic | MISS |
| compatible | scifi_soft_lit | philosophical_meditative | noir_cold | noir_cold, literary, melancholic | MISS |
| compatible | apocalypse_wasteland | rough_grit_realism | rough_grit_realism | rough_grit_realism, noir_cold, literary | TOP1 |

## Top confusions

- `philosophical_meditative` → `noir_cold`: 2
- `ensemble_epic` → `noir_cold`: 1
- `ensemble_epic` → `xianxia_fast`: 1
- `warm_healing` → `rough_grit_realism`: 1
- `xianxia_fast` → `noir_cold`: 1
