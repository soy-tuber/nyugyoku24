# -*- coding: utf-8 -*-
"""評価に使う特徴量の抽出。重みは外から与える (自動調整の対象)。

これまでの評価に欠けていたのは「駒の安全性」だった。
所有点数・宣言点数・敵陣内の枚数・持ち駒枚数・玉の位置のどれも、
その駒が取られるかどうかを表していない。だから
  - 取られるマスに打ち込む (局3: 7枚で停滞)
  - 勝勢の駒を取られ続ける  (局1: 所有34点 -> 22点)
という失敗が起きた。重みをいくら調整しても、無い特徴量は補えない。

安全性は指し手生成から取る。手番側の合法手と、push_pass() 後の相手の合法手、
計2回の生成で両者分をまとめて作る (色ごとに呼ぶと3回になる)。

注意: 駒を打つ手の行き先は「利き」ではない。打てるマスは取られるマスではないので、
      利きの集合からは駒打ちを除外する。
"""
import cshogi

from engine_decl24 import PT_POINT, HAND_POINT, ZONE, NEED_N, WIN_POINT

NAMES = [
    'own',        # min(所有点数, 31)      駒取りでしか動かない保存量。31で飽和 -> 自動フェーズ切替
    'own_x',      # max(0, 所有点数 - 31)  余剰 = 取られる余裕
    'dec',        # min(宣言点数, 31)      持駒 + 敵陣内。運び込みで動く
    'zone_n',     # min(敵陣内の駒数, 10)
    'zone_pot',   # 打てば届く分 (持ち駒枚数)
    'zone_x',     # max(0, 敵陣内の駒数 - 10)
    'king_in',    # 玉が敵陣三段目以内 (宣言の前提条件)
    'hang_all',   # 相手に取られうる自駒の点数合計
    'hang_zone',  # うち敵陣内にあるもの (取られると点数も枚数も失う)
    'safe_drop',  # 敵陣の空きマスのうち相手の利きが無いもの (打ち込める場所)
    'threat',     # 自分が取れる相手の駒の点数合計 (所有点数を増やす唯一の手段)
]
NF = len(NAMES)

INIT_W = [
    20.0,    # own
    4.0,     # own_x
    10.0,    # dec
    25.0,    # zone_n
    12.0,    # zone_pot
    6.0,     # zone_x
    400.0,   # king_in
    -18.0,   # hang_all
    -12.0,   # hang_zone
    2.0,     # safe_drop
    6.0,     # threat
]


def _side_scan(board, color, occupied):
    """盤面と持ち駒だけから取れる分 (指し手生成を使わない)。"""
    pieces = board.pieces
    is_white = (color == cshogi.WHITE)
    zone = ZONE[color]
    owned = zone_pts = n = 0
    for sq in occupied:
        pc = pieces[sq]
        if (pc >= 17) != is_white:
            continue
        pt = cshogi.piece_to_piece_type(pc)
        if pt == cshogi.KING:
            continue
        v = PT_POINT[pt]
        owned += v
        if sq in zone:
            zone_pts += v
            n += 1
    hand_pts = hand_cnt = 0
    for i, c in enumerate(board.pieces_in_hand[color]):
        if c:
            hand_pts += HAND_POINT[i] * c
            hand_cnt += c
    return owned + hand_pts, zone_pts + hand_pts, n, hand_cnt


def _movegen_scan(board):
    """手番側の (取れる点数, 利きのマス集合) を1回の生成で得る。
       駒打ちの行き先は利きに含めない。"""
    cover = set()
    threat = 0
    for m in board.legal_moves:
        cap = cshogi.move_cap(m)
        to = cshogi.move_to(m)
        if cap:
            threat += PT_POINT[cap]
        if not cshogi.move_is_drop(m):
            cover.add(to)
    return threat, cover


def extract_both(board):
    """(先手の特徴量, 後手の特徴量) を返す。指し手生成は2回だけ。"""
    pieces = board.pieces
    occupied = [sq for sq in range(81) if pieces[sq]]
    occ = set(occupied)

    stm = board.turn
    opp = 1 - stm
    in_check = board.is_check()

    # 手番側の生成
    threat_stm, cover_stm = _movegen_scan(board)
    # 相手側の生成 (王手中は手番を渡せないので、その場合は諦める)
    if in_check:
        threat_opp, cover_opp = 0, set()
    else:
        board.push_pass()
        try:
            threat_opp, cover_opp = _movegen_scan(board)
        finally:
            board.pop_pass()

    out = {}
    for color in (cshogi.BLACK, cshogi.WHITE):
        owned, dec, n, hand_cnt = _side_scan(board, color, occupied)
        if color == stm:
            threat = threat_stm
            enemy_cover = cover_opp
            hang = threat_opp          # 相手が取れる = 自分が取られる
        else:
            threat = threat_opp
            enemy_cover = cover_stm
            hang = threat_stm
        # 敵陣内で取られうる分は、点数と枚数の両方を失うので別項にする
        zone = ZONE[color]
        hang_zone = 0
        if hang:
            src = board if color != stm else None
            # 敵陣内の自駒のうち相手の利きが乗っているものの点数
            for sq in zone:
                pc = pieces[sq]
                if pc and ((pc >= 17) == (color == cshogi.WHITE)):
                    pt = cshogi.piece_to_piece_type(pc)
                    if pt != cshogi.KING and sq in enemy_cover:
                        hang_zone += PT_POINT[pt]
        safe_drop = 0
        if hand_cnt:
            for sq in zone:
                if sq not in occ and sq not in enemy_cover:
                    safe_drop += 1
            if safe_drop > 12:
                safe_drop = 12
        have = min(n, NEED_N)
        reach = min(NEED_N, n + hand_cnt)
        out[color] = (
            float(min(owned, WIN_POINT)),
            float(max(0, owned - WIN_POINT)),
            float(min(dec, WIN_POINT)),
            float(have),
            float(reach - have),
            float(max(0, n - NEED_N)),
            1.0 if board.king_square(color) in zone else 0.0,
            float(min(hang, 30)),
            float(min(hang_zone, 30)),
            float(safe_drop),
            float(min(threat, 20)),
        )
    return out[cshogi.BLACK], out[cshogi.WHITE]


def extract(board, color):
    fb, fw = extract_both(board)
    return fb if color == cshogi.BLACK else fw
