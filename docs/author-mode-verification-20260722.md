# 历史 Author 重构记录（已退役）

这份日期化记录对应早期单节 Author 重构，随后已被整书 ProductionSpec、BookOutline、
StyleProfile、持久化 Job/SSE 和新的恢复边界替代。旧命令、测试计数、Provider 注入方式和
运行结论均不再作为当前证据。

当前操作与验收只参考：

- [最终产品架构](./FINAL_ARCHITECTURE.md)
- [长篇生产手册](./LONG_NOVEL_PRODUCTION.md)
- [Provider 生命周期](./PROVIDER_RUNTIME_LIFECYCLE.md)
- [最终验收](./FINAL_ACCEPTANCE.md)

真实调用统一通过当前 runner 的显式只读 `--provider-file` 使用原始 `coding.txt`；不复制、
不修改、不提交，也不把路径、内容或 secret 写入报告。
