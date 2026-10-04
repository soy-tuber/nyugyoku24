# -*- coding: utf-8 -*-
"""取り残しの運び込みの回帰テスト (統合エンジン)。

出典局面: floodgate 2026-10-04 wdoor+floodgate-300-10F+miao-R+Sense+20261004190001
    実戦は相入玉のまま512手打ち切り。先手は所有28点のまま宣言点数10〜23点で終わった。

STALLED は、191手目 (START) から旧版の統合エンジン同士 (depth 2) で80手進めた局面。
先手は所有32点・敵陣22枚・宣言30点に到達しているが、自陣の歩2枚 (8六・1六) が
敵陣まで3手かかるため浅い探索では評価が平坦になり、旧版は以後250手停滞した。
取り残しの前進項 (engine_unified.W_ADV) が入っていれば、短手数で宣言勝ちに届く。

    python engine/test_stranded.py
"""
import os, sys
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine_unified import UnifiedEngine, full_stats

START = '+L2+S2g1l/2+R3g2/1+P7/1K1+N+B1p1p/9/1P4s1P/2N+r1+b3/6k2/9 b GSNL7Pgsnl6p 191'
STALLED = '+LGG+SGSKS+B/PL+RPPPPPL/+P1P1+N1G1N/8p/6p2/1P6P/5+r+b+sn/1+p+p+p+p1k1+l/1+n3+p1+p1 b - 271'


def selfplay_until_declare(sfen, plies, depth=2):
    b = cshogi.Board(sfen)
    eng = UnifiedEngine(depth)
    for i in range(plies):
        mv, _ = eng.pick(b)
        if mv == 'declare_win':
            return b.turn, i, b
        if mv is None:
            return None, i, b
        b.push(mv)
    return None, plies, b


def main():
    ok = True

    b = cshogi.Board(STALLED)
    o, d, n, h, k = full_stats(b, cshogi.BLACK)
    assert (o, d, n, k) == (32, 30, 22, True), (o, d, n, k)

    side, i, _ = selfplay_until_declare(STALLED, 40)
    good = side == cshogi.BLACK
    ok &= good
    print('[%s] 停滞局面 (所有32 宣言30 敵陣22枚) から40手以内に先手が宣言勝ち: %s'
          % ('OK' if good else 'NG', '%d手' % i if good else '届かず'))

    side, i, _ = selfplay_until_declare(START, 200)
    good = side == cshogi.BLACK
    ok &= good
    print('[%s] 実戦191手目から200手以内に先手が宣言勝ち: %s'
          % ('OK' if good else 'NG', '%d手' % i if good else '届かず'))

    print('すべて通過' if ok else '失敗あり')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
