/**
 * 客户端记忆系统
 * 管理 prompt 构建和分析结果的应用
 */

const ANALYSIS_SYSTEM_PROMPT = `你是一个专业的小说分析助手。你需要仔细阅读给定的小说章节内容，提取结构化信息。
请严格按照 JSON 格式输出分析结果，不要输出任何其他内容。`;

function buildAnalysisPrompt(chapterNum, chapterTitle, content) {
  // 截取内容（避免超限）
  const maxChars = 6000;
  let text = content;
  if (text.length > maxChars) {
    const head = text.slice(0, maxChars * 2 / 3);
    const tail = text.slice(-maxChars / 3);
    text = head + '\n\n... [中间部分省略] ...\n\n' + tail;
  }

  return `请分析以下小说章节内容，提取关键信息。

## 章节信息
- 章节号：第${chapterNum}章
- 章节标题：${chapterTitle}

## 章节内容
${text}

## 要求
请严格按照以下 JSON 格式输出分析结果：

\`\`\`json
{
  "characters": [
    {
      "name": "角色名",
      "role": "主角/配角/反派/路人",
      "description": "简短描述该角色在本章中的表现和状态（50字以内）",
      "location": "角色在本章中所处的地点（如有）",
      "status_changes": "角色状态的重要变化（如受伤、获得能力等，无变化则为空字符串）"
    }
  ],
  "relationships": [
    {
      "char1": "角色1名",
      "char2": "角色2名",
      "relationship_type": "关系类型（如：师徒、恋人、仇敌、朋友、同伴、对手等）",
      "emotion_changes": {
        "trust": 0.0,
        "affection": 0.0,
        "loyalty": 0.0,
        "conflict": 0.0
      },
      "event": "导致关系变化的事件描述（30字以内）"
    }
  ],
  "locations": [
    {
      "name": "地点名",
      "description": "地点描述（30字以内）"
    }
  ],
  "key_events": [
    {
      "title": "事件标题（10字以内）",
      "description": "事件描述（50字以内）",
      "involved_characters": ["相关角色名"]
    }
  ],
  "chapter_summary": "本章内容摘要（100-200字，概述主要情节发展）",
  "story_arc": "本章所属的故事弧线名称（10字以内）",
  "story_arc_summary": "故事弧线进展描述（50字以内）"
}
\`\`\`

注意事项：
- emotion_changes 中的值表示情感变化量（-1.0 到 1.0），正数表示增加，负数表示减少
- 只提取本章中实际出现的角色，不要编造
- relationships 只列出本章中有互动的角色对
- 如果某个字段没有相关内容，返回空数组 [] 或空字符串 ""`;
}

/**
 * 构建小说生成的完整提示词
 */
