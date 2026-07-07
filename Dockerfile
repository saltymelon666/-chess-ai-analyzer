FROM python:3.11-slim

# 安装 Stockfish
RUN apt-get update && apt-get install -y --no-install-recommends \
    stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000 8501

# 创建启动脚本
RUN echo '#!/bin/bash\n\
echo "🚀 启动 Stockfish 引擎..."\n\
stockfish --version || echo "⚠️  Stockfish 未找到"\n\
echo "🌐 启动 FastAPI 后端 (端口 8000)..."\n\
uvicorn app.api:app --host 0.0.0.0 --port 8000 &\n\
sleep 2\n\
echo "🎨 启动 Streamlit 前端 (端口 8501)..."\n\
streamlit run app/frontend.py --server.port 8501 --server.address 0.0.0.0\n\
' > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]
