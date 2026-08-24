# -*- coding: utf-8 -*-
"""相入玉24点法エンジン — 評価と探索を一体化した終盤特化探索部。

目的関数:
    24点法では先後の点数合計が常に54点なので
        自分の点数 >= 31  <=>  駒得差 d = my24 - opp24 >= +8   ... 勝ち
        自分の点数 <= 23  <=>  d <= -8                          ... 負け
        その間                                                  ... 引き分け
    したがって評価は駒得差ただ一つで足り、位置項を持たない。
    末端では d を返し、±8 を跨いだ瞬間に不連続な段差を入れる。
    この段差が「24点法の目的関数」そのものであり、既存エンジンに欠けているもの。

前提:
    相入玉局面 (両玉が敵陣3段目以内) 専用。詰みの脅威が消えているため
    駒得のみを目的関数にしてよい、という仮定の上に立っている。
"""
import cshogi

# ---- 駒点 (大駒5点, 小駒1点, 玉0点) ----
# PT_POINT は「駒種」で引く。cshogi の駒種は 1..14 (9..14 が成駒)。
# move_cap() は駒種をそのまま返すので、この配列で直接引ける。
PT_POINT = [0] * 16
for _pt in (cshogi.PAWN, cshogi.LANCE, cshogi.KNIGHT, cshogi.SILVER, cshogi.GOLD,
            cshogi.PROM_PAWN, cshogi.PROM_LANCE, cshogi.PROM_KNIGHT, cshogi.PROM_SILVER):
    PT_POINT[_pt] = 1
for _pt in (cshogi.BISHOP, cshogi.ROOK, cshogi.PROM_BISHOP, cshogi.PROM_ROOK):
    PT_POINT[_pt] = 5
PT_POINT[cshogi.KING] = 0

# 持ち駒インデックス (p,l,n,s,g,b,r) -> 点数
HAND_POINT = [PT_POINT[cshogi.hand_piece_to_piece_type(_i)] for _i in cshogi.HAND_PIECES]

WIN = 30000          # 24点法の勝ち (詰みとは別)
MATE = 32000         # 実際の詰み
DECISIVE = 8         # 駒得差がこれ以上なら31点以上 = 勝ち


def point24(board, color):
    """color 側の24点法での持点。盤上のどこにあっても自駒は全て数える。"""
    p = 0
    pieces = board.pieces
    for sq in range(81):
        pc = pieces[sq]
        if pc and (pc >= 17) == (color == cshogi.WHITE):
            p += PT_POINT[cshogi.piece_to_piece_type(pc)]
    for i, n in enumerate(board.pieces_in_hand[color]):
        p += HAND_POINT[i] * n
    return p


def material_diff(board):
    """手番側から見た駒得差 d = my24 - opp24。d>=+8 で勝ち, d<=-8 で負け。"""
    us = board.turn
    return point24(board, us) - point24(board, 1 - us)


def is_aiiru(board):
    """両玉が敵陣3段目以内にいるか。"""
    bk = board.king_square(cshogi.BLACK)
    wk = board.king_square(cshogi.WHITE)
    # cshogi の square は file*9 + rank (0-origin), rank0 が1段目
    return (bk % 9) <= 2 and (wk % 9) >= 6


class Engine24:
    def __init__(self, max_depth=6, qdepth=8):
        self.max_depth = max_depth
        self.qdepth = qdepth
        self.nodes = 0
        self.tt = {}
        self.stop = False

    # ---- 冷えた局面でのみ確定値を返す ----
    # ここが設計の核心。24点法の裁定は終局時に行われるので、
    # 「今 d >= +8 だから勝ち」と即断してはならない。取り返されうるからである。
    # 点数が確定するのは双方が駒取りを持たない (= 冷えた) 局面だけで、
    # ±8 の段差はそこでのみ入る。評価と探索が一体である、とはこの意味。
    def cold_value(self, board, ply):
        d = material_diff(board)
        if d >= DECISIVE:
            return WIN - ply
        if d <= -DECISIVE:
            return -WIN + ply
        return d

    def is_cold(self, board, in_check):
        """双方に駒取りが無いか。近似的な「進展なし」判定。"""
        if in_check:
            return False
        for m in board.legal_moves:
            if cshogi.move_cap(m) != cshogi.NONE:
                return False
        board.push_pass()
        try:
            if board.is_check():
                return False
            for m in board.legal_moves:
                if cshogi.move_cap(m) != cshogi.NONE:
                    return False
        finally:
            board.pop_pass()
        return True

    # ---- 静止探索: 点数を変える手 (駒取り) が尽きるまで ----
    def qsearch(self, board, alpha, beta, ply, qleft):
        self.nodes += 1
        in_check = board.is_check()
        moves = []
        for m in board.legal_moves:
            cap = cshogi.move_cap(m)
            if in_check or cap != cshogi.NONE:
                moves.append((PT_POINT[cap], m))
        if not moves:
            if in_check:
                return -MATE + ply            # 王手で合法手なし = 詰み
            # 手番側に駒取りが無い。相手にも無ければ点数は確定。
            if self.is_cold(board, in_check):
                return self.cold_value(board, ply)
            return material_diff(board)       # まだ熱い -> 生の駒得差
        # 地平線に達した場合も未確定なので生の d を返す (段差を入れてはならない)
        stand = material_diff(board)
        if qleft <= 0:
            return stand
        if stand >= beta:
            return stand
        if stand > alpha:
            alpha = stand
        moves.sort(key=lambda x: -x[0])
        for _, m in moves:
            board.push(m)
            v = -self.qsearch(board, -beta, -alpha, ply + 1, qleft - 1)
            board.pop()
            if v >= beta:
                return v
            if v > alpha:
                alpha = v
        return alpha

    def search(self, board, depth, alpha, beta, ply):
        self.nodes += 1
        if board.is_draw() == cshogi.REPETITION_DRAW:
            return 0                          # 千日手は引き分け
        if depth <= 0:
            return self.qsearch(board, alpha, beta, ply, self.qdepth)
        key = board.zobrist_hash()
        ent = self.tt.get(key)
        if ent and ent[0] >= depth:
            return ent[1]
        best = -MATE
        n = 0
        moves = []
        for m in board.legal_moves:
            moves.append((PT_POINT[cshogi.move_cap(m)], m))
        if not moves:
            return -MATE + ply                # 詰まされた
        moves.sort(key=lambda x: -x[0])
        for _, m in moves:
            board.push(m)
            v = -self.search(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            n += 1
            if v > best:
                best = v
            if v >= beta:
                break
            if v > alpha:
                alpha = v
        self.tt[key] = (depth, best)
        return best

    def go(self, board, max_depth=None):
        """反復深化。(bestmove, score, depth, nodes) を返す。"""
        self.nodes = 0
        self.tt.clear()
        md = max_depth or self.max_depth
        best_move, best_score = None, -MATE
        for depth in range(1, md + 1):
            alpha, beta = -MATE, MATE
            cur_move, cur_score = None, -MATE
            moves = []
            for m in board.legal_moves:
                pri = 100 if m == best_move else PT_POINT[cshogi.move_cap(m)]
                moves.append((pri, m))
            if not moves:
                return None, -MATE, depth, self.nodes
            moves.sort(key=lambda x: -x[0])
            for _, m in moves:
                board.push(m)
                v = -self.search(board, depth - 1, -beta, -alpha, 1)
                board.pop()
                if v > cur_score:
                    cur_score, cur_move = v, m
                if v > alpha:
                    alpha = v
            best_move, best_score = cur_move, cur_score
            if abs(best_score) >= WIN - 1000:
                break
        return best_move, best_score, md, self.nodes