function buildGenerationPrompt(memory, recentChapters, customPrompt) {
  const parts = [];

  // 1. 实体状态
  const chars = memory.characters || {};
  const locs = memory.locations || {};
  const ws = memory.worldState || {};
  if (Object.keys(chars).length || Object.keys(locs).length || Object.keys(ws).length) {
    const sec = ['[世界观与实体当前状态]:'];
    if (Object.keys(chars).length) {
      sec.push('\n人物档案:');
      for (const [name, a] of Object.entries(chars)) {
        const desc = [a.role, a.description, a.status].filter(Boolean).join('，');
        sec.push(`- ${name}: ${desc}`);
      }
    }
    if (Object.keys(locs).length) {
      sec.push('\n地点设定:');
      for (const [name, a] of Object.entries(locs)) {
        sec.push(`- ${name}: ${a.description || ''}`);
      }
    }
    if (Object.keys(ws).length) {
      sec.push('\n世界观/规则:');
      for (const [name, a] of Object.entries(ws)) {
        sec.push(`- ${name}: ${a.description || ''}`);
      }
    }
    parts.push(sec.join('\n'));
  }

  // 2. 角色关系
  const rels = memory.relationships || {};
  if (Object.keys(rels).length) {
    const sec = ['[角色关系图谱]:'];
    for (const [, r] of Object.entries(rels)) {
      const emotionHints = [];
      const em = r.emotions || {};
      if (em.affection > 0.7) emotionHints.push('好感');
      if (em.trust > 0.7) emotionHints.push('信任');
      if (em.conflict > 0.5) emotionHints.push('冲突');
      const hint = emotionHints.length ? ` (${emotionHints.join('/')})` : '';
      sec.push(`  ${r.char1} ↔ ${r.char2}: ${r.type}${hint}`);
    }
    parts.push(sec.join('\n'));
  }

  // 3. 层级摘要
  const summaries = memory.chapterSummaries || [];
  const arcs = memory.arcs || [];
  if (memory.outline || arcs.length || summaries.length) {
    const sec = ['[故事大纲与前情提要]:'];
    if (memory.outline) sec.push(`\n高层大纲: ${memory.outline}`);
    if (arcs.length) {
      sec.push('\n中层剧情弧线:');
      for (const a of arcs.slice(-3)) sec.push(`- ${a.title}: ${a.summary}`);
    }
    if (summaries.length) {
      sec.push('\n近期章节摘要:');
      for (const s of summaries.slice(-5)) {
        sec.push(`第${s.chapterNum}章《${s.title}》: ${s.summary}`);
      }
    }
    parts.push(sec.join('\n'));
  }

  // 4. 相关历史事件（简单关键词匹配）
  const events = memory.events || [];
  if (events.length && recentChapters.length) {
    // 从最近章节提取关键词
    const lastContent = recentChapters[recentChapters.length - 1]?.content || '';
    const charNames = Object.keys(chars);
    const relevantEvents = events
      .filter(e => e.entities?.some(ent => charNames.includes(ent) || lastContent.includes(ent)))
      .slice(-3);
    if (relevantEvents.length) {
      const sec = ['[相关历史事件]:'];
      for (const e of relevantEvents) {
        sec.push(`- 第${e.chapterNum}章 (${e.title}): ${e.summary}`);
      }
      parts.push(sec.join('\n'));
    }
  }

  // 5. 近期正文（滑动窗口）
  if (recentChapters.length) {
    const recent = recentChapters.slice(-2);
    let recentText = recent.map(ch => `### ${ch.title}\n${ch.content}`).join('\n\n');
    if (recentText.length > 3000) recentText = recentText.slice(-3000);
    parts.push(`[近期正文]:\n${recentText}`);
  }

  // 6. 自定义提示词
  if (customPrompt) parts.push(`[自定义指令]: ${customPrompt}`);

  // 7. 生成指令
  parts.push(
    '[指令]: 请基于以上设定、摘要和前文，续写接下来的剧情，要求符合人物当前状态，' +
    '且自然推进当前主线。保持文风一致，情节连贯，避免逻辑错误。' +
    '输出纯正文内容，不要包含章节标题。字数在2000-4000字之间。'
  );

  return parts.join('\n\n');
}

/**
 * 将 LLM 分析结果应用到记忆对象（返回新对象，不可变）
 */
