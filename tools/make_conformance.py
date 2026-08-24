# -*- coding: utf-8 -*-
"""入玉宣言法 24点法 適合性テスト集合の生成。

なぜ作るか:
    positions/ の局面は floodgate から採った実戦の相入玉局面で、すべて
    「宣言できるか、まだできないか」の陽性側しか含んでいない。しかし
    入玉宣言法の適合性は半分が陰性側にある。

      第5項「条件1〜4のうち一つでも満たしていない場合、宣言側が負けとなる」

    つまり適合性とは
      (1) 宣言できるときに宣言する
      (2) 宣言してはいけないときに宣言しない
    の両方であり、(2) の方が診断力が高い。27点法で作られたエンジンは
    24〜30点で宣言して指し直しにする、あるいは28点で運び込みを止める、という
    予測可能な形で (2) に失敗する。これは弱さではなく目的関数の不一致の署名である。

作り方:
    実戦局面を改変すると合法性の保証が難しいので、空の盤に構成する。
    測りたい量 (敵陣内の枚数 n / 宣言点数 p / 玉の位置 / 王手 / 手数) だけを
    動かし、他をすべて固定する。tsumego 側で 2x2 行列を組んだのと同じ理屈で、
    交絡を持ち込まないため。

    盤上の小駒には「と金」を使う。と金は1点で、行き所のない駒にならず、
    二歩の制約も受けないので、枚数と点数を独立に制御できる。

正解ラベル:
    engine_decl24.declaration() を使わず、規則の条文から書き起こした
    ref_declaration() で採点する。さらに構成時の意図した (n, p) と
    盤面から数え直した (n, p) が一致することを表明する。二重の独立検査。

使い方:
    python tools/make_conformance.py            # positions/conformance.tsv を書く
    python tools/make_conformance.py --stdout   # 標準出力に出す
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'engine'))
import cshogi

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'positions', 'conformance.tsv')

# ---------------------------------------------------------------- 規則 (条文からの独立実装)
# 第4項一: 大駒(飛・角)1枚を5点、小駒(金・銀・桂・香・歩)1枚を1点。玉は数えない。
# 成駒は元の駒として数える (成った飛角は大駒5点、と金等は小駒1点)。
BIG = set('RB')      # 成っても大駒
SMALL = set('GSNLP')
NEED_N = 10          # 条件2: 敵陣三段目以内に玉を除いて10枚以上
WIN_POINT = 31       # 条件4A: 31点以上で勝ち
DRAW_POINT = 24      # 条件4B: 24〜30点で指し直し
MAX_PLY = 500        # 第5項: 手数が500手に満たない場合に使用できる


def base_char(ch):
    """成駒を元の駒に落とす。'+P' -> 'P'"""
    return ch[-1].upper()


def piece_point(ch):
    b = base_char(ch)
    if b == 'K':
        return 0
    return 5 if b in BIG else 1


def zone_ranks(color):
    """敵陣三段目以内の段番号。先手にとっては1〜3段、後手にとっては7〜9段。"""
    return (1, 2, 3) if color == cshogi.BLACK else (7, 8, 9)


def ref_declaration(board, color):
    """条文から書き起こした宣言判定。engine 側の実装を一切参照しない。

    戻り値: 'win' / 'draw' / None (Noneは「宣言すれば負けるので宣言不可」)
    """
    if board.turn != color:
        return None                                   # 宣言側の手番であること
    if board.move_number - 1 >= MAX_PLY:
        return None                                   # 第5項: 手数500未満であること
    ranks = zone_ranks(color)
    pieces = board.pieces
    n = 0
    pts = 0
    king_in = False
    for sq in range(81):
        pc = pieces[sq]
        if not pc:
            continue
        is_white_piece = pc >= 17
        if is_white_piece != (color == cshogi.WHITE):
            continue
        rank = sq % 9 + 1
        ch = cshogi.PIECE_SYMBOLS[cshogi.piece_to_piece_type(pc)].upper()
        if rank not in ranks:
            continue
        if ch.endswith('K'):
            king_in = True                            # 条件1: 玉が敵陣三段目以内
            continue
        n += 1                                        # 条件2: 玉を除く枚数
        pts += piece_point(ch)
    for i, cnt in enumerate(board.pieces_in_hand[color]):
        if cnt:
            hp = cshogi.hand_piece_to_piece_type(cshogi.HAND_PIECES[i])
            ch = cshogi.PIECE_SYMBOLS[hp].upper()
            pts += piece_point(ch) * cnt              # 持ち駒も点数に入る (枚数には入らない)
    if not king_in:
        return None
    if n < NEED_N:
        return None
    if board.is_check():                              # 条件3: 王手がかかっていない
        return None
    if pts >= WIN_POINT:
        return 'win'
    if pts >= DRAW_POINT:
        return 'draw'
    return None                                       # 23点以下で宣言すれば負け


def ref_count(board, color):
    """(敵陣内枚数, 宣言点数, 玉が敵陣内) を条文から数え直す。"""
    ranks = zone_ranks(color)
    pieces = board.pieces
    n = pts = 0
    king_in = False
    for sq in range(81):
        pc = pieces[sq]
        if not pc or (pc >= 17) != (color == cshogi.WHITE):
            continue
        if sq % 9 + 1 not in ranks:
            continue
        ch = cshogi.PIECE_SYMBOLS[cshogi.piece_to_piece_type(pc)].upper()
        if ch.endswith('K'):
            king_in = True
            continue
        n += 1
        pts += piece_point(ch)
    for i, cnt in enumerate(board.pieces_in_hand[color]):
        if cnt:
            hp = cshogi.hand_piece_to_piece_type(cshogi.HAND_PIECES[i])
            pts += piece_point(cshogi.PIECE_SYMBOLS[hp].upper()) * cnt
    return n, pts, king_in


# ---------------------------------------------------------------- 盤面の構成
MAX_PIECES = {'P': 18, 'L': 4, 'N': 4, 'S': 4, 'G': 4, 'B': 2, 'R': 2, 'K': 2}


class Position(object):
    """(筋, 段) -> 駒文字 の辞書として盤を持ち、SFEN を吐く。"""

    def __init__(self):
        self.sq = {}                     # (file 1-9, rank 1-9) -> 'P' / '+P' / 'p' ...
        self.hand = {cshogi.BLACK: {}, cshogi.WHITE: {}}
        self.turn = cshogi.BLACK
        self.ply = 1                     # SFEN の手数フィールド

    def put(self, file, rank, ch):
        assert (file, rank) not in self.sq, '重複配置 (%d,%d)' % (file, rank)
        self.sq[(file, rank)] = ch

    def give(self, color, ch, n=1):
        if n:
            self.hand[color][ch] = self.hand[color].get(ch, 0) + n

    def sfen(self):
        rows = []
        for rank in range(1, 10):
            row, blank = '', 0
            for file in range(9, 0, -1):
                ch = self.sq.get((file, rank))
                if ch is None:
                    blank += 1
                    continue
                if blank:
                    row += str(blank)
                    blank = 0
                row += ch
            if blank:
                row += str(blank)
            rows.append(row)
        hand = ''
        for color, up in ((cshogi.BLACK, True), (cshogi.WHITE, False)):
            for ch in 'RBGSNLP':
                c = self.hand[color].get(ch, 0)
                if c:
                    hand += ('' if c == 1 else str(c)) + (ch if up else ch.lower())
        return '%s %s %s %d' % ('/'.join(rows), 'b' if self.turn == cshogi.BLACK else 'w',
                                hand or '-', self.ply)


class _quiet(object):
    """cshogi の C++ 側が標準出力に吐く診断を抑える。

    相手玉の候補マスを総当たりする過程では、不正な局面を Board() に渡すことが
    前提になっている。そのたびに盤面が印字されると出力が読めなくなる。
    """

    def __enter__(self):
        sys.stdout.flush()
        self.saved = os.dup(1)
        self.null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self.null, 1)
        return self

    def __exit__(self, *exc):
        sys.stdout.flush()
        os.dup2(self.saved, 1)
        os.close(self.null)
        os.close(self.saved)
        return False


def validate(pos):
    """cshogi の is_ok() が見ない部分も含めて合法性を検査する。

    is_ok() が見るのは「玉が双方揃っているか」と「手番でない側が王手されていないか」
    だけで、駒数超過・二歩・行き所のない駒は素通しする。ここで自前で見る。
    """
    errs = []
    # 駒数
    cnt = {}
    for ch in pos.sq.values():
        cnt[base_char(ch)] = cnt.get(base_char(ch), 0) + 1
    for color in (cshogi.BLACK, cshogi.WHITE):
        for ch, c in pos.hand[color].items():
            cnt[base_char(ch)] = cnt.get(base_char(ch), 0) + c
    for ch, c in cnt.items():
        if c > MAX_PIECES.get(ch, 0):
            errs.append('駒数超過 %s x%d (上限%d)' % (ch, c, MAX_PIECES.get(ch, 0)))
    # 玉は各1枚
    kings = [ch for ch in pos.sq.values() if base_char(ch) == 'K']
    if sorted(kings) != ['K', 'k']:
        errs.append('玉の枚数が不正 %s' % kings)
    # 行き所のない駒
    for (f, r), ch in pos.sq.items():
        if ch.startswith('+'):
            continue
        if ch == 'P' or ch == 'L':
            if r == 1:
                errs.append('行き所のない駒 先手%s %d%d' % (ch, f, r))
        elif ch == 'N':
            if r <= 2:
                errs.append('行き所のない駒 先手N %d%d' % (f, r))
        elif ch == 'p' or ch == 'l':
            if r == 9:
                errs.append('行き所のない駒 後手%s %d%d' % (ch, f, r))
        elif ch == 'n':
            if r >= 8:
                errs.append('行き所のない駒 後手n %d%d' % (f, r))
    # 二歩 (成っていない歩のみ)
    for up in (True, False):
        per_file = {}
        for (f, r), ch in pos.sq.items():
            if ch == ('P' if up else 'p'):
                per_file[f] = per_file.get(f, 0) + 1
        for f, c in per_file.items():
            if c > 1:
                errs.append('二歩 %s %d筋' % ('先手' if up else '後手', f))
    # cshogi 側 (玉の有無・手番でない側の王手)
    with _quiet():
        board = cshogi.Board(pos.sfen())
        ok = board.is_ok()
    if not ok:
        errs.append('cshogi is_ok() が False')
    return board, errs


# ---------------------------------------------------------------- 利きの前判定
# 相手玉を置く前に、そのマスが宣言側の駒に取られていないかを自前で見る。
# cshogi は不正な局面を Board() に渡すと C++ 側のバッファに盤面を吐き、
# Python からは止められないタイミングでフラッシュされる。不正局面を作らないのが唯一の解。
# ここで扱うのは build() が実際に置く駒種だけ (K, R, B, と金, 香)。未知の駒は表明で落とす。
def _attack_squares(pos, f, r, ch):
    """(f, r) にある駒 ch が利いているマスの集合。占有は pos.sq で見る。"""
    up = ch[-1].isupper()
    fwd = -1 if up else 1                       # 先手は段が減る向きが前
    base = base_char(ch)
    out = set()

    def ray(df, dr):
        cf, cr = f + df, r + dr
        while 1 <= cf <= 9 and 1 <= cr <= 9:
            out.add((cf, cr))
            if (cf, cr) in pos.sq:
                break                            # 駒に当たったらそこまで (そのマスは利き)
            cf += df
            cr += dr

    def step(df, dr):
        if 1 <= f + df <= 9 and 1 <= r + dr <= 9:
            out.add((f + df, r + dr))

    if base == 'K':
        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if df or dr:
                    step(df, dr)
    elif base == 'R':
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ray(*d)
        if ch.startswith('+'):
            for df in (-1, 1):
                for dr in (-1, 1):
                    step(df, dr)
    elif base == 'B':
        for d in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            ray(*d)
        if ch.startswith('+'):
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                step(*d)
    elif base == 'L':
        if ch.startswith('+'):
            for d in ((0, fwd), (1, fwd), (-1, fwd), (1, 0), (-1, 0), (0, -fwd)):
                step(*d)                         # 成香は金と同じ
        else:
            ray(0, fwd)
    elif base in ('P', 'G', 'S', 'N'):
        assert ch.startswith('+') or base in ('P', 'G'), '未対応の駒 %s' % ch
        if base == 'P' and not ch.startswith('+'):
            step(0, fwd)                         # 歩
        else:
            for d in ((0, fwd), (1, fwd), (-1, fwd), (1, 0), (-1, 0), (0, -fwd)):
                step(*d)                         # 金・と金・成香成桂成銀
    else:
        raise AssertionError('未対応の駒 %s' % ch)
    return out


def _is_attacked(pos, target, by_upper):
    """target が by_upper 側 (True=先手) の駒に取られているか。"""
    for (f, r), ch in pos.sq.items():
        if ch[-1].isupper() != by_upper:
            continue
        if target in _attack_squares(pos, f, r, ch):
            return True
    return False


# ---------------------------------------------------------------- 目標 (n, p) の実現
def solve_composition(n, p):
    """敵陣内 n 枚・宣言点数 p 点を実現する (と金, 大駒, 持歩, 持大駒) を返す。

    盤上: と金 a 枚 (1点) + 大駒 b 枚 (5点)   -> 枚数 n = a + b
    持駒: 歩   c 枚 (1点) + 大駒 d 枚 (5点)   -> 点数 p = a + 5b + c + 5d
    制約: a + c <= 18 (歩は全部で18枚), b + d <= 4 (飛2 + 角2)
    """
    for b in range(min(4, n), -1, -1):
        a = n - b
        if a > 18:
            continue
        rest = p - (a + 5 * b)
        if rest < 0:
            continue
        for d in range(min(4 - b, rest // 5), -1, -1):
            c = rest - 5 * d
            if 0 <= c <= 18 - a:
                return a, b, c, d
    return None


BIG_ORDER = ['R', 'R', 'B', 'B']        # 盤上・持駒あわせて飛2角2まで


def _opponent_king_candidates(color):
    """相手玉を置く候補マス。宣言側の敵陣から遠い側を優先して総当たりする。"""
    far = zone_ranks(1 - color)          # 宣言側から見た自陣側 = 相手玉が入玉している側
    order = list(far) + [r for r in range(1, 10) if r not in far]
    for r in order:
        for f in range(1, 10):
            yield f, r


def build(color, n, p, king_in=True, check=False, ply=1):
    """宣言側 color について、敵陣内 n 枚・宣言点数 p 点の局面を構成する。

    相手玉の位置だけは総当たりで決める。宣言側の飛角が相手玉に利いてしまうと
    「手番でない側が王手されている」非合法局面になるため、置ける場所は
    盤面の中身に依存して変わる。最初に合法になったマスを採る (決定的)。
    """
    comp = solve_composition(n, p)
    if comp is None:
        return None, ['(n=%d, p=%d) は構成不能' % (n, p)]
    a, b, c, d = comp
    up = (color == cshogi.BLACK)
    def own(ch):
        return ch if up else ch.lower()
    def opp(ch):
        return ch.lower() if up else ch

    zr = zone_ranks(color)
    krank = (zr[2] if up else zr[0]) if king_in else 5    # 王手用の香を置ける段に寄せる
    kfile = 5

    def skeleton():
        """相手玉以外をすべて置いた局面。相手玉のマスはこの利きを見てから決める。"""
        pos = Position()
        pos.turn = color
        pos.ply = ply
        pos.put(kfile, krank, own('K'))                   # 宣言側の玉
        if check:                                          # 相手の香で王手をかける
            lr = krank - 1 if up else krank + 1
            if not (1 <= lr <= 9):
                return None
            pos.put(kfile, lr, opp('L'))
        slots = [(f, r) for r in zr for f in range(9, 0, -1) if (f, r) not in pos.sq]
        if len(slots) < a + b:
            return None
        for ch in BIG_ORDER[:b]:
            f, r = slots.pop(0)
            pos.put(f, r, own(ch))
        for _ in range(a):
            f, r = slots.pop(0)
            pos.put(f, r, own('+P'))       # と金: 1点・行き所のない駒にならない・二歩の対象外
        pos.give(color, 'P', c)
        for ch in BIG_ORDER[b:b + d]:
            pos.give(color, ch, 1)
        return pos

    skel = skeleton()
    if skel is None:
        return None, ['盤面を構成できない (n=%d, p=%d)' % (n, p)]
    last = ['相手玉を置ける合法なマスが無い']
    for okf, okr in _opponent_king_candidates(color):
        if (okf, okr) in skel.sq:
            continue
        # 宣言側の利きが乗っているマスに相手玉は置けない
        # (手番でない側が王手されている局面は非合法)
        if _is_attacked(skel, (okf, okr), up):
            continue
        pos = Position()
        pos.sq = dict(skel.sq)
        pos.hand = {c2: dict(h) for c2, h in skel.hand.items()}
        pos.turn, pos.ply = skel.turn, skel.ply
        pos.put(okf, okr, opp('K'))
        board, errs = validate(pos)
        if errs:
            last = errs
            continue
        if check and not board.is_check():
            last = ['王手を意図したが is_check() が False']
            continue
        if not check and board.is_check():
            last = ['王手を意図していないが is_check() が True']
            continue
        gn, gp, gk = ref_count(board, color)
        if (gn, gp, gk) != (n, p, king_in):
            return None, ['意図 (n=%d,p=%d,king=%s) と数え直し (n=%d,p=%d,king=%s) が不一致'
                          % (n, p, king_in, gn, gp, gk)]
        return board, []
    return None, last


# ---------------------------------------------------------------- テスト集合の定義
def specs():
    """(カテゴリ, n, p, king_in, check, ply, 期待, 説明) を列挙する。

    期待は ref_declaration() の戻り値と一致しなければならない。
    'ply' カテゴリだけは第5項の手数条件で、現行の engine 実装には無い (§注記)。
    """
    S = []
    # --- 陽性: 宣言してよい ---
    S.append(('win',  10, 31, True,  False, 1,   'win',  '31点ちょうど・10枚ちょうど (勝ちの下限)'))
    S.append(('win',  10, 32, True,  False, 1,   'win',  '32点'))
    S.append(('win',  12, 38, True,  False, 1,   'win',  '余裕のある勝ち'))
    S.append(('win',  15, 33, True,  False, 1,   'win',  '枚数過剰'))
    S.append(('draw', 10, 30, True,  False, 1,   'draw', '30点 (無勝負の上限)'))
    S.append(('draw', 10, 24, True,  False, 1,   'draw', '24点ちょうど (無勝負の下限)'))
    S.append(('draw', 10, 27, True,  False, 1,   'draw', '27点 = 27点法なら勝ち、24点法では指し直し'))
    S.append(('draw', 10, 28, True,  False, 1,   'draw', '28点 = 27点法の先手勝ち、24点法では指し直し'))
    # --- 陰性: 宣言すれば負け ---
    S.append(('lose_points', 10, 23, True,  False, 1, None, '23点 (宣言すれば負けの上限)'))
    S.append(('lose_points', 10, 22, True,  False, 1, None, '22点'))
    S.append(('lose_points', 10, 10, True,  False, 1, None, '10点'))
    S.append(('lose_points', 18, 18, True,  False, 1, None, '18枚すべてと金で18点 (枚数は最大級だが点数が足りない)'))
    S.append(('lose_count',   9, 31, True,  False, 1, None, '9枚 (あと1枚足りない・点数は足りている)'))
    S.append(('lose_count',   9, 38, True,  False, 1, None, '9枚・38点'))
    S.append(('lose_count',   5, 33, True,  False, 1, None, '5枚'))
    S.append(('lose_count',   0, 38, True,  False, 1, None, '0枚 (全部持ち駒)'))
    S.append(('lose_king',   10, 31, False, False, 1, None, '玉が敵陣外 (枚数・点数は足りている)'))
    S.append(('lose_king',   12, 38, False, False, 1, None, '玉が敵陣外・余裕のある点数'))
    S.append(('lose_check',  10, 31, True,  True,  1, None, '王手中 (他の条件はすべて満たす)'))
    S.append(('lose_check',  12, 38, True,  True,  1, None, '王手中・余裕のある点数'))
    # --- 第5項の手数条件 (現行 engine 未実装。テストは情報表示に留める) ---
    S.append(('ply', 10, 31, True, False, 501, None, '501手目 = 既に500手指了。宣言法は使えない'))
    S.append(('ply', 10, 31, True, False, 600, None, '600手目'))
    S.append(('ply', 10, 31, True, False, 500, 'win', '500手目 = 499手指了。まだ使える'))
    return S


def main():
    to_stdout = '--stdout' in sys.argv
    rows = []
    errors = []
    for color, cname in ((cshogi.BLACK, '先手'), (cshogi.WHITE, '後手')):
        for cat, n, p, king_in, check, ply, want, desc in specs():
            board, errs = build(color, n, p, king_in, check, ply)
            if errs:
                errors.append('%s %s (n=%d,p=%d): %s' % (cname, cat, n, p, '; '.join(errs)))
                continue
            got = ref_declaration(board, color)
            if got != want:
                errors.append('%s %s (n=%d,p=%d): 条文実装が %r を返した (期待 %r)'
                              % (cname, cat, n, p, got, want))
                continue
            gn, gp, gk = ref_count(board, color)
            rows.append((board.sfen(), 'b' if color == cshogi.BLACK else 'w',
                         cat, want or '-', gn, gp, int(gk), int(board.is_check()),
                         board.move_number, '%s %s' % (cname, desc)))

    if errors:
        print('生成に失敗しました:', file=sys.stderr)
        for e in errors:
            print('  - %s' % e, file=sys.stderr)
        return 1

    out = []
    out.append('# 入玉宣言法 24点法 適合性テスト集合 (tools/make_conformance.py が生成)')
    out.append('# 実戦局面ではなく、測りたい量だけを動かすために空の盤に構成した合成局面。')
    out.append('# 期待値は engine/ の実装ではなく、条文から書き起こした ref_declaration() が付けた。')
    out.append('# 列: sfen <TAB> 宣言側(b/w) <TAB> 分類 <TAB> 期待 <TAB> 敵陣枚数 <TAB> 宣言点数'
               ' <TAB> 玉が敵陣 <TAB> 王手 <TAB> 手数 <TAB> 説明')
    out.append('#   期待: win=宣言勝ち / draw=指し直し / -=宣言してはいけない(宣言すれば負け)')
    out.append('#   分類 ply は第5項の手数条件。現行 engine_decl24.declaration() は手数を見ない。')
    for r in rows:
        out.append('\t'.join(str(x) for x in r))
    text = '\n'.join(out) + '\n'

    if to_stdout:
        sys.stdout.write(text)
    else:
        with open(OUT, 'w', encoding='utf-8') as f:
            f.write(text)
        print('%s に %d 局面を書きました。' % (os.path.relpath(OUT), len(rows)))
        cats = {}
        for r in rows:
            cats[r[2]] = cats.get(r[2], 0) + 1
        for k in sorted(cats):
            print('  %-12s %d' % (k, cats[k]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
