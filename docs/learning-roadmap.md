# 尚未实施的引擎学习与 Profiling

本页为后续步骤，不是已完成能力。

1. 固定 nano-vLLM 上游提交、依赖组合和许可证；走读 tokenization、Prefill/Decode、scheduler、KV Cache 生命周期。
2. 在隔离 Linux/GPU 环境先运行未修改版本，再增加小范围时间/状态插桩；保存自己的补丁、离线命令、原始结果与解释。
3. 离线批吞吐和在线客户端 TTFT 分报告，不把 step 时长改名为网络 TTFT。
4. 采用 vLLM 官方支持的 Profiler 路径独立采集短窗口。只有实际采到服务端 GPU trace 才分析 Kernel；客户端 Python trace 不能证明 GPU 瓶颈。
5. GPU 显存采样应区分设备/进程显存与引擎 KV Cache 指标，记录采样间隔和来源。
6. Kubernetes 扩展后置：先实际验证 CPU fixture Deployment/Service/Job/探针/requests/limits，不宣称具备 Device Plugin、RDMA 或多机调度经验。
