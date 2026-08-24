# -*- coding: utf-8 -*-
"""入玉宣言法の規則テスト。

このテストは改良の自由を制限するためのものではなく、
**宣言判定の厳密さだけは壊してはならない**という一点を守るためにある。

入玉宣言法では、条件を1つでも欠いた状態で宣言すると宣言した側の負けになる。
評価関数・探索・重み・特徴量は自由に変えてよいが、
declaration() が返す判定は、下の全ケースで一致し続けなければならない。

実行:  python tests/test_rules.py
"""
import os, sys, random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'engine'))
import cshogi
from engine_decl24 import declaration, zone_stats, PT_POINT, HAND_POINT, NEED_N

FAIL = []


def check(cond, msg):
    if cond:
        print('  ok   %s' % msg)
    else:
        print('  FAIL %s' % msg)
        FAIL.append(msg)


# ---------------------------------------------------------------- 宣言条件
# 先手玉が1段目、先手の駒が敵陣(1-3段目)に10枚、点数31点ちょうど。
#   2段目: R B G G S S N N L = 9枚 17点
#   3段目: P                 = 1枚  1点
#   持ち駒: R B P P P        =      13点
#   合計 31点 / 10枚  -> 宣言勝ち
WIN_SFEN = '4K4/RBGGSSNNL/P8/9/9/9/9/9/4k4 b RB3P 1'


def t_declaration():
    print('\n[1] 宣言条件 — 5条件それぞれが必要であること')

    b = cshogi.Board(WIN_SFEN)
    n, p, king_in = zone_stats(b, cshogi.BLACK)
    check((n, p, king_in) == (10, 31, True), '基準局面が 10枚/31点/玉が敵陣 (得: %d枚/%d点/%s)' % (n, p, king_in))
    check(declaration(b, cshogi.BLACK) == 'win', '31点・10枚・王手なし -> 宣言勝ち')

    # (a) 手番でなければ宣言できない
    check(declaration(b, cshogi.WHITE) is None, '手番でない側は宣言できない')

    # (b) 玉が敵陣にいなければ宣言できない (玉を5aから5eへ)
    b2 = cshogi.Board('9/RBGGSSNNL/P8/9/4K4/9/9/9/4k4 b RB3P 1')
    n2, p2, k2 = zone_stats(b2, cshogi.BLACK)
    check(k2 is False and n2 == 10 and p2 == 31, '玉だけ敵陣外にした局面 (10枚/31点は維持)')
    check(declaration(b2, cshogi.BLACK) is None, '玉が敵陣外 -> 宣言できない')

    # (c) 敵陣の駒が10枚未満なら宣言できない (3段目の歩を除く = 9枚)
    b3 = cshogi.Board('4K4/RBGGSSNNL/9/9/9/9/9/9/4k4 b RB4P 1')
    n3, p3, k3 = zone_stats(b3, cshogi.BLACK)
    check(n3 == 9 and p3 == 31, '9枚に減らした局面 (点数31点は維持: %d枚/%d点)' % (n3, p3))
    check(declaration(b3, cshogi.BLACK) is None, '敵陣に9枚 -> 宣言できない (点数は足りていても)')

    # (d) 王手がかかっていたら宣言できない (後手の飛を1筋に置いて王手)
    b4 = cshogi.Board('4K3r/RBGGSSNNL/P8/9/9/9/9/9/4k4 b RB3P 1')
    check(b4.is_check(), '王手がかかった局面を作れている')
    check(declaration(b4, cshogi.BLACK) is None, '王手中 -> 宣言できない')

    # (e) 点数による分岐
    #   24-30点 -> 無勝負 / 23点以下 -> 宣言してはいけない
    b5 = cshogi.Board('4K4/RBGGSSNNL/P8/9/9/9/9/9/4k4 b B3P 1')      # 18 + 5+3 = 26点
    n5, p5, _ = zone_stats(b5, cshogi.BLACK)
    check(p5 == 26 and n5 == 10, '26点/10枚の局面 (得: %d点/%d枚)' % (p5, n5))
    check(declaration(b5, cshogi.BLACK) == 'draw', '24-30点 -> 無勝負')

    b6 = cshogi.Board('4K4/RBGGSSNNL/P8/9/9/9/9/9/4k4 b 4P 1')       # 18 + 4 = 22点
    n6, p6, _ = zone_stats(b6, cshogi.BLACK)
    check(p6 == 22 and n6 == 10, '22点/10枚の局面 (得: %d点/%d枚)' % (p6, n6))
    check(declaration(b6, cshogi.BLACK) is None, '23点以下 -> 宣言してはいけない')

    # 境界ちょうど
    b7 = cshogi.Board('4K4/RBGGSSNNL/P8/9/9/9/9/9/4k4 b 6P 1')       # 18 + 6 = 24点
    check(zone_stats(b7, cshogi.BLACK)[1] == 24, '24点ちょうどの局面')
    check(declaration(b7, cshogi.BLACK) == 'draw', '24点ちょうど -> 無勝負')

    b8 = cshogi.Board('4K4/RBGGSSNNL/P8/9/9/9/9/9/4k4 b R2B3P 1')    # 18 + 5+10+3 = 36点
    check(declaration(b8, cshogi.BLACK) == 'win', '31点超 -> 宣言勝ち')


