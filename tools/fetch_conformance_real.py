# -*- coding: utf-8 -*-
"""実戦由来の適合性テスト集合を HuggingFace から層化サンプリングで作る。

出典:
    penguinkumimanu/nyugyoku24points (HuggingFace, 約30億局面 / 119GB)
    著者の説明: floodgate 2020年以降の棋譜から、片方の玉が敵陣三段目にあり、
    互いの玉に詰み・詰めろが無く、24点法で勝敗を判定できる局面だけを抽出したもの。
    形式は PackedSfenValue (40バイト/局面)。評価値項は常に0で、勝敗項にのみ
    24点法の判定が入る。

このスクリプトが作るもの:
    positions/conformance_real.tsv — 手番側 (=宣言側) の宣言点数と色で層化した部分集合。

    positions/conformance.tsv (合成) が第5項の陰性側
    (23点以下・10枚未満・玉が敵陣外・王手中 = 宣言すれば負ける局面) を担うのに対し、
    こちらは陽性側を実戦の分布で担う。両方揃って第5項の全条件を覆う。

なぜ層化するか:
    判別の軸は「宣言点数 × 宣言側の色」だけである。27点法の宣言勝ちの閾値は
    先手28点 / 後手27点と非対称なので、色を分けないと判別帯がぼける。
    31点を超えると両ルールとも宣言勝ちで判別力が無いため、そこは1帯にまとめる。

    生の分布は24点に4割が集中し、30点付近は4.5%しかない。そのまま取ると
    判別帯の標本が薄くなるので、セルあたりの数を揃える。

なぜ80MBで足りるか:
    最も希少なセルは 30点 x 片方の色 = 約2.25%。1セル300局面を得るのに
    必要なのは約13,000レコード。200万レコード (80MB) あれば全セルが20倍以上埋まる。
    セルあたり300局面は、誤り率を標準誤差2.6%以下で測れる大きさである。

なぜ飛び飛びに取るか:
    6ファイルすべてで勝敗比 (0が90%、1が10%) がほぼ一致しており、
    データは並びに構造を持たないと見てよい。それでも念のため
    6ファイル x 10箇所に分散して取り、並びの偏りに備える。

使い方:
    python tools/fetch_conformance_real.py                    # 既定 (80MB取得)
    python tools/fetch_conformance_real.py --pool-dir /mnt/e/nyugyoku24_hf
    python tools/fetch_conformance_real.py --per-cell 300
    python tools/fetch_conformance_real.py --reuse            # 取得済みプールを使う
"""
import os, sys, subprocess, collections, argparse

import numpy as np
import cshogi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'engine'))
from engine_decl24 import declaration, zone_stats, NEED_N, WIN_POINT, DRAW_POINT

BASE = 'https://huggingface.co/datasets/penguinkumimanu/nyugyoku24points/resolve/main/'
FILES = [('bucket6_000_nyugyoku_%03d.bin' % i, 20_000_000_000) for i in range(5)] \
        + [('bucket6_000_nyugyoku_005.bin', 19_059_640_080)]
REC = 40
OUT = os.path.join(HERE, '..', 'positions', 'conformance_real.tsv')

# 27点法の宣言勝ちの閾値。先後で非対称なのがこのルールの性質である。
T27 = {cshogi.BLACK: 28, cshogi.WHITE: 27}
TOP_BIN = 32                      # 32点以上は1帯にまとめる (両ルールとも勝ちで判別力が無い)


def cell_of(color, p):
    return (color, min(p, TOP_BIN))


