"""Streamlit 前端界面"""

from __future__ import annotations

import chess
import chess.svg
import base64
import json

import streamlit as st
import httpx

from app.config import settings

# ---- 页面配置 ----
st.set_page_config(
    page_title="AI 国际象棋分析助手",
    page_icon="♟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- 自定义 CSS ----
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #6b7280;
        margin-bottom: 2rem;
    }
    .eval-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px;
        padding: 1.5rem;
        color: white;
        margin-bottom: 1rem;
    }
    .eval-value {
        font-size: 2rem;
        font-weight: 800;
    }
    .move-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.5rem;
    }
    .move-rank {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .move-san {
        font-size: 1.2rem;
        font-weight: 700;
        color: #1e293b;
    }
    .move-score {
        font-size: 0.95rem;
        color: #475569;
    }
    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #374151;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        padding-bottom: 0.3rem;
        border-bottom: 2px solid #e5e7eb;
    }
    .explanation-box {
        background: #f0fdf4;
        border-left: 4px solid #22c55e;
        border-radius: 4px;
        padding: 1rem;
        margin-bottom: 0.8rem;
    }
    .tactical-item {
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
        border-radius: 4px;
        padding: 0.6rem 1rem;
        margin-bottom: 0.4rem;
        font-size: 0.95rem;
    }
    .key-idea {
        background: #eff6ff;
        border-left: 4px solid #3b82f6;
        border-radius: 4px;
        padding: 0.6rem 1rem;
        margin-bottom: 0.4rem;
        font-size: 0.95rem;
    }
    .footer {
        text-align: center;
        color: #9ca3af;
        font-size: 0.8rem;
        margin-top: 3rem;
    }
