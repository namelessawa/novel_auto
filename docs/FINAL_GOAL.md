# 当前最终目标

当前目标是把默认 Author 模式交付为可建立、可持续生成、可暂停恢复、可审计并可安全导出的
整书长篇小说产品。本文只定义完成范围，不缓存任何一次验收结论。

## 用户结果

用户应能在五步向导中完成：

1. 输入故事、主题、核心问题与结局方向；
2. 设定总字数、卷章数、章节范围与分节目标；
3. 选择内置 preset，或创建可版本化的自定义风格；
4. 选择并测试浏览器会话、当前设备或服务端 fallback 的 Provider 配置；
5. 创建 Author 作品、生成整书大纲并进入生产中心。

生产中心应支持开始、暂停、恢复、取消、失败章节重试、状态读取和 SSE；章节页只展示
committed 内容；导出只包含 committed manuscript 和 allowlisted evidence。

## 系统不变量

```text
ProductionSpec + BookOutline + frozen StyleProfile
  → NarrativeContract + frozen Author authority revisions
  → one initial Writer call
  → deterministic validation
  → at most one bounded local Patch Repair
  → complete revalidation
  → RevisionGuard
  → journaled atomic commit
```

- 默认整书生产不依赖九 Agent simulation。
- `CanonicalState` 是唯一当前事实源；Memory 不是 Canon。
- StyleProfile 只控制表达，不能改变事件、事实、终态、故事线或长度门槛。
- 默认没有 LLM Planner 和全文 Writer retry。
- 每次重试创建新 attempt/transaction，旧失败证据不可覆盖。
- 服务重启、暂停/恢复和 transaction recovery 都必须幂等。
- Provider 认证与应用 JWT 分离；Provider 401 不退出应用登录。
- 完整 key、Authorization、完整 Base URL、Provider 原始响应、拒绝正文和样文原句不得
  进入日志、诊断、报告、导出或 Git。

## 完成定义

完成不仅是代码存在，还必须同时满足：

- 整书规格、大纲、风格、Job、event、chapter 与 Provider API 契约完整；
- 五步向导、生产控制、章节阅读、风格管理和错误恢复具有对应 UI；
- 权威文件使用 revision guard、原子写、last-good、隔离和启动恢复；
- recorded 30 章长程、真实 G1/G2、真实产品 smoke 与秘密扫描均在当前源码上通过；
- 全新 evidence 目录生成 `report.json`、`report.md`、`manifest.json`、
  `artifact-sha256.json` 和 `recovery.md`；
- 最终 verdict 只由该新报告计算。

任何历史分支、旧基线、旧 evidence 或旧 PASS/FAIL 都不是当前完成证据。当前是否完成请按
[最终验收](./FINAL_ACCEPTANCE.md) 重新执行，不从本文推断。

## 文档入口

- [最终产品架构](./FINAL_ARCHITECTURE.md)
- [长篇生产手册](./LONG_NOVEL_PRODUCTION.md)
- [API 参考](./API.md)
- [自定义风格档案](./CUSTOM_STYLE_PROFILES.md)
- [Provider 生命周期](./PROVIDER_RUNTIME_LIFECYCLE.md)
- [迁移与回滚](./FINAL_MIGRATION_ROLLBACK.md)
