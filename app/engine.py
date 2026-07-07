"""Stockfish 引擎封装模块 — Milestone 1: Engine

使用 subprocess 直接调用 Stockfish，避免 python-chess 在 Windows/Python 3.13 下的兼容性问题。
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

import chess
import chess.pgn

from app.config import settings
from app.models import TopMove, EngineAnalysis


@dataclass
class _RawMove:
    rank: int
    score_cp: Optional[int]
    mate_in: Optional[int]
    pv_uci: list[str]
    depth: int
    nodes: int


def _resolve_stockfish_path() -> str:
    """解析 Stockfish 路径"""
    path = settings.stockfish_path
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
    path = os.path.normpath(path)
    if os.path.exists(path):
        return path
    raise FileNotFoundError(f"找不到 Stockfish 引擎: {path}")


class StockfishAnalyzer:
    """Stockfish 分析器封装"""

    def __init__(self):
        self._lock = threading.Lock()

    def check_engine(self) -> bool:
        """检查引擎是否可用"""
        try:
            path = _resolve_stockfish_path()
            result = subprocess.run(
                [path],
                input="uci\nquit\n",
                capture_output=True,
                text=True,
                timeout=10,
            )
            return "Stockfish" in result.stdout
        except Exception:
            return False

    def _run_stockfish(
        self,
        fen: str,
        depth: int,
        multi_pv: int = 3,
    ) -> list[_RawMove]:
        """直接调用 Stockfish 进行多 PV 分析"""
        path = _resolve_stockfish_path()

        commands = [
            "uci",
            f"setoption name Threads value {settings.stockfish_threads}",
            f"setoption name Hash value {settings.stockfish_hash}",
            "isready",
            "position fen " + fen,
            f"go depth {depth} multipv {multi_pv}",
        ]

        proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        stdout_lines: list[str] = []
        try:
            assert proc.stdin is not None
            assert proc.stdout is not None

            for cmd in commands:
                proc.stdin.write(cmd + "\n")
                proc.stdin.flush()

            # 读取输出直到 bestmove
            start = time.time()
            while True:
                if proc.stdout.readable():
                    line = proc.stdout.readline()
                    if line:
                        stdout_lines.append(line.strip())
                        if line.startswith("bestmove"):
                            break
                if time.time() - start > 60:
                    raise TimeoutError("Stockfish 分析超时")

            proc.stdin.write("quit\n")
            proc.stdin.flush()
        finally:
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

        return self._parse_output(stdout_lines, fen, depth)

    @staticmethod
    def _parse_output(lines: list[str], fen: str, depth: int) -> list[_RawMove]:
        """解析 Stockfish info 输出"""
        # 按 multipv 分组，取每个 multipv 最后一条（最深）
        last_by_rank: dict[int, _RawMove] = {}

        for line in lines:
            if not line.startswith("info") or " pv " not in line:
                continue
            if " score " not in line:
                continue

            rank_match = re.search(r" multipv (\d+) ", line)
            if not rank_match:
                continue
            rank = int(rank_match.group(1))

            score_cp: Optional[int] = None
            mate_in: Optional[int] = None
            score_match = re.search(r" score (cp|mate) (-?\d+) ", line)
            if score_match:
                score_type = score_match.group(1)
                score_value = int(score_match.group(2))
                if score_type == "cp":
                    score_cp = score_value
                else:
                    mate_in = score_value

            nodes_match = re.search(r" nodes (\d+) ", line)
            nodes = int(nodes_match.group(1)) if nodes_match else 0

            pv_match = re.search(r" pv (.+)$", line)
            if not pv_match:
                continue
            pv_uci = pv_match.group(1).strip().split()
            if not pv_uci:
                continue

            last_by_rank[rank] = _RawMove(
                rank=rank,
                score_cp=score_cp,
                mate_in=mate_in,
                pv_uci=pv_uci,
                depth=depth,
                nodes=nodes,
            )

        return [last_by_rank[r] for r in sorted(last_by_rank)]

    def _clean_pgn(self, content: str) -> str:
        """清洗 chess.com / lichess 导出的 PGN 文本"""
        # 去除首尾空白
        content = content.strip()
        # 统一换行符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        # chess.com 有时在行末有额外空格
        content = '\n'.join(line.rstrip() for line in content.split('\n'))
        # 去除 BOM
        if content.startswith('\ufeff'):
            content = content[1:]
        return content

    def _detect_input_type(self, content: str) -> str:
        """自动检测输入类型：fen 或 pgn"""
        content = content.strip()
        if not content:
            raise ValueError("输入内容为空")

        # PGN 特征：以 [ 开头的标签头
        if content.startswith('['):
            return 'pgn'

        # PGN 特征：包含典型的棋谱着法模式 (如 "1." 或 "1...")
        # 但要排除 FEN（FEN 也包含数字和点）
        pgn_pattern = content.replace('\n', ' ').replace('\r', ' ')
        # 检查是否以 1. 或 1... 开头（棋谱）
        if re.match(r'^\s*1\.', pgn_pattern) or re.match(r'^\s*1\.\.\.', pgn_pattern):
            return 'pgn'

        # 否则当作 FEN 处理
        return 'fen'

    def _parse_fen(self, content: str) -> tuple[str, chess.Board]:
        """解析 FEN — 支持不完整的 FEN（自动补全）"""
        content = content.strip()
        # 按空格分割 FEN 段
        parts = content.split()
        if not parts:
            raise ValueError("FEN 内容为空")

        # 检查第一部分是否是合法的棋盘排列（8 段用 / 分隔）
        board_part = parts[0]
        ranks = board_part.split('/')
        if len(ranks) != 8:
            raise ValueError(f"FEN 棋盘排列格式错误：需要 8 行，当前 {len(ranks)} 行。\n请粘贴完整的 FEN 字符串，例如：\nrnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")

        # 如果 FEN 不足 6 段，自动补全默认值
        defaults = ['', 'w', 'KQkq', '-', '0', '1']
        while len(parts) < 6:
            parts.append(defaults[len(parts)])

        fen = ' '.join(parts[:6])
        board = chess.Board(fen)
        return board.fen(), board

    def _parse_pgn(
        self,
        content: str,
        step: Optional[int] = None,
    ) -> tuple[str, chess.Board, dict]:
        """解析 PGN — 支持逐步分析

        Args:
            content: PGN 文本
            step: 走到第几步分析 (None/-1=终局, 0=初始, 1=第1步后...)

        Returns:
            (fen, board, meta) — meta 包含 pgn_info 用于前端展示
        """
        content = self._clean_pgn(content)

        # 尝试解析 PGN（用 io.StringIO 包装字符串）
        game = chess.pgn.read_game(io.StringIO(content))
        if game is None:
            raise ValueError(
                "无法解析 PGN 内容。\n\n请确保粘贴的是标准 PGN 格式，例如：\n"
                '[Event "Live Chess"]\n[Site "Chess.com"]\n\n1. e4 e5 2. Nf3 Nc6\n\n'
                "支持的来源：\n"
                "• chess.com — 对局结束后点击「下载PGN」\n"
                "• lichess.org — 对局页面底部点击「FEN & PGN」标签页\n"
                "• 也可以直接粘贴只有着法的纯文本：1. e4 e5 2. Nf3"
            )

        # 获取主变例所有着法
        moves = list(game.mainline_moves())
        total_moves = len(moves)

        # 提取棋谱元信息
        headers = dict(game.headers) if game.headers else {}
        meta = {
            "total_moves": total_moves,
            "total_plies": total_moves,
            "white": headers.get("White", "?"),
            "black": headers.get("Black", "?"),
            "result": headers.get("Result", "*"),
            "event": headers.get("Event", ""),
            "site": headers.get("Site", ""),
            "date": headers.get("Date", ""),
        }

        # 构建着法 SAN 列表
        meta["moves_san"] = self._build_moves_san(game, moves)

        # 确定目标步数
        target_step = total_moves  # 默认终局
        if step is not None and step >= 0:
            target_step = min(step, total_moves)

        # 走到目标步数
        board = game.board()
        for i, move in enumerate(moves):
            if i >= target_step:
                break
            board.push(move)

        meta["current_step"] = target_step
        return board.fen(), board, meta

    @staticmethod
    def _build_moves_san(game, moves: list) -> list[str]:
        """构建着法的 SAN 列表"""
        board = game.board()
        result = []
        for move in moves:
            san = board.san(move)
            move_num = board.fullmove_number
            is_white = board.turn == chess.WHITE
            if is_white:
                result.append(f"{move_num}. {san}")
            elif not result:
                result.append(f"{move_num}... {san}")
            else:
                result[-1] += f" {san}"
            board.push(move)
        return result

    def fen_to_board_info(self, fen: str) -> dict:
        """从 FEN 提取局面基本信息"""
        board = chess.Board(fen)
        return {
            "turn": "白方" if board.turn == chess.WHITE else "黑方",
            "fullmove_number": board.fullmove_number,
            "piece_count": {
                "white": sum(len(board.pieces(pt, chess.WHITE)) for pt in chess.PIECE_TYPES),
                "black": sum(len(board.pieces(pt, chess.BLACK)) for pt in chess.PIECE_TYPES),
            },
            "castling_rights": board.castling_rights,
            "is_check": board.is_check(),
            "is_checkmate": board.is_checkmate(),
            "is_stalemate": board.is_stalemate(),
        }

    def analyze(
        self,
        fen: str,
        depth: Optional[int] = None,
        multi_pv: int = 3,
    ) -> EngineAnalysis:
        """分析局面"""
        with self._lock:
            target_depth = depth or settings.stockfish_depth
            board = chess.Board(fen)
            start_time = time.time()
            raw_moves = self._run_stockfish(fen, target_depth, multi_pv)
            elapsed_ms = int((time.time() - start_time) * 1000)

        top_moves = []
        total_nodes = 0

        for raw in raw_moves:
            if not raw.pv_uci:
                continue
            try:
                best_move = chess.Move.from_uci(raw.pv_uci[0])
                if best_move not in board.legal_moves:
                    continue
            except Exception:
                continue

            pv_san = []
            temp_board = board.copy()
            for uci in raw.pv_uci[:6]:
                try:
                    move = chess.Move.from_uci(uci)
                    if move not in temp_board.legal_moves:
                        break
                    pv_san.append(temp_board.san(move))
                    temp_board.push(move)
                except Exception:
                    break

            top_moves.append(TopMove(
                move=best_move.uci(),
                san=board.san(best_move),
                centipawn=raw.score_cp,
                mate_in=raw.mate_in,
                pv=pv_san,
            ))
            total_nodes = max(total_nodes, raw.nodes)

        eval_summary = self._format_evaluation(top_moves, board)

        return EngineAnalysis(
            fen=fen,
            best_moves=top_moves,
            evaluation=eval_summary,
            depth=target_depth,
            nodes=total_nodes,
            time_ms=elapsed_ms,
        )

    @staticmethod
    def _format_evaluation(top_moves: list[TopMove], board: chess.Board) -> str:
        """格式化评估值摘要"""
        if not top_moves:
            return "无法评估"

        best = top_moves[0]
        turn_name = "白方" if board.turn == chess.WHITE else "黑方"

        if best.mate_in is not None:
            if best.mate_in > 0:
                return f"{turn_name} {best.mate_in} 步将杀"
            else:
                return f"{turn_name} {abs(best.mate_in)} 步内被将杀"

        if best.centipawn is not None:
            cp = best.centipawn
            pawns = abs(cp) / 100.0
            if cp > 150:
                return f"{turn_name}胜势 (+{pawns:.1f})"
            elif cp > 50:
                return f"{turn_name}优势 (+{pawns:.1f})"
            elif cp > 20:
                return f"{turn_name}略优 (+{pawns:.1f})"
            elif cp >= -20:
                return f"均势 ({cp/100:+.1f})"
            elif cp > -50:
                return f"{turn_name}略劣 ({cp/100:.1f})"
            elif cp > -150:
                return f"{turn_name}劣势 ({cp/100:.1f})"
            else:
                return f"{turn_name}败势 ({cp/100:.1f})"

        return "均势 (0.0)"

    def close(self):
        """关闭引擎（subprocess 版本无需维护长连接）"""
        pass


# 全局单例
_analyzer: Optional[StockfishAnalyzer] = None


def get_analyzer() -> StockfishAnalyzer:
    """获取 Stockfish 分析器单例"""
    global _analyzer
    if _analyzer is None:
        _analyzer = StockfishAnalyzer()
    return _analyzer


# ============================================================
# Milestone 1 独立测试: python -m app.engine
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  Milestone 1: Stockfish Engine 测试")
    print("=" * 60)

    test_fens = [
        ("初始局面", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
        ("意大利开局", "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"),
        ("残局 - 车兵对车", "4k3/4p3/8/8/8/8/4P3/4K2R w K - 0 1"),
    ]

    analyzer = StockfishAnalyzer()
    try:
        for name, fen in test_fens:
            print(f"\n📌 测试局面: {name}")
            result = analyzer.analyze(fen, depth=15)
            print(f"   评估: {result.evaluation}")
            print(f"   深度: {result.depth} | 节点: {result.nodes:,} | 耗时: {result.time_ms}ms")
            for i, move in enumerate(result.best_moves):
                score = f"M{move.mate_in}" if move.mate_in is not None else f"{move.centipawn / 100:+.1f}" if move.centipawn is not None else "?"
                pv_str = " → ".join(move.pv[:5])
                print(f"     {i + 1}. {move.san} ({score}) PV: {pv_str}")
        print(f"\n{'=' * 60}")
        print("  ✅ Milestone 1 测试通过!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        raise
