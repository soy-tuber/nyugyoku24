# -*- coding: utf-8 -*-
"""入玉宣言法 24点法エンジン — 評価と探索を一体化した終盤特化探索部。

ルール (日本将棋連盟 入玉宣言法・24点法):
    宣言側が以下を「すべて」満たすとき宣言できる。
      (a) 宣言側の手番
      (b) 宣言側の玉が敵陣三段目以内
      (c) 玉以外の宣言側の駒が敵陣三段目以内に10枚以上
      (d) 宣言側に王手がかかっていない
      (e) 点数 = 持ち駒 + 敵陣三段目以内の駒 (大駒5/小駒1/玉0)
            31点以上 -> 勝ち
            24-30点  -> 無勝負 (指し直し)
            23点以下 -> 宣言した側の負け
      (f) 持ち時間が残っている
    条件を1つでも欠くと宣言側の負けになるので、判定は厳密でなければならない。

    ※ 持将棋 (合意による無勝負) は数え方が違う (盤上どこでも+持駒、合計54点)。
      そちらは engine24.py が扱う。混同しないこと。

目的関数の構造:
    27点法/24点法の点数は「敵陣三段目以内 + 持ち駒」なので、
    先後で保存されない。零和の駒得ではなく、片側だけの閾値到達問題である。
      - 持ち駒は点数に入るが 10枚条件には入らない
      - よって持ち駒を敵陣に打つと、点数は不変のまま 10枚条件が1枚進む
      - 自陣の駒を敵陣まで運ぶと、点数と枚数の両方が進む
    つまり目標は構成的:「敵陣三段目以内に10枚運び込み、31点を作る」。

    floodgate 12,670サンプルでの実測:
      10枚不足が束縛的なのが 10.9%、31点不足が束縛的なのが 6.1% (約1.8倍)
      不足量の中央値は 4枚 / 11点
    この比を評価の重みに反映している。
"""
import cshogi

# ---- 駒点 (駒種で引く。move_cap() は駒種を返す) ----
PT_POINT = [0] * 16
for _pt in (cshogi.PAWN, cshogi.LANCE, cshogi.KNIGHT, cshogi.SILVER, cshogi.GOLD,
            cshogi.PROM_PAWN, cshogi.PROM_LANCE, cshogi.PROM_KNIGHT, cshogi.PROM_SILVER):
    PT_POINT[_pt] = 1
for _pt in (cshogi.BISHOP, cshogi.ROOK, cshogi.PROM_BISHOP, cshogi.PROM_ROOK):
    PT_POINT[_pt] = 5
PT_POINT[cshogi.KING] = 0
HAND_POINT = [PT_POINT[cshogi.hand_piece_to_piece_type(_i)] for _i in cshogi.HAND_PIECES]

# 敵陣三段目以内のマス。cshogi の square は (筋-1)*9 + (段-1)。
# 先手にとっての敵陣 = 1〜3段目 = sq%9 in {0,1,2}
ZONE = {
    cshogi.BLACK: frozenset(sq for sq in range(81) if sq % 9 <= 2),
    cshogi.WHITE: frozenset(sq for sq in range(81) if sq % 9 >= 6),
}
ZONE_LIST = {c: sorted(ZONE[c]) for c in (cshogi.BLACK, cshogi.WHITE)}

NEED_N = 10          # 敵陣三段目以内に必要な駒数 (玉を除く)
WIN_POINT = 31       # 24点法の勝ち
DRAW_POINT = 24      # 24点法の無勝負

WIN = 30000
MATE = 32000

# 評価の重み。不足量の中央値 4枚 / 11点 から、1枚 ≒ 2.75点相当。
W_PIECE = 30         # 現に敵陣三段目以内にある駒 (10枚条件に効く)
W_POTENT = 15        # 持ち駒 = 1手で敵陣に届く予備の駒。打っても点数は減らない
W_PIECE_X = 8        # 10枚を超えた分。取られる余裕なので0にはしない
W_POINT = 10         # 31点までの点数
W_POINT_X = 3        # 31点を超えた分。ここを0にすると余剰点を捨てても無料になる
W_KING = 400         # 玉が敵陣にいることは宣言の前提条件


