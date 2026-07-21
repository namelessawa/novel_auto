# StateGuard 人工盲审案例

## Case 01 — `sg-019-ddf88718`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice已进入city_gate_inner"
  }
]
```

### 正文

Alice爬上门外守望塔，隔着铁栅看见城内灯火；她没有越过内门。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "gate_watchtower",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Alice爬上门外守望塔，隔着铁栅看见城内灯火；她没有越过内门。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "gate_watchtower",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Alice爬上门外守望塔，隔着铁栅看见城内灯火；她没有越过内门。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "gate_watchtower",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 02 — `sg-024-f9e68432`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map仍为damaged"
  }
]
```

### 正文

Alice只是把湿透开裂的地图重新折好，没有进行任何修复。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "intact"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Alice只是把湿透开裂的地图重新折好，没有进行任何修复。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "intact"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Alice只是把湿透开裂的地图重新折好，没有进行任何修复。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "intact"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 03 — `sg-025-fd34880a`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map由bob持有"
  }
]
```

### 正文

Bob收下地图。Alice却无来源地说出了只有守门人才知道的内门暗号。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Bob收下地图。Alice却无来源地说出了只有守门人才知道的内门暗号。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Bob收下地图。Alice却无来源地说出了只有守门人才知道的内门暗号。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 04 — `sg-001-0a056ae0`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [
        {
          "injury_id": "injury_arm",
          "body_part": "arm",
          "severity": "moderate",
          "status": "active",
          "source_event_id": "evt_map_gate"
        }
      ],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice仍在city_gate_inner"
  }
]
```

### 正文

Alice守在门内观察巡逻灯，始终没有离开原位。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [
        {
          "injury_id": "injury_arm",
          "body_part": "arm",
          "severity": "moderate",
          "status": "active",
          "source_event_id": "evt_map_gate"
        }
      ],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 05 — `sg-014-a33dd200`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：谈判产生一项正文明写的新代价"
  }
]
```

### 正文

内门打开，Alice和Bob进入城内。Alice随后无来源地念出值班口令。谈判没有产生任何代价。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "内门打开，Alice和Bob进入城内。Alice随后无来源地念出值班口令。谈判没有产生任何代价。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_inner",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_inner",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "内门打开，Alice和Bob进入城内。Alice随后无来源地念出值班口令。谈判没有产生任何代价。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_inner",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_inner",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 06 — `sg-006-3d9727bd`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map仍由Alice持有，两人已进入city_gate_inner，出口已锁死"
  }
]
```

### 正文

Alice夹紧地图，架着Bob跨过出口。铁门随即锁死在他们身后。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "gate_locked",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 07 — `sg-023-f5f15238`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map由bob持有"
  }
]
```

### 正文

Bob接过地图，锁进铁匣。Alice摊开空手。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "bob"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Alice把地图收回自己的内袋，Bob没有拿到它。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Alice把地图收回自己的内袋，Bob没有拿到它。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 08 — `sg-018-d503d05e`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：两人仍在city_gate_inner"
  }
]
```

### 正文

Bob检查内门门轴，Alice在旁边望风；本段没有触碰地图。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 09 — `sg-004-29fdd7fc`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map由bob持有"
  }
]
```

### 正文

Bob接过地图，封进自己的铁匣。Alice空着手退开。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Bob接过地图，封进自己的铁匣。Alice空着手退开。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Bob接过地图，封进自己的铁匣。Alice空着手退开。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 10 — `sg-015-bce956e4`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map由bob持有"
  }
]
```

### 正文

Bob把地图收进铁匣，Alice松开了手。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": "alice",
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Bob把地图收进铁匣，Alice松开了手。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": "alice",
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Bob把地图收进铁匣，Alice松开了手。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": "alice",
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 11 — `sg-007-5f4dfffc`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice仍在city_gate_inner"
  }
]
```

### 正文

Alice站在城门内侧检查脚印，没有触碰或交付地图。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 12 — `sg-016-c32e1c88`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [
        {
          "injury_id": "injury_arm",
          "body_part": "arm",
          "severity": "moderate",
          "status": "active",
          "source_event_id": "evt_map_gate"
        }
      ],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice伤势仍active且map仍damaged"
  }
]
```

