# -*- coding: utf-8 -*-
"""相入玉・256手引き分け局で、途中の手番に 27点宣言勝ち が成立していたかを全手数スキャンする。
   CSA宣言法: (a)手番 (b)玉が敵陣3段目以内 (c)敵陣内に玉除く10枚以上
              (d)王手なし (e)持ち時間残 (f)先手28点/後手27点以上(敵陣内駒+持駒)"""
import sys, os, collections
from multiprocessing import Pool

BIG   = {'HI','KA','RY','UM'}
SMALL = {'FU','KY','KE','GI','KI','TO','NY','NK','NG'}
UNPROMOTE = {'TO':'FU','NY':'KY','NK':'KE','NG':'GI','RY':'HI','UM':'KA'}
def pts(p): return 5 if p in BIG else (1 if p in SMALL else 0)

GOLD = [(0,-1),(1,-1),(-1,-1),(1,0),(-1,0),(0,1)]
STEP = {'FU':[(0,-1)], 'KE':[(1,-2),(-1,-2)],
        'GI':[(0,-1),(1,-1),(-1,-1),(1,1),(-1,1)],
        'KI':GOLD,'TO':GOLD,'NY':GOLD,'NK':GOLD,'NG':GOLD,
        'OU':[(0,-1),(1,-1),(-1,-1),(1,0),(-1,0),(0,1),(1,1),(-1,1)],
        'UM':[(0,-1),(0,1),(1,0),(-1,0)], 'RY':[(1,-1),(-1,-1),(1,1),(-1,1)]}
SLIDE = {'KY':[(0,-1)], 'HI':[(0,-1),(0,1),(1,0),(-1,0)],
         'KA':[(1,-1),(-1,-1),(1,1),(-1,1)],
         'RY':[(0,-1),(0,1),(1,0),(-1,0)], 'UM':[(1,-1),(-1,-1),(1,1),(-1,1)]}

def attacks(board, side, target):
    """side の駒が target マスに利いているか"""
    d = 1 if side == '+' else -1          # 先手の前進は rank-1
    tf, tr = target
    for (f, r), (s, p) in board.items():
        if s != side:
            continue
        for df, dr in STEP.get(p, ()):
            if (f + df, r + dr * d) == target:
                return True
        for df, dr in SLIDE.get(p, ()):
            cf, cr = f + df, r + dr * d
            while 1 <= cf <= 9 and 1 <= cr <= 9:
                if (cf, cr) == target:
                    return True
                if (cf, cr) in board:
                    break
                cf += df; cr += dr * d
    return False

def declarable(board, hands, side):
    zone = 0; n = 0; king = None
    for (f, r), (s, p) in board.items():
        if s != side: continue
        inz = (r <= 3) if side == '+' else (r >= 7)
        if p == 'OU':
            king = (f, r)
            if not inz: return False
        elif inz:
            zone += pts(p); n += 1
    if king is None or n < 10: return False
    zone += sum(pts(p) * c for p, c in hands[side].items())
    if zone < (28 if side == '+' else 27): return False
    return not attacks(board, '-' if side == '+' else '+', king)

def analyze(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    board, hands = {}, {'+': collections.Counter(), '-': collections.Counter()}
    rows = 0
    for ln in lines:
        if ln.startswith('P') and len(ln) > 1:
            if ln[1].isdigit():
                rank = int(ln[1]); rows += 1
                for i in range(9):
                    c = ln[2+i*3:5+i*3]
                    if len(c) == 3 and c[0] in '+-':
                        board[(9-i, rank)] = (c[0], c[1:])
            elif ln[1] in '+-':
                for i in range(2, len(ln)-3, 4):
                    t = ln[i:i+4]
                    if t[:2] == '00': hands[ln[1]][t[2:]] += 1
                    else: board[(int(t[0]), int(t[1]))] = (ln[1], t[2:])
    if rows != 9: return None
    moves = [ln for ln in lines if len(ln) >= 7 and ln[0] in '+-' and ln[1].isdigit()]
    first = {'+': None, '-': None}      # 宣言可能になった最初の手数
    for i, ln in enumerate(moves):
        side = ln[0]
        if declarable(board, hands, side):
            if first[side] is None:
                first[side] = i          # i 手目を指す代わりに宣言できた
        src = (int(ln[1]), int(ln[2])); dst = (int(ln[3]), int(ln[4])); p = ln[5:7]
        cap = board.get(dst)
        if cap: hands[side][UNPROMOTE.get(cap[1], cap[1])] += 1
        if src == (0, 0): hands[side][UNPROMOTE.get(p, p)] -= 1
        else: del board[src]
        board[dst] = (side, p)
    # 最終局面(手番側)も判定
    side = '+' if len(moves) % 2 == 0 else '-'
    if declarable(board, hands, side) and first[side] is None:
        first[side] = len(moves)
    tot = {s: sum(pts(p) for (_, (ss, p)) in board.items() if ss == s)
              + sum(pts(p)*c for p, c in hands[s].items()) for s in '+-'}
    return (os.path.basename(path), len(moves), first['+'], first['-'], tot['+'], tot['-'])

if __name__ == '__main__':
    tsv, root, out = sys.argv[1], sys.argv[2], sys.argv[3]
    names = [ln.split('\t')[3].rstrip('\n') for ln in open(tsv, encoding='utf-8')
             if ln.startswith('AI\t\t')]
    idx = {}
    for dp, _, fns in os.walk(root):
        for fn in fns: idx[fn] = os.path.join(dp, fn)
    paths = [idx[n] for n in names if n in idx]
    res = []
    with Pool() as p:
        for r in p.imap_unordered(analyze, paths, chunksize=10):
            if r: res.append(r)
    print(f'games: {len(res)}')
    c = collections.Counter(); missed = []
    for nm, nm_moves, fs, fg, ts, tg in res:
        tag = ('S' if fs is not None else '.') + ('G' if fg is not None else '.')
        c[tag] += 1
        for side, fmv, mine, theirs in (('+', fs, ts, tg), ('-', fg, tg, ts)):
            if fmv is not None:
                missed.append((nm, side, fmv, nm_moves - fmv, mine, theirs))
    print('宣言条件が一度でも成立した局:')
    lab = {'..':'なし','S.':'先手のみ','.G':'後手のみ','SG':'双方'}
    for k, v in c.most_common(): print(f'  {lab[k]}: {v}')
    if missed:
        rem = [m[3] for m in missed]
        rem.sort()
        print(f'\n見逃し件数(側ごと): {len(missed)}')
        print(f'  成立してから終局までの残り手数: 中央値 {rem[len(rem)//2]}, 最大 {rem[-1]}, 最小 {rem[0]}')
        u24 = sum(1 for m in missed if m[4] <= 23)
        print(f'  うち 24点法では自分が負けだった側: {u24}')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('game\tside\tfirst_declarable_ply\tplies_remaining\tmy24\topp24\n')
        for m in sorted(missed): f.write('\t'.join(map(str, m)) + '\n')
    print('\nwrote', out)