function applyAnalysisToMemory(memory, analysis, chapterNum, chapterTitle, chapterContent) {
  // 深拷贝
  const mem = JSON.parse(JSON.stringify(memory));

  // 1. 更新角色
  for (const ch of analysis.characters || []) {
    mem.characters[ch.name] = {
      ...(mem.characters[ch.name] || {}),
      role: ch.role || mem.characters[ch.name]?.role || '',
      description: ch.description || '',
      location: ch.location || '',
      status: ch.status_changes || mem.characters[ch.name]?.status || '',
      lastChapter: chapterNum,
    };
  }

  // 2. 更新地点
  for (const loc of analysis.locations || []) {
    mem.locations[loc.name] = {
      description: loc.description || '',
      lastChapter: chapterNum,
    };
  }

  // 3. 更新角色关系
  for (const rel of analysis.relationships || []) {
    const key = [rel.char1, rel.char2].sort().join('|');
    const existing = mem.relationships[key];
    if (existing) {
      // 更新情感
      const em = existing.emotions || { trust: 0.5, affection: 0.5, loyalty: 0.5, conflict: 0 };
      const changes = rel.emotion_changes || {};
      existing.emotions = {
        trust: clamp(em.trust + (changes.trust || 0)),
        affection: clamp(em.affection + (changes.affection || 0)),
        loyalty: clamp(em.loyalty + (changes.loyalty || 0)),
        conflict: clamp(em.conflict + (changes.conflict || 0)),
      };
      if (rel.event) {
        existing.history = [...(existing.history || []), { chapter: chapterNum, event: rel.event }];
      }
    } else {
      // 新关系
      const changes = rel.emotion_changes || {};
      mem.relationships[key] = {
        char1: rel.char1,
        char2: rel.char2,
        type: rel.relationship_type || '未知',
        emotions: {
          trust: clamp(0.5 + (changes.trust || 0)),
          affection: clamp(0.5 + (changes.affection || 0)),
          loyalty: clamp(0.5 + (changes.loyalty || 0)),
          conflict: clamp(0 + (changes.conflict || 0)),
        },
        history: rel.event ? [{ chapter: chapterNum, event: rel.event }] : [],
      };
    }
  }

  // 4. 添加事件
  const entities = new Set();
  for (const evt of analysis.key_events || []) {
    (evt.involved_characters || []).forEach(c => entities.add(c));
  }
  for (const ch of analysis.characters || []) entities.add(ch.name);

  // 用摘要作为事件 summary，原文太长不存
  const summary = analysis.chapter_summary || chapterContent.slice(0, 200) + '...';
  mem.events = [
    ...mem.events,
    {
      chapterNum,
      title: chapterTitle,
      summary,
      entities: [...entities],
      keyEvents: (analysis.key_events || []).map(e => e.title + ': ' + e.description),
    },
  ];

  // 5. 更新章节摘要
  if (analysis.chapter_summary) {
    mem.chapterSummaries = [
      ...mem.chapterSummaries.filter(s => s.chapterNum !== chapterNum),
      { chapterNum, title: chapterTitle, summary: analysis.chapter_summary },
    ];
    // 保留最近 10 条
    if (mem.chapterSummaries.length > 10) {
      mem.chapterSummaries = mem.chapterSummaries.slice(-10);
    }
  }

  // 6. 更新故事弧线
  if (analysis.story_arc && analysis.story_arc_summary) {
    const idx = mem.arcs.findIndex(a => a.title === analysis.story_arc);
    if (idx >= 0) {
      mem.arcs = [...mem.arcs];
      mem.arcs[idx] = { ...mem.arcs[idx], summary: analysis.story_arc_summary };
    } else {
      mem.arcs = [...mem.arcs, { title: analysis.story_arc, summary: analysis.story_arc_summary }];
    }
  }

  return mem;
}

function clamp(v, min = 0, max = 1) {
  return Math.max(min, Math.min(max, v));
}

/**
 * 获取某章节的记忆上下文（用于 UI 展示）
 */
function getChapterMemoryView(memory, chapterNum) {
  const chars = memory.characters || {};
  const rels = memory.relationships || {};
  const events = memory.events || [];
  const summaries = memory.chapterSummaries || [];

  return {
    characters: Object.entries(chars).map(([name, a]) => ({ name, ...a })),
    relationships: Object.values(rels),
    chapterEvents: events.filter(e => e.chapterNum === chapterNum),
    allEvents: events.slice(-5),
    chapterSummary: summaries.find(s => s.chapterNum === chapterNum),
    arcs: memory.arcs || [],
    outline: memory.outline || '',
  };
}

window.Memory = {
  ANALYSIS_SYSTEM_PROMPT,
  buildAnalysisPrompt,
  buildGenerationPrompt,
  applyAnalysisToMemory,
  getChapterMemoryView,
};