def hand_count(board, color):
    """持ち駒の枚数 (点数ではなく枚数)。打てば敵陣内の駒数を1増やせる。"""
    return sum(board.pieces_in_hand[color])


def zone_stats(board, color):
    """(n, p, king_in) を返す。
       n = 敵陣三段目以内の自駒の枚数 (玉を除く)
       p = 持ち駒 + 敵陣三段目以内の自駒 の点数 (玉は0点)
       king_in = 自玉が敵陣三段目以内にいるか
    """
    pieces = board.pieces
    is_white = (color == cshogi.WHITE)
    n = 0
    zp = 0
    for sq in ZONE_LIST[color]:
        pc = pieces[sq]
        if pc and (pc >= 17) == is_white:
            pt = cshogi.piece_to_piece_type(pc)
            if pt == cshogi.KING:
                continue
            n += 1
            zp += PT_POINT[pt]
    hp = 0
    for i, cnt in enumerate(board.pieces_in_hand[color]):
        if cnt:
            hp += HAND_POINT[i] * cnt
    king_in = board.king_square(color) in ZONE[color]
    return n, zp + hp, king_in


def declaration(board, color, in_check=None):
    """手番側 color が今この瞬間に宣言したらどうなるか。
       'win' / 'draw' / None (宣言すると負けるので不可) を返す。
    """
    if board.turn != color:
        return None
    n, p, king_in = zone_stats(board, color)
    if not king_in or n < NEED_N:
        return None
    if in_check is None:
        in_check = board.is_check()
    if in_check:
        return None
    if p >= WIN_POINT:
        return 'win'
    if p >= DRAW_POINT:
        return 'draw'
    return None


def progress(board, color):
    """宣言条件 (敵陣内10枚 かつ 31点) への到達度。

    設計上の注意 (2026-08-24 のバグ修正):
      1) 閾値の上で完全に飽和させてはならない。
         min(p, 31) だけにすると p=34 から 31 まで駒を捨てても評価が動かず、
         実際にエンジンが持ち駒を自陣に投げ捨てる挙動を起こした。
         超過分にも小さい重み (W_POINT_X / W_PIECE_X) を残して、余剰を守らせる。
      2) 持ち駒は「1手で敵陣に届く予備の駒」である。
         敵陣に打つと n が1増え、点数は変わらない (持駒も敵陣の駒も同じく計上)。
         よって持ち駒の枚数は 10枚条件への到達可能性そのもの。これを見ないと、
         持ち駒を12枚抱えたまま敵陣4枚で止まる、という失敗が起きる。
      3) 逆に、敵陣「外」に打つ手は点数の純損失である
         (持ち駒は計上されるが、自陣の盤上の駒は計上されない)。
         上の2項によって自動的に減点される。
    """
    n, p, king_in = zone_stats(board, color)
    h = hand_count(board, color)
    have = min(n, NEED_N)
    reach = min(NEED_N, n + h)          # 打ち切れば届く枚数
    v = (W_PIECE * have
         + W_POTENT * (reach - have)    # 打てば届く分。実際に打つと +W_PIECE-W_POTENT の得
         + W_PIECE_X * max(0, n - NEED_N)
         + W_POINT * min(p, WIN_POINT)
         + W_POINT_X * max(0, p - WIN_POINT))
    if king_in:
        v += W_KING
    return v


def evaluate(board):
    """手番側から見た評価値。零和ではないので自分の到達度と相手の到達度の差を取る。"""
    us = board.turn
    them = 1 - us
    return progress(board, us) - progress(board, them)