### 正文

Alice手臂伤口仍在流血，她把破损地图压在胸前。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [
        {
          "injury_id": "injury_arm",
          "body_part": "arm",
          "severity": "moderate",
          "status": "active",
          "source_event_id": "evt_map_gate"
        }
      ],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Alice毫发无伤地展开完好地图，想起妹妹Clara留下的密道遗言。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "intact"
        }
      },
      "newly_known_fact_ids": {
        "alice": [
          "fact_clara_sister"
        ]
      }
    }
  },
  {
    "round": 2,
    "prose": "Alice毫发无伤地展开完好地图，想起妹妹Clara留下的密道遗言。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "intact"
        }
      },
      "newly_known_fact_ids": {
        "alice": [
          "fact_clara_sister"
        ]
      }
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 13 — `sg-011-8f74100e`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map仍由Alice持有"
  }
]
```

### 正文

Alice嘴上说没有地图，手却一直压着装地图的内袋；她没有交给任何人。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 14 — `sg-005-2d677c0e`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map仍由Alice持有，两人已进入city_gate_inner，出口已锁死"
  }
]
```

### 正文

Alice把地图按回内袋。她拖着Bob滚过门线。下一秒，落栓封住了出口。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "gate_locked",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 15 — `sg-012-9011b4c3`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 0,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：map仍为damaged且quantity为0"
  }
]
```

### 正文

最后一片地图也被酸雨泡烂，Alice确认已经没有可用副本。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 0,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Alice从口袋取出一张完好地图，数量重新变成一。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "intact"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Alice从口袋取出一张完好地图，数量重新变成一。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "intact"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 16 — `sg-017-d069a4c1`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice已进入city_gate_inner"
  }
]
```

### 正文

Bob架着Alice向门边挪动，两人最终仍停在外侧。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "由Alice架着",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Bob架着Alice向门边挪动，两人最终仍停在外侧。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "由Alice架着",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Bob架着Alice向门边挪动，两人最终仍停在外侧。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "由Alice架着",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 17 — `sg-022-ebfc1859`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice仍在city_gate_inner"
  }
]
```

### 正文

守门人转述‘北桥已经塌了’，又承认自己没有亲眼看见。Alice仍留在门内。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 18 — `sg-021-e40f93e1`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：两人已进入city_gate_inner"
  }
]
```

### 正文

Alice扶住Bob的肩，两个人一同跨过内门。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "supporting_character_ids": [
        "alice"
      ],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 19 — `sg-020-e1cf70fa`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice已进入city_gate_inner"
  }
]
```

### 正文

Alice穿过第一道拒马，在外堡门洞停住；内城门仍紧闭。Bob还在她身后喘息。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Alice穿过第一道拒马，在外堡门洞停住；内城门仍紧闭。Bob还在她身后喘息。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  },
  {
    "round": 2,
    "prose": "Alice穿过第一道拒马，在外堡门洞停住；内城门仍紧闭。Bob还在她身后喘息。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {}
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 20 — `sg-003-1fe252d1`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice仍在city_gate_inner"
  }
]
```

### 正文

Alice按住藏着地图的内袋，却对守门人说：‘地图不在我这里。’她仍站在门内。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 21 — `sg-013-9de35926`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [
        {
          "injury_id": "injury_arm",
          "body_part": "arm",
          "severity": "moderate",
          "status": "active",
          "source_event_id": "evt_map_gate"
        }
      ],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice仍在city_gate_inner"
  }
]
```

### 正文

Alice数完门内的三盏巡逻灯，又回到原来的掩体。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [
        {
          "injury_id": "injury_arm",
          "body_part": "arm",
          "severity": "moderate",
          "status": "active",
          "source_event_id": "evt_map_gate"
        }
      ],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 22 — `sg-002-0c52a2d9`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：Alice不得新增无来源的密道知识"
  }
]
```

### 正文

