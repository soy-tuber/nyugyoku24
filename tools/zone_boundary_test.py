# -*- coding: utf-8 -*-
"""入玉宣言法の正しい点数 (敵陣3段目以内の駒 + 持ち駒) で境界を検定する。

重要な区別:
  入玉宣言法 27点法 : 敵陣3段目以内+持駒。先手28点/後手27点で勝ち。
  入玉宣言法 24点法 : 同じ数え方。31点以上で勝ち、24-30点で無勝負。
  持将棋(合意)      : 盤上どこでも+持駒 (合計54点)。24点未満で負け。 <- 別物

陽性対照:
  floodgate は27点法なので、28点(先手)/27点(後手)を超えた局面は宣言されて
  終わっているはず。よって打ち切り局の敵陣内点数の分布は 27/28 で切れる (打ち切り崖)
  はずである。この崖が観測できれば、この測定手法にルール由来の構造を
  検出する力があることが示される。その上で 24 に崖が無いことが意味を持つ。
"""
import os, collections, statistics

ROOT = r"D:\book_project"

rows = []
with open(os.path.join(ROOT, 'nyugyoku_all_years.tsv'), encoding='utf-8') as fh:
    hdr = fh.readline().rstrip('\n').split('\t')
    for ln in fh:
        d = dict(zip(hdr, ln.rstrip('\n').split('\t')))
        if d['kind'] != 'AI':
            continue
        rows.append((int(d['year']), d['end'],
                     int(d['sente_zone']), int(d['sente_zone_n']),
                     int(d['gote_zone']), int(d['gote_zone_n']),
                     int(d['sente24']), int(d['gote24'])))

# 256手時代のみ (2024年に512手化しているため)
cut = [r for r in rows if r[0] <= 2023 and r[1] == '']
print('打ち切り引き分けの相入玉局 (2008-2023): %d局\n' % len(cut))

print('=== 敵陣内点数の分布 (入玉宣言法の正しい数え方) ===')
print('※ 先手は28点、後手は27点で宣言勝ちできるので、そこで分布が切れるはず')
for lab, zi, ni, thr in (('先手', 2, 3, 28), ('後手', 4, 5, 27)):
    d = collections.Counter(r[zi] for r in cut)
    mx = max(d.values())
    print('\n--- %s (27点法の閾値=%d点) ---' % (lab, thr))
    for v in range(0, 42):
        if d[v]:
            mark = ''
            if v == 23:
                mark = '  <- 24点法で負けになる上限'
            elif v == 24:
                mark = '  <- 24点法で無勝負になる下限'
            elif v == thr - 1:
                mark = '  <- 27点法の閾値の直下'
            elif v == thr:
                mark = '  <- 27点法の閾値 (宣言可能)'
            elif v == 31:
                mark = '  <- 24点法で勝ちになる下限'
            print('  %2d点 %5d %s%s' % (v, d[v], '#' * max(1, round(d[v] / mx * 40)), mark))

print('\n=== 崖の検定 ===')
print('%-10s %-26s %8s %8s %8s' % ('側', '境界', 'n(下)', 'n(上)', '比'))


def step(d, k):
    lo, hi = d[k], d[k + 1]
    return lo, hi, (hi / lo if lo else float('nan'))


for lab, zi, thr in (('先手', 2, 28), ('後手', 4, 27)):
    d = collections.Counter(r[zi] for r in cut)
    for k, name in ((23, '23->24 (24点法の無勝負線)'),
                    (30, '30->31 (24点法の勝ち線)'),
                    (thr - 1, '%d->%d (27点法の宣言線)' % (thr - 1, thr))):
        lo, hi, ratio = step(d, k)
        print('%-10s %-26s %8d %8d %8.2f' % (lab, name, lo, hi, ratio))
    near = []
    for k in range(10, 36):
        if k in (23, 30, thr - 1) or d[k] < 5:
            continue
        near.append(d[k + 1] / d[k])
    near.sort()
    print('%-10s %-26s %8s %8s %8.2f  (範囲 %.2f-%.2f)'
          % (lab, '非境界の近傍比 中央値', '', '', statistics.median(near), near[0], near[-1]))

print('\n=== 10枚条件の充足状況 (宣言に必須) ===')
for lab, ni in (('先手', 3), ('後手', 5)):
    d = collections.Counter(r[ni] for r in cut)
    ok = sum(v for k, v in d.items() if k >= 10)
    print('  %s: 敵陣内10枚以上 %d局 (%.1f%%)  中央値 %d枚'
          % (lab, ok, ok / len(cut) * 100, statistics.median([r[ni] for r in cut])))

print('\n=== 24点法なら何が起きたか (敵陣内点数ベース) ===')
w = collections.Counter()
for r in cut:
    sz, sn, gz, gn = r[2], r[3], r[4], r[5]
    s_ok = sn >= 10
    g_ok = gn >= 10
    s = ('win' if sz >= 31 else 'draw' if sz >= 24 else 'lose') if s_ok else 'ng'
    g = ('win' if gz >= 31 else 'draw' if gz >= 24 else 'lose') if g_ok else 'ng'
    w[(s, g)] += 1
print('  (10枚条件を満たさない場合は ng = そもそも宣言できない)')
for k, v in w.most_common(10):
    print('  先手%-5s 後手%-5s : %5d (%.1f%%)' % (k[0], k[1], v, v / len(cut) * 100))
