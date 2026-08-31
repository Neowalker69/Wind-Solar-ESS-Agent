# wind-solar-ESS-Agent

<p align="center">
  <img src="digital-twin-agent-demo.gif" alt="Digital Twin Agent Demo" width="900">
</p>

面向风、光、储工业场站的 AI Agent Harness 个人作品项目。系统将模型调用、RAG、工具执行、工作流和数字孪生界面组合成一个可本地部署的智能体工作台。

> [!IMPORTANT]
> 本项目仅用于个人展示、学习和本地演示，不是生产安全基线，也不要直接连接真实工业控制系统。

支持的 LLM Provider：

- DeepSeek
- 阿里云百炼

本开源版不包含 Mock Provider，也不包含 Embedding/Reranker 模型权重。

## 项目架构

![Agent Harness 架构摘要图](architecture-summary.png)

核心组件包括 API Gateway、Agent Runtime、工作流、RAG、Tool Gateway、PostgreSQL、Redis，以及可选的 Harness Control 数字孪生前端。

## 快速开始

### 1. 准备环境

- Docker Engine 与 Docker Compose v2
- DeepSeek 或百炼 API Key
- 可选：Python 3.11+、uv、Node.js 22

```bash
git clone https://github.com/Neowalker69/Wind-Solar-ESS-Agent.git
cd Wind-Solar-ESS-Agent
cp .env.example .env
```

### 2. 配置模型与密钥

编辑 `.env`，选择一个 Provider。

DeepSeek：

```env
AGENT_HARNESS_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=<your-api-key>
DEEPSEEK_MODEL=deepseek-v4-flash
```

阿里云百炼：

```env
AGENT_HARNESS_MODEL_PROVIDER=bailian
DASHSCOPE_API_KEY=<your-api-key>
BAILIAN_MODEL=qwen3.7-plus
```

使用 `openssl rand -hex 32` 分别生成独立值并填写：

```env
HARNESS_DB_PASSWORD=<database-password>
CONTROL_RUNTIME_SHARED_SECRET=<runtime-secret>
TOOL_GATEWAY_JWT_SECRET=<tool-gateway-secret>
JWT_SECRET=<control-jwt-secret>
```

本地演示账号默认为 `admin / admin123`。该密码只适用于服务绑定 `127.0.0.1` 的本机演示；对外开放前必须修改。

### 3. 启动后端

```bash
docker compose config
docker compose up -d --build
docker compose ps
```

检查服务：

```bash
curl http://127.0.0.1:8000/api/v1/gateway/health
```

- API 文档：<http://127.0.0.1:8000/docs>
- API Gateway：<http://127.0.0.1:8000>

### 4. 启动前端工作台

```bash
docker compose --profile frontend up -d --build harness-control
```

浏览器访问 <http://127.0.0.1:3000>。

其他可选服务：

```bash
docker compose --profile workers up -d
docker compose --profile tool-gateway up -d
```

## CLI 运行

不使用 Docker 时，可在项目根目录安装 Python 依赖：

```bash
python -m venv .venv
source .venv/bin/activate       # Linux / macOS / WSL
# PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

使用 uv：

```bash
uv venv
source .venv/bin/activate
uv sync --frozen --no-dev
```

启动 API Gateway：

```bash
uv run --env-file .env python -m apps.api_gateway.daemon run \
  --host 127.0.0.1 --port 8000
```

百炼未配置 Key 时，CLI 会隐藏输入并保存到 `~/.agent-harness/config.json`；DeepSeek 请通过 `.env` 或密钥文件配置。已完成非交互式配置时可追加 `--no-model-prompt`。

## RAG 与本地模型

`rag_dataset_20docs/` 内含 20 份合成演示文档，不对应任何真实企业、设备或场站，也不能作为真实运维依据。

模型权重不会进入 Git 仓库。按需从 ModelScope 下载到被忽略的 `models/` 目录：

| 用途 | 推荐模型 | 本地目录 |
| --- | --- | --- |
| Embedding | `Qwen/Qwen3-Embedding-0.6B` | `models/embedding/Qwen3-Embedding-0.6B` |
| Reranker | `AI-ModelScope/bge-reranker-v2-m3` | `models/reranker/bge-reranker-v2-m3` |

```bash
pip install modelscope
modelscope download --model Qwen/Qwen3-Embedding-0.6B \
  --local_dir ./models/embedding/Qwen3-Embedding-0.6B
modelscope download --model AI-ModelScope/bge-reranker-v2-m3 \
  --local_dir ./models/reranker/bge-reranker-v2-m3
```

启用仓库内保留的本地 Reranker 部署脚本：

```env
AGENT_HARNESS_RAG_ENABLED=true
AGENT_HARNESS_RAG_RERANKER_ENABLED=true
RAG_RERANKER_BASE_URL=http://harness-reranker:80
```

```bash
docker compose --profile rag-local up -d --build harness-reranker
```

首次启动会下载模型。Embedding、Reranker 和 TEI 的其他参数见 `.env.example`。

## 前端开发

```bash
cd apps/harness-control
npm install
npm test
npm run typecheck
npm run build
```

当前验证基线为 Node.js 22、Next.js 15.5.20 和 React 19.1.0，具体版本以 `package.json` 和 `package-lock.json` 为准。

## 后端验证

```bash
uv sync --frozen --dev
uv run pytest -q
docker compose config
docker build -t agent-harness-llm-providers:local .
```

## 常见问题

- `model_provider_api_key_missing`：检查对应 API Key 或 `_FILE` 配置。
- `model_provider_unsupported:mock`：改用 `deepseek` 或 `bailian`。
- 端口冲突：在 `.env` 中修改 `AGENT_HARNESS_PORT` 或 `HARNESS_CONTROL_PORT`。
- 模型请求失败：检查模型名称、Base URL、账户权限和容器网络。

## 安全与数据声明

- 不要提交 `.env`、API Key、数据库密码、日志或真实工业数据。
- 默认端口只绑定 `127.0.0.1`；公网部署前需补齐 TLS、认证、访问控制、限流和审计。
- 优先使用 Docker Secrets、云 Secret Manager 或 `_FILE` 配置传入密钥。
- 合成数据说明见 [`rag_dataset_20docs/README.md`](rag_dataset_20docs/README.md)。
- 安全边界与漏洞报告方式见 [`SECURITY.md`](SECURITY.md)。

## 许可证

源代码采用 [MIT License](LICENSE)。原创视觉资产使用时请注明出处，详见 [`ASSET-ATTRIBUTION.md`](ASSET-ATTRIBUTION.md)；第三方资产声明见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

提交 Issue 或 Pull Request 前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
