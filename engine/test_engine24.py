# -*- coding: utf-8 -*-
"""engine24 の正しさと速度を実データで確認する。

1) point24() を、106,645局で検証済みの CSA ベース採点と突き合わせる
2) 相入玉が成立した瞬間の局面を取り出す
3) 探索速度と読みの深さを測る
"""
import os, sys, glob, random, time, collections
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine24 import Engine24, point24, material_diff, is_aiiru

DS = r"D:\book_project\nyugyoku_dataset"

# ---- 検証済みの CSA ベース採点 (build_nyugyoku_dataset.py と同一ロジック) ----
BIG = {'HI', 'KA', 'RY', 'UM'}
SMALL = {'FU', 'KY', 'KE', 'GI', 'KI', 'TO', 'NY', 'NK', 'NG'}
UNPROMOTE = {'TO': 'FU', 'NY': 'KY', 'NK': 'KE', 'NG': 'GI', 'RY': 'HI', 'UM': 'KA'}
BACK = ['KY', 'KE', 'GI', 'KI', 'OU', 'KI', 'GI', 'KE', 'KY']


def pts(p):
    return 5 if p in BIG else (1 if p in SMALL else 0)


def csa_replay(path):
    """CSA を再生し、(相入玉成立時のSFEN, 最終の先手24点, 最終の後手24点, 手数) を返す。"""
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    board = {}
    hands = {'+': collections.Counter(), '-': collections.Counter()}
    rows = 0
    for ln in lines:
        if ln.startswith('P') and len(ln) > 1 and ln[1].isdigit():
            rank = int(ln[1]); rows += 1
            for i in range(9):
                c = ln[2 + i * 3:5 + i * 3]
                if len(c) == 3 and c[0] in '+-':
                    board[(9 - i, rank)] = (c[0], c[1:])
    if rows != 9:
        return None
    moves = [ln for ln in lines if len(ln) >= 7 and ln[0] in '+-' and ln[1].isdigit()]

    cb = cshogi.Board()
    aiiru_sfen = None
    aiiru_ply = None
    for i, ln in enumerate(moves):
        side = ln[0]
        src = (int(ln[1]), int(ln[2])); dst = (int(ln[3]), int(ln[4])); p = ln[5:7]
        cap = board.get(dst)
        if cap:
            hands[side][UNPROMOTE.get(cap[1], cap[1])] += 1
        if src == (0, 0):
            hands[side][UNPROMOTE.get(p, p)] -= 1
        else:
            if src not in board:
                return None
            del board[src]
        board[dst] = (side, p)
        # cshogi 側も同じ手を進める
        try:
            cm = cb.move_from_csa(ln[1:])   # cshogi は先後記号を含めない形式
            if cm == 0 or not cb.is_legal(cm):
                return None
            cb.push(cm)
        except Exception:
            return None
        if aiiru_sfen is None and is_aiiru(cb):
            aiiru_sfen = cb.sfen()
            aiiru_ply = i + 1
    s = sum(pts(p) for (_, (sd, p)) in board.items() if sd == '+') + \
        sum(pts(p) * n for p, n in hands['+'].items())
    g = sum(pts(p) for (_, (sd, p)) in board.items() if sd == '-') + \
        sum(pts(p) * n for p, n in hands['-'].items())
    return aiiru_sfen, aiiru_ply, s, g, len(moves), cb.sfen()


def main():
    random.seed(20260823)
    files = []
    for y in ('2021', '2022', '2023'):
        files += glob.glob(os.path.join(DS, y, '*.csa'))
    random.shuffle(files)

    print('=== 1) point24() の検証: CSAベース採点との突き合わせ ===')
    ok = ng = skip = 0
    samples = []
    for path in files:
        if ok >= 300:
            break
        r = csa_replay(path)
        if r is None:
            skip += 1
            continue
        aiiru_sfen, aiiru_ply, s, g, nmv, final_sfen = r
        b = cshogi.Board(final_sfen)
        cs, cg = point24(b, cshogi.BLACK), point24(b, cshogi.WHITE)
        if (cs, cg) == (s, g) and cs + cg == 54:
            ok += 1
            if aiiru_sfen:
                samples.append((os.path.basename(path), aiiru_sfen, aiiru_ply, nmv, s, g))
        else:
            ng += 1
            if ng <= 3:
                print('  不一致: %s  cshogi=(%d,%d) csa=(%d,%d)'
                      % (os.path.basename(path), cs, cg, s, g))
    print('  一致 %d / 不一致 %d / 再生失敗 %d' % (ok, ng, skip))
    print('  相入玉成立局面を取得できた局: %d' % len(samples))

    if not samples:
        print('サンプルなし')
        return

    print('\n=== 2) 相入玉が成立した瞬間の局面 (例) ===')
    for nm, sfen, ply, nmv, s, g in samples[:3]:
        b = cshogi.Board(sfen)
        print('  %s' % nm[:60])
        print('    成立=%d手目 / 全%d手   その時点 先手%d点 後手%d点 -> 終局 先手%d点 後手%d点'
              % (ply, nmv, point24(b, cshogi.BLACK), point24(b, cshogi.WHITE), s, g))

    print('\n=== 3) 探索速度 ===')
    eng = Engine24()
    for nm, sfen, ply, nmv, s, g in samples[:5]:
        b = cshogi.Board(sfen)
        nlegal = len(list(b.legal_moves))
        print('  %s  合法手=%d' % (nm[:48], nlegal))
        for d in (1, 2, 3, 4, 5):
            t0 = time.perf_counter()
            mv, sc, _, nodes = eng.go(b, max_depth=d)
            dt = time.perf_counter() - t0
            print('    depth %d: %-7s score=%+5d  %8d nodes  %5.2fs  %8.0f nps'
                  % (d, cshogi.move_to_usi(mv) if mv else '-', sc, nodes, dt,
                     nodes / dt if dt > 0 else 0))
            if dt > 20:
                break


if __name__ == '__main__':
    main()