def fetch_pool(pool_path, n_records, spots_per_file):
    """飛び飛びの範囲リクエストでプールを作る。既にあれば作り直さない。"""
    if os.path.exists(pool_path) and os.path.getsize(pool_path) >= n_records * REC:
        print('プールを再利用: %s (%.1f MB)' % (pool_path, os.path.getsize(pool_path) / 1e6))
        return
    per_spot = n_records // (len(FILES) * spots_per_file)
    chunk = per_spot * REC
    print('取得: %d ファイル x %d 箇所 x %d 局面 = %d 局面 (%.0f MB)'
          % (len(FILES), spots_per_file, per_spot,
             per_spot * spots_per_file * len(FILES), n_records * REC / 1e6))
    os.makedirs(os.path.dirname(pool_path), exist_ok=True)
    got = 0
    with open(pool_path, 'wb') as out:
        for fn, size in FILES:
            nrec = size // REC
            for k in range(spots_per_file):
                off = (nrec * k // spots_per_file) * REC
                r = subprocess.run(
                    ['curl', '-sL', '--max-time', '300', '-r', '%d-%d' % (off, off + chunk - 1),
                     BASE + fn], capture_output=True)
                raw = r.stdout
                usable = (len(raw) // REC) * REC
                out.write(raw[:usable])
                got += usable // REC
                print('\r  %s +%d  計 %d 局面' % (fn, usable // REC, got), end='', flush=True)
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pool-dir', default='/mnt/e/nyugyoku24_hf')
    ap.add_argument('--records', type=int, default=2_000_000)
    ap.add_argument('--spots-per-file', type=int, default=10)
    ap.add_argument('--per-cell', type=int, default=300)
    ap.add_argument('--reuse', action='store_true')
    a = ap.parse_args()

    pool = os.path.join(a.pool_dir, 'pool_%dk.bin' % (a.records // 1000))
    if not a.reuse or not os.path.exists(pool):
        fetch_pool(pool, a.records, a.spots_per_file)

    arr = np.fromfile(pool, dtype=cshogi.PackedSfenValue)
    print('プール %d 局面' % len(arr))

    cells = collections.defaultdict(list)
    seen = set()
    b = cshogi.Board()
    stat = collections.Counter()
    mismatch = []
    for r in arr:
        b.set_psfen(r['sfen'])
        color = b.turn
        n, p, king_in = zone_stats(b, color)
        # 著者のラベルと、こちらの条文実装の判定を突き合わせる
        ours = declaration(b, color)
        theirs = 'win' if int(r['game_result']) == 1 else 'draw'
        if ours != theirs:
            stat['ラベル不一致'] += 1
            if len(mismatch) < 5:
                mismatch.append((b.sfen(), ours, theirs, n, p, king_in, b.is_check()))
            continue
        key = cell_of(color, p)
        if len(cells[key]) >= a.per_cell:
            continue
        s = b.sfen()
        if s in seen:
            stat['重複'] += 1
            continue
        seen.add(s)
        _, _, opp_king = zone_stats(b, 1 - color)
        cells[key].append((s, color, ours, n, p, king_in, int(b.is_check()),
                           int(r['gamePly']), int(opp_king)))

    print('ラベル不一致 %d / 重複 %d' % (stat['ラベル不一致'], stat['重複']))
    for m in mismatch:
        print('  不一致: 条文=%r 著者=%r  %d枚 %d点 玉%s 王手%s\n          %s'
              % (m[1], m[2], m[3], m[4], m[5], m[6], m[0]))

    rows = []
    print('\n%-6s %-7s %6s  %s' % ('宣言側', '宣言点数', '採取', '27点法 / 24点法'))
    short = []
    for color in (cshogi.BLACK, cshogi.WHITE):
        cname = '先手' if color == cshogi.BLACK else '後手'
        for p in range(DRAW_POINT, TOP_BIN + 1):
            got = cells.get((color, p), [])
            v27 = 'win' if p >= T27[color] else 'draw'
            v24 = 'win' if p >= WIN_POINT else 'draw'
            band = '判別' if v27 != v24 else '一致'
            label = '%d点%s' % (p, '以上' if p == TOP_BIN else '')
            print('  %-6s %-7s %6d  %-4s / %-4s  %s'
                  % (cname, label, len(got), v27, v24, band))
            if len(got) < a.per_cell:
                short.append('%s %s (%d/%d)' % (cname, label, len(got), a.per_cell))
            for s, c, want, n, pp, k, chk, ply, ok in got:
                rows.append((s, 'b' if c == cshogi.BLACK else 'w',
                             '%s%s' % (band, want), want, n, pp, int(k), chk, ply, ok, v27,
                             '%s %d点 %d枚 %s' % (cname, pp, n, '相入玉' if ok else '片方入玉')))
    if short:
        print('\n不足セル: %s' % ', '.join(short))

    hdr = [
        '# 入玉宣言法 24点法 適合性テスト集合 — 実戦由来 (tools/fetch_conformance_real.py が生成)',
        '# 出典: penguinkumimanu/nyugyoku24points (HuggingFace) より層化サンプリング。',
        '#       floodgate 2020年以降の棋譜から、片方の玉が敵陣三段目にあり、詰み・詰めろが無く、',
        '#       24点法で勝敗を判定できる局面を抽出したもの。',
        '# すべて「手番側が宣言できる」局面である。宣言すれば負ける陰性側は',
        '# positions/conformance.tsv (合成) が担う。',
        '#',
        '# 分類の「判別」= 27点法と24点法で答えが違う局面。27点法のエンジンはここで',
        '#   宣言勝ちと判断するが、24点法では指し直しにしかならない (第4項二・第7項)。',
        '# 列: sfen <TAB> 宣言側(b/w) <TAB> 分類 <TAB> 24点法の答え <TAB> 敵陣枚数 <TAB> 宣言点数'
        ' <TAB> 玉が敵陣 <TAB> 王手 <TAB> 手数 <TAB> 相入玉 <TAB> 27点法の答え <TAB> 説明',
    ]
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(hdr) + '\n')
        for r in rows:
            f.write('\t'.join(str(x) for x in r) + '\n')
    n_disc = sum(1 for r in rows if r[2].startswith('判別'))
    print('\n%s に %d 局面 (うち判別帯 %d = %.1f%%)'
          % (os.path.relpath(OUT), len(rows), n_disc, 100.0 * n_disc / max(1, len(rows))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
