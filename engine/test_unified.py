# -*- coding: utf-8 -*-
"""統合エンジンの自己対局テスト。3段階の漏斗を実際に通過できるかを見る。

追跡する量:
    所有点数 (駒取りで動く保存量) / 宣言点数 (持駒+敵陣) / 取り残し / 敵陣内の駒数
"""
import os, sys, glob, random, time, collections
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine_unified import UnifiedEngine, full_stats
from engine_decl24 import declaration, NEED_N, WIN_POINT

DS = r"D:\book_project\nyugyoku_dataset"


def aiiru_sfen(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    moves = [ln for ln in lines if len(ln) >= 7 and ln[0] in '+-' and ln[1].isdigit()]
    b = cshogi.Board()
    for ln in moves:
        try:
            m = b.move_from_csa(ln[1:])
            if m == 0 or not b.is_legal(m):
                return None
            b.push(m)
        except Exception:
            return None
        if b.king_square(cshogi.BLACK) % 9 <= 2 and b.king_square(cshogi.WHITE) % 9 >= 6:
            return b.sfen()
    return None


def fmt(board, c):
    o, d, n, h, k = full_stats(board, c)
    return '所有%2d 宣言%2d 残%2d %2d枚' % (o, d, o - d, n)


def selfplay(sfen, plies, depth, verbose=False):
    b = cshogi.Board(sfen)
    eng = UnifiedEngine(depth)
    start = (full_stats(b, cshogi.BLACK), full_stats(b, cshogi.WHITE))
    for i in range(plies):
        side = b.turn
        if declaration(b, side) == 'win':
            return ('宣言勝ち:%s' % ('先手' if side == cshogi.BLACK else '後手'), i, b, start
                    )
        mv, sc = eng.pick(b)
        if mv is None:
            return ('詰み:%s敗' % ('先手' if side == cshogi.BLACK else '後手'), i, b, start)
        if not isinstance(mv, int):
            return ('宣言勝ち:%s' % ('先手' if side == cshogi.BLACK else '後手'), i, b, start)
        b.push(mv)
        if verbose and i % 10 == 0:
            print('    %3d手 先手[%s] 後手[%s]' % (i, fmt(b, cshogi.BLACK), fmt(b, cshogi.WHITE)))
        if b.is_draw() == cshogi.REPETITION_DRAW:
            return ('千日手', i + 1, b, start)
    return ('打ち切り', plies, b, start)


def main():
    random.seed(5)
    files = []
    for y in ('2021', '2022', '2023'):
        files += glob.glob(os.path.join(DS, y, '*.csa'))
    random.shuffle(files)
    NPOS = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    DEPTH = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    PLIES = int(sys.argv[3]) if len(sys.argv) > 3 else 140

    pos = []
    for p in files:
        if len(pos) >= NPOS:
            break
        s = aiiru_sfen(p)
        if s:
            pos.append((os.path.basename(p), s))

    print('統合エンジン 自己対局  局面%d / depth %d / 上限%d手\n' % (len(pos), DEPTH, PLIES))
    tally = collections.Counter()
    for nm, sfen in pos:
        t0 = time.perf_counter()
        res, n, b, start = selfplay(sfen, PLIES, DEPTH)
        dt = time.perf_counter() - t0
        (o1, d1, n1, h1, k1), (o2, d2, n2, h2, k2) = start
        print('%s' % nm[:58])
        print('  開始 先手[所有%2d 宣言%2d 残%2d %2d枚]  後手[所有%2d 宣言%2d 残%2d %2d枚]'
              % (o1, d1, o1 - d1, n1, o2, d2, o2 - d2, n2))
        print('  終了 先手[%s]  後手[%s]' % (fmt(b, cshogi.BLACK), fmt(b, cshogi.WHITE)))
        print('  -> %s (%d手, %.0fs)\n' % (res, n, dt))
        tally[res.split(':')[0]] += 1

    print('=== 集計 ===')
    for k, v in tally.most_common():
        print('  %-12s %d' % (k, v))


if __name__ == '__main__':
    main()
