"""API 测试脚本

用法:
    python test_api.py [--url http://localhost:8080]
"""

import argparse
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError


BASE_URL = "http://localhost:8080"


def test_endpoint(method, path, body=None, description=""):
    """测试单个端点"""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None

    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            ok = resp.status == 200
            status = "✅" if ok else "⚠️"
            print(f"  {status} {description} (HTTP {resp.status})")
            return ok, result
    except URLError as e:
        print(f"  ❌ {description}: {e.reason}")
        return False, None
    except Exception as e:
        print(f"  ❌ {description}: {e}")
        return False, None


def test_health():
    """测试健康检查"""
    print("\n📋 健康检查")
    ok, data = test_endpoint("GET", "/health", description="GET /health")
    if ok and data:
        print(f"     状态: {data.get('status')}")
        print(f"     引擎: {data.get('engine')} ({data.get('version')})")
    return ok


def test_position_fen():
    """测试 FEN 解析"""
    print("\n📋 FEN 解析")
    ok, data = test_endpoint("POST", "/api/position", body={
        "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    }, description="POST /api/position (FEN)")
    if ok and data:
        print(f"     局面: {data.get('board_info', {}).get('turn')} 走棋")
    return ok


def test_position_pgn():
    """测试 PGN 解析"""
    print("\n📋 PGN 解析")
    ok, data = test_endpoint("POST", "/api/position", body={
        "pgn": "[Event \"Test\"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6",
        "pgn_step": 3
    }, description="POST /api/position (PGN, step=3)")
    if ok and data:
        info = data.get("pgn_info", {})
        print(f"     总步数: {info.get('total_moves')}, 当前步: {info.get('current_step')}")
    return ok


def test_analyze_initial():
    """测试分析初始局面"""
    print("\n📋 分析初始局面 (depth=15)")
    ok, data = test_endpoint("POST", "/api/analyze", body={
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "depth": 15,
        "multi_pv": 3
    }, description="POST /api/analyze (初始局面)")
    if ok and data:
        print(f"     评估: {data.get('evaluation')}")
        print(f"     深度: {data.get('depth')}, 耗时: {data.get('time_ms')}ms")
        for i, move in enumerate(data.get("top_moves", [])[:3]):
            print(f"     #{i+1}: {move['san']} (评分: {move['score']:+.1f}) PV: {' → '.join(move['pv'][:5])}")
    return ok


def test_analyze_middlegame():
    """测试分析中局"""
    print("\n📋 分析意大利开局 (depth=15)")
    ok, data = test_endpoint("POST", "/api/analyze", body={
        "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
        "depth": 15,
        "multi_pv": 3
    }, description="POST /api/analyze (意大利开局)")
    if ok and data:
        print(f"     评估: {data.get('evaluation')}")
        print(f"     深度: {data.get('depth')}, 耗时: {data.get('time_ms')}ms")
        for i, move in enumerate(data.get("top_moves", [])[:3]):
            print(f"     #{i+1}: {move['san']} (评分: {move['score']:+.1f})")
    return ok


def test_analyze_pgn():
    """测试 PGN 分析"""
    print("\n📋 PGN 分析 (depth=15)")
    ok, data = test_endpoint("POST", "/api/analyze", body={
        "pgn": "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6",
        "pgn_step": 4,
        "depth": 15,
        "multi_pv": 2
    }, description="POST /api/analyze (PGN)")
    if ok and data:
        print(f"     评估: {data.get('evaluation')}")
        for i, move in enumerate(data.get("top_moves", [])[:2]):
            print(f"     #{i+1}: {move['san']} (评分: {move['score']:+.1f})")
    return ok


def test_batch():
    """测试批量分析"""
    print("\n📋 批量分析")
    ok, data = test_endpoint("POST", "/api/analyze/batch", body=[
        {"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "depth": 12, "multi_pv": 1},
        {"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", "depth": 12, "multi_pv": 1},
    ], description="POST /api/analyze/batch (2 个局面)")
    if ok and data:
        results = data.get("results", [])
        print(f"     分析 {len(results)} 个局面:")
        for i, r in enumerate(results):
            if r.get("success"):
                print(f"     #{i+1}: {r.get('evaluation')}")
            else:
                print(f"     #{i+1}: ❌ {r.get('error')}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Stockfish Service API 测试")
    parser.add_argument("--url", default="http://localhost:8080", help="服务地址")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url

    print("=" * 60)
    print(f"  Stockfish Service API 测试")
    print(f"  目标: {BASE_URL}")
    print("=" * 60)

    results = []

    # 先检查服务是否可用
    if not test_health():
        print("\n❌ 服务不可用，请确认已启动: python api.py")
        sys.exit(1)

    # 运行测试
    results.append(("位置解析 (FEN)", test_position_fen()))
    results.append(("位置解析 (PGN)", test_position_pgn()))
    results.append(("分析初始局面", test_analyze_initial()))
    results.append(("分析中局", test_analyze_middlegame()))
    results.append(("PGN 分析", test_analyze_pgn()))
    results.append(("批量分析", test_batch()))

    # 汇总
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"  结果: {passed}/{total} 通过")
    for name, ok in results:
        print(f"    {'✅' if ok else '❌'} {name}")
    print("=" * 60)

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
