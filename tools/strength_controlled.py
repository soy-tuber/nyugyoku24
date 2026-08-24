# -*- coding: utf-8 -*-
"""レートインフレを補正して入玉巧拙の年次推移を見る。
   各年の入玉局に現れたレート分布の上位 P パーセンタイルを閾値とし、
   両者がそれを超える対局だけを集計する。
   使い方: python strength_controlled.py [percentile]   (既定 75)"""
import sys, os, collections, statistics

ROOT = r"D:\book_project"
P = float(sys.argv[1]) if len(sys.argv) > 1 else 75.0


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
        br, wr = fl(d['black_rate']), fl(d['white_rate'])
        if br is None or wr is None:
            continue
        rows.append((int(d['year']), d['kind'], d['end'], br, wr,
                     int(d['sente24']), int(d['gote24'])))

byyear = collections.defaultdict(list)
for r in rows:
    byyear[r[0]] += [r[3], r[4]]
thr = {}
for y, v in byyear.items():
    v.sort()
    thr[y] = v[min(len(v) - 1, int(len(v) * P / 100))]

print('レート閾値 = 各年の入玉局レート分布の上位%.0f%%点' % (100 - P))
print('\n%-6s %8s %6s %8s %10s %10s %10s' %
      ('year', '閾値', '相入玉', '打切', '宣言勝ち率', '打切率', '23点以下率'))
era_acc = collections.defaultdict(lambda: collections.Counter())
ERAS = [('2008-2013 KPPT以前', range(2008, 2014)),
        ('2014-2017 KPPT全盛', range(2014, 2018)),
        ('2018-2020 NNUE移行', range(2018, 2021)),
        ('2021-2023 NNUE定着', range(2021, 2024)),
        ('2024-2026 512手化後', range(2024, 2027))]
for y in sorted(thr):
    a = [r for r in rows if r[0] == y and r[1] == 'AI' and r[3] >= thr[y] and r[4] >= thr[y]]
    if len(a) < 10:
        print('%-6d %8.0f %6d   (標本不足)' % (y, thr[y], len(a)))
        continue
    n = len(a)
    k = sum(1 for r in a if r[2] == '%KACHI')
    m = [r for r in a if r[2] == '']
    lo = sum(1 for r in m if r[5] <= 23 or r[6] <= 23)
    print('%-6d %8.0f %6d %8d %9.1f%% %9.1f%% %9s' %
          (y, thr[y], n, len(m), k / n * 100, len(m) / n * 100,
           ('%.1f%%' % (lo / len(m) * 100)) if m else '-'))
    for lab, rng in ERAS:
        if y in rng:
            era_acc[lab]['n'] += n; era_acc[lab]['k'] += k
            era_acc[lab]['m'] += len(m); era_acc[lab]['lo'] += lo

print('\n=== 年代別集計 (強豪限定) ===')
print('%-22s %8s %10s %10s %12s' % ('era', '相入玉', '宣言勝ち率', '打切率', '打切局の23点以下率'))
for lab, _ in ERAS:
    c = era_acc[lab]
    if not c['n']:
        continue
    print('%-22s %8d %9.1f%% %9.1f%% %11s' %
          (lab, c['n'], c['k'] / c['n'] * 100, c['m'] / c['n'] * 100,
           ('%.1f%%' % (c['lo'] / c['m'] * 100)) if c['m'] else '-'))
