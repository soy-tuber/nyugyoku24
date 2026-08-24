# -*- coding: utf-8 -*-
"""攻撃側 / 防御側の役割固定エンジンと、攻防入れ替えによる局面判定。

設計:
    目的量を一つに固定する。
        V = progress(攻撃側)   … 入玉宣言法24点法の宣言条件への到達度
    攻撃側は V を最大化し、防御側は V を最小化する。完全な零和ゲームになる。

    この定義は構造的に自己整合する。守備側が駒を取られると、その駒は
    攻撃側の持ち駒に入って点数に数えられる (24点法の点数は 持駒 + 敵陣内の駒)。
    したがって「駒を渡して妨害する」ことは不可能で、V を最小化するだけで
    守備側は自駒も守る。別の防御項を足す必要がない。

判定:
    attacker_win : 攻撃側が31点の宣言勝ちに到達
    defender_win : 攻撃側が詰まされた / 防御側が自力で宣言勝ちした
    draw         : 手数上限まで防がれた / 千日手 / 攻撃側が24-30点で無勝負宣言

    1つの局面について「先手が攻め」「後手が攻め」の2回を走らせ、
    両方の結果から局面を分類する。
"""
import cshogi

from engine_decl24 import (zone_stats, declaration, progress, ZONE,
                           PT_POINT, HAND_POINT, NEED_N, WIN_POINT, DRAW_POINT)

WIN = 30000
MATE = 32000


class RoleEngine:
    """役割固定エンジン。attacker の宣言到達度 V だけを目的量とする。"""

    def __init__(self, attacker, max_depth=3, pure=True):
        self.attacker = attacker          # cshogi.BLACK or cshogi.WHITE
        self.defender = 1 - attacker
        self.pure = pure                  # True: 防御側は妨害専門 (自分の到達度を持たない)
        self.max_depth = max_depth
        self.nodes = 0
        self.tt = {}

    # ---- 攻撃側から見た値 ----
    def leaf(self, board):
        # pure=True では目的量は progress(攻撃側) ただ一つ。
        # 防御側はこれを最小化するだけで、自分の宣言到達度を目的に持たない。
        if self.pure:
            return progress(board, self.attacker)
        return progress(board, self.attacker) - progress(board, self.defender)

    def order_key(self, board, m, side):
        """攻撃側は敵陣へ、防御側は攻撃側の敵陣駒を取る手を優先する。"""
        to = cshogi.move_to(m)
        cap = cshogi.move_cap(m)
        k = 0
        if side == self.attacker:
            is_drop = cshogi.move_is_drop(m)
            if to in ZONE[self.attacker]:
                if is_drop:
                    k += 50
                elif cshogi.move_from(m) not in ZONE[self.attacker]:
                    k += 60
                else:
                    k += 5
            elif is_drop:
                # 敵陣外への打ち込みは点数の純損失 (持駒は計上、自陣の盤上駒は非計上)
                k -= 40 + HAND_POINT[cshogi.move_drop_hand_piece(m)] * 8
            elif cshogi.move_from(m) in ZONE[self.attacker]:
                k -= 60
            if cap:
                k += 20 + PT_POINT[cap] * 2
        else:
            # 防御側: 攻撃側の敵陣内の駒を取る手が最優先
            if cap and to in ZONE[self.attacker]:
                k += 80 + PT_POINT[cap] * 2
            elif cap:
                k += 15 + PT_POINT[cap] * 2
            if to in ZONE[self.attacker]:
                k += 10          # 攻撃側の敵陣に利きを作る
        return -k

    def search(self, board, depth, alpha, beta, ply):
        """negamax。手番側から見た値を返す。"""
        self.nodes += 1
        rep = board.is_draw()
        if rep == cshogi.REPETITION_DRAW:
            return 0
        if rep == cshogi.REPETITION_WIN:      # 連続王手の千日手: 相手の反則
            return WIN - ply
        if rep == cshogi.REPETITION_LOSE:     # 連続王手の千日手: 自分の反則
            return -WIN + ply
        side = board.turn
        sign = 1 if side == self.attacker else -1
        in_check = board.is_check()

        d = declaration(board, side, in_check)
        if side == self.attacker:
            if d == 'win':
                return WIN - ply                     # 攻撃側の手番、攻撃側が勝ち
            if d == 'draw':                          # 無勝負を確保できる = 0 が下限
                if 0 >= beta:
                    return 0
                if 0 > alpha:
                    alpha = 0
        elif not self.pure:
            if d == 'win':
                return WIN - ply                     # 防御側の手番、防御側が勝ち

        if depth <= 0:
            return sign * self.leaf(board)

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


def play(sfen, attacker, max_plies=120, depth=3, pure=True):
    """1局面を攻撃側固定で最後まで指し継ぐ。(結果, 手数, 記録) を返す。"""
    board = cshogi.Board(sfen)
    eng = RoleEngine(attacker, depth, pure)
    trace = []
    for i in range(max_plies):
        side = board.turn
        d = declaration(board, side)
        if d == 'win':
            if side == attacker:
                return 'attacker_win', i, trace
            if not pure:
                return 'defender_win', i, trace
        mv, sc = eng.pick(board)
        if mv is None:
            # 手番側が詰まされた
            return ('defender_win' if side == attacker else 'attacker_win'), i, trace
        board.push(mv)
        if board.is_draw() == cshogi.REPETITION_DRAW:
            return 'draw', i + 1, trace
        if i % 10 == 0:
            n, p, k = zone_stats(board, attacker)
            trace.append((i, n, p, k))
    return 'draw', max_plies, trace


def judge(sfen, max_plies=120, depth=3, pure=True):
    """攻防を入れ替えて2回走らせ、局面を分類する。"""
    rb, nb, tb = play(sfen, cshogi.BLACK, max_plies, depth, pure)
    rw, nw, tw = play(sfen, cshogi.WHITE, max_plies, depth, pure)
    black_ok = (rb == 'attacker_win')
    white_ok = (rw == 'attacker_win')
    if black_ok and white_ok:
        verdict = '攻めた側が勝つ (防御が機能せず)'
    elif black_ok:
        verdict = '先手優勢'
    elif white_ok:
        verdict = '後手優勢'
    else:
        verdict = '引き分け (双方防御可能)'
    return verdict, (rb, nb), (rw, nw), (tb, tw)
