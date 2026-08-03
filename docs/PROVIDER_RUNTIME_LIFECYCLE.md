# Provider 运行时生命周期

## 目标

所有 OpenAI-compatible 调用在调用时解析配置，不再依赖模块导入时冻结的 API key、
Base URL、model 或 active provider。兼容对象 `llm_client` 只是轻量代理，`chat()` 和
`chat_stream()` 使用同一套 resolver。

运行时优先级固定为：

```text
当前请求显式配置
  → 当前 Stage 显式配置
  → 服务端持久配置
  → 环境变量 fallback
```

真实验收命令显式传入只读 `coding.txt`。该文件只在进程内解析，不复制到实施
worktree，不修改，不提交，也不把路径、内容或秘密写入报告。普通浏览器产品流不读取该
文件；它使用会话/设备配置或服务端 fallback。

## ProviderRuntimeConfig

不可变运行时配置包含 provider、凭据、Base URL、model、thinking mode、timeout、
SDK retries、temperature、max token cap、来源和非敏感配置指纹。

完整性校验在创建客户端前完成。客户端缓存键包含 provider、Base URL、model、
API key 的不可逆哈希、thinking mode、timeout 和 retries；日志、异常、诊断和 repr
都不包含明文凭据。

reload 会让下一次调用使用新配置，并异步关闭从缓存移除的旧连接池。不同 ContextVar
请求彼此隔离，不能串用凭据。

## 前端与请求配置

浏览器可以把配置限定为当前会话，或保存在当前设备。请求通过以下 headers 传递：

- `X-User-LLM-Key`
- `X-User-LLM-Base-Url`
- `X-User-LLM-Model`
- `X-User-LLM-Provider`
- `X-User-LLM-Thinking-Mode`
- `X-User-LLM-Timeout`
- `X-User-LLM-Max-Retries`

完整 key 不会从服务端重新返回。Base URL 继续经过公共地址安全校验。

用户未在浏览器保存 key 时，前端省略整组 `X-User-LLM-*` headers，服务端按持久配置与
环境 fallback 解析。不要发送只有 provider/model、没有凭据的残缺 header 覆盖。浏览器
会话配置随会话结束清除；设备配置只属于当前浏览器设备，不同步到服务端配置文件。

## API

| 接口 | 返回 |
| --- | --- |
| `GET /api/config/llm` | 兼容的服务端配置视图；不会作为读取完整 secret 的接口 |
| `GET /api/config/llm/providers` | 后端 catalog 的 provider、label、默认 model 和默认 Base URL |
| `GET /api/config/llm/runtime` | provider、model、source、thinking、timeout、retries、凭据存在性和短指纹 |
| `POST /api/config/llm/probe` | 最小请求的状态、HTTP 分类、tokens、延迟和脱敏错误码 |
| `PUT /api/config/llm` | 部署级更新服务端持久配置，并 reload 下一次调用 |

诊断不得包含 API key、Authorization、完整 Base URL、请求头、prompt、用户正文或
Provider 原始响应。

## 错误边界

应用登录认证与上游 Provider 认证严格分开：

| 场景 | HTTP | 错误码 | 登录状态 |
| --- | ---: | --- | --- |
| 应用 JWT 无效/过期 | 401 | `AUTH_TOKEN_INVALID` / `AUTH_TOKEN_EXPIRED` | 清除并重新登录 |
| Provider 认证失败 | 424 | `PROVIDER_AUTH_FAILED` | 保留 |
| Provider 限流 | 429 | `PROVIDER_RATE_LIMITED` | 保留 |
| Provider 网络/5xx | 502 | `PROVIDER_UNAVAILABLE` | 保留 |
| Provider 输出不可解析 | 502 | `PROVIDER_OUTPUT_INVALID` | 保留 |

前端 `authedFetch` 只有在 HTTP 401 且错误码明确属于 `AUTH_*` 时才清 token 并触发
`auth:expired`。Provider 错误会显示 provider、model 和脱敏来源，提供重新测试与打开
配置入口，并把活动生产任务停在可恢复边界。

## 失败证据与调用计数

Writer、结构化输出修复、局部 Repair 和可选 Planner 的失败调用都先写入对应的
`GenerationTransaction`。事务是调用次数的唯一权威：`planner_calls + writer_calls +
structured_output_repair_count` 等于该 attempt 已发生的 Provider 调用总数，外层 runner
只能读取这个总数，不能再叠加异常对象中的局部计数。

Provider 异常正文是不可信输入。事务日志、长程报告和验收 evidence 只允许固定错误码、
HTTP 分类、阶段、上述三个计数，以及 provider/model/source/config fingerprint 四项脱敏
运行时回执；不得保存 `str(exception)`、上游响应、URL、header、prompt 或正文。失败回执
缺字段、计数不能分解、类别与错误码不匹配，或运行时回执与本阶段 `coding.txt` 配置漂移时，
验收立即 fail closed。

## Stage runner

真实 Stage runner 必须按以下顺序启动：

1. 解析 CLI。
2. 读取 `--provider-file`。
3. 构建并应用强类型 `ProviderRuntimeConfig`。
4. 配置完成后才导入 Writer、long-range runtime 或兼容 `llm_client`。
5. 进入真实生成前再次调用统一 apply/reload 接口。

不得用修改 `coding.txt`、逐个 `importlib.reload()` 模块或重启进程来掩盖导入顺序
问题。

当前统一入口为 `scripts/run_final_long_novel_acceptance.py`，phase 固定为
`offline → probe → g1 → g2 → product → final`。每次调用都显式传入同一只读
`--provider-file`、受保护 user root、只读旧 evidence root 和全新当前 evidence root；
phase 不可复用，也没有 resume/force。完整命令见 [最终验收](./FINAL_ACCEPTANCE.md)。

## 安全检查

每个真实周期都在调用前完成完整离线 Gate。周期结束后，对源码 diff 和全部新 artifact
执行：

- `coding.txt` 中 API key 的 exact scan；
- Base URL 的 exact scan；
- 通用密钥模式 scan；
- 未跟踪敏感文件检查。

发现秘密立即终止，删除含秘密的新 artifact，并把 Gate 标为失败。旧 evidence 保持
只读，不会被复用或覆盖。

完整接口与错误响应见 [API 参考](./API.md)；真实调用顺序、阈值和 evidence 规则见
[最终验收](./FINAL_ACCEPTANCE.md)。
