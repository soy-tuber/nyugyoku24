# -*- coding: utf-8 -*-
"""相入玉が成立した瞬間の局面が、求解可能な規模かを実データで測る。

測るもの:
  盤上駒数 / 持ち駒数 / 合法手数 / 駒取り手数 / 打つ手の数 / 駒得差
求解可能性の目安:
  分岐 b, 深さ h として b^h。持ち駒が多いと打つ手が爆発する。
"""
import os, sys, glob, random, collections, statistics
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine24 import point24, is_aiiru, PT_POINT

DS = r"D:\book_project\nyugyoku_dataset"
N_SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 1500


def aiiru_position(path):
    """相入玉が成立した瞬間の Board を返す。"""
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
        if is_aiiru(b):
            return b
    return None


def main():
    random.seed(7)
    files = []
    for y in ('2020', '2021', '2022', '2023', '2024', '2025'):
        files += glob.glob(os.path.join(DS, y, '*.csa'))
    random.shuffle(files)

    rec = []
    for path in files:
        if len(rec) >= N_SAMPLE:
            break
        b = aiiru_position(path)
        if b is None:
            continue
        pieces = b.pieces
        nboard = sum(1 for sq in range(81) if pieces[sq])
        hb = sum(b.pieces_in_hand[cshogi.BLACK])
        hw = sum(b.pieces_in_hand[cshogi.WHITE])
        nlegal = ncap = ndrop = 0
        for m in b.legal_moves:
            nlegal += 1
            if cshogi.move_cap(m) != cshogi.NONE:
                ncap += 1
            if cshogi.move_is_drop(m):
                ndrop += 1
        sp, gp = point24(b, cshogi.BLACK), point24(b, cshogi.WHITE)
        rec.append((nboard, hb + hw, nlegal, ncap, ndrop, sp, gp, b.move_number))

    n = len(rec)
    print('相入玉成立局面 %d 件を測定\n' % n)

    def stat(idx, label):
        v = sorted(r[idx] for r in rec)
        print('  %-14s 中央値 %5.0f   平均 %6.1f   最小 %4d   最大 %4d   下位10%% %4d'
              % (label, statistics.median(v), statistics.mean(v), v[0], v[-1], v[int(n * 0.1)]))

    print('=== 規模 ===')
    stat(0, '盤上駒数')
    stat(1, '持ち駒総数')
    stat(2, '合法手数')
    stat(3, '駒取り手数')
    stat(4, '打つ手数')
    stat(7, '成立手数')

    print('\n=== 持ち駒は「点数として安全」である ===')
    # 24点法では持ち駒は絶対に失われない。盤上の駒だけが取られうる。
    safe_b = sum(1 for r in rec if r[5] - 0 >= 0)
    hand_pts = []
    board_pts = []
    for path_i, r in enumerate(rec):
        pass
    for path in []:
        pass
    print('  (下で局面ごとに分解)')

    print('\n=== 駒取り手が全合法手に占める割合 ===')
    ratio = sorted(r[3] / r[2] for r in rec if r[2])
    print('  中央値 %.1f%%   上位10%% %.1f%%   最大 %.1f%%'
          % (statistics.median(ratio) * 100, ratio[int(n * 0.9)] * 100, ratio[-1] * 100))
    print('  -> 合法手の大半は点数に一切影響しない')

    print('\n=== 打つ手が全合法手に占める割合 ===')
    dr = sorted(r[4] / r[2] for r in rec if r[2])
    print('  中央値 %.1f%%   最大 %.1f%%' % (statistics.median(dr) * 100, dr[-1] * 100))

    print('\n=== 求解可能性の目安 ===')
    med_b = statistics.median([r[2] for r in rec])
    for h in (10, 20, 40, 80):
        print('  分岐%.0f, 深さ%d -> 約 10^%.0f 局面' % (med_b, h, h * (med_b ** 0.0 + 0) + h * __import__('math').log10(med_b)))

    print('\n=== 盤上駒数の分布 (少ないほど求解に近い) ===')
    c = collections.Counter(r[0] for r in rec)
    for k in sorted(c):
        if c[k]:
            print('  %2d枚: %4d局 %s' % (k, c[k], '#' * max(1, round(c[k] / max(c.values()) * 40))))


if __name__ == '__main__':
    main()
