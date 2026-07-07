# ♟️ AI 国际象棋分析助手

基于 **Stockfish 18** 引擎 + **DeepSeek AI** 的智能国际象棋局面分析工具。

将 Stockfish 的精确引擎分析结果，通过 AI 翻译为普通棋手易于理解的自然语言解释。

---

## 🏗️ 技术架构

```
┌──────────────────────────────────────────┐
│            Web 前端 (HTML)               │
│         同一个 Railway 域名              │
└──────────────┬───────────────────────────┘
               │ :8000
       ┌───────▼────────┐
       │  前端服务 (FastAPI)│  ← 静态文件 + AI 解释 + Stockfish 代理
       └───────┬────────┘
               │ :8080 (内部)
       ┌───────▼────────┐
       │ Stockfish 微服务 │  ← 引擎分析
       │  (UCI 子进程)    │
       └────────────────┘
```

| 层级 | 技术 | 端口 |
|------|------|------|
| 前端 | 纯 HTML + CSS + JS | 8000 |
| 后端代理 | FastAPI (静态文件 + 路由转发) | 8000 |
| 引擎服务 | FastAPI + Stockfish 18 | 8080 (内部) |
| AI | DeepSeek API (可选) | 外部 |

---

## 🚀 Railway 一键部署

### 前置准备

1. 安装 [Git](https://git-scm.com/download/win)
2. 注册 [GitHub](https://github.com) 账号
3. 注册 [Railway](https://railway.app) 账号（可用 GitHub 登录）

### 步骤 1: 上传代码到 GitHub

```bash
# 在项目根目录打开终端
git init
git add .
git commit -m "初始提交: 国际象棋 AI 分析助手"

# 在 GitHub 创建新仓库 (如 chess-ai-analyzer)，然后:
git remote add origin https://github.com/你的用户名/chess-ai-analyzer.git
git branch -M main
git push -u origin main
```

### 步骤 2: 在 Railway 部署

1. 打开 [Railway Dashboard](https://railway.app/dashboard)
2. 点击 **New Project** → **Deploy from GitHub repo**
3. 选择你的 `chess-ai-analyzer` 仓库
4. Railway 会自动检测 `railway.json` 和 `Dockerfile.railway`
5. 点击 **Deploy**

### 步骤 3: 配置环境变量 (可选)

部署完成后，在 Railway 项目的 **Variables** 中添加：

| 变量 | 说明 | 必填 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 否（不填则无 AI 解释） |
| `DEEPSEEK_BASE_URL` | API 地址 | 否（默认 https://api.deepseek.com） |
| `DEEPSEEK_MODEL` | 模型名称 | 否（默认 deepseek-chat） |

### 步骤 4: 访问

Railway 会自动生成一个域名，如 `https://chess-ai-analyzer.up.railway.app`，直接打开即可使用。

> 前端输入框默认留空即可，会自动使用当前域名调用后端。

---

## 🐳 本地 Docker 运行

```bash
# 构建
docker build -f Dockerfile.railway -t chess-ai .

# 运行
docker run -p 8000:8000 chess-ai
```

打开 `http://localhost:8000`

---

## 📡 API 接口

所有接口走同一个域名（前端代理）：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web 前端页面 |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/position` | 解析 FEN/PGN 局面 |
| `POST` | `/api/analyze` | 引擎分析 (核心) |
| `POST` | `/api/explain` | AI 自然语言解释 (需 API Key) |

---

## 📁 项目结构

```
.
├── app/
│   ├── api.py              # 前端服务 + Stockfish 代理
│   ├── ai_explainer.py     # DeepSeek AI 解释器
│   ├── config.py           # 配置管理
│   ├── engine.py           # Stockfish 引擎封装 (旧版)
│   ├── models.py           # 数据模型
│   └── static/
│       └── index.html      # Web 前端
├── stockfish-service/
│   ├── api.py              # Stockfish 微服务 (FastAPI)
│   ├── engine.py           # 引擎封装 (新版, 线程池)
│   └── config.py           # 微服务配置
├── Dockerfile.railway      # Railway 部署镜像
├── supervisord.conf        # 多进程管理
├── railway.json            # Railway 部署配置
├── docker-compose.yml      # 本地多容器开发
└── README.md
```

---

## ⚙️ 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 空 |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-chat` |
| `STOCKFISH_PATH` | Stockfish 路径 | `stockfish` |
| `STOCKFISH_DEPTH` | 分析深度 | `18` |
| `STOCKFISH_THREADS` | 线程数 | `2` |
| `STOCKFISH_HASH` | 哈希表 (MB) | `64` |

---

## 📝 License

MIT
