# 推荐配对 — 16 主题 × 13 风格 matrix 数据驱动

> 数据源: 208/208 cell 含 glm-5.1 retro judge
> 评分 mean (1-5): 见 `matrix-bench-retro-1781668495.md`
> 重生成: `python scripts/gen_recommended_pairs.py`

## 速查 — 每主题 top-3 推荐风格

| 主题 key | 中文名 | 推荐风格 (mean) |
| --- | --- | --- |
| `ancient_romance` | 古风言情 | **hot_blooded** (5.00) / **black_humor** (4.67) / **colloquial_web** (4.67) |
| `apocalypse_wasteland` | 末世废土 | **colloquial_web** (4.67) / **ensemble_epic** (4.67) / **first_person_immersive** (4.67) |
| `campus_youth` | 校园青春 | **colloquial_web** (4.67) / **ensemble_epic** (4.67) / **hot_blooded** (4.67) |
| `high_fantasy_xuanhuan` | 玄幻冒险 | **black_humor** (4.67) / **ensemble_epic** (4.67) / **first_person_immersive** (4.67) |
| `history_military` | 历史军事 | **black_humor** (4.67) / **colloquial_web** (4.67) / **ensemble_epic** (4.67) |
| `modern_romance` | 现代言情 | **black_humor** (4.67) / **first_person_immersive** (4.67) / **warm_healing** (4.67) |
| `republic_spy` | 民国谍战 | **black_humor** (4.67) / **classical_chapter** (4.67) / **colloquial_web** (4.67) |
| `scifi_hard` | 硬科幻 | **black_humor** (4.67) / **hot_blooded** (4.67) / **literary** (4.67) |
| `scifi_soft_lit` | 软科幻文学 | **black_humor** (4.67) / **colloquial_web** (4.67) / **ensemble_epic** (4.67) |
| `steampunk_archive` | 蒸汽朋克悬疑 (默认) | **classical_chapter** (4.67) / **ensemble_epic** (4.67) / **hot_blooded** (4.67) |
| `supernatural_horror` | 灵异恐怖 | **classical_chapter** (4.67) / **ensemble_epic** (4.67) / **lyrical_poetic** (4.67) |
| `urban_mystery` | 都市悬疑 | **black_humor** (4.67) / **ensemble_epic** (4.67) / **hot_blooded** (4.67) |
| `western_fantasy` | 西式奇幻 | **black_humor** (4.67) / **first_person_immersive** (4.67) / **noir_cold** (4.67) |
| `workplace_drama` | 职场商战 | **black_humor** (4.67) / **ensemble_epic** (4.67) / **first_person_immersive** (4.67) |
| `wuxia_jianghu` | 武侠江湖 | **xianxia_fast** (5.00) / **black_humor** (4.67) / **ensemble_epic** (4.67) |
| `xianxia_cultivation` | 仙侠修真 | **black_humor** (4.67) / **classical_chapter** (4.67) / **colloquial_web** (4.67) |

## 速查 — 每风格 top-3 适配主题

| 风格 key | 中文名 | 适配主题 (mean) |
| --- | --- | --- |
| `black_humor` | 黑色幽默 (荒诞讽刺) | **ancient_romance** (4.67) / **high_fantasy_xuanhuan** (4.67) / **history_military** (4.67) |
| `classical_chapter` | 章回体古典 (传统笔法) | **republic_spy** (4.67) / **steampunk_archive** (4.67) / **supernatural_horror** (4.67) |
| `colloquial_web` | 大白话网文 (口语轻读) | **ancient_romance** (4.67) / **apocalypse_wasteland** (4.67) / **campus_youth** (4.67) |
| `ensemble_epic` | 群像史诗 (多 POV) | **apocalypse_wasteland** (4.67) / **campus_youth** (4.67) / **high_fantasy_xuanhuan** (4.67) |
| `first_person_immersive` | 第一人称沉浸 ('我' 视角) | **apocalypse_wasteland** (4.67) / **high_fantasy_xuanhuan** (4.67) / **history_military** (4.67) |
| `hot_blooded` | 燃血热血 (高能高燃) | **ancient_romance** (5.00) / **apocalypse_wasteland** (4.67) / **campus_youth** (4.67) |
| `literary` | 描写细致 (文学性, 默认) | **high_fantasy_xuanhuan** (4.67) / **scifi_hard** (4.67) / **scifi_soft_lit** (4.67) |
| `lyrical_poetic` | 抒情诗化 (诗意散文) | **supernatural_horror** (4.67) / **wuxia_jianghu** (4.67) / **apocalypse_wasteland** (4.33) |
| `melancholic` | 致郁忧伤 (悲怆基调) | **ancient_romance** (4.67) / **apocalypse_wasteland** (4.67) / **campus_youth** (4.67) |
| `noir_cold` | 冷峻冷酷 (黑色硬派) | **campus_youth** (4.67) / **high_fantasy_xuanhuan** (4.67) / **republic_spy** (4.67) |
| `somber` | 沉郁严肃 (严肃文学) | **ancient_romance** (4.67) / **apocalypse_wasteland** (4.67) / **steampunk_archive** (4.33) |
| `warm_healing` | 治愈温馨 (慢生活) | **high_fantasy_xuanhuan** (4.67) / **history_military** (4.67) / **modern_romance** (4.67) |
| `xianxia_fast` | 爽文快节奏 (网文动作向) | **wuxia_jianghu** (5.00) / **apocalypse_wasteland** (4.67) / **high_fantasy_xuanhuan** (4.67) |