</style>
""", unsafe_allow_html=True)

# ---- 辅助函数 ----
def render_svg(svg: str) -> str:
    """将 SVG 转为 base64 用于 img 标签"""
    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"


def fen_to_svg(fen: str, flipped: bool = False, size: int = 360) -> str:
    """将 FEN 渲染为棋盘 SVG"""
    board = chess.Board(fen)
    return chess.svg.board(board=board, flipped=flipped, size=size)


def format_eval_value(move) -> str:
    """格式化着法评估值"""
    if move.mate_in is not None:
        return f"M{abs(move.mate_in)}" if move.mate_in > 0 else f"M-{abs(move.mate_in)}"
    if move.centipawn is not None:
        return f"{move.centipawn / 100:+.1f}"
    return "?"


# ---- 主界面 ----
st.markdown('<div class="main-header">♟️ AI 国际象棋分析助手</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">基于 Stockfish 18 引擎 + DeepSeek AI 的智能局面分析</div>',
    unsafe_allow_html=True,
)

# ---- 侧边栏 ----
with st.sidebar:
    st.markdown("### ⚙️ 配置")

    api_url = st.text_input(
        "后端 API 地址",
        value=f"http://localhost:{settings.backend_port}",
        help="FastAPI 后端服务地址",
    )

    input_type = st.radio(
        "输入类型",
        options=["FEN", "PGN"],
        horizontal=True,
        help="FEN: 局面字符串 | PGN: 完整棋谱",
    )

    language = st.radio(
        "输出语言",
        options=["中文", "English"],
        horizontal=True,
    )

    depth = st.slider(
        "分析深度",
        min_value=10,
        max_value=30,
        value=18,
        step=1,
        help="更高的深度 = 更准确但更慢",
    )

    st.markdown("---")
    st.markdown("### 📖 示例")

    col_ex1, col_ex2 = st.columns(2)
    with col_ex1:
        if st.button("开局局面", use_container_width=True):
            st.session_state.example_fen = (
                "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
            )
            st.session_state.input_mode = "FEN"
    with col_ex2:
        if st.button("中局战术", use_container_width=True):
            st.session_state.example_fen = (
                "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
            )
            st.session_state.input_mode = "FEN"

    if st.button("PGN 示例 (名局)", use_container_width=True):
        st.session_state.example_pgn = (
            "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 "
            "7. Bb3 d6 8. c3 O-O 9. h3 Na5 10. Bc2 c5 11. d4 Qc7 12. Nbd2 cxd4 "
            "13. cxd4 Nc6 14. Nb3 a5 15. Be3 a4 16. Nbd2 Bd7 17. Rc1 Qb7 "
            "18. d5 Nb4 19. Bb1 Rfc8"
        )
        st.session_state.input_mode = "PGN"

    st.markdown("---")
    st.markdown("### ℹ️ 关于")
    st.markdown(
        "使用 Stockfish 18 进行精确的引擎分析，"
        "再通过 DeepSeek AI 将分析结果翻译为"
        "普通棋手易于理解的自然语言解释。"
    )

# ---- 输入区域 ----
st.markdown("### 📝 输入局面")

# 从 session_state 恢复示例值
default_fen = st.session_state.get("example_fen", "")
default_pgn = st.session_state.get("example_pgn", "")
default_mode = st.session_state.get("input_mode", "FEN")

if input_type == "FEN":
    fen_input = st.text_area(
        "FEN 字符串",
        value=default_fen or "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        height=80,
        placeholder="输入 FEN 局面字符串...",
        key="fen_input_area",
    )
else:
    fen_input = st.text_area(
        "PGN 棋谱",
        value=default_pgn or "",
        height=150,
        placeholder="粘贴 PGN 格式棋谱...\n例如: 1. e4 e5 2. Nf3 Nc6 ...",
        key="pgn_input_area",
    )

analyze_btn = st.button("🔍 开始分析", type="primary", use_container_width=True)

# ---- 分析逻辑 ----
if analyze_btn and fen_input.strip():
    with st.spinner("🤔 Stockfish 正在分析局面..."):

        # 准备请求
        lang_code = "zh" if language == "中文" else "en"
        itype = "fen" if input_type == "FEN" else "pgn"

        request_data = {
            "input_type": itype,
            "content": fen_input.strip(),
            "depth": depth,
            "language": lang_code,
        }

        try:
            async def fetch_analysis():
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"{api_url}/api/analyze",
                        json=request_data,
                    )
                    response.raise_for_status()
                    return response.json()

            import asyncio
            result = asyncio.run(fetch_analysis())

            if not result.get("success"):
                st.error(f"❌ 分析失败: {result.get('error', '未知错误')}")
            else:
                st.session_state.analysis_result = result
                st.success("✅ 分析完成！")
                st.rerun()

        except httpx.ConnectError:
            st.error(
                f"❌ 无法连接到后端服务 ({api_url})。"
                "请确保 FastAPI 服务已启动。"
            )
        except httpx.HTTPStatusError as e:
            st.error(f"❌ API 请求失败: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            st.error(f"❌ 分析出错: {str(e)}")

# ---- 结果展示 ----
if "analysis_result" in st.session_state:
    result = st.session_state.analysis_result
    engine = result["engine"]
    explanation = result["explanation"]

    # 解析 FEN 用于棋盘渲染
    fen = engine["fen"]
    board = chess.Board(fen)
    board_info = {
        "turn": "白方" if board.turn == chess.WHITE else "黑方",
        "turn_en": "White" if board.turn == chess.WHITE else "Black",
        "fullmove": board.fullmove_number,
    }

    st.markdown("---")

    # 布局: 棋盘 + 评估 | 最佳着法
    col_board, col_moves = st.columns([1, 1])

    with col_board:
        st.markdown("### ♟️ 当前局面")

        # 渲染棋盘
        flipped = board.turn == chess.BLACK
        svg = fen_to_svg(fen, flipped=flipped, size=380)
        st.markdown(
            f'<div style="text-align:center"><img src="{render_svg(svg)}" '
            f'style="max-width:100%;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.1);"></div>',
            unsafe_allow_html=True,
        )

        # 局面信息
        info_col1, info_col2, info_col3 = st.columns(3)
        with info_col1:
            st.metric("轮到", board_info["turn"])
        with info_col2:
            st.metric("回合", board_info["fullmove"])
        with info_col3:
            st.metric("分析深度", f"{engine['depth']} 层")

        # 评估卡片
        st.markdown(f"""
        <div class="eval-card">
            <div style="font-size:0.85rem;opacity:0.9;margin-bottom:0.3rem;">局面评估</div>
            <div class="eval-value">{engine['evaluation']}</div>
            <div style="font-size:0.8rem;opacity:0.8;margin-top:0.3rem;">
                搜索 {engine['nodes']:,} 节点 · 耗时 {engine['time_ms']}ms
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_moves:
        st.markdown("### 🎯 最佳着法 (Top 3)")

        for i, move in enumerate(engine["best_moves"]):
            rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
            score_str = format_eval_value(move)
            score_color = "#22c55e" if (move.centipawn or 0) >= 0 else "#ef4444"

            pv_display = " → ".join(move["pv"][:5]) if move["pv"] else "—"

            st.markdown(f"""
            <div class="move-card">
                <div style="display:flex;align-items:center;justify-content:space-between;">
                    <div>
                        <span class="move-rank">{rank_emoji} 最佳着法</span>
                        <span class="move-san" style="margin-left:8px;">{move['san']}</span>
                        <span style="color:#94a3b8;font-size:0.85rem;margin-left:6px;">({move['move']})</span>
                    </div>
                    <span class="move-score" style="color:{score_color};font-weight:700;">
                        {score_str}
                    </span>
                </div>
                <div style="color:#64748b;font-size:0.85rem;margin-top:0.3rem;">
                    PV: {pv_display}
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ---- AI 自然语言解释 ----
    st.markdown("---")
    st.markdown("### 🤖 AI 分析解读")

    # 摘要
    st.markdown(f"""
    <div class="explanation-box" style="background:#f0f9ff;border-left-color:#3b82f6;">
        <strong>📋 局面总结</strong>
        <p style="margin:0.5rem 0 0 0;font-size:1.05rem;">{explanation['summary']}</p>
    </div>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns(2)

    with col_left:
        # 战略分析
        st.markdown(f"""
        <div class="explanation-box">
            <strong>🧠 战略分析</strong>
            <p style="margin:0.5rem 0 0 0;">{explanation['strategic_analysis']}</p>
        </div>
        """, unsafe_allow_html=True)

        # 战术要点
        if explanation.get("tactical_points"):
            st.markdown('<div class="section-title">⚡ 战术要点</div>', unsafe_allow_html=True)
            for point in explanation["tactical_points"]:
                st.markdown(f'<div class="tactical-item">🔸 {point}</div>', unsafe_allow_html=True)

    with col_right:
        # 最佳着法推理
        st.markdown(f"""
        <div class="explanation-box">
            <strong>💡 最佳着法推理</strong>
            <p style="margin:0.5rem 0 0 0;">{explanation['best_move_reasoning']}</p>
        </div>
        """, unsafe_allow_html=True)

        # 计划建议
        st.markdown(f"""
        <div class="explanation-box" style="background:#fdf2f8;border-left-color:#ec4899;">
            <strong>📋 计划建议</strong>
            <p style="margin:0.5rem 0 0 0;">{explanation['plan_suggestion']}</p>
        </div>
        """, unsafe_allow_html=True)

    # 关键思路
    if explanation.get("key_ideas"):
        st.markdown('<div class="section-title">🔑 关键思路</div>', unsafe_allow_html=True)
        for idea in explanation["key_ideas"]:
            st.markdown(f'<div class="key-idea">✨ {idea}</div>', unsafe_allow_html=True)

    # 原始数据 (可折叠)
    with st.expander("🔧 原始分析数据 (JSON)"):
        st.json(result)

    st.markdown('<div class="footer">AI 国际象棋分析助手 · Stockfish 18 + DeepSeek · v1.0</div>', unsafe_allow_html=True)

else:
    # 初始状态展示
    st.markdown("---")
    st.markdown("### 👋 欢迎使用")

    col_welcome1, col_welcome2 = st.columns(2)

    with col_welcome1:
        st.markdown("""
        #### 🚀 快速开始

        1. 在输入框中粘贴 **FEN** 或 **PGN**
        2. 点击「开始分析」按钮
        3. 等待 AI 返回分析结果

        #### 📋 支持格式

        - **FEN**: 标准国际象棋局面描述
        - **PGN**: 完整棋谱或部分走法记录
        """)

    with col_welcome2:
        st.markdown("""
        #### 🎯 分析内容

        - ♟️ **棋盘可视化** — 直观展示当前局面
        - 📊 **引擎评估** — Stockfish 18 精确分析
        - 🧠 **战略解读** — AI 自然语言解释
        - ⚡ **战术要点** — 关键战术机会
        - 📋 **计划建议** — 实用行棋指导

        #### 🔧 技术栈

        - Stockfish 18 (引擎)
        - DeepSeek API (AI 解释)
        - FastAPI + Streamlit
        """)

# 清除 session state 中的示例值 (避免持久化)
for key in ["example_fen", "example_pgn", "input_mode"]:
    if key in st.session_state and "example" in key:
        # 不在重新运行时自动保留
        pass