# ---------------------------------------------------------------- 点数計算
def t_points():
    print('\n[2] 点数計算 — 大駒5点 / 小駒1点 / 玉0点、成っても変わらない')
    for pt, want, nm in ((cshogi.ROOK, 5, '飛'), (cshogi.BISHOP, 5, '角'),
                         (cshogi.PROM_ROOK, 5, '龍'), (cshogi.PROM_BISHOP, 5, '馬'),
                         (cshogi.PAWN, 1, '歩'), (cshogi.PROM_PAWN, 1, 'と金'),
                         (cshogi.LANCE, 1, '香'), (cshogi.PROM_LANCE, 1, '成香'),
                         (cshogi.KNIGHT, 1, '桂'), (cshogi.PROM_KNIGHT, 1, '成桂'),
                         (cshogi.SILVER, 1, '銀'), (cshogi.PROM_SILVER, 1, '成銀'),
                         (cshogi.GOLD, 1, '金'), (cshogi.KING, 0, '玉')):
        check(PT_POINT[pt] == want, '%s = %d点' % (nm, want))


# ---------------------------------------------------------------- 不変量
def owned_points(board, color):
    """所有点数 = 盤上のどこにあっても自駒 + 持ち駒 (持将棋の数え方)。"""
    pieces = board.pieces
    is_white = (color == cshogi.WHITE)
    v = 0
    for sq in range(81):
        pc = pieces[sq]
        if pc and (pc >= 17) == is_white:
            v += PT_POINT[cshogi.piece_to_piece_type(pc)]
    for i, c in enumerate(board.pieces_in_hand[color]):
        v += HAND_POINT[i] * c
    return v


def t_invariants(trials=300, plies=120, seed=1):
    print('\n[3] 不変量 — ランダム合法手で %d 局面を検査' % trials)
    rnd = random.Random(seed)
    bad_54 = bad_le = 0
    n = 0
    b = cshogi.Board()
    for i in range(trials):
        b.reset()
        for _ in range(rnd.randrange(10, plies)):
            ms = list(b.legal_moves)
            if not ms or b.is_game_over():
                break
            b.push(rnd.choice(ms))
        n += 1
        # (i) 所有点数の先後合計は常に54 (飛角4枚20点 + 小駒34枚34点)
        if owned_points(b, cshogi.BLACK) + owned_points(b, cshogi.WHITE) != 54:
            bad_54 += 1
        # (ii) 宣言点数 <= 所有点数 (宣言点数は所有点数の部分集合)
        for c in (cshogi.BLACK, cshogi.WHITE):
            if zone_stats(b, c)[1] > owned_points(b, c):
                bad_le += 1
    check(bad_54 == 0, '所有点数の先後合計が常に54点 (違反 %d/%d)' % (bad_54, n))
    check(bad_le == 0, '宣言点数 <= 所有点数 (違反 %d/%d)' % (bad_le, n * 2))

    b0 = cshogi.Board()
    check(owned_points(b0, cshogi.BLACK) == 27 and owned_points(b0, cshogi.WHITE) == 27,
          '平手初形は先後とも所有27点 (飛角10 + 歩9 + 金銀桂香8)')
    check(zone_stats(b0, cshogi.BLACK)[1] == 0 and zone_stats(b0, cshogi.WHITE)[1] == 0,
          '平手初形の宣言点数は0点 (敵陣に駒も持ち駒も無い)')
    check(declaration(b0, cshogi.BLACK) is None, '平手初形では宣言できない')


# ---------------------------------------------------------------- 到達性
def t_reachability():
    print('\n[4] 31点は駒取りなしには到達できない')
    # 自陣営の駒の総点は27点。宣言点数は所有点数の部分集合なので、
    # 相手から4点以上奪わない限り31点には届かない。
    b = cshogi.Board()
    check(owned_points(b, cshogi.BLACK) == 27, '自駒だけの上限は27点')
    check(27 < 31, '27 < 31 なので、勝ちには最低4点の駒取りが必要')
    check(24 <= 27, '24 <= 27 なので、無勝負は駒取りなしでも到達可能')


if __name__ == '__main__':
    t_declaration()
    t_points()
    t_invariants()
    t_reachability()
    print('\n' + '=' * 60)
    if FAIL:
        print('失敗 %d 件:' % len(FAIL))
        for m in FAIL:
            print('  - %s' % m)
        sys.exit(1)
    print('すべて通過')
