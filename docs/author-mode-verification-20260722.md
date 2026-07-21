# 作者模式重构验证报告（2026-07-22）

## 结论

默认作者路径、模拟隔离、迁移、故障恢复、HTTP 鉴权隔离和前端入口均已验证。真实 OpenAI 兼容 provider 完成四节连续生成，其中一节触发且只触发一次修复；进程级 runtime 重建后继续生成成功。测试与冒烟均未写入真实密钥或正文样本。

## 基线与最终结果

| 项目 | 重构前 | 重构后 |
| --- | ---: | ---: |
| 后端测试 | 1343 passed | 1374 passed |
| 前端模块 | 55 | 59 |
| 前端 CSS | 92.93 kB | 110.86 kB |
| 前端 JS | 320.55 kB | 352.25 kB |

最终验证命令：

```powershell
python -m pytest backend/tests/ -q
python -m ruff check backend/story backend/api/story_routes.py backend/tick_runtime.py scripts/smoke_author_mode.py backend/tests/test_author_context_validator.py backend/tests/test_author_generation_service.py backend/tests/test_author_runtime_factory.py backend/tests/test_simulation_gateway.py backend/tests/test_story_api.py backend/tests/test_story_migration.py
python -m compileall -q backend/story backend/api/story_routes.py scripts/smoke_author_mode.py
Set-Location frontend
npm run test:author
npm run build
```

结果：后端 `1374 passed`（仅保留一个既有 Starlette/httpx deprecation warning）；Ruff 与 compileall 通过；作者 UI 组件测试 `3 passed`；Vite 生产构建成功。

## 覆盖的风险场景

- 新作品默认 author，加载/切换作品不构造九 Agent runtime。
- 显式 simulation 初始化失败时模式与缓存回滚。
- 同名 novel ID 的不同用户不会共享 SectionStore、任务、状态或上下文。
- StoryBible 修订冲突返回 409，且不能由 Writer StateDelta 修改。
- CanonicalState 只接受验证后的单修订增量。
- 角色复活、位置跳跃、物品归属、知识越权、重复揭示和无证据故事线变更被拦截。
- Writer 第一次失败最多修复一次；修复输出不能重引入未验证 delta。
- 提交在 CanonicalState 写入后故障，重启可继续提交，正式章节不重复。
- 损坏现有权威文件先隔离并拒绝覆盖；last-good 备份可读取。
- 旧数据迁移幂等、保留源文件；L3 传说不升级为规范事实。
- 模拟候选被拒绝时不写正式章节、CanonicalState 或 legacy narrative。
- 任务/事务状态 API 不泄露候选正文、prompt 或目标状态快照。
- 作者模式前端不轮询 Tick；切换 simulation 后首次主动取状态。

## 真实 provider 冒烟

`scripts/smoke_author_mode.py` 从环境变量接收 base URL、API key 和 model，在临时作品目录中运行。最终一次通过结果：

| 节 | 正文字数 | Writer 总 token | 修复 | Canonical 修订 |
| ---: | ---: | ---: | --- | ---: |
| 1 | 1118 | 4239 | 否 | 2 |
| 2 | 1344 | 8760 | 是，恰好一次 | 3 |
| 3 | 2432 | 8210 | 否 | 4 |
| 4（runtime 重建后） | 2172 | 9892 | 否 | 5 |

StoryBible 保持修订 2 不变；四节全部 `committed`，最终校验严重度均为 low、违规码为零，共生成 16 条带证据的 MemoryRecord。冒烟过程中发现并修复了兼容 provider 的中文枚举漂移、JSON 截断/修复、singleton-list 漂移与 repair delta 越权问题。一次外部 TLS 连接失败发生在提交前，未产生半提交数据。

## 第二轮审查结论

重点复审了模式回滚、Windows 删除句柄、simulation gateway、真实 provider 解析边界、修复权限、跨用户缓存键和前端模式切换。最终没有未解决的高/中风险发现。保留的低风险提示是依赖栈中的 Starlette `TestClient` / httpx 弃用警告，与本次运行逻辑无关。
