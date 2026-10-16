# 复现与验收

## CPU

```text
uv sync --locked --python 3.11
uv run pytest
uv run ruff check .
uv run nanoserve smoke --output results
uv run nanoserve report results/<run-id>
uv build
```

CPU fixture 的 Token 及延迟为合成值，仅确认执行流程和计算口径。CI 不需要 GPU、Docker 或真实 API。

## HTTP 协议测试与真实服务的区别

协议测试通过 httpx MockTransport 注入真实字节分片，覆盖 SSE 解析、错误分类和完整性检查；它验证 HTTP 客户端路径，但不代表部署过真实 vLLM。真实服务模式不依赖 CUDA 包，只向用户已启动的 endpoint 发请求。

每轮 manifest 记录配置、代码提交、uv.lock 哈希、Python/系统及用户填写的模型与引擎标识。未提供的 revision 为 null，不能称为完全固定的跨环境基线。GPU 信息目前明确为未采集；不推测本机/远程 GPU。

原始产物默认忽略，可能含请求和模型输出。对外展示前检查敏感信息，提交小型已审阅样例和实际环境说明，不上传 API 密钥/私人输入/权重。

## 真实 GPU 后续门槛

先验证 Linux/WSL、驱动、引擎兼容性和容量；固定模型 revision、镜像 digest、精度、chat template、缓存与预热。基线和 profiling 独立运行。若发生超时/取消，先确认服务端无在途请求，无法确认时重启独占实例，再开展下一轮。
