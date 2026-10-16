# 架构与 ADR

1. **独立仓库，无共享 SDK**：本项目自身安装即可运行，黄金指标 fixture 约束与 AgentServe 的语义一致性。
2. **在线与离线分离**：HTTP 流式计时只测客户端观察；nano-vLLM 离线 generate/step 不能直接产出同口径 TTFT。
3. **少量 worker 而非每请求一个 Task**：worker 数不超过并发，闭环完成一条再取下一条，避免大负载预先创建大量 Task。
4. **事件优先**：每条完成/失败/取消请求及时落盘，报告从事件重算；不自动重试，不覆盖失败。
5. **没有数值就保留 null**：缺 usage、未确认 Token 域、未采 GPU 时不制造估计值。
6. **CPU/GPU 分层**：fixture 和协议测试为首版验收；真实引擎和性能结论另行验收。

模块：`schemas` 配置/记录；`workloads` 确定性请求；`backends` SSE 归一化；`runner` 闭环调度；`metrics` 纯函数计算；`reports` 产物/重算；`cli` 命令入口。
