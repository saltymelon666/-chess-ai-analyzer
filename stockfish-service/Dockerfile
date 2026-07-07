FROM python:3.11-slim

# 安装 Stockfish 18
# Debian Bookworm 仓库自带 Stockfish 16, 我们用官方二进制安装最新版
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 下载 Stockfish 18 官方 Linux x64 二进制
# 如果网络不可达，可降级为 apt 仓库版本: apt-get install -y stockfish
RUN wget -q https://github.com/official-stockfish/Stockfish/releases/download/sf18/stockfish-ubuntu-x86-64-avx2.tar \
    -O /tmp/sf.tar && \
    mkdir -p /tmp/sf && tar -xf /tmp/sf.tar -C /tmp/sf && \
    mv /tmp/sf/stockfish/stockfish-ubuntu-x86-64-avx2 /usr/local/bin/stockfish && \
    chmod +x /usr/local/bin/stockfish && \
    rm -rf /tmp/sf.tar /tmp/sf

# 验证安装
RUN stockfish --version || \
    (echo "Stockfish 18 download failed, falling back to apt..." && \
     apt-get update && apt-get install -y stockfish && rm -rf /var/lib/apt/lists/*)

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY config.py .
COPY engine.py .
COPY api.py .

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# 启动服务
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
