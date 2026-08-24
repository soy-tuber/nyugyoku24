# -*- coding: utf-8 -*-
"""重みベクトルを外から受け取るエンジン。自動調整の対象。"""
import cshogi

from features import extract_both, NF, INIT_W, NAMES
from engine_decl24 import PT_POINT, HAND_POINT, ZONE, declaration, NEED_N, WIN_POINT

WIN = 30000
MATE = 32000


class LearnEngine:
    def __init__(self, w=None, max_depth=3):
        self.w = list(w) if w is not None else list(INIT_W)
        self.max_depth = max_depth
        self.nodes = 0
        self.tt = {}

    def evaluate(self, board):
        w = self.w
        fb, fw = extract_both(board)
        a, b = (fb, fw) if board.turn == cshogi.BLACK else (fw, fb)
        s = 0.0
        for i in range(NF):
            s += (a[i] - b[i]) * w[i]
        return s

    def order_key(self, board, m, us):
        to = cshogi.move_to(m)
        cap = cshogi.move_cap(m)
        in_zone = to in ZONE[us]
        is_drop = cshogi.move_is_drop(m)
        k = 0
        if cap:
            k += 70 + PT_POINT[cap] * 6
        if in_zone:
            if is_drop:
                k += 25
            elif cshogi.move_from(m) not in ZONE[us]:
                k += 45
            else:
                k += 5
        elif is_drop:
            k -= 40 + HAND_POINT[cshogi.move_drop_hand_piece(m)] * 8
        elif cshogi.move_from(m) in ZONE[us]:
            k -= 55
        return -k

    def search(self, board, depth, alpha, beta, ply):
        self.nodes += 1
        rep = board.is_draw()
        if rep == cshogi.REPETITION_DRAW:
            return 0.0
        if rep == cshogi.REPETITION_WIN:      # 連続王手の千日手: 相手の反則
            return WIN - ply
        if rep == cshogi.REPETITION_LOSE:     # 連続王手の千日手: 自分の反則
            return -WIN + ply
        side = board.turn
        in_check = board.is_check()
        d = declaration(board, side, in_check)
        if d == 'win':
            return WIN - ply
        if d == 'draw':
            if 0 >= beta:
                return 0.0
            if 0 > alpha:
                alpha = 0.0
        if depth <= 0:
            return self.evaluate(board)
        key = (board.zobrist_hash(), side)
        ent = self.tt.get(key)
        if ent is not None and ent[0] >= depth:
            return ent[1]
        moves = sorted(board.legal_moves, key=lambda m: self.order_key(board, m, side))
        if not moves:
            return -MATE + ply
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

    def pick(self, board):
        self.nodes = 0
        self.tt.clear()
        side = board.turn
        if declaration(board, side) == 'win':
            return 'declare_win', WIN
        best_move, best_score = None, -MATE
        for depth in range(1, self.max_depth + 1):
            alpha = -MATE
            cur_move, cur_score = None, -MATE
            moves = sorted(board.legal_moves,
                           key=lambda m: (0 if m == best_move else 1,
                                          self.order_key(board, m, side)))
            if not moves:
                return None, -MATE
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
        return best_move, best_score


def _progress_frac(board, color):
    """宣言条件への到達率を 0..1 で返す。引き分け局にも連続的な信号を与えるため。"""
    from features import extract_both
    fb, fw = extract_both(board)
    f = fb if color == cshogi.BLACK else fw
    dec = f[2]                   # min(宣言点数, 31)
    n = f[3]                     # min(敵陣内の駒数, 10)
    return 0.5 * (dec / WIN_POINT) + 0.4 * (n / NEED_N) + 0.1 * f[6]


def game(sfen, w_black, w_white, max_plies=140, depth=3):
    """先手に w_black、後手に w_white を持たせて1局指す。
       戻り値: (先手視点の得点, 手数)
       決着すれば ±1。決着しなければ宣言条件への到達率の差 (-0.9..0.9)。
       引き分け局を捨てずに信号として使うための密な採点。"""
    b = cshogi.Board(sfen)
    eb = LearnEngine(w_black, depth)
    ew = LearnEngine(w_white, depth)
    for i in range(max_plies):
        side = b.turn
        if declaration(b, side) == 'win':
            return (1.0 if side == cshogi.BLACK else -1.0), i
        eng = eb if side == cshogi.BLACK else ew
        mv, sc = eng.pick(b)
        if mv is None:                       # 詰まされた
            return (-1.0 if side == cshogi.BLACK else 1.0), i
        if not isinstance(mv, int):
            return (1.0 if side == cshogi.BLACK else -1.0), i
        b.push(mv)
        if b.is_draw() == cshogi.REPETITION_DRAW:
            break
    d = _progress_frac(b, cshogi.BLACK) - _progress_frac(b, cshogi.WHITE)
    return max(-0.9, min(0.9, d)), i + 1