Alice说密道就在钟楼第三块砖后，但此前没有人向她透露这个位置。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {
    "alice": "fact_secret_route"
  }
}
```

### Repair

[
  {
    "round": 1,
    "prose": "Alice说密道就在钟楼第三块砖后，但此前没有人向她透露这个位置。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {
        "alice": "fact_secret_route"
      }
    }
  },
  {
    "round": 2,
    "prose": "Alice说密道就在钟楼第三块砖后，但此前没有人向她透露这个位置。",
    "declared_ledger": {
      "schema_version": "1",
      "time_marker": "tick:1",
      "characters": {
        "alice": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        },
        "bob": {
          "location_id": "city_gate_outer",
          "movement_status": "arrived",
          "alive_status": "alive",
          "injuries": [],
          "knowledge_fact_ids": []
        }
      },
      "items": {
        "map": {
          "holder_character_ids": [
            "alice"
          ],
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {
        "alice": "fact_secret_route"
      }
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 23 — `sg-008-6a37a33d`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：两人已进入city_gate_inner"
  }
]
```

### 正文

爆风追上来时，Alice和Bob一起跌进门内，门线留在两人脚后。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

[
  {
    "round": 1,
    "prose": "爆风追上来时，Alice和Bob一起跌进门内，门线留在两人脚后。",
    "declared_ledger": {
      "characters": {
        "alice": {
          "location": "city_gate_inner",
          "injuries": [],
          "status": "alive"
        },
        "bob": {
          "location": "city_gate_inner",
          "injuries": [],
          "status": "alive"
        }
      },
      "items": {
        "map": {
          "holder": "alice",
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {},
      "time_marker": "tick:1"
    }
  },
  {
    "round": 2,
    "prose": "爆风追上来时，Alice和Bob一起跌进门内，门线留在两人脚后。",
    "declared_ledger": {
      "characters": {
        "alice": {
          "location": "city_gate_inner",
          "injuries": [],
          "status": "alive"
        },
        "bob": {
          "location": "city_gate_inner",
          "injuries": [],
          "status": "alive"
        }
      },
      "items": {
        "map": {
          "holder": "alice",
          "quantity": 1,
          "condition": "damaged"
        }
      },
      "newly_known_fact_ids": {},
      "time_marker": "tick:1"
    }
  }
]

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 24 — `sg-009-6ff842ec`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_outer",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：两人已进入city_gate_inner"
  }
]
```

### 正文

Alice架着Bob跨过内门，铁门在他们身后落下。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：

## Case 25 — `sg-010-7fe23b9c`

### 上一状态

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### 必达终态

```json
[
  {
    "event_id": "evt_map_gate",
    "requirement": "本段结束前：两人仍在city_gate_inner"
  }
]
```

### 正文

Bob说他听说国王已经死了；Alice只把这句话当作未经确认的传闻。两人仍在门内。

### 声明账本

```json
{
  "schema_version": "1",
  "time_marker": "tick:1",
  "characters": {
    "alice": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    },
    "bob": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "alive_status": "alive",
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {
    "map": {
      "holder_character_ids": [
        "alice"
      ],
      "quantity": 1,
      "condition": "damaged"
    }
  },
  "newly_known_fact_ids": {}
}
```

### Repair

无。

### 必要地点关系

```json
[
  {
    "location_id": "city_gate_outer",
    "name": "城门外侧",
    "type": "gate",
    "present_character_ids": []
  },
  {
    "location_id": "city_gate_inner",
    "name": "城门内侧",
    "type": "gate",
    "present_character_ids": [
      "alice",
      "bob"
    ]
  }
]
```

### 必要知识边界

```json
[
  {
    "character_id": "alice",
    "known_facts": [
      "地图可换取通行"
    ]
  },
  {
    "character_id": "bob",
    "known_facts": []
  }
]
```

### 请填写

- 终态是否完成：是 / 否 / 无法判断
- 是否有无来源状态变化：是 / 否 / 无法判断
- 账本是否匹配正文：是 / 否 / 无法判断
- 是否有知识越权：是 / 否 / 无法判断
- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断
- 最终决定：accept / reject / ambiguous
- 错误类型：
- 置信度：
- 理由：
