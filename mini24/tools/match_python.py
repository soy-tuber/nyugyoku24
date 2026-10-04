# -*- coding: utf-8 -*-
"""Rust 版 (USI) と Python 版 (engine_unified.UnifiedEngine) を相入玉局面から対局させる。

    cargo build --release
    python mini24/tools/match_python.py [局面数] [Rust の1手の秒数] [Python の深さ] [上限手数]

先後を入れ替えて 局面数 x 2 局。終局:
    宣言勝ち (24点法)。Rust 版の `bestmove win` は Python 版の declaration() で検算し、
    条件を満たしていなければ宣言した側の反則負けとする
    詰み / 千日手 / 上限手数 (引き分け)
"""
import os, sys, subprocess, collections, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'engine'))
import cshogi
from engine_decl24 import declaration
from engine_unified import UnifiedEngine, full_stats

BIN = os.environ.get('MINI_BIN') or os.path.join(HERE, '..', 'target', 'release', 'nyugyoku-mini')


class Usi:
    def __init__(self, movetime_ms):
        self.p = subprocess.Popen([BIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.movetime = movetime_ms
        self.send('usi'); self.wait('usiok')
        self.send('isready'); self.wait('readyok')

    def send(self, s):
        self.p.stdin.write(s + '\n')

    def wait(self, prefix):
        while True:
            ln = self.p.stdout.readline()
            if not ln:
                raise RuntimeError('engine died')
            if ln.startswith(prefix):
                return ln.strip()

    def go(self, sfen, moves):
        self.send('position sfen %s%s' % (sfen, (' moves ' + ' '.join(moves)) if moves else ''))
        self.send('go movetime %d' % self.movetime)
        return self.wait('bestmove').split()[1]

    def close(self):
        self.send('quit')
        self.p.wait()


def play(sfen, rust_is_black, usi, depth, maxply):
    b = cshogi.Board(sfen)
    py = UnifiedEngine(depth)
    rust = cshogi.BLACK if rust_is_black else cshogi.WHITE
    moves = []
    for i in range(maxply):
        side = b.turn
        if side == rust:
            bm = usi.go(sfen, moves)
            if bm == 'win':
                ok = declaration(b, side) == 'win'
                return ('rust' if ok else 'py'), ('宣言勝ち' if ok else '不正な宣言'), i
            if bm == 'resign':
                return 'py', '投了', i
            m = b.move_from_usi(bm)
            if not b.is_legal(m):
                return 'py', '非合法手 %s' % bm, i
        else:
            mv, _ = py.pick(b)
            if mv == 'declare_win':
                return 'py', '宣言勝ち', i
            if mv is None:
                return 'rust', '詰み', i
            m = mv
        moves.append(cshogi.move_to_usi(m))
        b.push(m)
        if b.is_draw() == cshogi.REPETITION_DRAW:
            return 'draw', '千日手', i + 1
        if b.is_game_over():
            return ('rust' if b.turn != rust else 'py'), '詰み', i + 1
    return 'draw', '上限手数', maxply


def main():
    npos = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    sec = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3
    depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    maxply = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    pos = [ln.split('\t')[0] for ln in open(os.path.join(ROOT, 'positions', 'holdout40.tsv'), encoding='utf-8')
           if ln.strip() and not ln.startswith('#')][:npos]
    usi = Usi(int(sec * 1000))
    tally = collections.Counter()
    t0 = time.time()
    for s in pos:
        for rust_black in (True, False):
            who, why, n = play(s, rust_black, usi, depth, maxply)
            tally[who] += 1
            print('%s Rust=%s -> %s (%s, %d手)' % (s.split()[3], '先手' if rust_black else '後手', who, why, n),
                  flush=True)
    usi.close()
    print('Rust %d勝 Python %d勝 引き分け %d  (%d局, Rust %.1f秒/手, Python 深さ%d, %.0fs)'
          % (tally['rust'], tally['py'], tally['draw'], sum(tally.values()), sec, depth, time.time() - t0))


if __name__ == '__main__':
    main()
