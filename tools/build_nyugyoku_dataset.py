# -*- coding: utf-8 -*-
"""floodgate 全年アーカイブから入玉局のデータセットを構築する。
   年ごとに 7z 展開 -> 全局スキャン -> 入玉局を dataset へ退避 -> 展開を削除。
   出力: nyugyoku_all_years.tsv (1局1行), year_summary.tsv"""
import os, sys, shutil, subprocess, collections
from multiprocessing import Pool

SEVENZ = r"C:\Program Files\7-Zip\7z.exe"
ROOT   = r"D:\book_project"
EXT    = os.path.join(ROOT, "_ext")
DS     = os.path.join(ROOT, "nyugyoku_dataset")

BIG   = {'HI', 'KA', 'RY', 'UM'}
SMALL = {'FU', 'KY', 'KE', 'GI', 'KI', 'TO', 'NY', 'NK', 'NG'}
UNPROMOTE = {'TO': 'FU', 'NY': 'KY', 'NK': 'KE', 'NG': 'GI', 'RY': 'HI', 'UM': 'KA'}


def pts(p):
    return 5 if p in BIG else (1 if p in SMALL else 0)


GOLD = [(0, -1), (1, -1), (-1, -1), (1, 0), (-1, 0), (0, 1)]
STEP = {'FU': [(0, -1)], 'KE': [(1, -2), (-1, -2)],
        'GI': [(0, -1), (1, -1), (-1, -1), (1, 1), (-1, 1)],
        'KI': GOLD, 'TO': GOLD, 'NY': GOLD, 'NK': GOLD, 'NG': GOLD,
        'OU': [(0, -1), (1, -1), (-1, -1), (1, 0), (-1, 0), (0, 1), (1, 1), (-1, 1)],
        'UM': [(0, -1), (0, 1), (1, 0), (-1, 0)],
        'RY': [(1, -1), (-1, -1), (1, 1), (-1, 1)]}
SLIDE = {'KY': [(0, -1)], 'HI': [(0, -1), (0, 1), (1, 0), (-1, 0)],
         'KA': [(1, -1), (-1, -1), (1, 1), (-1, 1)],
         'RY': [(0, -1), (0, 1), (1, 0), (-1, 0)],
         'UM': [(1, -1), (-1, -1), (1, 1), (-1, 1)]}
BACK = ['KY', 'KE', 'GI', 'KI', 'OU', 'KI', 'GI', 'KE', 'KY']   # file 9 -> 1


def hirate():
    b = {}
    for i, p in enumerate(BACK):
        b[(9 - i, 1)] = ('-', p)
        b[(9 - i, 9)] = ('+', p)
    b[(8, 2)] = ('-', 'HI'); b[(2, 2)] = ('-', 'KA')
    b[(8, 8)] = ('+', 'KA'); b[(2, 8)] = ('+', 'HI')
    for f in range(1, 10):
        b[(f, 3)] = ('-', 'FU'); b[(f, 7)] = ('+', 'FU')
    return b


def attacks(board, side, target):
    d = 1 if side == '+' else -1
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


def zone_score(board, hands, side):
    z = n = 0
    king = None
    king_in = False
    for (f, r), (s, p) in board.items():
        if s != side:
            continue
        inz = (r <= 3) if side == '+' else (r >= 7)
        if p == 'OU':
            king = (f, r); king_in = inz
        elif inz:
            z += pts(p); n += 1
    z += sum(pts(p) * c for p, c in hands[side].items())
    return z, n, king, (king is not None and king_in)


def declarable(board, hands, side):
    z, n, king, kin = zone_score(board, hands, side)
    if not kin or n < 10:
        return False
    if z < (28 if side == '+' else 27):
        return False
    return not attacks(board, '-' if side == '+' else '+', king)


def total24(board, hands, side):
    return (sum(pts(p) for (_, (s, p)) in board.items() if s == side)
            + sum(pts(p) * c for p, c in hands[side].items()))


def read_pos(lines, prefix):
    board = {}
    hands = {'+': collections.Counter(), '-': collections.Counter()}
    rows = 0
    for ln in lines:
        if not ln.startswith(prefix + 'P'):
            continue
        ln = ln[len(prefix):]
        if len(ln) < 2:
            continue
        if ln[1].isdigit():
            rank = int(ln[1]); rows += 1
            for i in range(9):
                c = ln[2 + i * 3:5 + i * 3]
                if len(c) == 3 and c[0] in '+-':
                    board[(9 - i, rank)] = (c[0], c[1:])
        elif ln[1] == 'I':
            board = hirate(); rows = 9
            for i in range(2, len(ln) - 3, 4):
                t = ln[i:i + 4]
                board.pop((int(t[0]), int(t[1])), None)
        elif ln[1] in '+-':
            for i in range(2, len(ln) - 3, 4):
                t = ln[i:i + 4]
                if t[:2] == '00':
                    hands[ln[1]][t[2:]] += 1
                else:
                    board[(int(t[0]), int(t[1]))] = (ln[1], t[2:])
    return board, hands, rows


