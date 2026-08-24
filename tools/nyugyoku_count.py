# -*- coding: utf-8 -*-
"""floodgate CSA: count 相入玉 / 片方入玉 by final king positions."""
import sys, os, collections
from multiprocessing import Pool

def analyze(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().split('\n')
    except OSError:
        return None
    ks = kg = None          # sente / gote king square (file, rank)
    nmove = 0
    endmark = ''
    gname = ''
    for ln in lines:
        if not ln:
            continue
        c = ln[0]
        if c == 'P':
            if len(ln) > 1 and ln[1].isdigit():          # P1..P9 board rows
                rank = int(ln[1]); body = ln[2:]
                for i in range(9):
                    cell = body[i*3:i*3+3]
                    if cell[1:] == 'OU':
                        if cell[0] == '+': ks = (9-i, rank)
                        elif cell[0] == '-': kg = (9-i, rank)
            elif ln.startswith('PI'):                     # standard start (+ drops)
                ks, kg = (5, 9), (5, 1)
            elif len(ln) > 1 and ln[1] in '+-':           # P+59OU style
                side, body = ln[1], ln[2:]
                for i in range(0, len(body) - 3, 4):
                    tok = body[i:i+4]
                    if tok[2:] == 'OU' and tok[:2] != '00':
                        sq = (int(tok[0]), int(tok[1]))
                        if side == '+': ks = sq
                        else: kg = sq
        elif c in '+-' and len(ln) >= 7 and ln[1].isdigit():   # a move
            nmove += 1
            if ln[5:7] == 'OU':
                sq = (int(ln[3]), int(ln[4]))
                if c == '+': ks = sq
                else: kg = sq
        elif c == '%':
            endmark = ln.split(',')[0].strip()
        elif ln.startswith("$EVENT:"):
            gname = ln[7:].strip()
    if ks is None or kg is None:
        return ('BROKEN', '', '', 0, path)
    s_in = ks[1] <= 3        # sente king inside gote camp
    g_in = kg[1] >= 7        # gote  king inside sente camp
    kind = 'AI' if (s_in and g_in) else ('KATA' if (s_in or g_in) else 'NONE')
    return (kind, endmark, gname, nmove, path)

if __name__ == '__main__':
    root = sys.argv[1]
    out = sys.argv[2]
    files = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith('.csa'):
                files.append(os.path.join(dp, fn))
    files.sort()
    cnt = collections.Counter()
    end_by_kind = collections.defaultdict(collections.Counter)
    ai_list, kata_list = [], []
    with Pool() as p:
        for r in p.imap_unordered(analyze, files, chunksize=200):
            if r is None:
                cnt['READFAIL'] += 1; continue
            kind, endmark, gname, nmove, path = r
            cnt[kind] += 1
            end_by_kind[kind][endmark] += 1
            rel = os.path.basename(path)
            if kind == 'AI': ai_list.append((rel, endmark, nmove))
            elif kind == 'KATA': kata_list.append((rel, endmark, nmove))
    print('total files :', len(files))
    for k in ('AI', 'KATA', 'NONE', 'BROKEN', 'READFAIL'):
        print(f'{k:9s}: {cnt[k]}')
    print()
    for k in ('AI', 'KATA'):
        print(f'--- end marks [{k}] ---')
        for m, n in end_by_kind[k].most_common(12):
            print(f'   {m or "(none)":16s} {n}')
    with open(out, 'w', encoding='utf-8') as f:
        for tag, lst in (('AI', ai_list), ('KATA', kata_list)):
            for rel, endmark, nmove in sorted(lst):
                f.write(f'{tag}\t{endmark}\t{nmove}\t{rel}\n')
    print('\nwrote', out)
