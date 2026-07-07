"""Stockfish 引擎封装模块

使用 subprocess 调用 Stockfish 18，通过 UCI 协议通信。
采用线程池隔离，确保并发请求安全。
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

import chess
import chess.pgn

from config import settings


@dataclass
class _RawMove:
    """Stockfish 原始输出的一行 PV 信息"""
    rank: int
    score_cp: Optional[int]
    mate_in: Optional[int]
    pv_uci: list[str]
    depth: int
    nodes: int


@dataclass
class TopMove:
    """最佳着法"""
    move: str          # UCI 格式, 如 e2e4
    san: str           # 标准代数记谱, 如 e4
    centipawn: Optional[int] = None
    mate_in: Optional[int] = None
    pv: list[str] = field(default_factory=list)  # SAN 格式


@dataclass
class EngineAnalysis:
    """引擎分析结果"""
    fen: str
    best_moves: list[TopMove] = field(default_factory=list)
    evaluation: str = ""
    depth: int = 0
    nodes: int = 0
    time_ms: int = 0


def _resolve_stockfish_path() -> str:
    """解析 Stockfish 路径"""
    path = settings.stockfish_path
    if os.path.isabs(path):
        return path
    # 尝试从 PATH 中查找
    import shutil
    found = shutil.which(path)
    if found:
        return found
    raise FileNotFoundError(f"找不到 Stockfish 引擎: {path}")


class StockfishAnalyzer:
    """Stockfish 分析器 — 线程池隔离，每次分析启动独立进程"""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

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

    def get_version(self) -> str:
        """获取 Stockfish 版本号"""
        try:
            path = _resolve_stockfish_path()
            result = subprocess.run(
                [path],
                input="uci\nquit\n",
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("id name"):
                    return line.split("id name", 1)[1].strip()
            return "unknown"
        except Exception:
            return "unknown"

    def analyze_sync(
        self,
        fen: str,
        depth: Optional[int] = None,
        multi_pv: int = 3,
    ) -> EngineAnalysis:
        """同步分析局面 (在 exec 线程中调用)"""
        target_depth = depth or settings.stockfish_depth
        board = chess.Board(fen)
        start_time = time.time()
        raw_moves = self._run_stockfish(fen, target_depth, multi_pv)
        elapsed_ms = int((time.time() - start_time) * 1000)

        top_moves: list[TopMove] = []
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

            pv_san: list[str] = []
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

    async def analyze(
        self,
        fen: str,
        depth: Optional[int] = None,
        multi_pv: int = 3,
    ) -> EngineAnalysis:
        """异步分析局面 — 提交到线程池执行，不阻塞事件循环"""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self.analyze_sync,
            fen,
            depth,
            multi_pv,
        )

    # ---------- 内部方法 ----------

    def _run_stockfish(
        self,
        fen: str,
        depth: int,
        multi_pv: int = 3,
    ) -> list[_RawMove]:
        """启动 Stockfish 子进程进行多 PV 分析"""
        path = _resolve_stockfish_path()

        commands = [
            "uci",
            f"setoption name Threads value {settings.stockfish_threads}",
            f"setoption name Hash value {settings.stockfish_hash}",
            "isready",
            f"position fen {fen}",
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

            start = time.time()
            while True:
                if proc.stdout.readable():
                    line = proc.stdout.readline()
                    if line:
                        stdout_lines.append(line.strip())
                        if line.startswith("bestmove"):
                            break
                if time.time() - start > 120:
                    raise TimeoutError("Stockfish 分析超时 (120s)")

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

    def fen_to_board_info(self, fen: str) -> dict:
        """从 FEN 提取局面基本信息"""
        board = chess.Board(fen)
        return {
            "turn": "白方" if board.turn == chess.WHITE else "黑方",
            "turn_en": "white" if board.turn == chess.WHITE else "black",
            "fullmove_number": board.fullmove_number,
            "piece_count": {
                "white": sum(len(board.pieces(pt, chess.WHITE)) for pt in chess.PIECE_TYPES),
                "black": sum(len(board.pieces(pt, chess.BLACK)) for pt in chess.PIECE_TYPES),
            },
            "castling_rights": str(board.castling_rights) if board.castling_rights else "",
            "is_check": board.is_check(),
            "is_checkmate": board.is_checkmate(),
            "is_stalemate": board.is_stalemate(),
        }

    def parse_pgn(
        self,
        content: str,
        step: Optional[int] = None,
    ) -> tuple[str, chess.Board, dict]:
        """解析 PGN — 支持逐步分析

        Args:
            content: PGN 文本
            step: 走到第几步分析 (None/-1=终局, 0=初始, 1=第1步后...)

        Returns:
            (fen, board, meta)
        """
        content = self._clean_pgn(content)

        game = chess.pgn.read_game(io.StringIO(content))
        if game is None:
            raise ValueError(
                "无法解析 PGN 内容。\n\n请确保粘贴的是标准 PGN 格式，例如：\n"
                '[Event "Live Chess"]\n[Site "Chess.com"]\n\n1. e4 e5 2. Nf3 Nc6'
            )

        moves = list(game.mainline_moves())
        total_moves = len(moves)

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

        meta["moves_san"] = self._build_moves_san(game, moves)

        target_step = total_moves
        if step is not None and step >= 0:
            target_step = min(step, total_moves)

        board = game.board()
        for i, move in enumerate(moves):
            if i >= target_step:
                break
            board.push(move)

        meta["current_step"] = target_step
        return board.fen(), board, meta

    # ---------- 辅助方法 ----------

    @staticmethod
    def _clean_pgn(content: str) -> str:
        content = content.strip()
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        content = "\n".join(line.rstrip() for line in content.split("\n"))
        if content.startswith("\ufeff"):
            content = content[1:]
        return content

    @staticmethod
    def _build_moves_san(game, moves: list) -> list[str]:
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

    @staticmethod
    def _format_evaluation(top_moves: list[TopMove], board: chess.Board) -> str:
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
                return f"均势 ({cp / 100:+.1f})"
            elif cp > -50:
                return f"{turn_name}略劣 ({cp / 100:.1f})"
            elif cp > -150:
                return f"{turn_name}劣势 ({cp / 100:.1f})"
            else:
                return f"{turn_name}败势 ({cp / 100:.1f})"

        return "均势 (0.0)"

    def shutdown(self):
        """关闭线程池"""
        self._executor.shutdown(wait=True)


# 全局单例
_analyzer: Optional[StockfishAnalyzer] = None
_lock = threading.Lock()


def get_analyzer() -> StockfishAnalyzer:
    """获取 Stockfish 分析器单例"""
    global _analyzer
    if _analyzer is None:
        with _lock:
            if _analyzer is None:
                _analyzer = StockfishAnalyzer()
    return _analyzer
