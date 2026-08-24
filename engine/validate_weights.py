# -*- coding: utf-8 -*-
"""調整した重みが初期値より強いかを検定する。

調整に使った局面での勝率は楽観的になるので、
別シードで取った未使用の局面 (ホールドアウト) でも測る。
"""
import os, sys, json, time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import NAMES, INIT_W
from tune_spsa import load_positions, match

HERE = os.path.dirname(os.path.abspath(__file__))


def last_weights():
    w = None
    it = 0
    with open(os.path.join(HERE, 'tune_log.jsonl'), encoding='utf-8') as f:
        for ln in f:
            r = json.loads(ln)
            w = r['w']
            it = r['iter']
    return w, it


def main():
    depth = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    maxply = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    npos = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    w, it = last_weights()
    print('反復 %d 時点の重み\n' % it)
    print('%-10s %10s %10s %8s' % ('特徴量', '初期', '調整後', '倍率'))
    for i, n in enumerate(NAMES):
        r = (w[i] / INIT_W[i]) if INIT_W[i] else float('nan')
        print('  %-10s %9.1f %10.1f %8.2f' % (n, INIT_W[i], w[i], r))

    tune_pos = load_positions(npos, seed=20260825)        # 調整に使った局面
    hold_pos = load_positions(npos, seed=99999999)        # 未使用の局面
    with Pool() as pool:
        for label, pos in (('調整に使った局面', tune_pos), ('ホールドアウト', hold_pos)):
            t0 = time.perf_counter()
            wi, lo, dr, sc = match(pool, pos, w, INIT_W, depth, maxply)
            dt = time.perf_counter() - t0
            n = len(pos) * 2
            print('\n=== %s (%d局) ===' % (label, n))
            print('  調整後 %d勝 %d敗 %d分   得点 %+.2f  (%.0fs)' % (wi, lo, dr, sc, dt))
            if wi + lo:
                print('  決着局のみの勝率: %.1f%%' % (wi / (wi + lo) * 100))


if __name__ == '__main__':
    main()
