# -*- coding: utf-8 -*-
"""相入玉 統合エンジン — 「取られない・取りまくる・勝ちが見えたら勝ちに動く」

構造:
    所有点数 = 自分の全駒 (盤上どこでも) + 持ち駒     … 先後合計54の保存量
    宣言点数 = 持ち駒 + 敵陣三段目以内の駒            … 入玉宣言法が数える量
    取り残し = 所有点数 - 宣言点数                    … 敵陣外で死んでいる自駒

    宣言点数 <= 所有点数 なので、所有点数が31未満なら
    どれだけ運び込んでも24点法の宣言勝ちは数学的に不可能である。
    そして所有点数は駒取りでしか動かない。

    したがって目的は2段階になる。
      第1段階 (駒取り)  : 所有点数を31以上にする。相手と厳密に零和
      第2段階 (変換)    : 取り残しを敵陣に運び込み、敵陣内10枚を満たす

    フェーズ判定は書かない。min(所有点数, 31) を評価に入れるだけで、
    31に達した瞬間に飽和して限界価値が変換側へ移る。

実測 (floodgate 打ち切り相入玉局 12,670サンプル):
    所有31点以上            32.8%
    かつ宣言点数31以上       13.8%  (所有31点ある側の 42.0%)
    かつ敵陣内10枚          2.8%   (変換できた側の 20.6%)
    所有31点以上の側の取り残しは中央値7点
"""
import cshogi

from engine_decl24 import (PT_POINT, HAND_POINT, ZONE, ZONE_LIST,
                           NEED_N, WIN_POINT, DRAW_POINT, declaration, zone_stats)

WIN = 30000
MATE = 32000

# --- 重み ---
W_OWN = 20      # 所有点数 (31まで)。保存量なので差分評価では実質2倍効く = 駒取りと防御の主項
W_OWN_X = 4     # 31点を超えた所有点数。取られる余裕なので0にはしない
W_DEC = 10      # 宣言点数 (31まで)。運び込みで動く
W_N = 25        # 敵陣三段目以内の駒数 (10枚まで)
W_POT = 12      # 持ち駒 = 1手で敵陣に届く予備の駒
W_N_X = 6       # 10枚を超えた分
W_KING = 400    # 玉が敵陣にいることは宣言の前提条件
W_ADV = 0.8     # 取り残し (敵陣外の自駒) の前進。1段近づくごとに 駒点 x W_ADV
                # 敵陣の1段手前でも 5 x W_ADV x 駒点 = 飛角で20 < W_N なので、
                # 敵陣に入る手が常に得になる (宣言点数が31で飽和した後も)

# 敵陣外のマスから敵陣三段目までの段数 (1..6)。敵陣内は 0。
# cshogi の square は (筋-1)*9 + (段-1)。先手の敵陣 = 1〜3段目。
ZONE_DIST = {
    cshogi.BLACK: [max(0, sq % 9 - 2) for sq in range(81)],
    cshogi.WHITE: [max(0, 6 - sq % 9) for sq in range(81)],
}


def full_stats(board, color):
    """(owned, declarable, n, hand_cnt, king_in) を返す。"""
    return _stats(board, color)[:5]


def _stats(board, color):
    """full_stats に加えて adv (取り残しの前進度) を返す。

    adv = 敵陣外の自駒について 駒点 x (6 - 敵陣までの段数) の和。
    宣言点数は敵陣に入った瞬間にしか動かないので、敵陣まで3手以上かかる
    取り残しは浅い探索では評価が平坦になり、運び込まれない (地平線効果)。
    2026-10-04 の floodgate 局 (miao-R vs Sense) から始めた自己対局で、
    所有32点・敵陣22枚・宣言30点のまま 自陣の歩2枚を残して250手停滞した。
    これを段数の勾配で埋める。

    減点 (遠いほどマイナス) ではなく加点にしている理由:
    減点だと、取り残しを相手に取らせれば減点ごと消えるので
    「遠くの駒を捨てる」手が得に見えてしまう。加点なら駒を失うと加点も失う。
    """
    pieces = board.pieces
    is_white = (color == cshogi.WHITE)
    zone = ZONE[color]
    owned = 0
    zone_pts = 0
    n = 0
    adv = 0
    dist = ZONE_DIST[color]
    for sq in range(81):
        pc = pieces[sq]
        if not pc or (pc >= 17) != is_white:
            continue
        pt = cshogi.piece_to_piece_type(pc)
        if pt == cshogi.KING:
            continue
        v = PT_POINT[pt]
        owned += v
        if sq in zone:
            zone_pts += v
            n += 1
        else:
            adv += v * (6 - dist[sq])
    hand_pts = 0
    hand_cnt = 0
    for i, c in enumerate(board.pieces_in_hand[color]):
        if c:
            hand_pts += HAND_POINT[i] * c
            hand_cnt += c
    owned += hand_pts
    king_in = board.king_square(color) in zone
    return owned, zone_pts + hand_pts, n, hand_cnt, king_in, adv


def value(board, color):
    owned, dec, n, h, king_in, adv = _stats(board, color)
    have = min(n, NEED_N)
    reach = min(NEED_N, n + h)
    v = (W_OWN * min(owned, WIN_POINT)          # 第1段階: 駒取り。31で飽和
         + W_OWN_X * max(0, owned - WIN_POINT)
         + W_DEC * min(dec, WIN_POINT)          # 第2段階: 変換
         + W_N * have
         + W_POT * (reach - have)
         + W_N_X * max(0, n - NEED_N)
         + int(W_ADV * adv))
    if king_in:
        v += W_KING
    return v


def evaluate(board):
    us = board.turn
    return value(board, us) - value(board, 1 - us)


class UnifiedEngine:
    def __init__(self, max_depth=3):
        self.max_depth = max_depth
        self.nodes = 0
        self.tt = {}

    def order_key(self, board, m, us):
        to = cshogi.move_to(m)
        cap = cshogi.move_cap(m)
        in_zone = to in ZONE[us]
        is_drop = cshogi.move_is_drop(m)
        k = 0
        if cap:
            k += 70 + PT_POINT[cap] * 6      # 駒取りが最優先 (所有点数を動かす唯一の手段)
        if in_zone:
            if is_drop:
                k += 25
            elif cshogi.move_from(m) not in ZONE[us]:
                k += 45                      # 運び込み: 取り残しを減らす
            else:
                k += 5
        elif is_drop:
            k -= 40 + HAND_POINT[cshogi.move_drop_hand_piece(m)] * 8   # 敵陣外は純損失
        elif cshogi.move_from(m) in ZONE[us]:
            k -= 55
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
        side = board.turn
        in_check = board.is_check()
        d = declaration(board, side, in_check)
        if d == 'win':
            return WIN - ply
        if d == 'draw':
            if 0 >= beta:
                return 0
            if 0 > alpha:
                alpha = 0
        if depth <= 0:
            return evaluate(board)
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
