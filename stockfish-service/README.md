# Stockfish Analysis Service

基于 FastAPI + Stockfish 18 的国际象棋引擎微服务。

## 项目结构

```
stockfish-service/
├── api.py              # FastAPI 应用入口
├── engine.py           # Stockfish 引擎封装 (UCI 协议)
├── config.py           # 配置管理
├── requirements.txt    # Python 依赖
├── Dockerfile          # Docker 镜像构建
├── docker-compose.yml  # 本地测试编排
├── test_api.py         # API 测试脚本
├── .env.example        # 环境变量模板
└── README.md
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| POST | `/api/position` | 解析 FEN/PGN 返回局面信息 |
| POST | `/api/analyze` | 分析局面（核心接口） |
| POST | `/api/analyze/batch` | 批量分析多个局面 |

### POST `/api/analyze` 请求示例

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "depth": 20,
  "multi_pv": 3
}
```

```json
{
  "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bb5",
  "pgn_step": 3,
  "depth": 18
}
```

### 响应示例

```json
{
  "success": true,
  "fen": "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
  "evaluation": "黑方劣势 (-0.3)",
  "depth": 18,
  "nodes": 2456789,
  "time_ms": 850,
  "top_moves": [
    {
      "move": "a7a6",
      "san": "a6",
      "score": -0.3,
      "score_cp": 30,
      "mate_in": null,
      "pv": ["a6", "Ba4", "Nf6", "O-O", "Be7"]
    }
  ],
  "board_info": {
    "turn": "黑方",
    "fullmove_number": 3,
    "is_check": false,
    "is_checkmate": false,
    "is_stalemate": false
  }
}
```

## 本地测试

### 方式 1: 直接运行 (需要本地安装 Stockfish)

```bash
# 安装 Stockfish (macOS)
brew install stockfish

# 安装 Stockfish (Ubuntu/Debian)
sudo apt-get install stockfish

# 安装 Python 依赖
pip install -r requirements.txt

# 启动服务
python api.py

# 另开终端运行测试
python test_api.py
```

### 方式 2: Docker 运行

```bash
# 构建并启动
docker compose up -d --build

# 查看日志
docker compose logs -f

# 运行测试
python test_api.py

# 停止
docker compose down
```

### 方式 3: 纯 Docker 命令

```bash
docker build -t stockfish-service .
docker run -p 8080:8080 stockfish-service
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STOCKFISH_PATH` | `stockfish` | Stockfish 可执行文件路径 |
| `STOCKFISH_DEPTH` | `18` | 分析深度 |
| `STOCKFISH_THREADS` | `2` | 线程数 |
| `STOCKFISH_HASH` | `64` | 哈希表大小 (MB) |
| `PORT` | `8080` | 服务端口 |

## 部署到 Railway/Render

此服务设计为独立部署到 Railway、Render 或 Fly.io 等平台：

1. 推送代码到 GitHub
2. 在 Railway 中导入仓库
3. Railway 自动识别 Dockerfile 并构建
4. 设置环境变量
5. 获取公网 URL，如 `https://stockfish-service.up.railway.app`
