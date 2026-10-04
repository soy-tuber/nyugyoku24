# -*- coding: utf-8 -*-
"""Rust 版 (nyugyoku-mini stats) と Python 版 (engine/) の宣言関連の量を全局面で照合する。

照合する量: 敵陣枚数 / 宣言点数 / 所有点数 / 玉が敵陣 (先後とも)、手番側の宣言判定 (24点法・27点法)
Python 版は第5項の手数条件を見ないので、手数500未満の局面だけを使う。

    cargo build --release
    python mini24/tools/compare_python.py [追加のSFENファイル ...]
"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'engine'))
import cshogi
from engine_decl24 import declaration, zone_stats
from engine_unified import full_stats

BIN = os.path.join(HERE, '..', 'target', 'release', 'nyugyoku-mini')


def read_sfens(path):
    out = []
    for ln in open(path, encoding='utf-8'):
        if ln.startswith('#') or not ln.strip():
            continue
        out.append(ln.split('\t')[0].strip())
    return out


def decl27(b):
    c = b.turn
    n, p, k = zone_stats(b, c)
    if not k or n < 10 or b.is_check():
        return '-'
    return 'win' if p >= (28 if c == cshogi.BLACK else 27) else '-'


def main():
    files = [os.path.join(ROOT, 'positions', f) for f in
             ('aiiru_bench.tsv', 'tune40.tsv', 'holdout40.tsv', 'conformance.tsv')] + sys.argv[1:]
    sfens = []
    for f in files:
        sfens += [s for s in read_sfens(f) if int(s.split()[3]) < 500]
    out = subprocess.run([BIN, 'stats'], input='\n'.join(sfens), capture_output=True,
                         text=True, check=True).stdout.splitlines()
    assert len(out) == len(sfens), (len(out), len(sfens))
    bad = 0
    for s, ln in zip(sfens, out):
        c = ln.split('\t')
        b = cshogi.Board(s)
        want = []
        for color in (cshogi.BLACK, cshogi.WHITE):
            n, p, k = zone_stats(b, color)
            owned = full_stats(b, color)[0]
            want += [n, p, owned, int(k)]
        got = [int(c[1]), int(c[2]), int(c[3]), int(c[4]), int(c[7]), int(c[8]), int(c[9]), int(c[10])]
        d24 = declaration(b, b.turn) or '-'
        if got != want or c[13] != d24 or c[14] != decl27(b):
            bad += 1
            if bad <= 10:
                print('MISMATCH', s, 'rust', got, c[13], c[14], 'python', want, d24, decl27(b))
    print('%d 局面を照合: 不一致 %d' % (len(sfens), bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
