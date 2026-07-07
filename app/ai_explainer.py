"""DeepSeek API 分析模块 — Milestone 2: AI Explain
将 Stockfish 分析翻译为自然语言解释"""

from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from app.config import settings
from app.models import EngineAnalysis, AIExplanation, TopMove


SYSTEM_PROMPT_ZH = """你是一位国际象棋大师级别的教练，擅长用通俗易懂的语言向普通棋手解释复杂的局面分析。

你的任务是将 Stockfish 引擎的分析数据翻译成自然语言解释。请遵循以下原则：
1. 使用比喻和生活化的语言解释战略概念
2. 指出关键战术动机和计划思路
3. 解释为什么最佳着法是好的，而不只是罗列变化
4. 给出实用的计划建议
5. 避免使用过于专业的术语，如果必须使用，请附带解释

请严格按照 JSON 格式返回，不要包含任何其他内容。"""

SYSTEM_PROMPT_EN = """You are a chess master-level coach, skilled at explaining complex positional analysis to amateur players in plain language.

Your task is to translate Stockfish engine analysis data into natural language explanations. Follow these principles:
1. Use analogies and accessible language to explain strategic concepts
2. Point out key tactical motifs and planning ideas
3. Explain WHY the best move is good, not just list variations
4. Provide practical plan suggestions
5. Avoid overly technical jargon; when necessary, explain the terms

Return strictly in JSON format with no additional content."""


class DeepSeekExplainer:
    """DeepSeek AI 解释器"""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.deepseek_base_url,
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    def _build_user_prompt(
        self,
        engine_analysis: EngineAnalysis,
        board_info: dict,
        language: str,
    ) -> str:
        """构建用户提示词"""
        top_moves_text = []
        for i, move in enumerate(engine_analysis.best_moves, 1):
            pv_line = " → ".join(move.pv[:5]) if move.pv else "无"
            if move.mate_in is not None:
                score_str = f"将杀步数: {move.mate_in}"
            elif move.centipawn is not None:
                score_str = f"评估: {move.centipawn / 100:.1f} 分"
            else:
                score_str = "评估: 未知"

            top_moves_text.append(
                f"第{i}佳着法: {move.san} ({move.move}) | {score_str}\n"
                f"  主要变化: {pv_line}"
            )

        if language == "zh":
            prompt = f"""请分析以下国际象棋局面：

【局面信息】
- FEN: {engine_analysis.fen}
- 轮到: {board_info['turn']}
- 回合数: 第 {board_info['fullmove_number']} 回合
- 子力对比: 白方 {board_info['piece_count']['white']} 子 vs 黑方 {board_info['piece_count']['black']} 子
- 是否被将军: {'是' if board_info['is_check'] else '否'}
- 是否将杀: {'是' if board_info['is_checkmate'] else '否'}
- 是否逼和: {'是' if board_info['is_stalemate'] else '否'}

【引擎分析】
- 整体评估: {engine_analysis.evaluation}
- 分析深度: {engine_analysis.depth} 层
- Top 着法:
{chr(10).join(top_moves_text)}

请从以下几个角度分析，并返回 JSON：
1. summary: 一句话概括当前局面 (20字以内)
2. strategic_analysis: 战略层面分析 (100-150字)，包括兵型结构、子力配置、空间优势等
3. tactical_points: 当前局面的战术要点列表 (3-5条)
4. best_move_reasoning: 最佳着法的推理过程 (80-120字)
5. plan_suggestion: 给当前走棋方的计划建议 (80-120字)
6. key_ideas: 当前局面下的关键思路 (2-3条)

请直接返回 JSON，不要包含 markdown 代码块标记。"""
        else:
            prompt = f"""Please analyze the following chess position:

【Position Info】
- FEN: {engine_analysis.fen}
- Side to move: {board_info['turn']}
- Move number: {board_info['fullmove_number']}
- Material: White {board_info['piece_count']['white']} pieces vs Black {board_info['piece_count']['black']} pieces
- In check: {'Yes' if board_info['is_check'] else 'No'}
- Checkmate: {'Yes' if board_info['is_checkmate'] else 'No'}
- Stalemate: {'Yes' if board_info['is_stalemate'] else 'No'}

【Engine Analysis】
- Evaluation: {engine_analysis.evaluation}
- Depth: {engine_analysis.depth}
- Top moves:
{chr(10).join(top_moves_text)}

Please analyze from the following angles and return JSON:
1. summary: One-line position summary (within 15 words)
2. strategic_analysis: Strategic analysis (80-120 words), covering pawn structure, piece configuration, space advantage
3. tactical_points: Key tactical points (3-5 items)
4. best_move_reasoning: Reasoning for the best move (60-100 words)
5. plan_suggestion: Plan suggestion for the side to move (60-100 words)
6. key_ideas: Key ideas in this position (2-3 items)

Return raw JSON directly, no markdown code blocks."""

        return prompt

    async def explain(
        self,
        engine_analysis: EngineAnalysis,
        board_info: dict,
        language: str = "zh",
    ) -> AIExplanation:
        """调用 DeepSeek API 生成自然语言解释"""
        if not settings.deepseek_api_key:
            raise ValueError("请设置 DEEPSEEK_API_KEY 环境变量")

        client = await self._get_client()
        system_prompt = SYSTEM_PROMPT_ZH if language == "zh" else SYSTEM_PROMPT_EN
        user_prompt = self._build_user_prompt(engine_analysis, board_info, language)

        try:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2048,
                },
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"].strip()

            # 清理可能的 markdown 代码块
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

            parsed = json.loads(content)

            return AIExplanation(
                summary=parsed.get("summary", ""),
                strategic_analysis=parsed.get("strategic_analysis", ""),
                tactical_points=parsed.get("tactical_points", []),
                best_move_reasoning=parsed.get("best_move_reasoning", ""),
                plan_suggestion=parsed.get("plan_suggestion", ""),
                key_ideas=parsed.get("key_ideas", []),
            )

        except json.JSONDecodeError as e:
            # 如果 JSON 解析失败，返回包含原始内容的降级响应
            return AIExplanation(
                summary="AI 分析返回格式异常",
                strategic_analysis=f"原始回复: {content[:200]}...",
                tactical_points=[],
                best_move_reasoning="请重试",
                plan_suggestion="请重试",
                key_ideas=[],
            )
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"DeepSeek API 请求失败 (HTTP {e.response.status_code}): {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"DeepSeek API 调用异常: {e}")

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# 全局单例
_explainer: Optional[DeepSeekExplainer] = None


