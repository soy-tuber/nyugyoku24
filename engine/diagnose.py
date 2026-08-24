# -*- coding: utf-8 -*-
"""1局面の攻防を1手ずつ追跡し、何が起きているかを出力する。"""
import os, sys, glob, random
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roles import RoleEngine
from engine_decl24 import zone_stats, declaration, ZONE, PT_POINT, NEED_N, WIN_POINT

DS = r"D:\book_project\nyugyoku_dataset"


def aiiru_sfen(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    moves = [ln for ln in lines if len(ln) >= 7 and ln[0] in '+-' and ln[1].isdigit()]
    b = cshogi.Board()
    for ln in moves:
        try:
            m = b.move_from_csa(ln[1:])
            if m == 0 or not b.is_legal(m):
                return None
            b.push(m)
        except Exception:
            return None
        if b.king_square(cshogi.BLACK) % 9 <= 2 and b.king_square(cshogi.WHITE) % 9 >= 6:
            return b.sfen()
    return None


def trace(sfen, attacker, plies, depth, pure=True, label=''):
    board = cshogi.Board(sfen)
    eng = RoleEngine(attacker, depth, pure)
    A = '先手' if attacker == cshogi.BLACK else '後手'
    D = '後手' if attacker == cshogi.BLACK else '先手'
    print('\n%s' % ('=' * 78))
    print('%s  攻撃=%s / 妨害=%s  (depth %d, pure=%s)' % (label, A, D, depth, pure))
    print('%s' % ('=' * 78))
    print('%4s %-6s %-8s %-26s %6s %6s %5s %s'
          % ('手', '手番', '指し手', '種別', '攻n', '攻p', '玉', '評価'))
    n0, p0, k0 = zone_stats(board, attacker)
    print('%4s %-6s %-8s %-26s %6d %6d %5s' % ('-', '-', '(開始)', '', n0, p0, 'in' if k0 else 'OUT'))
    for i in range(plies):
        side = board.turn
        d = declaration(board, side)
        if d == 'win' and side == attacker:
            print('  -> %s の宣言勝ち (%d手目)' % (A, i))
            return
        mv, sc = eng.pick(board)
        if mv is None:
            print('  -> %s が詰み (%d手目)' % ('先手' if side == cshogi.BLACK else '後手', i))
            return
        to = cshogi.move_to(mv)
        cap = cshogi.move_cap(mv)
        kind = []
        if to in ZONE[attacker]:
            if cshogi.move_is_drop(mv):
                kind.append('攻陣へ打ち込み' if side == attacker else '妨害側が攻陣へ打つ')
            elif cshogi.move_from(mv) not in ZONE[attacker]:
                kind.append('攻陣へ運び込み' if side == attacker else '妨害側が攻陣へ入る')
            else:
                kind.append('攻陣内で移動')
        elif not cshogi.move_is_drop(mv) and cshogi.move_from(mv) in ZONE[attacker]:
            kind.append('★攻陣から出る')
        if cap:
            tag = '取(%d点)' % PT_POINT[cap]
            if to in ZONE[attacker] and side != attacker:
                tag = '★妨害側が攻陣の駒を取る(%d点)' % PT_POINT[cap]
            kind.append(tag)
        board.push(mv)
        n, p, k = zone_stats(board, attacker)
        mark = ''
        if n != n0:
            mark += ' n%+d' % (n - n0)
        if p != p0:
            mark += ' p%+d' % (p - p0)
        n0, p0 = n, p
        print('%4d %-6s %-8s %-26s %6d %6d %5s %6d%s'
              % (i, '先手' if side == cshogi.BLACK else '後手',
                 cshogi.move_to_usi(mv), '/'.join(kind) or '-', n, p,
                 'in' if k else 'OUT', sc, mark))
        if board.is_draw() == cshogi.REPETITION_DRAW:
            print('  -> 千日手 (%d手目)' % (i + 1))
            return
    print('  -> %d手で打ち切り。攻撃側 %d枚/%d点 (必要 %d枚/%d点)'
          % (plies, n, p, NEED_N, WIN_POINT))


def main():
    random.seed(5)
    files = []
    for y in ('2021', '2022', '2023'):
        files += glob.glob(os.path.join(DS, y, '*.csa'))
    random.shuffle(files)
    pos = []
    for p in files:
        if len(pos) >= 1:
            break
        s = aiiru_sfen(p)
        if s:
            pos.append((os.path.basename(p), s))
    nm, sfen = pos[0]
    print('局面: %s' % nm)
    b = cshogi.Board(sfen)
    print('sfen: %s' % sfen)
    print('先手 %d枚/%d点  後手 %d枚/%d点  手番=%s'
          % (zone_stats(b, cshogi.BLACK)[0], zone_stats(b, cshogi.BLACK)[1],
             zone_stats(b, cshogi.WHITE)[0], zone_stats(b, cshogi.WHITE)[1],
             '先手' if b.turn == cshogi.BLACK else '後手'))
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    trace(sfen, cshogi.BLACK, N, 3, True, '【防がれた側】先手が攻め')
    trace(sfen, cshogi.WHITE, N, 3, True, '【成功した側】後手が攻め')


if __name__ == '__main__':
    main()
