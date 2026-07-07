"""Stockfish 微服务 — FastAPI 后端

提供纯引擎分析 API，供前端或其他服务调用。
不包含 AI 解释功能（由前端服务独立处理）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import settings
from engine import get_analyzer, EngineAnalysis, TopMove


# ============================================================
# 数据模型
# ============================================================

class InputType(str, Enum):
    auto = "auto"
    fen = "fen"
    pgn = "pgn"


class AnalyzeRequest(BaseModel):
    """分析请求"""
    fen: str = Field(
        default="",
        description="FEN 字符串 (直接指定局面时使用)",
    )
    pgn: str = Field(
        default="",
        description="PGN 棋谱内容 (自动解析到终局)",
    )
    pgn_step: Optional[int] = Field(
        default=None,
        description="PGN 走到第几步分析 (None/-1=终局, 0=初始)",
    )
    depth: Optional[int] = Field(
        default=None,
        description="分析深度 (默认 18)",
    )
    multi_pv: int = Field(
        default=3,
        ge=1,
        le=5,
        description="返回的着法数量 (1-5)",
    )


class TopMoveResponse(BaseModel):
    """最佳着法"""
    move: str
    san: str
    score: float = Field(description="引擎评估值 (兵单位, 正值=当前方优势)")
    score_cp: Optional[int] = None
    mate_in: Optional[int] = None
    pv: list[str] = []


class AnalyzeResponse(BaseModel):
    """分析响应"""
    success: bool
    fen: str
    evaluation: str
    depth: int
    nodes: int
    time_ms: int
    top_moves: list[TopMoveResponse]
    board_info: dict


class PositionRequest(BaseModel):
    """局面解析请求"""
    fen: str = ""
    pgn: str = ""
    pgn_step: Optional[int] = None


class PositionResponse(BaseModel):
    """局面解析响应"""
    success: bool
    fen: str
    pgn_info: Optional[dict] = None
    board_info: dict


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    engine: str
    version: str


# ============================================================
# 应用生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时检查引擎，关闭时清理资源"""
    analyzer = get_analyzer()
    ok = analyzer.check_engine()
    version = analyzer.get_version() if ok else "N/A"
    if ok:
        print(f"[OK] Stockfish ready — {version}")
    else:
        print(f"[WARN] Stockfish not found at: {settings.stockfish_path}")
        print("[WARN] 请安装 Stockfish 或设置 STOCKFISH_PATH 环境变量")

    app.state.engine_ready = ok
    app.state.engine_version = version

    yield

    try:
        get_analyzer().shutdown()
        print("[OK] Engine shut down")
    except Exception:
        pass


app = FastAPI(
    title="Stockfish Analysis Service",
    description="Stockfish 18 国际象棋引擎微服务",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — 允许前端跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 辅助函数
# ============================================================

def _resolve_fen(request: PositionRequest) -> tuple[str, Optional[dict]]:
    """从请求中解析 FEN 和 PGN 元信息"""
    analyzer = get_analyzer()
    pgn_meta = None

    # 优先使用 PGN
    if request.pgn.strip():
        fen, board, pgn_meta = analyzer.parse_pgn(request.pgn, step=request.pgn_step)
    elif request.fen.strip():
        board = __import__("chess").Board(request.fen.strip())
        fen = board.fen()
    else:
        raise HTTPException(status_code=400, detail="请提供 fen 或 pgn 参数")

    return fen, pgn_meta


def _score_to_float(move: TopMove, board) -> float:
    """将评分统一转为浮点数 (兵单位)，正值=走棋方优势"""
    turn = board.turn
    if move.mate_in is not None:
        # 将杀评分: 正值为走棋方将杀对方
        return 999.0 if move.mate_in > 0 else -999.0
    if move.centipawn is not None:
        # centipawn 始终是 Stockfish 视角 (白方为正)
        cp = move.centipawn
        if not turn:  # 黑方走棋，反转符号
            cp = -cp
        return cp / 100.0
    return 0.0


def _build_response(analysis: EngineAnalysis, board) -> dict:
    """构建统一的分析响应"""
    top_moves = []
    for m in analysis.best_moves:
        top_moves.append(TopMoveResponse(
            move=m.move,
            san=m.san,
            score=_score_to_float(m, board),
            score_cp=m.centipawn,
            mate_in=m.mate_in,
            pv=m.pv,
        ))

    return {
        "success": True,
        "fen": analysis.fen,
        "evaluation": analysis.evaluation,
        "depth": analysis.depth,
        "nodes": analysis.nodes,
        "time_ms": analysis.time_ms,
        "top_moves": top_moves,
        "board_info": get_analyzer().fen_to_board_info(analysis.fen),
    }


# ============================================================
# API 路由
# ============================================================

@app.get("/", response_model=dict)
async def root():
    """服务信息"""
    return {
        "service": "Stockfish Analysis Service",
        "version": "2.0.0",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    analyzer = get_analyzer()
    engine_ok = analyzer.check_engine()
    version = analyzer.get_version() if engine_ok else "N/A"

    return HealthResponse(
        status="healthy" if engine_ok else "degraded",
        engine="connected" if engine_ok else "disconnected",
        version=version,
    )


@app.post("/api/position", response_model=PositionResponse)
async def preview_position(request: PositionRequest):
    """解析 FEN/PGN 并返回局面信息（不分析）"""
    try:
        fen, pgn_meta = _resolve_fen(request)
        analyzer = get_analyzer()
        return PositionResponse(
            success=True,
            fen=fen,
            pgn_info=pgn_meta,
            board_info=analyzer.fen_to_board_info(fen),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_position(request: AnalyzeRequest):
    """分析局面 — 核心接口

    请求方式:
      1. 发送 FEN: {"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"}
      2. 发送 PGN: {"pgn": "1. e4 e5 2. Nf3 Nc6", "pgn_step": 2}
    """
    try:
        fen, pgn_meta = _resolve_fen(PositionRequest(
            fen=request.fen,
            pgn=request.pgn,
            pgn_step=request.pgn_step,
        ))

        analyzer = get_analyzer()
        board = __import__("chess").Board(fen)

        analysis = await analyzer.analyze(
            fen=fen,
            depth=request.depth,
            multi_pv=request.multi_pv,
        )

        result = _build_response(analysis, board)
        if pgn_meta:
            result["pgn_info"] = pgn_meta

        return AnalyzeResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"分析超时: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@app.post("/api/analyze/batch")
async def analyze_batch(requests: list[AnalyzeRequest]):
    """批量分析多个局面

    请求: [{"fen": "..."}, {"pgn": "...", "pgn_step": 5}, ...]
    返回: 对应的分析结果列表
    """
    import asyncio

    async def analyze_one(req: AnalyzeRequest):
        try:
            fen, _ = _resolve_fen(PositionRequest(
                fen=req.fen,
                pgn=req.pgn,
                pgn_step=req.pgn_step,
            ))
            analyzer = get_analyzer()
            board = __import__("chess").Board(fen)
            analysis = await analyzer.analyze(
                fen=fen,
                depth=req.depth,
                multi_pv=req.multi_pv,
            )
            return _build_response(analysis, board)
        except Exception as e:
            return {"success": False, "error": str(e)}

    results = await asyncio.gather(*[analyze_one(r) for r in requests])
    return {"results": results}


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
    )
