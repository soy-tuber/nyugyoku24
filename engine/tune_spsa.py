# -*- coding: utf-8 -*-
"""SPSA による評価重みの自動調整。

方式:
  適合度は自己対局。固定した相入玉局面の集合について、候補の重み w+ と w- を
  先後入れ替えて戦わせ、宣言勝ちの差を得点とする。
  SPSA (同時摂動確率近似) は全次元を1度に揺らすので、次元数によらず
  1反復あたり2回の評価で済む。適合度が雑音まみれの対局結果である本件に向く。

  探索の値はスケール不変 (アルファベータは w を正数倍しても同じ手を選ぶ) なので、
  各反復のあとで L2 ノルムを初期値に戻し、スケールの発散を防ぐ。

使い方:
  python tune_spsa.py [反復数] [局面数] [depth] [手数上限]
"""
import os, sys, glob, random, time, json, math
from multiprocessing import Pool
import cshogi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import NAMES, NF, INIT_W
from engine_learn import game

DS = r"D:\book_project\nyugyoku_dataset"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tune_log.jsonl')

DEPTH = 2
MAXPLY = 100


def aiiru_sfen(path):
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
        if b.king_square(cshogi.BLACK) % 9 <= 2 and b.king_square(cshogi.WHITE) % 9 >= 6:
            return b.sfen()
    return None


POSDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'positions')


def read_tsv(path):
    out = []
    with open(path, encoding='utf-8') as f:
        for ln in f:
            if ln.startswith('#') or not ln.strip():
                continue
            out.append(ln.split('	')[0])
    return out


def load_positions(n, seed=20260825):
    """同梱の局面ファイルから読む。無ければ棋譜ディレクトリから抽出する。

    リポジトリを自己完結させるため、既定では positions/ の TSV を使う。
    棋譜アーカイブ (2.7GB) が無くても再現できる。
    """
    named = {20260825: 'tune40.tsv', 99999999: 'holdout40.tsv'}
    cand = named.get(seed)
    if cand:
        path = os.path.join(POSDIR, cand)
        if os.path.exists(path):
            p = read_tsv(path)
            if len(p) >= n:
                return p[:n]
    bench = os.path.join(POSDIR, 'aiiru_bench.tsv')
    if os.path.exists(bench):
        p = read_tsv(bench)
        rnd = random.Random(seed)
        rnd.shuffle(p)
        if len(p) >= n:
            return p[:n]
    # 同梱ファイルが無い場合のみ、生の棋譜から抽出する
    rnd = random.Random(seed)
    files = []
    for y in ('2020', '2021', '2022', '2023', '2024'):
        files += glob.glob(os.path.join(DS, y, '*.csa'))
    rnd.shuffle(files)
    pos = []
    for p in files:
        if len(pos) >= n:
            break
        s = aiiru_sfen(p)
        if s:
            pos.append(s)
    return pos


def _one(arg):
    """1局。a を先手か後手に置いて指し、a 視点の得点を返す。"""
    sfen, wa, wb, a_is_black, depth, maxply = arg
    if a_is_black:
        r, n = game(sfen, wa, wb, maxply, depth)
        return r
    else:
        r, n = game(sfen, wb, wa, maxply, depth)
        return -r


def match(pool, positions, wa, wb, depth=DEPTH, maxply=MAXPLY):
    """先後入れ替えで総当たり。a 視点の (勝ち, 負け, 引分, 得点) を返す。"""
    jobs = []
    for s in positions:
        jobs.append((s, wa, wb, True, depth, maxply))
        jobs.append((s, wa, wb, False, depth, maxply))
    res = pool.map(_one, jobs, chunksize=1)
    win = sum(1 for r in res if r >= 1.0)
    loss = sum(1 for r in res if r <= -1.0)
    draw = len(res) - win - loss
    return win, loss, draw, sum(res)


# 符号は理論から確定しているので学習させない。
# 「取られそうな駒があるのは良いこと」のような無意味な向きに落ちるのを防ぐ。
BOUNDS = {
    'own':       (0.0, None),    # 所有点数は多いほど良い
    'own_x':     (0.0, None),
    'dec':       (0.0, None),    # 宣言点数は多いほど良い
    'zone_n':    (0.0, None),    # 敵陣内の駒数は多いほど良い
    'zone_pot':  (0.0, None),
    'zone_x':    (0.0, None),
    'king_in':   (None, None),   # 固定 (摂動 0)
    'hang_all':  (None, 0.0),    # 取られうる自駒があるのは悪い
    'hang_zone': (None, 0.0),
    'safe_drop': (0.0, None),    # 安全に打てるマスがあるのは良い
    'threat':    (0.0, None),    # 取れる相手駒があるのは良い
}