def get_explainer() -> DeepSeekExplainer:
    global _explainer
    if _explainer is None:
        _explainer = DeepSeekExplainer()
    return _explainer


# ============================================================
# Milestone 2 独立测试: python -m app.ai_explainer
# 需要先有引擎分析数据，所以这里用 Mock 数据
# ============================================================
if __name__ == "__main__":
    import asyncio
    from app.models import TopMove, EngineAnalysis

    print("=" * 60)
    print("  Milestone 2: DeepSeek AI Explain 测试")
    print("=" * 60)

    # 构造 Mock 引擎分析数据 (意大利开局)
    mock_engine = EngineAnalysis(
        fen="r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
        best_moves=[
            TopMove(
                move="e1g1", san="O-O",
                centipawn=35,
                mate_in=None,
                pv=["O-O", "Nf6", "d3", "Be7", "Nc3"],
            ),
            TopMove(
                move="d2d4", san="d4",
                centipawn=20,
                mate_in=None,
                pv=["d4", "exd4", "O-O", "Nf6", "e5"],
            ),
            TopMove(
                move="b1c3", san="Nc3",
                centipawn=15,
                mate_in=None,
                pv=["Nc3", "Nf6", "d3", "Be7", "O-O"],
            ),
        ],
        evaluation="白方略优 (+0.4)",
        depth=18,
        nodes=1234567,
        time_ms=850,
    )

    board_info = {
        "turn": "白方",
        "fullmove_number": 4,
        "piece_count": {"white": 15, "black": 14},
        "is_check": False,
        "is_checkmate": False,
        "is_stalemate": False,
    }

    explainer = DeepSeekExplainer()

    async def test():
        try:
            result = await explainer.explain(
                engine_analysis=mock_engine,
                board_info=board_info,
                language="zh",
            )
            print(f"\n📋 局面总结: {result.summary}")
            print(f"🧠 战略分析: {result.strategic_analysis}")
            print(f"⚡ 战术要点: {result.tactical_points}")
            print(f"💡 最佳着法推理: {result.best_move_reasoning}")
            print(f"📋 计划建议: {result.plan_suggestion}")
            print(f"🔑 关键思路: {result.key_ideas}")
            print(f"\n{'=' * 60}")
            print("  ✅ Milestone 2 测试通过!")
            print("=" * 60)
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
        finally:
            await explainer.close()

    asyncio.run(test())
