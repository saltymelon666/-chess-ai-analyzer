"""前端服务 — 静态文件 + AI 解释端点 + Stockfish 代理

此服务负责:
1. 提供 Web 前端静态文件
2. 提供 AI 解释 API（调用 DeepSeek）
3. 代理 Stockfish 请求到内部微服务 (127.0.0.1:8080)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from typing import Optional

from app.config import settings
from app.ai_explainer import get_explainer

# Stockfish 微服务地址 (同容器内部)
STOCKFISH_SERVICE_URL = os.environ.get("STOCKFISH_SERVICE_URL", "http://127.0.0.1:8080")


# ---------- 请求模型 ----------

class ExplainRequest(BaseModel):
    """AI 解释请求 — 由前端传入 Stockfish 分析结果"""
    fen: str = Field(description="当前局面 FEN")
    engine: dict = Field(description="Stockfish 引擎分析结果 (top_moves, evaluation 等)")
    board_info: dict = Field(default_factory=dict, description="局面基本信息")
    language: str = Field(default="zh", description="输出语言: zh/en")


# ---------- 应用 ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    api_ok = bool(settings.deepseek_api_key)
    if api_ok:
        print(f"[OK] DeepSeek API configured (model: {settings.deepseek_model})")
    else:
        print("[WARN] DEEPSEEK_API_KEY not set — AI explanation disabled")

    yield

    try:
        await get_explainer().close()
        print("[OK] Resources cleaned up")
    except Exception:
        pass


app = FastAPI(
    title="Chess AI Frontend Service",
    description="国际象棋 Web 前端 + DeepSeek AI 解释",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
ASSETS_DIR = STATIC_DIR / "assets"
ASSETS_DIR.mkdir(exist_ok=True)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/")
async def root():
    """Web 前端"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"service": "Chess AI Frontend", "version": "2.0.0"}


@app.get("/demo")
async def web_demo():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.json")
async def manifest():
    manifest_path = STATIC_DIR / "manifest.json"
    if manifest_path.exists():
        return FileResponse(manifest_path, media_type="application/json")
    return {}


@app.get("/sw.js")
async def service_worker():
    sw_path = STATIC_DIR / "sw.js"
    if sw_path.exists():
        return FileResponse(sw_path, media_type="application/javascript")
    return Response(status_code=404)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "ai_api": "configured" if settings.deepseek_api_key else "not_configured",
    }


@app.post("/api/explain")
async def explain_position(request: ExplainRequest):
    """AI 自然语言解释 — 接收引擎分析结果，返回中文/英文解读"""
    try:
        explainer = get_explainer()

        # 将新 API 格式转为 AI 解释器需要的格式
        from app.models import EngineAnalysis, TopMove

        top_moves = []
        for m in request.engine.get("top_moves", request.engine.get("best_moves", [])):
            top_moves.append(TopMove(
                move=m.get("move", ""),
                san=m.get("san", ""),
                centipawn=m.get("score_cp"),
                mate_in=m.get("mate_in"),
                pv=m.get("pv", []),
            ))

        engine_analysis = EngineAnalysis(
            fen=request.fen,
            best_moves=top_moves,
            evaluation=request.engine.get("evaluation", ""),
            depth=request.engine.get("depth", 0),
            nodes=request.engine.get("nodes", 0),
            time_ms=request.engine.get("time_ms", 0),
        )

        board_info = request.board_info or {
            "turn": "白方",
            "fullmove_number": 1,
            "piece_count": {"white": 16, "black": 16},
            "is_check": False,
            "is_checkmate": False,
            "is_stalemate": False,
        }

        explanation = await explainer.explain(
            engine_analysis=engine_analysis,
            board_info=board_info,
            language=request.language,
        )

        return explanation.model_dump()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 解释失败: {str(e)}")


# ---------- Stockfish 代理路由 ----------

SF_PROXY_PATHS = ["/api/position", "/api/analyze", "/api/analyze/batch", "/api/health-sf"]


async def _proxy_to_stockfish(request: Request):
    """将请求转发到同容器的 Stockfish 微服务"""
    path = request.url.path
    # 映射: /api/health-sf -> /health (Stockfish 服务的健康检查)
    if path == "/api/health-sf":
        path = "/health"

    body = await request.body()
    headers = dict(request.headers)
    # 移除 hop-by-hop headers
    for h in ["host", "transfer-encoding", "connection"]:
        headers.pop(h, None)

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.request(
            method=request.method,
            url=f"{STOCKFISH_SERVICE_URL}{path}",
            headers=headers,
            content=body,
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
        )


# 注册代理路由
for sf_path in SF_PROXY_PATHS:
    app.add_api_route(
        sf_path,
        _proxy_to_stockfish,
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.api:app",
        host="0.0.0.0",
        port=settings.backend_port,
        reload=True,
    )
