# -*- coding: utf-8 -*-
"""floodgate の実戦棋譜から、相入玉が成立した瞬間の局面を抽出して同梱用に書き出す。

リポジトリを自己完結させるために使う。棋譜そのもの (2.7GB) は同梱せず、
局面の SFEN だけを配布する。

出典: floodgate (wdoor) 公開アーカイブ https://wdoor.c.u-tokyo.ac.jp/shogi/
      棋譜は東京大学 wdoor が公開している対局記録。
      本ファイルはそこから機械的に抽出した局面のみを含む。

使い方: python tools/make_positions.py <棋譜ディレクトリ> <出力ディレクトリ> [件数]
"""
import os, sys, glob, random
import cshogi

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'engine'))
from engine_decl24 import zone_stats


def aiiru(path):
    """相入玉が成立した瞬間の (sfen, 手数) を返す。"""
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().split('\n')
    moves = [ln for ln in lines if len(ln) >= 7 and ln[0] in '+-' and ln[1].isdigit()]
    b = cshogi.Board()
    for i, ln in enumerate(moves):
        try:
            m = b.move_from_csa(ln[1:])
            if m == 0 or not b.is_legal(m):
                return None
            b.push(m)
        except Exception:
            return None
        if b.king_square(cshogi.BLACK) % 9 <= 2 and b.king_square(cshogi.WHITE) % 9 >= 6:
            return b.sfen(), i + 1
    return None


HEADER = ('# 相入玉が成立した瞬間の局面 (両玉が敵陣三段目以内に入った最初の局面)\n'
          '# 出典: floodgate (wdoor) https://wdoor.c.u-tokyo.ac.jp/shogi/ の公開棋譜から機械抽出\n'
          '# 列: sfen <TAB> 成立手数 <TAB> 先手の敵陣枚数 <TAB> 先手の宣言点数'
          ' <TAB> 後手の敵陣枚数 <TAB> 後手の宣言点数 <TAB> 出典棋譜名\n')


def dump(rows, path):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(HEADER)
        for r in rows:
            f.write('\t'.join(str(x) for x in r) + '\n')
    print('%s  %d局面' % (path, len(rows)))


def collect(files, want, seed):
    rnd = random.Random(seed)
    fs = list(files)
    rnd.shuffle(fs)
    out = []
    for p in fs:
        if len(out) >= want:
            break
        r = aiiru(p)
        if not r:
            continue
        sfen, ply = r
        b = cshogi.Board(sfen)
        sn, sp, _ = zone_stats(b, cshogi.BLACK)
        gn, gp, _ = zone_stats(b, cshogi.WHITE)
        out.append((sfen, ply, sn, sp, gn, gp, os.path.basename(p)))
    return out


def main():
    src = sys.argv[1]
    dst = sys.argv[2]
    want = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    os.makedirs(dst, exist_ok=True)
    files = []
    for y in ('2020', '2021', '2022', '2023', '2024'):
        files += glob.glob(os.path.join(src, y, '*.csa'))
    print('棋譜 %d 局から抽出' % len(files))

    # ベンチマーク本体
    dump(collect(files, want, 20260825), os.path.join(dst, 'aiiru_bench.tsv'))
    # 重み調整に使った40局面と、検証用の未使用40局面 (再現性のため固定)
    dump(collect(files, 40, 20260825), os.path.join(dst, 'tune40.tsv'))
    dump(collect(files, 40, 99999999), os.path.join(dst, 'holdout40.tsv'))


if __name__ == '__main__':
    main()
