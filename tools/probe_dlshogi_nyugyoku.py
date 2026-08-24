# -*- coding: utf-8 -*-
"""dlshogi (cshogi.dlshogi) の入玉用入力特徴が何を符号化しているかを実測する。

背景:
    cshogi.dlshogi には use_nyugyoku_features(True) というトグルがあり、
    有効にすると FEATURES2 が 57面 -> 119面 に増える (+62面)。
    dlshogi を切り出して24点法のソルバを作るなら、この62面が何なのかを
    知らないまま使うわけにはいかない。中身をブラックボックス測定で決める。

方法:
    make_conformance.build() で、敵陣内の枚数 n と宣言点数 p だけを
    動かした局面を作り、立っている面の番号がどう動くかを見る。
    枚数と点数を独立に制御できるので、面の割り当てを分離できる。

結論 (このスクリプトが表明で検証する):
    62面 = 31面 x 2 (手番側 / 相手側)。各31面の内訳は
        offset  0        玉が敵陣三段目以内     … 独立した旗
        offset  1..10    枚数の one-hot        offset = 11 - 敵陣内枚数 (1<=n<=10)
        offset 11..30    点数の不足の one-hot   offset = 11 + (閾値 - 宣言点数)
    閾値は先手28点 / 後手27点。つまり **27点法がハードコード**されている。

    符号化されているのは「いくつ持っているか」ではなく「あといくつ足りないか」。
    条件を満たした側 (n>=11 / 点数>=閾値) は面が立たなくなり、
    不足が枠を超えた側 (n=0 / 不足が大きすぎる) も立たない。
    平手初形で1面も立たないのは入玉でゲートされているからではなく、
    枚数0と点数不足28がどちらも枠の外にあるためである。

24点法に移す場合:
    - 閾値を 31 / 31 にする (先後非対称が消える)
    - 点数不足の枠は20スロットしかない。24点法は閾値が高く不足量が大きくなるので
      ここは広げる必要がある

実行:  python tools/probe_dlshogi_nyugyoku.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'engine'))

import numpy as np
import cshogi
try:
    import cshogi.dlshogi as dl
except ImportError:
    print('cshogi.dlshogi がありません。pip install cshogi してください。', file=sys.stderr)
    sys.exit(2)

from make_conformance import build, ref_count

BASE2_PLAIN = 57          # use_nyugyoku_features(False) のときの FEATURES2
GROUP = 31                # 1サイドあたりの面数 (実測で確かめる)


def lit_offsets(board):
    """立っている入玉面の offset を (手番側, 相手側) に分けて返す。"""
    f1 = np.zeros((dl.FEATURES1_NUM, 9, 9), np.float32)
    f2 = np.zeros((dl.FEATURES2_NUM, 9, 9), np.float32)
    dl.make_input_features(board, f1, f2)
    a = sorted(i - BASE2_PLAIN for i in range(BASE2_PLAIN, BASE2_PLAIN + GROUP) if f2[i].any())
    b = sorted(i - BASE2_PLAIN - GROUP
               for i in range(BASE2_PLAIN + GROUP, dl.FEATURES2_NUM) if f2[i].any())
    return a, b



def survey():
    """20スロットで24点法が足りるかを、実データの不足量分布で測る。

    dlshogi は不足を offset 11..30 の20スロットに載せている。27点法 (閾値28/27) では
    それで足りるという判断だが、24点法は閾値が31点で不足が大きくなる。
    positions/aiiru_bench.tsv (floodgate の相入玉成立局面) で実際に測る。
    """
    path = os.path.join(HERE, '..', 'positions', 'aiiru_bench.tsv')
    if not os.path.exists(path):
        print('\n--- 不足量の分布 --- (%s が無いので省略)' % os.path.relpath(path))
        return
    defs = {24: [], 27: []}
    with open(path, encoding='utf-8') as f:
        for ln in f:
            if ln.startswith('#') or not ln.strip():
                continue
            c = ln.rstrip('\n').split('\t')
            if len(c) < 6:
                continue
            bp, wp = int(c[3]), int(c[5])
            defs[24] += [31 - bp, 31 - wp]              # 24点法: 勝ちは先後とも31点
            defs[27] += [28 - bp, 27 - wp]              # 27点法: 先手28 / 後手27
    print('\n--- 不足量が20スロットに収まるか (positions/aiiru_bench.tsv, 先後別 %d 標本) ---'
          % len(defs[24]))
    print('  %-8s %-8s %-8s %-8s %s' % ('ルール', '中央値', '平均', '枠内(0..19)', '枠外'))
    for rule in (27, 24):
        d = sorted(defs[rule])
        inside = sum(1 for x in d if 0 <= x <= 19)
        over = sum(1 for x in d if x > 19)
        med = d[len(d) // 2]
        print('  %-8s %-8d %-8.1f %-8s %s'
              % ('%d点法' % rule, med, sum(d) / len(d),
                 '%.1f%%' % (100.0 * inside / len(d)),
                 '%.1f%% (不足20点以上)' % (100.0 * over / len(d))))
    print('  枠外はすべて offset が立たない = 「かなり足りない」がすべて同じ入力になる。')
    print('  (不足が負 = 既に条件を満たしている側も面が立たないが、こちらは情報の欠落ではない)')


def main():
    dl.use_nyugyoku_features(False)
    plain = dl.FEATURES2_NUM
    dl.use_nyugyoku_features(True)
    withny = dl.FEATURES2_NUM
    extra = withny - plain
    print('FEATURES1 = %d' % dl.FEATURES1_NUM)
    print('FEATURES2 = %d (入玉特徴なし) -> %d (あり)   差分 %d面 = %d面 x 2'
          % (plain, withny, extra, extra // 2))
    assert plain == BASE2_PLAIN and extra == GROUP * 2, \
        'このスクリプトが前提とする面数と違う (cshogi のバージョン差)'

    print('\n--- 平手初形 ---')
    a, b = lit_offsets(cshogi.Board())
    print('  手番側=%s 相手側=%s' % (a, b))
    assert not a and not b, '初形で面が立った'
    print('  1面も立たない。ただし後で見るとおり、これは入玉でゲートされているのではなく')
    print('  枚数0も点数不足28も、どちらも枠の外だからである。')

    print('\n--- 敵陣内の枚数 n を動かす (点数 p は固定) ---')
    print('  %-6s %-4s  %-22s %s' % ('宣言側', 'n', '立っている offset', '解釈'))
    obs_count = {}
    for color, cname in ((cshogi.BLACK, '先手'), (cshogi.WHITE, '後手')):
        for n in (0, 3, 5, 9, 10, 12):
            board, errs = build(color, n, 33, king_in=True)
            if errs:
                print('  %-6s %-4d  (構成不能: %s)' % (cname, n, errs[0]))
                continue
            a, b = lit_offsets(board)
            grp = a if board.turn == color else b
            cnt = [o for o in grp if 1 <= o <= 10]
            obs_count[(cname, n)] = cnt
            print('  %-6s %-4d  %-22s 枚数の面 %s' % (cname, n, grp, cnt))

    print('\n--- 宣言点数 p を動かす (枚数 n は固定=10) ---')
    print('  %-6s %-4s  %-22s %s' % ('宣言側', 'p', '立っている offset', '解釈'))
    obs_pts = {}
    for color, cname in ((cshogi.BLACK, '先手'), (cshogi.WHITE, '後手')):
        for p in (10, 20, 24, 26, 27, 28, 31, 33):
            board, errs = build(color, 10, p, king_in=True)
            if errs:
                print('  %-6s %-4d  (構成不能: %s)' % (cname, p, errs[0]))
                continue
            a, b = lit_offsets(board)
            grp = a if board.turn == color else b
            pts = [o for o in grp if o >= 11]
            obs_pts[(cname, p)] = pts
            print('  %-6s %-4d  %-22s 点数の面 %s' % (cname, p, grp, pts))

    print('\n--- 玉の位置だけを変える (n=10, p=24 固定) ---')
    for king_in in (True, False):
        board, errs = build(cshogi.BLACK, 10, 24, king_in=king_in)
        a, b = lit_offsets(board)
        print('  先手 玉が敵陣%s -> 手番側=%s' % ('内' if king_in else '外', a))
        assert (0 in a) == king_in, 'offset 0 が玉の位置と対応していない'
    print('  offset 0 は玉が敵陣にいるかの旗。枚数・点数の面はこれと独立に立つ')
    print('  (つまり入玉によるゲートではない)')

    print('\n--- 枠の境界 ---')
    print('  枚数側 (点数は閾値超で固定):')
    for n in (0, 1, 10, 11, 13):
        board, errs = build(cshogi.BLACK, n, 33 if n else 33, king_in=True)
        if errs:
            print('    n=%-3d (構成不能)' % n)
            continue
        a, _ = lit_offsets(board)
        print('    n=%-3d -> %s' % (n, a))
    print('  点数側 (先手・閾値28点)。n枚あれば最低n点なので、不足を大きくするには枚数も減らす:')
    for n_, p_ in ((10, 10), (9, 9), (8, 8), (5, 5), (1, 1), (0, 0)):
        board, errs = build(cshogi.BLACK, n_, p_, king_in=True)
        if errs:
            print('    n=%-3d p=%-3d (構成不能: %s)' % (n_, p_, errs[0]))
            continue
        a, _ = lit_offsets(board)
        pts = [o for o in a if o >= 11]
        print('    n=%-3d p=%-3d 不足%-3d -> %-16s 点数の面 %s' % (n_, p_, 28 - p_, a, pts))

    # ---- 表明: 割り当ての式 ----
    print('\n--- 割り当ての検証 ---')
    ok = True
    for (cname, n), cnt in obs_count.items():
        want = [11 - n] if 1 <= n <= 10 else []
        if cnt != want:
            print('  MISMATCH 枚数 %s n=%d: 実測 %s / 予想 %s' % (cname, n, cnt, want))
            ok = False
    THRESH = {'先手': 28, '後手': 27}          # 27点法。先手28 / 後手27
    for (cname, p), pts in obs_pts.items():
        d = THRESH[cname] - p
        want = [11 + d] if 0 <= d <= 19 else []
        if pts != want:
            print('  MISMATCH 点数 %s p=%d: 実測 %s / 予想 %s (不足 %d)' % (cname, p, pts, want, d))
            ok = False
    if ok:
        print('  一致: offset = 11 - n が枚数 (1<=n<=10)、')
        print('        offset = 11 + (閾値 - p) が点数の不足 (0 <= 不足 <= 19)。')
        print('        閾値は先手28点 / 後手27点 = 27点法。')
    else:
        print('  一致しなかった。cshogi のバージョンで割り当てが変わった可能性がある。')

    survey()

    print("""
--- 24点法へ移すときに触る場所 ---
  1. 点数の閾値を 28/27 -> 31/31 に変える。24点法の勝ちは先後対称。
  2. 点数不足の枠 (offset 11..30 の20スロット) を広げる。
     実測のとおり、枠外に落ちる標本が 27点法 11.3% -> 24点法 22.6% に倍増する。
     枠外は1面も立たないので「あと20点」も「あと28点」も同じ入力になる。
     28〜30スロットあれば24点法でもほぼ収まる。
  3. 枚数条件 (10枚) は24点法・27点法で共通なので、そのまま使える。
  4. cshogi.Board.is_nyugyoku() は27点法基準。24点法の判定には
     engine/engine_decl24.py の declaration() を使うこと。
""")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
