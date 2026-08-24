# -*- coding: utf-8 -*-
"""24点法における「確定点 S (持ち駒)」と「係争点 R (盤上)」の分解を実データで検証する。

主張:
  持ち駒は取られない。盤上の駒は取られる。自分の盤上駒を自分の持ち駒に戻す手段は無い。
  したがって「打たない」戦略の下で S は単調非減少であり、
      最終点数 >= 現在の S
  が保証される。最終点数は必ず [S, S+R] に入る。

測ること:
  1) 相入玉成立時点の S, R の分布
  2) S >= 31 (勝ち確定) / S >= 24 (負けない) が成立する局面の割合
  3) 実際の終局点数が [S, S+R] に入っているか
  4) S だけで終局の勝敗をどれだけ予測できるか (静的評価器としての性能)
"""
import os, sys, glob, random, collections, statistics
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine24 import point24, is_aiiru, PT_POINT, HAND_POINT

DS = r"D:\book_project\nyugyoku_dataset"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000


def split_points(board, color):
    """(S, R) = (持ち駒の点数, 盤上の自駒の点数)"""
    s = sum(HAND_POINT[i] * n for i, n in enumerate(board.pieces_in_hand[color]))
    r = 0
    pieces = board.pieces
    for sq in range(81):
        pc = pieces[sq]
        if pc and (pc >= 17) == (color == cshogi.WHITE):
            r += PT_POINT[cshogi.piece_to_piece_type(pc)]
    return s, r


def scan(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    moves = [ln for ln in lines if len(ln) >= 7 and ln[0] in '+-' and ln[1].isdigit()]
    b = cshogi.Board()
    at = None
    for ln in moves:
        try:
            m = b.move_from_csa(ln[1:])
            if m == 0 or not b.is_legal(m):
                return None
            b.push(m)
        except Exception:
            return None
        if at is None and is_aiiru(b):
            at = (split_points(b, cshogi.BLACK), split_points(b, cshogi.WHITE), b.move_number)
    if at is None:
        return None
    fin = (point24(b, cshogi.BLACK), point24(b, cshogi.WHITE))
    return at[0], at[1], at[2], fin


def main():
    random.seed(11)
    files = []
    for y in ('2020', '2021', '2022', '2023', '2024', '2025'):
        files += glob.glob(os.path.join(DS, y, '*.csa'))
    random.shuffle(files)

    rec = []
    for p in files:
        if len(rec) >= N:
            break
        r = scan(p)
        if r:
            rec.append(r)
    n = len(rec)
    print('相入玉成立局面 %d 件\n' % n)

    print('=== 1) 成立時点の S (持ち駒=確定) と R (盤上=係争) ===')
    S = [x for (sb, rb), (sw, rw), _, _ in rec for x in (sb, sw)]
    R = [x for (sb, rb), (sw, rw), _, _ in rec for x in (rb, rw)]
    print('  S: 中央値 %.0f  平均 %.1f  範囲 %d-%d' % (statistics.median(S), statistics.mean(S), min(S), max(S)))
    print('  R: 中央値 %.0f  平均 %.1f  範囲 %d-%d' % (statistics.median(R), statistics.mean(R), min(R), max(R)))
    print('  -> 点数の %.0f%% が既に確定し、%.0f%% が係争中'
          % (statistics.mean(S) / 27 * 100, statistics.mean(R) / 27 * 100))

    print('\n=== 2) S だけで結論が出る局面 ===')
    win = sum(1 for (sb, _), (sw, _), _, _ in rec if sb >= 31 or sw >= 31)
    nolose_b = sum(1 for (sb, _), _, _, _ in rec if sb >= 24)
    nolose_w = sum(1 for _, (sw, _), _, _ in rec if sw >= 24)
    print('  S>=31 (勝ち確定) がどちらかに成立: %d局 (%.1f%%)' % (win, win / n * 100))
    print('  S>=24 (負けない) 成立: 先手 %d局 (%.1f%%) / 後手 %d局 (%.1f%%)'
          % (nolose_b, nolose_b / n * 100, nolose_w, nolose_w / n * 100))

    print('\n=== 3) 実際の終局点数は [S, S+R] に入ったか ===')
    inb = viol_lo = viol_hi = 0
    for (sb, rb), (sw, rw), _, (fb, fw) in rec:
        for s, r, f in ((sb, rb, fb), (sw, rw, fw)):
            if f < s:
                viol_lo += 1
            elif f > s + r:
                viol_hi += 1
            else:
                inb += 1
    tot = n * 2
    print('  区間内 %d/%d (%.1f%%)' % (inb, tot, inb / tot * 100))
    print('  下限割れ %d (%.1f%%)  <- 実戦では打つので S は保証にならない'
          % (viol_lo, viol_lo / tot * 100))
    print('  上限超え %d (%.1f%%)  <- 相手の駒を取れば S+R を超える(想定通り)'
          % (viol_hi, viol_hi / tot * 100))

    print('\n=== 4) 静的評価器としての予測性能 (先手視点) ===')
    print('  指標: 成立時点の値で終局の24点法勝敗を当てられるか')
    print('  %-22s %8s %8s %8s' % ('指標', '的中', '外れ', '的中率'))

    def evaluate(fn, label):
        ok = ng = 0
        for (sb, rb), (sw, rw), _, (fb, fw) in rec:
            true = 1 if fb >= 31 else (-1 if fb <= 23 else 0)
            pred = fn(sb, rb, sw, rw)
            if pred == true:
                ok += 1
            else:
                ng += 1
        print('  %-22s %8d %8d %7.1f%%' % (label, ok, ng, ok / (ok + ng) * 100))
        return ok / (ok + ng)

    def cls(v):
        return 1 if v >= 31 else (-1 if v <= 23 else 0)

    evaluate(lambda sb, rb, sw, rw: cls(sb + rb), '現在の総点 (S+R)')
    evaluate(lambda sb, rb, sw, rw: cls(sb), '確定点 S のみ')
    evaluate(lambda sb, rb, sw, rw: cls(sb + rb / 2 + 0.0), 'S + R/2 (係争を折半)')
    base = collections.Counter(1 if fb >= 31 else (-1 if fb <= 23 else 0)
                               for _, _, _, (fb, fw) in rec)
    mc = base.most_common(1)[0]
    print('  %-22s %8d %8d %7.1f%%  <- 常に最頻値を答える基準線'
          % ('(基準線)', mc[1], n - mc[1], mc[1] / n * 100))

    print('\n=== 終局の24点法での結果分布 ===')
    for k, v in sorted(base.items()):
        lab = {1: '先手勝ち(31点以上)', 0: '引き分け(24-30点)', -1: '先手負け(23点以下)'}[k]
        print('  %-20s %5d (%.1f%%)' % (lab, v, v / n * 100))


if __name__ == '__main__':
    main()
