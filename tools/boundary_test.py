# -*- coding: utf-8 -*-
"""24点法の境界(23/24点)に段差があるかを検定する。
   段差比 = count(24)/count(23) を、境界でない近傍ペアの比の分布と比較する。
   使い方: python boundary_test.py [最低レート]"""
import sys, os, collections, statistics

ROOT = r"D:\book_project"
MINR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0


def fl(x):
    try:
        return float(x)
    except ValueError:
        return None


rows = []
with open(os.path.join(ROOT, 'nyugyoku_all_years.tsv'), encoding='utf-8') as fh:
    hdr = fh.readline().rstrip('\n').split('\t')
    for ln in fh:
        d = dict(zip(hdr, ln.rstrip('\n').split('\t')))
        if d['kind'] != 'AI':
            continue
        br, wr = fl(d['black_rate']), fl(d['white_rate'])
        if MINR and (br is None or wr is None or br < MINR or wr < MINR):
            continue
        rows.append((int(d['year']), d['end'], int(d['moves']),
                     int(d['sente24']), int(d['gote24'])))

ERAS = [('2008-2013 KPPT以前', range(2008, 2014)),
        ('2014-2017 KPPT全盛', range(2014, 2018)),
        ('2018-2020 NNUE移行', range(2018, 2021)),
        ('2021-2023 NNUE定着', range(2021, 2024)),
        ('2024-2026 512手化後', range(2024, 2027))]

print('rating filter: >= %.0f' % MINR if MINR else 'rating filter: none')
print('\n=== 打ち切り引き分け局の点数分布: 23/24点の境界に段差があるか ===')
print('※ 段差比 = n(24点)/n(23点)。24点法を目的関数に持つなら 1 より有意に大きくなるはず')
print('%-22s %6s %8s %8s %8s %9s %10s' %
      ('era', 'n', 'n(23)', 'n(24)', '段差比', '近傍比中央', '近傍比範囲'))
for lab, rng in ERAS:
    a = [r for r in rows if r[0] in rng and r[1] == '']
    if len(a) < 30:
        print('%-22s %6d  (標本不足)' % (lab, len(a)))
        continue
    d = collections.Counter()
    for _, _, _, s, g in a:
        d[s] += 1
        d[g] += 1
    n23, n24 = d[23], d[24]
    step = n24 / n23 if n23 else float('nan')
    # 近傍の非境界ペア k -> k+1 の比
    near = []
    for k in list(range(16, 23)) + list(range(24, 33)):
        if d[k] >= 5 and d[k + 1] >= 1:
            near.append(d[k + 1] / d[k])
    near.sort()
    print('%-22s %6d %8d %8d %8.2f %9.2f %10s' %
          (lab, len(a), n23, n24, step, statistics.median(near),
           '%.2f-%.2f' % (near[0], near[-1])))

print('\n=== 参考: 打ち切り時点で23点以下だった側の割合 (相入玉・打ち切り局) ===')
print('%-22s %6s %10s %10s' % ('era', 'n', '先手<24', '後手<24'))
for lab, rng in ERAS:
    a = [r for r in rows if r[0] in rng and r[1] == '']
    if len(a) < 30:
        continue
    s = sum(1 for r in a if r[3] <= 23)
    g = sum(1 for r in a if r[4] <= 23)
    print('%-22s %6d %9.1f%% %9.1f%%' % (lab, len(a), s / len(a) * 100, g / len(a) * 100))

print('\n=== 相入玉局が宣言勝ちで決着した割合 (入玉巧拙の直接指標) ===')
print('%-22s %6s %10s %10s' % ('era', '相入玉', '宣言勝ち', '打ち切り'))
for lab, rng in ERAS:
    a = [r for r in rows if r[0] in rng]
    if not a:
        continue
    k = sum(1 for r in a if r[1] == '%KACHI')
    m = sum(1 for r in a if r[1] == '')
    print('%-22s %6d %9.1f%% %9.1f%%' % (lab, len(a), k / len(a) * 100, m / len(a) * 100))
