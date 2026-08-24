# -*- coding: utf-8 -*-
"""相入玉局面を攻防入れ替えで判定する。

各局面について
   run A: 先手が攻撃 / 後手が防御
   run B: 後手が攻撃 / 先手が防御
を走らせ、両結果から局面を分類する。
"""
import os, sys, glob, random, time, collections
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roles import judge, play
from engine_decl24 import zone_stats

DS = r"D:\book_project\nyugyoku_dataset"
NPOS = int(sys.argv[1]) if len(sys.argv) > 1 else 6
DEPTH = int(sys.argv[2]) if len(sys.argv) > 2 else 3
MAXPLY = int(sys.argv[3]) if len(sys.argv) > 3 else 120
PURE = (len(sys.argv) <= 4 or sys.argv[4] != 'mixed')


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


def main():
    random.seed(5)
    files = []
    for y in ('2021', '2022', '2023'):
        files += glob.glob(os.path.join(DS, y, '*.csa'))
    random.shuffle(files)

    pos = []
    for p in files:
        if len(pos) >= NPOS:
            break
        s = aiiru_sfen(p)
        if s:
            pos.append((os.path.basename(p), s))

    print('局面 %d / depth %d / 手数上限 %d\n' % (len(pos), DEPTH, MAXPLY))
    tally = collections.Counter()
    for nm, sfen in pos:
        b = cshogi.Board(sfen)
        sn, sp, _ = zone_stats(b, cshogi.BLACK)
        gn, gp, _ = zone_stats(b, cshogi.WHITE)
        t0 = time.perf_counter()
        verdict, (rb, nb), (rw, nw), _ = judge(sfen, MAXPLY, DEPTH, PURE)
        dt = time.perf_counter() - t0
        tally[verdict] += 1
        print('%s' % nm[:62])
        print('  開始: 先手 %d枚/%d点   後手 %d枚/%d点   手番=%s'
              % (sn, sp, gn, gp, '先手' if b.turn == cshogi.BLACK else '後手'))
        print('  先手が攻め -> %-14s (%3d手)' % (rb, nb))
        print('  後手が攻め -> %-14s (%3d手)' % (rw, nw))
        print('  判定: %s   [%.0fs]\n' % (verdict, dt))

    print('=== 集計 ===')
    for k, v in tally.most_common():
        print('  %-28s %d' % (k, v))


if __name__ == '__main__':
    main()
