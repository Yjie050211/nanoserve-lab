# NanoServe-Lab

**Reproducible LLM serving benchmarks, nano-vLLM learning experiments, and performance diagnostics.**

一个以原始事件为依据的 LLM 推理服务评测实验室。当前实现普通合成负载、有界闭环并发、流式 HTTP 客户端、指标重算和 CPU fixture；不是自主实现的推理引擎。

## 当前可运行能力

- 独立 CPU fixture 与 OpenAI/vLLM 兼容单 choice SSE backend，共用 runner 与指标计算。
- 正确处理 UTF-8/CRLF 分片、role/usage 空块、工具参数、reasoning、断流、超时和 HTTP 错误。
- 保存 manifest、确定性请求、逐请求原始事件、结果、summary 与 Markdown 报告。
- TTFT 为客户端首个非空文本观察；TPOT 仅在完整纯文本流、可靠同域 usage、输出 Token > 1 时给出代理值。
- 所有已发请求进入失败率分母；吞吐窗口包含客户端排空，缺 usage 不补造 Token 数。

**尚未验收：真实 GPU/vLLM 性能、显存采样、Profiler、nano-vLLM 插桩、Kubernetes。** CPU fixture 只验证代码正确性，不能用于性能结论。

## 快速开始

需要 Python 3.11 与 [uv](https://docs.astral.sh/uv/)。不需要 GPU、Docker、模型权重。

```powershell
uv sync --locked --python 3.11
uv run nanoserve smoke --output results
uv run nanoserve report results/<run-id>
uv run pytest
uv run ruff check .
```

运行目录包含：

```text
manifest.json        # 运行模式、配置、版本/锁文件哈希、硬件可知信息
workload.jsonl       # 实际计划发出的请求 body
requests.jsonl       # 每条已发请求的原始事件、结果、错误、时间
warmup_requests.jsonl # 可选，预热独立记录、不纳入测量
summary.json         # 可离线重建的指标
report.md            # 含来源与局限的报告
```

## 连接已有真实服务

本工具不安装或启动 vLLM，不下载模型。准备好独占的兼容服务后，复制并填写 `configs/http_baseline.yaml` 的模型、版本和缓存状态：

```powershell
# 有鉴权时仅通过环境变量提供；不放入配置或 Git。
$env:NANOSERVE_API_KEY = "your-key"
uv run nanoserve run --config configs/http_baseline.yaml --output results
```

默认 `usage_token_scope: unknown`，保留 usage 但不计算 text TPOT。只有确认所选模型的服务 usage 覆盖可见纯文本、无隐藏 reasoning 等其他输出时才能显式设为 `text`。HTTP 200 不等于成功：需要合法单 choice 流、finish_reason 和 `[DONE]`。不做自动重试。

`prompt_words` 是合成单词数，**不是输入 Token 数**；真实 prompt Token 由服务返回记录。首次真实实验先做容量测试，再逐档增加输入/输出长度和并发。跨配置比较须自行固定模型、引擎、GPU、缓存和预热条件；当前不宣称服务端已排空。

## 架构

```text
validated YAML → deterministic workload → bounded workers → fixture / HTTP SSE
                                                        ↓
                 offline report ← pure metric reduction ← durable request events
```

边界：普通负载属于本仓库；Agent 任务执行属于 agent-harness-lab；多轮轨迹和缓存实验矩阵属于 agentserve-bench。本仓库不依赖另两个仓库安装。

更多说明：[指标](docs/metrics.md)、[复现](docs/reproduction.md)、[架构决策](docs/architecture.md)、[nano-vLLM 与 Profiling 后续路线](docs/learning-roadmap.md)。

本次实际检查见 [首版验收记录](docs/validation.md)；远程 CI 需推送后单独查看运行结果。

## 上游与许可

原创评测代码采用 MIT。参考 [vLLM](https://github.com/vllm-project/vllm) 的兼容 API 与 [nano-vLLM](https://github.com/GeeeekExplorer/nano-vllm) 的学习方向；当前未复制、修改或运行上游引擎代码。以后保存上游补丁时将固定提交并保留其许可。
