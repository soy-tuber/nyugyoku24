# -*- coding: utf-8 -*-
"""engine_decl24 の検証。

1) 判定器の突き合わせ: zone_stats() を、186万局走査で使った検証済みの値 (TSV) と比較
2) 目的関数の挙動テスト: 敵陣への打ち込み・運び込みを選ぶか
3) 本題: 相入玉成立局面から自己対局し、実際のエンジンが届かなかった
         「敵陣三段目以内に10枚」に到達できるか
"""
import os, sys, glob, random, time, collections
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine_decl24 import (DeclEngine24, zone_stats, declaration, ZONE,
                           NEED_N, WIN_POINT, DRAW_POINT)

DS = r"D:\book_project\nyugyoku_dataset"
TSV = r"D:\book_project\nyugyoku_all_years.tsv"


def load_tsv():
    m = {}
    with open(TSV, encoding='utf-8') as fh:
        hdr = fh.readline().rstrip('\n').split('\t')
        for ln in fh:
            d = dict(zip(hdr, ln.rstrip('\n').split('\t')))
            if d['kind'] == 'AI':
                m[d['game']] = (int(d['sente_zone']), int(d['sente_zone_n']),
                                int(d['gote_zone']), int(d['gote_zone_n']))
    return m


def replay(path):
    """(相入玉成立時のBoard, 最終Board) を返す。"""
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    moves = [ln for ln in lines if len(ln) >= 7 and ln[0] in '+-' and ln[1].isdigit()]
    b = cshogi.Board()
    at = None
    for ln in moves:
        try:
            m = b.move_from_csa(ln[1:])
            if m == 0 or not b.is_legal(m):
                return None, None
            b.push(m)
        except Exception:
            return None, None
        if at is None:
            bk = b.king_square(cshogi.BLACK)
            wk = b.king_square(cshogi.WHITE)
            if bk % 9 <= 2 and wk % 9 >= 6:
                at = cshogi.Board(b.sfen())
    return at, b


def main():
    random.seed(3)
    tsv = load_tsv()
    files = []
    for y in ('2021', '2022', '2023'):
        files += glob.glob(os.path.join(DS, y, '*.csa'))
    random.shuffle(files)

    print('=== 1) 判定器の突き合わせ (検証済みTSVとの比較) ===')
    ok = ng = 0
    samples = []
    for path in files:
        if ok + ng >= 400:
            break
        nm = os.path.basename(path)
        if nm not in tsv:
            continue
        at, fin = replay(path)
        if fin is None:
            continue
        sn, sp, _ = zone_stats(fin, cshogi.BLACK)
        gn, gp, _ = zone_stats(fin, cshogi.WHITE)
        exp = tsv[nm]
        if (sp, sn, gp, gn) == exp:
            ok += 1
            if at is not None:
                samples.append((nm, at))
        else:
            ng += 1
            if ng <= 3:
                print('  不一致 %s: 得=(%d,%d,%d,%d) 期待=%s' % (nm[:40], sp, sn, gp, gn, exp))
    print('  一致 %d / 不一致 %d' % (ok, ng))

    print('\n=== 2) 目的関数の挙動: 何を選ぶか ===')
    eng = DeclEngine24(max_depth=2)
    kinds = collections.Counter()
    for nm, b0 in samples[:40]:
        b = cshogi.Board(b0.sfen())
        us = b.turn
        mv, sc, _ = eng.go(b, max_depth=2)
        if not isinstance(mv, int):
            kinds['宣言'] += 1
            continue
        to = cshogi.move_to(mv)
        if to in ZONE[us]:
            if cshogi.move_is_drop(mv):
                kinds['敵陣へ打ち込み'] += 1
            elif cshogi.move_from(mv) not in ZONE[us]:
                kinds['敵陣へ運び込み'] += 1
            else:
                kinds['敵陣内で移動'] += 1
        else:
            kinds['敵陣外の手'] += 1
    tot = sum(kinds.values())
    for k, v in kinds.most_common():
        print('  %-16s %3d (%.0f%%)' % (k, v, v / tot * 100))

    print('\n=== 3) 本題: 相入玉局面から自己対局し10枚条件に到達できるか ===')
    print('  (実戦のエンジンは敵陣内の駒数が中央値6枚で止まっていた)')
    eng = DeclEngine24(max_depth=3)
    PLIES = 80
    results = []
    for nm, b0 in samples[:4]:
        b = cshogi.Board(b0.sfen())
        s0 = zone_stats(b, cshogi.BLACK)
        g0 = zone_stats(b, cshogi.WHITE)
        print('\n  %s' % nm[:56])
        print('    開始: 先手 %d枚/%d点   後手 %d枚/%d点' % (s0[0], s0[1], g0[0], g0[1]))
        t0 = time.perf_counter()
        outcome = None
        for i in range(PLIES):
            d = declaration(b, b.turn)
            if d == 'win':
                outcome = '%s の宣言勝ち (%d手目)' % ('先手' if b.turn == cshogi.BLACK else '後手', i)
                break
            mv, sc, nodes = eng.go(b)
            if mv is None:
                outcome = '詰み (%d手目)' % i
                break
            if not isinstance(mv, int):
                outcome = '%s が%s (%d手目)' % ('先手' if b.turn == cshogi.BLACK else '後手',
                                              '無勝負宣言', i)
                break
            b.push(mv)
            if b.is_draw() == cshogi.REPETITION_DRAW:
                outcome = '千日手 (%d手目)' % i
                break
        dt = time.perf_counter() - t0
        s1 = zone_stats(b, cshogi.BLACK)
        g1 = zone_stats(b, cshogi.WHITE)
        print('    %d手後: 先手 %d枚/%d点 (%+d枚)   後手 %d枚/%d点 (%+d枚)   [%.0fs]'
              % (i + 1, s1[0], s1[1], s1[0] - s0[0], g1[0], g1[1], g1[0] - g0[0], dt))
        if outcome:
            print('    -> %s' % outcome)
        results.append((s0, s1, g0, g1, outcome))

    print('\n=== まとめ ===')
    reach = sum(1 for s0, s1, g0, g1, o in results
                if s1[0] >= NEED_N or g1[0] >= NEED_N)
    print('  10枚条件に到達した対局: %d/%d' % (reach, len(results)))
    gained = [s1[0] - s0[0] for s0, s1, g0, g1, o in results] + \
             [g1[0] - g0[0] for s0, s1, g0, g1, o in results]
    print('  敵陣内の駒数の増分: %s' % gained)


if __name__ == '__main__':
    main()
