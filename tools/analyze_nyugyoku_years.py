# -*- coding: utf-8 -*-
"""nyugyoku_all_years.tsv / year_summary.tsv を年次集計する。
   使い方: python analyze_nyugyoku_years.py [最低レート]"""
import sys, os, collections

ROOT = r"D:\book_project"
MINR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0


def f(x):
    try:
        return float(x)
    except ValueError:
        return None


rows = []
with open(os.path.join(ROOT, 'nyugyoku_all_years.tsv'), encoding='utf-8') as fh:
    hdr = fh.readline().rstrip('\n').split('\t')
    for ln in fh:
        v = ln.rstrip('\n').split('\t')
        d = dict(zip(hdr, v))
        d['moves'] = int(d['moves'])
        d['sente24'] = int(d['sente24']); d['gote24'] = int(d['gote24'])
        d['sente_zone_n'] = int(d['sente_zone_n']); d['gote_zone_n'] = int(d['gote_zone_n'])
        d['br'] = f(d['black_rate']); d['wr'] = f(d['white_rate'])
        d['ds'] = int(d['decl_ply_s']) if d['decl_ply_s'] else None
        d['dg'] = int(d['decl_ply_g']) if d['decl_ply_g'] else None
        rows.append(d)

tot = {}
with open(os.path.join(ROOT, 'year_summary.tsv'), encoding='utf-8') as fh:
    fh.readline()
    for ln in fh:
        y, t, ai, kata, none, bad = ln.split('\t')
        tot[y] = (int(t), int(ai), int(kata), int(bad))

if MINR:
    rows = [d for d in rows if d['br'] and d['wr'] and d['br'] >= MINR and d['wr'] >= MINR]
    print('rating filter: both >= %.0f  (n=%d)' % (MINR, len(rows)))

years = sorted(tot)
print('\n=== 年次: 入玉の発生率 ===')
print('year  総局数    相入玉  率      片方入玉  率      検証NG')
for y in years:
    t, ai, kata, bad = tot[y]
    print('%s %8d %7d %6.2f%% %8d %6.2f%% %6d'
          % (y, t, ai, ai / t * 100, kata, kata / t * 100, bad))

print('\n=== 相入玉局の決着内訳 (レートフィルタ後) ===')
print('year   相入玉  宣言勝ち  率     256手切れ 率      投了   その他')
for y in years:
    a = [d for d in rows if d['year'] == y and d['kind'] == 'AI']
    if not a:
        continue
    n = len(a)
    k = sum(1 for d in a if d['end'] == '%KACHI')
    m = sum(1 for d in a if d['end'] == '')
    t_ = sum(1 for d in a if d['end'] == '%TORYO')
    print('%s %7d %8d %6.1f%% %8d %6.1f%% %6d %6d'
          % (y, n, k, k / n * 100, m, m / n * 100, t_, n - k - m - t_))

print('\n=== 256手切れの相入玉局を24点法で再採点 ===')
print('year      n   引分け   率      先手負け 後手負け  決着率   23点   24点  段差比')
agg = collections.Counter()
for y in years:
    a = [d for d in rows if d['year'] == y and d['kind'] == 'AI' and d['end'] == '']
    if not a:
        continue
    n = len(a)
    dr = sum(1 for d in a if d['sente24'] >= 24 and d['gote24'] >= 24)
    sl = sum(1 for d in a if d['sente24'] <= 23)
    gl = sum(1 for d in a if d['gote24'] <= 23)
    c23 = sum(1 for d in a if d['sente24'] == 23) + sum(1 for d in a if d['gote24'] == 23)
    c24 = sum(1 for d in a if d['sente24'] == 24) + sum(1 for d in a if d['gote24'] == 24)
    agg['n'] += n; agg['dr'] += dr; agg['sl'] += sl; agg['gl'] += gl
    agg['c23'] += c23; agg['c24'] += c24
    ratio = ('%.2f' % (c24 / c23)) if c23 else '-'
    print('%s %6d %7d %6.1f%% %8d %8d %6.1f%% %6d %6d %7s'
          % (y, n, dr, dr / n * 100, sl, gl, (sl + gl) / n * 100, c23, c24, ratio))
print('%-4s %6d %7d %6.1f%% %8d %8d %6.1f%% %6d %6d %7s'
      % ('計', agg['n'], agg['dr'], agg['dr'] / agg['n'] * 100, agg['sl'], agg['gl'],
         (agg['sl'] + agg['gl']) / agg['n'] * 100, agg['c23'], agg['c24'],
         '%.2f' % (agg['c24'] / agg['c23']) if agg['c23'] else '-'))

print('\n=== 27点宣言勝ちのうち24点法なら引き分けだった局 ===')
print('year   宣言勝ち  24点法で引分  率')
for y in years:
    a = [d for d in rows if d['year'] == y and d['kind'] == 'AI' and d['end'] == '%KACHI']
    if not a:
        continue
    n = len(a)
    dr = sum(1 for d in a if d['sente24'] >= 24 and d['gote24'] >= 24)
    print('%s %8d %12d %6.1f%%' % (y, n, dr, dr / n * 100))

print('\n=== 宣言可能だったのに宣言しなかった局 (王手判定込み・打ち切り手を除く) ===')
print('year   相入玉  見逃し  率     残り手数中央値')
for y in years:
    a = [d for d in rows if d['year'] == y and d['kind'] == 'AI']
    if not a:
        continue
    miss = []
    for d in a:
        for pl in (d['ds'], d['dg']):
            if pl is not None and d['moves'] - pl > 0 and d['end'] != '%KACHI':
                miss.append(d['moves'] - pl)
    med = sorted(miss)[len(miss) // 2] if miss else 0
    print('%s %7d %7d %6.1f%% %10d' % (y, len(a), len(miss), len(miss) / len(a) * 100, med))

print('\n=== 24点分布 (256手切れ・相入玉, 先手の点数) 年代別 ===')
eras = [('2008-2013 (KPPT前)', range(2008, 2014)),
        ('2014-2017 (KPPT)', range(2014, 2018)),
        ('2018-2021 (NNUE)', range(2018, 2022)),
        ('2022-2026 (NNUE後期)', range(2022, 2027))]
for lab, rng in eras:
    a = [d for d in rows if int(d['year']) in rng and d['kind'] == 'AI' and d['end'] == '']
    if not a:
        continue
    dist = collections.Counter(d['sente24'] for d in a)
    n = len(a)
    lo = sum(v for k, v in dist.items() if k <= 23)
    print('\n%s  n=%d  先手23点以下 %.1f%%' % (lab, n, lo / n * 100))
    mx = max(dist.values())
    for v in range(0, 55):
        if dist[v]:
            mark = ' <=23' if v == 23 else (' <24' if v == 24 else '')
            print('  %2d点 %4d %s%s' % (v, dist[v], '#' * max(1, round(dist[v] / mx * 40)), mark))
