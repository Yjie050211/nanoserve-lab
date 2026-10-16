# 首版验收记录

日期：2026-10-16。平台：Windows，uv 管理的 Python 3.11；独立项目环境。

| 检查 | 结果 |
|---|---|
| `uv sync --locked --python 3.11` | 成功；依赖固定在 uv.lock |
| `uv run --frozen pytest -q` | 62 passed |
| `uv run ruff check .` | 通过 |
| `uv run ruff format --check .` | 通过 |
| `uv run nanoserve smoke --output results` | 6 条合成请求完成，原始事件及报告生成 |
| `uv run nanoserve report results/<run-id>` | 可从事件离线重建同一 summary |
| `uv build` | sdist 与 wheel 构建成功 |
| 独立 uv 环境安装 wheel 后 `nanoserve --help` | 成功 |

测试包括：共享六组指标黄金样例、可靠 Token 域、零/单 Token、混合输出、缺 usage、失败分母和排空窗口；UTF-8 逐字节/CRLF/多行 SSE、空块、工具/reasoning、畸形帧、缺终止、重复终止；闭环并发、超时部分结果、取消；HTTP backend 与 runner 联合验证成功、缺 finish、HTTP 500、连接失败、超时，并确认不重试。

交叉审核后增加终止原因校验：拒绝空字符串和不支持的 finish_reason，并核对 HTTP 路径与离线事件重算的分类一致。共享协议验收中，CPU smoke 6/6 完成，重新生成的 summary 与原结果完全一致。

**未验收**：真实远程 API、真实 vLLM/GPU、显存、Profiler、nano-vLLM、Docker/WSL 与 Kubernetes。MockTransport 是协议正确性证据，fixture 是 CPU 执行链路证据，均不作为模型性能或优化收益。

Windows 中文路径下，Python 3.11 对普通 `.pth` 路径行可能按系统编码解读。使用 Hatch 的 [精确开发模式](https://hatch.pypa.io/latest/config/build/#dev-mode) 和 editables 导入钩子，使默认 `uv run` 可工作；该模式可能影响 IDE 自动发现源码，编辑器可直接配置 `src` 为源码目录。wheel 正常包含源码，不依赖 editable 路径。
