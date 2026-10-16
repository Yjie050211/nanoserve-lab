# 指标与协议口径

- 计时使用 `time.monotonic()`。事件时间为发送后秒数，run 内发送/结束时间为同一单调时钟原点的秒数；UTC 只用于日志关联。
- `first_text_delta_s`（客户端 text TTFT）不包括 role、空 content、usage、工具名称/参数、reasoning；网络批量到达会影响观察。
- `text_tpot_proxy_s = (last_text_delta_s - first_text_delta_s)/(completion_tokens - 1)`。单 choice、完整协议、有文本、无工具/reasoning/refusal、服务 usage 可靠且显式确认同一 text Token 域、n>1 才计算。单个 chunk 可以包含多个 Token，代理可能为 0；这不是精确 Token ITL，也不是服务端 Decode 时间。
- `usage_token_scope: unknown` 默认不输出 TPOT。Token 计数缺失时为 null；不把 SSE chunk 数视为 Token 数。
- 成功需要单次 finish_reason、单次 `[DONE]`，无协议/HTTP/超时错误；200 后断流依然失败。
- 支持的 finish_reason 为 `stop`、`length`、`tool_calls`、`content_filter`、`function_call`；空串、非字符串和未知值按协议错误处理，HTTP 与离线重算使用同一校验。这里的成功表示完整响应，不代表回答质量或任务成功。
- 保留失败和部分输出；HTTP 500 不自动归因于 OOM。没有服务日志或设备证据时只记录观察到的 HTTP 错误。
- 失败率分母为所有实际进入 backend 的请求；排队后取消、配置拒绝不计已发。`unsent_requests` 单列。
- 窗口为首条已发请求到最后一条已发请求客户端结束，包含排空。客户端终止不能证明服务端停止生成，`server_idle_verified=false`。超时/取消后的 run 不适合未经服务重置而直接与下一轮比较。
- 成功请求吞吐与成功输出 Token 吞吐分开；任一成功请求缺 usage 时，整体输出 Token 吞吐为 null，另给已知 Token 小计与覆盖样本数。
- p50/p95/p99 使用 `(n-1)*q` 线性插值，始终给样本数；小样本分位数不能说明稳定性。
- `execution_mode=fixture|real` 与 `workload_origin=synthetic` 分开。真实 HTTP 上的合成请求是服务测量，不是对真实 Agent 分布的观测。

`requests.jsonl` 含原始规范化事件，可用 `nanoserve report` 从这些事件重算。规范化事件保留文本/工具参数/reasoning/usage；未保存 Authorization、完整 HTTP 头或网络字节，因此不宣称可以重建网络逐字节流。
