# 无限小说生成系统

这是一个基于 DeepSeek API 和四层记忆机制的智能小说生成系统，能够持续创作连贯、有趣的小说内容。

## 系统特性

### 四层记忆机制
1. **滑动窗口（短期记忆）**：保留最近生成的文本内容，确保文风和情节连贯性
2. **实体状态追踪（全局状态）**：维护人物、地点等实体的当前状态，防止逻辑错误
3. **层级摘要（结构化记忆）**：保存故事大纲、剧情弧线和章节摘要，指导整体发展方向
4. **长期记忆（RAG 机制）**：存储历史事件，支持跨章节的情节呼应和伏笔回收

### 核心功能
- 自动续写小说章节
- 智能记忆管理
- 连贯的情节发展
- 人物状态追踪
- 世界观一致性维护
- 多媒体生成（语音、图片、视频）

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

**方式一：前端配置（推荐）**

1. 启动前端：`cd frontend && npm start`
2. 访问 http://localhost:8080
3. 点击"配置"按钮
4. 填写 API 密钥并保存
5. 重启前端服务器

**方式二：使用 `.env` 文件**

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入您的 API 密钥
```

**.env 文件内容**：
```bash
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
DASHSCOPE_API_KEY=sk-your-dashscope-api-key-here  # 可选，用于图片生成
```

### 3. 运行系统

**终端模式**：
```bash
python create_novel.py  # 创建新小说
python continue_novel.py  # 续写小说
```

**前端模式**：
```bash
cd frontend
npm install
npm start
```

访问 http://localhost:8080

## 配置说明

所有配置项都在 `config.py` 文件中统一管理。

### 主要配置项

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| DEEPSEEK_API_KEY | DeepSeek API 密钥 | - |
| DEEPSEEK_BASE_URL | DeepSeek API 地址 | https://api.deepseek.com/v1 |
| MODEL_NAME | 模型名称 | deepseek-chat |
| MAX_TOKENS | 最大 Token 数 | 8192 |
| TEMPERATURE | 生成随机性 | 0.7 |
| DASHSCOPE_API_KEY | DashScope API 密钥 | - |
| ENABLE_MULTIMEDIA | 默认启用多媒体 | false |
| FRONTEND_PORT | 前端端口 | 8080 |

### 使用环境变量

可以通过环境变量覆盖配置：

```bash
# Linux/Mac
export DEEPSEEK_API_KEY=sk-your-key
export FRONTEND_PORT=3000
python main.py

# Windows
set DEEPSEEK_API_KEY=sk-your-key
set FRONTEND_PORT=3000
python main.py
```

## 项目结构

```
novel_auto/
├── config.py              # 统一配置文件
├── .env.example           # 环境变量模板
├── core_generator.py      # 核心生成器
├── create_novel.py        # 创建新小说
├── continue_novel.py      # 续写小说
├── main.py                # 主程序入口
├── multimedia/            # 多媒体模块
│   ├── tts_service.py     # 文本转语音
│   ├── image_generator.py # 图片生成
│   └── video_synthesizer.py # 视频合成
├── memory_system/         # 记忆系统
│   ├── sliding_window.py  # 滑动窗口
│   ├── entity_state.py    # 实体状态
│   ├── hierarchical_summary.py # 层级摘要
│   └── long_term_memory.py # 长期记忆
├── frontend/              # 前端界面
│   ├── server.js          # Node.js 服务器
│   └── views/             # 视图文件
└── results/               # 生成结果
```

## 使用方法

### 创建新小说

1. 运行 `python create_novel.py`
2. 输入小说主题
3. 系统生成第一章并保存

### 续写小说

1. 运行 `python continue_novel.py`
2. 选择要续写的小说主题
3. 选择续写模式

### 启用多媒体功能

在 `.env` 文件中设置：
```bash
ENABLE_MULTIMEDIA=true
DASHSCOPE_API_KEY=sk-your-dashscope-api-key
```

## 注意事项

1. **API 密钥安全**：请妥善保管 API 密钥，不要提交到代码仓库
2. **成本控制**：AI 生成服务会产生费用，请监控使用量
3. **网络连接**：确保网络连接稳定

## 故障排除

### API 调用失败

1. 检查 API 密钥是否正确
2. 检查网络连接
3. 查看 `MAX_TOKENS` 是否过大（建议 8192）

### 终端乱码

Windows 用户如遇乱码，可运行：
```bash
chcp 65001
```

### 前端无法访问

1. 检查端口是否被占用
2. 确认防火墙设置
3. 查看服务器日志

## 许可证

此项目仅供学习和研究使用。