## 风格通配排名 (跨主题平均 mean 降序)

| 风格 key | 中文名 | 跨主题平均 mean | 覆盖主题数 |
| --- | --- | --- | --- |
| `black_humor` | 黑色幽默 (荒诞讽刺) | 4.50 | 16/16 |
| `xianxia_fast` | 爽文快节奏 (网文动作向) | 4.48 | 16/16 |
| `ensemble_epic` | 群像史诗 (多 POV) | 4.48 | 16/16 |
| `hot_blooded` | 燃血热血 (高能高燃) | 4.48 | 16/16 |
| `melancholic` | 致郁忧伤 (悲怆基调) | 4.38 | 16/16 |
| `noir_cold` | 冷峻冷酷 (黑色硬派) | 4.36 | 16/16 |
| `first_person_immersive` | 第一人称沉浸 ('我' 视角) | 4.34 | 16/16 |
| `warm_healing` | 治愈温馨 (慢生活) | 4.31 | 16/16 |
| `colloquial_web` | 大白话网文 (口语轻读) | 4.25 | 16/16 |
| `literary` | 描写细致 (文学性, 默认) | 4.17 | 16/16 |
| `classical_chapter` | 章回体古典 (传统笔法) | 4.15 | 16/16 |
| `somber` | 沉郁严肃 (严肃文学) | 4.06 | 16/16 |
| `lyrical_poetic` | 抒情诗化 (诗意散文) | 3.92 | 16/16 |

## 满分配对 (mean = 5.0)

- `ancient_romance` × `hot_blooded` — 古风言情 配 燃血热血 (高能高燃)
- `wuxia_jianghu` × `xianxia_fast` — 武侠江湖 配 爽文快节奏 (网文动作向)

## 避雷配对 (mean < 4)

| 主题 | 风格 | mean | judge 失败维度 |
| --- | --- | --- | --- |
| `campus_youth` | `first_person_immersive` | 3.00 | voice=3, plot=2 |
| `high_fantasy_xuanhuan` | `lyrical_poetic` | 3.00 | voice=2, plot=3 |
| `republic_spy` | `somber` | 3.00 | voice=2, plot=3 |
| `urban_mystery` | `classical_chapter` | 3.00 | voice=1 |
| `ancient_romance` | `ensemble_epic` | 3.33 | voice=3, plot=3 |
| `ancient_romance` | `literary` | 3.33 | voice=3, plot=3 |
| `ancient_romance` | `lyrical_poetic` | 3.33 | voice=2 |
| `ancient_romance` | `warm_healing` | 3.33 | voice=3, plot=3 |
| `campus_youth` | `black_humor` | 3.33 | voice=2 |
| `history_military` | `literary` | 3.33 | voice=3, plot=3 |
| `scifi_soft_lit` | `lyrical_poetic` | 3.33 | voice=3, plot=3 |
| `supernatural_horror` | `literary` | 3.33 | voice=3, plot=3 |
| `supernatural_horror` | `somber` | 3.33 | voice=3, plot=3 |
| `urban_mystery` | `colloquial_web` | 3.33 | voice=2 |
| `urban_mystery` | `lyrical_poetic` | 3.33 | voice=2 |
| `western_fantasy` | `xianxia_fast` | 3.33 | voice=3, plot=3 |
| `xianxia_cultivation` | `somber` | 3.33 | voice=3, plot=3 |
| `ancient_romance` | `classical_chapter` | 3.67 | voice=3 |
| `ancient_romance` | `noir_cold` | 3.67 | voice=3 |
| `campus_youth` | `classical_chapter` | 3.67 | voice=3 |
| `high_fantasy_xuanhuan` | `colloquial_web` | 3.67 | voice=3 |
| `history_military` | `noir_cold` | 3.67 | voice=3 |
| `history_military` | `somber` | 3.67 | voice=3 |
| `modern_romance` | `colloquial_web` | 3.67 | voice=3 |
| `modern_romance` | `lyrical_poetic` | 3.67 | voice=3 |
| `scifi_hard` | `colloquial_web` | 3.67 | voice=3 |
| `scifi_hard` | `lyrical_poetic` | 3.67 | voice=3 |
| `steampunk_archive` | `first_person_immersive` | 3.67 | voice=3 |
| `steampunk_archive` | `xianxia_fast` | 3.67 | voice=3 |
| `supernatural_horror` | `first_person_immersive` | 3.67 | voice=3 |
| `supernatural_horror` | `hot_blooded` | 3.67 | voice=3 |
| `supernatural_horror` | `warm_healing` | 3.67 | voice=3 |
| `western_fantasy` | `melancholic` | 3.67 | voice=3 |
| `workplace_drama` | `melancholic` | 3.67 | voice=3 |
| `wuxia_jianghu` | `warm_healing` | 3.67 | voice=3 |

## Notes

* glm-5.1 在 3-tick 短样本上分辨力有限 (大量 4.67 并列). 长程 (50+ tick)
  才能拉开差距 — 长程数据待 PHASE5_PLAN J 完成后更新本表.
* 'avoid' 列里部分 cell 仅 voice 或 plot 单维度低, 长样本可能补回.
* 满分 5.0 是高置信信号 — 即使短样本也能识别完美匹配.