def analyze(arg):
    year, path = arg
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().split('\n')
    except OSError:
        return ('READFAIL',)
    endmark = ''
    br = wr = ''
    moves = []
    for ln in lines:
        if not ln:
            continue
        c = ln[0]
        if c in '+-' and len(ln) >= 7 and ln[1].isdigit():
            moves.append(ln)
        elif c == '%':
            endmark = ln.split(',')[0].strip()
        elif c == "'":
            if ln.startswith("'black_rate:"):
                br = ln.rsplit(':', 1)[1]
            elif ln.startswith("'white_rate:"):
                wr = ln.rsplit(':', 1)[1]
    board, hands, rows = read_pos(lines, '')
    if rows != 9:
        return ('BROKEN',)

    # 安い判定: 玉だけ追って分類
    ks = kg = None
    for (f, r), (s, p) in board.items():
        if p == 'OU':
            if s == '+':
                ks = (f, r)
            else:
                kg = (f, r)
    if ks is None or kg is None:
        return ('BROKEN',)
    for ln in moves:
        if ln[5:7] == 'OU':
            sq = (int(ln[3]), int(ln[4]))
            if ln[0] == '+':
                ks = sq
            else:
                kg = sq
    s_in, g_in = ks[1] <= 3, kg[1] >= 7
    kind = 'AI' if (s_in and g_in) else ('KATA' if (s_in or g_in) else 'NONE')
    if kind == 'NONE':
        return ('NONE',)

    # 本再生 + 宣言可否スキャン
    first = {'+': None, '-': None}
    for i, ln in enumerate(moves):
        side = ln[0]
        if first[side] is None and declarable(board, hands, side):
            first[side] = i
        src = (int(ln[1]), int(ln[2])); dst = (int(ln[3]), int(ln[4])); p = ln[5:7]
        cap = board.get(dst)
        if cap:
            hands[side][UNPROMOTE.get(cap[1], cap[1])] += 1
        if src == (0, 0):
            b = UNPROMOTE.get(p, p)
            if hands[side][b] <= 0:
                return ('REPLAYFAIL',)
            hands[side][b] -= 1
        else:
            if src not in board:
                return ('REPLAYFAIL',)
            del board[src]
        board[dst] = (side, p)
    side = '+' if len(moves) % 2 == 0 else '-'
    if first[side] is None and declarable(board, hands, side):
        first[side] = len(moves)

    fb, fh, frows = read_pos(lines, "'")
    if frows == 9:
        verified = 'Y' if (board == fb and all(+hands[s] == +fh[s] for s in '+-')) else 'N'
    else:
        verified = '-'
    s24, g24 = total24(board, hands, '+'), total24(board, hands, '-')
    if s24 + g24 != 54:
        return ('BADTOTAL',)
    sz, sn, _, _ = zone_score(board, hands, '+')
    gz, gn, _, _ = zone_score(board, hands, '-')
    return ('OK', year, kind, endmark, len(moves), br, wr, s24, g24,
            sz, sn, gz, gn, first['+'], first['-'], verified, path)


def main():
    years = sys.argv[1:]
    os.makedirs(DS, exist_ok=True)
    out = open(os.path.join(ROOT, 'nyugyoku_all_years.tsv'), 'a', encoding='utf-8')
    if out.tell() == 0:
        out.write('year\tkind\tend\tmoves\tblack_rate\twhite_rate\tsente24\tgote24'
                  '\tsente_zone\tsente_zone_n\tgote_zone\tgote_zone_n'
                  '\tdecl_ply_s\tdecl_ply_g\tverified\tgame\n')
    summ = open(os.path.join(ROOT, 'year_summary.tsv'), 'a', encoding='utf-8')
    if summ.tell() == 0:
        summ.write('year\ttotal\tAI\tKATA\tNONE\tbad\n')
    pool = Pool()
    for y in years:
        arc = os.path.join(ROOT, 'wdoor%s.7z' % y)
        pre = os.path.join(ROOT, 'csa2017')
        src = pre if (y == '2017' and os.path.isdir(pre)) else os.path.join(EXT, y)
        if not os.path.isdir(src):
            os.makedirs(src, exist_ok=True)
            subprocess.run([SEVENZ, 'x', arc, '-o' + src, '-bso0', '-bsp0', '-y'], check=True)
        files = [(y, os.path.join(dp, fn)) for dp, _, fns in os.walk(src)
                 for fn in fns if fn.endswith('.csa')]
        c = collections.Counter()
        rows = []
        for r in pool.imap_unordered(analyze, files, chunksize=100):
            c[r[0]] += 1
            if r[0] == 'OK':
                c[r[2]] += 1
                rows.append(r)
        ddir = os.path.join(DS, y)
        os.makedirs(ddir, exist_ok=True)
        for r in rows:
            out.write('\t'.join('' if v is None else str(v) for v in r[1:-1]))
            out.write('\t' + os.path.basename(r[-1]) + '\n')
            shutil.copy2(r[-1], ddir)
        bad = c['BROKEN'] + c['REPLAYFAIL'] + c['BADTOTAL'] + c['READFAIL']
        summ.write('%s\t%d\t%d\t%d\t%d\t%d\n' % (y, len(files), c['AI'], c['KATA'], c['NONE'], bad))
        out.flush(); summ.flush()
        print('%s: total=%d AI=%d KATA=%d bad=%d' % (y, len(files), c['AI'], c['KATA'], bad), flush=True)
        if src.startswith(EXT):
            shutil.rmtree(src, ignore_errors=True)
    pool.close(); pool.join()
    out.close(); summ.close()


if __name__ == '__main__':
    main()
