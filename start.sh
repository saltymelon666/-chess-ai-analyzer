#!/bin/bash

echo "============================================"
echo "  AI 国际象棋分析助手 - 启动脚本"
echo "============================================"
echo ""

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "[!] 未找到 .env 文件，正在从 .env.example 创建..."
    cp .env.example .env
    echo "[!] 请编辑 .env 文件，填入你的 DEEPSEEK_API_KEY"
    echo ""
fi

# 检查 Stockfish
if ! command -v stockfish &> /dev/null; then
    echo "[!] 未在 PATH 中找到 Stockfish"
    echo "[!] 请确保 Stockfish 18 已安装并在 PATH 中"
    echo "[!] 或者设置 STOCKFISH_PATH 环境变量"
    echo ""
fi

# 安装依赖
echo "[*] 安装 Python 依赖..."
pip install -r requirements.txt -q
echo ""

# 启动后端
echo "[*] 启动 FastAPI 后端 (端口 8000)..."
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
sleep 2

# 启动前端
echo "[*] 启动 Streamlit 前端 (端口 8501)..."
streamlit run app/frontend.py --server.port 8501 &
FRONTEND_PID=$!

echo ""
echo "============================================"
echo "  启动完成！"
echo "  后端: http://localhost:8000"
echo "  前端: http://localhost:8501"
echo "  API 文档: http://localhost:8000/docs"
echo "============================================"
echo ""

# 等待进程
wait