def clip(w):
    out = []
    for i, nm in enumerate(NAMES):
        lo, hi = BOUNDS[nm]
        x = w[i]
        if lo is not None and x < lo:
            x = lo
        if hi is not None and x > hi:
            x = hi
        out.append(x)
    return out


def normalize(w, target_norm):
    nrm = math.sqrt(sum(x * x for x in w))
    if nrm < 1e-9:
        return list(INIT_W)
    return [x * target_norm / nrm for x in w]


def main():
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    npos = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    depth = int(sys.argv[3]) if len(sys.argv) > 3 else DEPTH
    maxply = int(sys.argv[4]) if len(sys.argv) > 4 else MAXPLY

    positions = load_positions(npos)
    print('局面 %d / depth %d / 手数上限 %d / 反復 %d' % (len(positions), depth, maxply, iters),
          flush=True)
    print('特徴量: %s' % ', '.join(NAMES), flush=True)

    w = list(INIT_W)
    base_norm = math.sqrt(sum(x * x for x in w))
    # 摂動幅と歩幅は各重みの大きさに比例させる。
    # king_in は宣言の前提条件で実質無限大なので調整対象から外す (摂動 0)。
    KING_IX = NAMES.index('king_in')
    scale = [max(1.2, abs(x) * 0.25) for x in INIT_W]
    scale[KING_IX] = 0.0
    rnd = random.Random(1)

    best_w = list(w)
    log = open(OUT, 'a', encoding='utf-8')
    with Pool() as pool:
        # 初期値と自分自身の対戦で、引き分け率と所要時間を確認
        t0 = time.perf_counter()
        wi, lo, dr, sc = match(pool, positions, w, w, depth, maxply)
        dt = time.perf_counter() - t0
        print('自己対戦(同一重み): %d勝 %d敗 %d分 得点%+.2f  [%.0fs/マッチ]'
              % (wi, lo, dr, sc, dt), flush=True)

        for it in range(1, iters + 1):
            ck = 1.0 / (it ** 0.101)          # 摂動幅の減衰
            ak = 2.5 / ((it + 20) ** 0.602)   # 歩幅の減衰 (雑音に振られないよう抑えめ)
            delta = [rnd.choice((-1.0, 1.0)) for _ in range(NF)]
            wp = clip([w[i] + ck * scale[i] * delta[i] for i in range(NF)])
            wm = clip([w[i] - ck * scale[i] * delta[i] for i in range(NF)])
            t0 = time.perf_counter()
            _, _, _, sp = match(pool, positions, wp, wm, depth, maxply)
            dt = time.perf_counter() - t0
            # sp > 0 なら wp が強い -> delta の向きへ進む
            g = sp / max(1.0, len(positions) * 2 * 0.35)   # 密な得点なので分母を絞る
            w = clip([w[i] + ak * scale[i] * g * delta[i] for i in range(NF)])
            w = normalize(w, base_norm)
            rec = {'iter': it, 'score': sp, 'sec': round(dt, 1),
                   'w': [round(x, 3) for x in w]}
            log.write(json.dumps(rec, ensure_ascii=False) + '\n')
            log.flush()
            print('%3d  wp-wm=%+7.2f  %5.0fs  w=[%s]'
                  % (it, sp, dt, ' '.join('%6.1f' % x for x in w)), flush=True)

        # 最終的な重みを初期値と比べる
        print('\n=== 初期値との対戦 ===', flush=True)
        wi, lo, dr, sc = match(pool, positions, w, INIT_W, depth, maxply)
        print('調整後 vs 初期値: %d勝 %d敗 %d分 (得点 %+.2f / %d局)'
              % (wi, lo, dr, sc, len(positions) * 2), flush=True)
    log.close()
    print('\n最終の重み:')
    for i, n in enumerate(NAMES):
        print('  %-10s %8.2f   (初期 %8.2f)' % (n, w[i], INIT_W[i]))


if __name__ == '__main__':
    main()