class DeclEngine24:
    def __init__(self, max_depth=4):
        self.max_depth = max_depth
        self.nodes = 0
        self.tt = {}

    # ---- 手の並べ替え: 目的関数をそのまま優先度にする ----
    def order_key(self, board, m, us):
        to = cshogi.move_to(m)
        in_zone = to in ZONE[us]
        cap = cshogi.move_cap(m)
        k = 0
        is_drop = cshogi.move_is_drop(m)
        if in_zone:
            if is_drop:
                k += 50           # 打ち込み: 点数不変のまま10枚条件が1枚進む
            else:
                frm = cshogi.move_from(m)
                if frm not in ZONE[us]:
                    k += 60       # 運び込み: 枚数と点数の両方が進む
                else:
                    k += 5        # 敵陣内での移動
        elif is_drop:
            # 敵陣「外」への打ち込みは点数の純損失。
            # 持ち駒は点数に計上されるが、自陣の盤上の駒は計上されないため。
            k -= 40 + HAND_POINT[cshogi.move_drop_hand_piece(m)] * 8
        else:
            frm = cshogi.move_from(m)
            if frm in ZONE[us]:
                k -= 60           # 敵陣から出る手は目的関数に反する
        if cap:
            k += 20 + PT_POINT[cap] * 2
        return -k

    def search(self, board, depth, alpha, beta, ply):
        self.nodes += 1
        rep = board.is_draw()
        if rep == cshogi.REPETITION_DRAW:
            return 0
        if rep == cshogi.REPETITION_WIN:      # 連続王手の千日手: 相手の反則
            return WIN - ply
        if rep == cshogi.REPETITION_LOSE:     # 連続王手の千日手: 自分の反則
            return -WIN + ply
        us = board.turn
        in_check = board.is_check()

        # 宣言は権利。勝ちが成立していれば即座に勝ち。
        d = declaration(board, us, in_check)
        if d == 'win':
            return WIN - ply
        if d == 'draw':
            # 無勝負を確保できるので、この局面の値は 0 以上。指し続ける選択も残す。
            if 0 >= beta:
                return 0
            if 0 > alpha:
                alpha = 0

        if depth <= 0:
            return evaluate(board)

        key = board.zobrist_hash()
        ent = self.tt.get(key)
        if ent is not None and ent[0] >= depth:
            return ent[1]

        moves = sorted(board.legal_moves, key=lambda m: self.order_key(board, m, us))
        if not moves:
            return -MATE + ply            # 詰まされた

        best = -MATE
        for m in moves:
            board.push(m)
            v = -self.search(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if v > best:
                best = v
            if v >= beta:
                break
            if v > alpha:
                alpha = v
        self.tt[key] = (depth, best)
        return best

    def go(self, board, max_depth=None):
        """(bestmove or 'declare', score, nodes) を返す。"""
        self.nodes = 0
        self.tt.clear()
        us = board.turn
        d = declaration(board, us)
        if d == 'win':
            return 'declare_win', WIN, 0

        md = max_depth or self.max_depth
        best_move, best_score = None, -MATE
        for depth in range(1, md + 1):
            alpha = -MATE
            cur_move, cur_score = None, -MATE
            moves = sorted(board.legal_moves,
                           key=lambda m: (0 if m == best_move else 1,
                                          self.order_key(board, m, us)))
            if not moves:
                return None, -MATE, self.nodes
            for m in moves:
                board.push(m)
                v = -self.search(board, depth - 1, -MATE, -alpha, 1)
                board.pop()
                if v > cur_score:
                    cur_score, cur_move = v, m
                if v > alpha:
                    alpha = v
            best_move, best_score = cur_move, cur_score
            if best_score >= WIN - 1000:
                break
        # 指し続けても無勝負以下しか見込めないなら、無勝負を確定させる
        if d == 'draw' and best_score < WIN - 1000 and best_score <= 0:
            return 'declare_draw', 0, self.nodes
        return best_move, best_score, self.nodes
