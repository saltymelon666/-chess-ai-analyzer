"""数据模型定义"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InputType(str, Enum):
    auto = "auto"
    fen = "fen"
    pgn = "pgn"


class AnalysisRequest(BaseModel):
    """分析请求"""

    input_type: InputType = Field(default=InputType.fen, description="输入类型: fen 或 pgn (auto 时自动检测)")
    content: str = Field(description="FEN 字符串或 PGN 棋谱内容")
    depth: Optional[int] = Field(default=None, description="Stockfish 分析深度 (默认使用配置值)")
    language: str = Field(default="zh", description="输出语言: zh/en")
    pgn_step: Optional[int] = Field(default=None, description="PGN 走到第几步分析 (None=终局, -1=终局)")


class TopMove(BaseModel):
    """最佳着法"""

    move: str = Field(description="着法 (UCI 格式, 如 e2e4)")
    san: str = Field(description="着法 (标准代数记谱, 如 e4)")
    centipawn: Optional[int] = Field(default=None, description="评估值 (厘兵)")
    mate_in: Optional[int] = Field(default=None, description="将杀步数 (如有)")
    pv: list[str] = Field(default_factory=list, description="主要变化 (SAN 格式)")


class EngineAnalysis(BaseModel):
    """引擎分析结果"""

    fen: str = Field(description="当前局面 FEN")
    best_moves: list[TopMove] = Field(description="最佳着法列表 (Top 3)")
    evaluation: str = Field(description="评估值摘要")
    depth: int = Field(description="分析深度")
    nodes: int = Field(default=0, description="搜索节点数")
    time_ms: int = Field(default=0, description="分析耗时 (毫秒)")


class AIExplanation(BaseModel):
    """AI 自然语言解释"""

    summary: str = Field(description="局面总结")
    strategic_analysis: str = Field(description="战略分析")
    tactical_points: list[str] = Field(default_factory=list, description="战术要点")
    best_move_reasoning: str = Field(description="最佳着法推理")
    plan_suggestion: str = Field(description="计划建议")
    key_ideas: list[str] = Field(default_factory=list, description="关键思路")


class AnalysisResponse(BaseModel):
    """完整分析响应"""

    success: bool = Field(description="是否成功")
    engine: EngineAnalysis = Field(description="引擎分析数据")
    explanation: AIExplanation = Field(description="AI 自然语言解释")
    raw_pv_text: str = Field(default="", description="原始 PV 文本 (供调试)")
    pgn_info: Optional[dict] = Field(default=None, description="PGN 元信息 (仅 PGN 输入时返回)")
    error: Optional[str] = Field(default=None, description="错误信息")
