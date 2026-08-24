# -*- coding: utf-8 -*-
"""相入玉局の最終図を 24点法 / 27点宣言法 で採点する。
   手を初形から再生し、CSA末尾の 'P1..'P9 / 'P+ / 'P- 最終図ブロックと照合して検証する。"""
import sys, os, collections
from multiprocessing import Pool

BIG   = {'HI', 'KA', 'RY', 'UM'}                       # 大駒 5点
SMALL = {'FU','KY','KE','GI','KI','TO','NY','NK','NG'} # 小駒 1点
UNPROMOTE = {'TO':'FU','NY':'KY','NK':'KE','NG':'GI','RY':'HI','UM':'KA'}

def pts(p):
    return 5 if p in BIG else (1 if p in SMALL else 0)

def parse_board_block(lines, prefix):
    """P1..P9 / P+ / P- を読む。board[(file,rank)] = (side, piece), hands[side][piece] = n"""
    board, hands = {}, {'+': collections.Counter(), '-': collections.Counter()}
    got_rows = 0
    for ln in lines:
        if not ln.startswith(prefix + 'P'):
            continue
        ln = ln[len(prefix):]
        if ln[1].isdigit():
            rank = int(ln[1]); body = ln[2:]
            got_rows += 1
            for i in range(9):
                cell = body[i*3:i*3+3]
                if len(cell) == 3 and cell[0] in '+-':
                    board[(9 - i, rank)] = (cell[0], cell[1:])
        elif ln[1] in '+-':
            side, body = ln[1], ln[2:]
            for i in range(0, len(body) - 3, 4):
                tok = body[i:i+4]
                if tok[:2] == '00':
                    hands[side][tok[2:]] += 1
                else:
                    board[(int(tok[0]), int(tok[1]))] = (side, tok[2:])
    return board, hands, got_rows

def replay(lines):
    board, hands, rows = parse_board_block(lines, '')
    if rows != 9:
        return None
    for ln in lines:
        if len(ln) >= 7 and ln[0] in '+-' and ln[1].isdigit():
            side = ln[0]
            src = (int(ln[1]), int(ln[2]))
            dst = (int(ln[3]), int(ln[4]))
            piece = ln[5:7]
            cap = board.get(dst)
            if cap:
                hands[side][UNPROMOTE.get(cap[1], cap[1])] += 1
            if src == (0, 0):
                base = UNPROMOTE.get(piece, piece)
                if hands[side][base] <= 0:
                    return None
                hands[side][base] -= 1
            else:
                if src not in board:
                    return None
                del board[src]
            board[dst] = (side, piece)
    return board, hands

def score(board, hands):
    """24点法(全所有駒) と 27点宣言法(敵陣3段目以内の盤上駒+持駒, 駒数)"""
    r = {'+': {'all': 0, 'zone': 0, 'zone_n': 0}, '-': {'all': 0, 'zone': 0, 'zone_n': 0}}
    for (f, rk), (side, p) in board.items():
        v = pts(p)
        r[side]['all'] += v
        in_zone = (rk <= 3) if side == '+' else (rk >= 7)
        if in_zone and p != 'OU':
            r[side]['zone'] += v
            r[side]['zone_n'] += 1
    for side in '+-':
        h = sum(pts(p) * n for p, n in hands[side].items())
        r[side]['all'] += h
        r[side]['zone'] += h
    return r

def analyze(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    rep = replay(lines)
    if rep is None:
        return ('REPLAY_FAIL', path, None)
    board, hands = rep
    fb, fh, frows = parse_board_block(lines, "'")
    if frows == 9:
        if board != fb or any(+hands[s] != +fh[s] for s in '+-'):
            return ('MISMATCH', path, None)
        checked = True
    else:
        checked = False
    r = score(board, hands)
    if r['+']['all'] + r['-']['all'] != 54:
        return ('BAD_TOTAL', path, r)
    return ('OK' if checked else 'OK_UNVERIFIED', path, r)

if __name__ == '__main__':
    tsv, root, want_end = sys.argv[1], sys.argv[2], sys.argv[3]
    names = []
    for ln in open(tsv, encoding='utf-8'):
        k, end, nm, rel = ln.rstrip('\n').split('\t')
        if k == 'AI' and (want_end == 'ALL' or end == want_end):
            names.append(rel)
    idx = {}
    for dp, _, fns in os.walk(root):
        for fn in fns:
            idx[fn] = os.path.join(dp, fn)
    paths = [idx[n] for n in names if n in idx]
    print(f'target games: {len(paths)} (from {len(names)} listed)')

    stat = collections.Counter()
    rows = []
    with Pool() as p:
        for status, path, r in p.imap_unordered(analyze, paths, chunksize=20):
            stat[status] += 1
            if r and status.startswith('OK'):
                rows.append((os.path.basename(path), r))
    print('parse status:', dict(stat))

    out = collections.Counter()
    dist = collections.Counter()
    decl = collections.Counter()
    detail = []
    for nm, r in rows:
        s, g = r['+']['all'], r['-']['all']
        if s <= 23:   res = 'SENTE_LOSE'
        elif g <= 23: res = 'GOTE_LOSE'
        else:         res = 'DRAW'
        out[res] += 1
        dist[s] += 1
        # 27点宣言法の到達度(王手判定は除く)
        sd = (r['+']['zone'] >= 28 and r['+']['zone_n'] >= 10)
        gd = (r['-']['zone'] >= 27 and r['-']['zone_n'] >= 10)
        decl[('S' if sd else '.') + ('G' if gd else '.')] += 1
        detail.append((nm, s, g, res, r['+']['zone'], r['+']['zone_n'], r['-']['zone'], r['-']['zone_n']))

    n = sum(out.values())
    print(f'\n=== 24点法による再採点 (n={n}) ===')
    for k in ('DRAW', 'SENTE_LOSE', 'GOTE_LOSE'):
        print(f'  {k:11s}: {out[k]:5d}  ({out[k]/n*100:5.1f}%)')
    print('\n=== 先手の点数分布 ===')
    for v in sorted(dist):
        bar = '#' * max(1, round(dist[v] / max(dist.values()) * 40))
        mark = ' <' if v in (23, 24, 30, 31) else ''
        print(f'  {v:2d}点: {dist[v]:4d} {bar}{mark}')
    print('\n=== 27点宣言法の条件充足 (点数+駒数のみ, 王手判定なし) ===')
    for k, v in decl.most_common():
        lab = {'..': 'どちらも不成立', 'S.': '先手のみ成立', '.G': '後手のみ成立', 'SG': '双方成立'}[k]
        print(f'  {lab}: {v}')
    with open(sys.argv[4], 'w', encoding='utf-8') as f:
        f.write('game\tsente24\tgote24\tresult24\tsente27zone\tsente27n\tgote27zone\tgote27n\n')
        for d in sorted(detail):
            f.write('\t'.join(map(str, d)) + '\n')
    print('\nwrote', sys.argv[4])
