# -*- coding: utf-8 -*-
"""入玉宣言法 24点法 適合性テスト。

test_rules.py が手書きの代表局面で判定の骨格を守るのに対し、
こちらは positions/conformance.tsv (tools/make_conformance.py が生成) を使って
**陰性側**を体系的に測る。

    第5項「条件1〜4のうち一つでも満たしていない場合、宣言側が負けとなる」

適合性は2つある。
    (1) 宣言できるときに宣言する
    (2) 宣言してはいけないときに宣言しない
このテストの主眼は (2)。27点法で作られたエンジンは 24〜30点で宣言して
指し直しにしてしまう、という予測可能な形で (2) に失敗する。
これは弱さではなく目的関数の不一致の署名である。

2段構えで測る:
    [判定] declaration() が条文どおりの答えを返すか
    [挙動] エンジンが実際に宣言してしまわないか
後者は将来 USI 経由で外部エンジンにも同じ集合を当てられるようにするための形。
USI では宣言は `bestmove win` で表現される。

実行:  python tests/test_conformance.py
       python tests/test_conformance.py --no-engine    # 判定だけ
       python tests/test_conformance.py --real         # 実戦由来の集合も
"""
import os, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'engine'))
import cshogi
from engine_decl24 import declaration, zone_stats, DeclEngine24

SUITE = os.path.join(HERE, '..', 'positions', 'conformance.tsv')
REAL = os.path.join(HERE, '..', 'positions', 'conformance_real.tsv')

FAIL = []
INFO = []


def check(cond, msg):
    if cond:
        print('  ok   %s' % msg)
    else:
        print('  FAIL %s' % msg)
        FAIL.append(msg)


def load():
    if not os.path.exists(SUITE):
        print('%s がありません。先に tools/make_conformance.py を実行してください。'
              % os.path.relpath(SUITE), file=sys.stderr)
        sys.exit(2)
    rows = []
    with open(SUITE, encoding='utf-8') as f:
        for ln in f:
            if ln.startswith('#') or not ln.strip():
                continue
            c = ln.rstrip('\n').split('\t')
            rows.append({
                'sfen': c[0],
                'color': cshogi.BLACK if c[1] == 'b' else cshogi.WHITE,
                'cat': c[2],
                'want': None if c[3] == '-' else c[3],
                'n': int(c[4]), 'p': int(c[5]),
                'king_in': bool(int(c[6])), 'check': bool(int(c[7])),
                'ply': int(c[8]), 'desc': c[9],
            })
    return rows


# ---------------------------------------------------------------- [0] 集合そのもの
def t_suite(rows):
    print('\n[0] テスト集合 — 記録された量が盤面と一致すること')
    bad = []
    for r in rows:
        b = cshogi.Board(r['sfen'])
        n, p, king_in = zone_stats(b, r['color'])
        if (n, p, king_in, b.is_check(), b.move_number) != \
           (r['n'], r['p'], r['king_in'], r['check'], r['ply']):
            bad.append('%s: 記録 (%d枚,%d点,玉%s,王手%s,%d手) / 盤面 (%d枚,%d点,玉%s,王手%s,%d手)'
                       % (r['desc'], r['n'], r['p'], r['king_in'], r['check'], r['ply'],
                          n, p, king_in, b.is_check(), b.move_number))
    check(not bad, '%d 局面すべてで記録と盤面が一致 (不一致 %d)' % (len(rows), len(bad)))
    for m in bad[:5]:
        print('       %s' % m)
    cats = {}
    for r in rows:
        cats[r['cat']] = cats.get(r['cat'], 0) + 1
    print('       内訳: %s' % ', '.join('%s=%d' % (k, cats[k]) for k in sorted(cats)))


# ---------------------------------------------------------------- [1] 判定
def t_declaration(rows):
    print('\n[1] 判定 — declaration() が条文どおりの答えを返すこと')
    groups = {}
    for r in rows:
        groups.setdefault(r['cat'], []).append(r)

    for cat in ('win', 'draw', 'lose_points', 'lose_count', 'lose_king', 'lose_check'):
        bad = []
        for r in groups.get(cat, []):
            got = declaration(cshogi.Board(r['sfen']), r['color'])
            if got != r['want']:
                bad.append('%s -> %r (期待 %r)' % (r['desc'], got, r['want']))
        check(not bad, '%-12s %d局面 (誤判定 %d)' % (cat, len(groups.get(cat, [])), len(bad)))
        for m in bad:
            print('       %s' % m)

    # 手番でない側は宣言できない (条文の前提)
    bad = [r['desc'] for r in rows
           if declaration(cshogi.Board(r['sfen']), 1 - r['color']) is not None]
    check(not bad, '手番でない側は常に宣言できない (違反 %d)' % len(bad))

    # 第5項の手数条件。現行 declaration() は手数を見ないので、失敗ではなく情報として出す。
    print('\n[1b] 第5項の手数条件 (手数500未満でのみ宣言法を使える)')
    miss = []
    for r in groups.get('ply', []):
        got = declaration(cshogi.Board(r['sfen']), r['color'])
        mark = 'ok  ' if got == r['want'] else 'MISS'
        if got != r['want']:
            miss.append(r['desc'])
        print('  %s %s -> %r (条文 %r)' % (mark, r['desc'], got, r['want']))
    if miss:
        INFO.append('第5項の手数条件が declaration() に未実装 (%d/%d 件で条文と食い違う)。'
                    % (len(miss), len(groups.get('ply', []))))
        INFO.append('  「手数が500手に満たない場合は入玉宣言法を使用することができる」')
        INFO.append('  現行の max_plies は100〜140なので実害は出ていないが、')
        INFO.append('  証明探索の終端述語に使うなら、この不足はそのまま偽陽性になる。')
        INFO.append('  手数の解釈 (SFEN の手数フィールド m のとき指了手数は m-1) も要確認。')


# ---------------------------------------------------------------- [2] 挙動
def t_engine(rows, depth=1):
    print('\n[2] 挙動 — エンジンが宣言してはいけない局面で宣言しないこと (depth %d)' % depth)
    eng = DeclEngine24(max_depth=depth)
    t0 = time.perf_counter()

    wrong = []
    for r in rows:
        if not r['cat'].startswith('lose'):
            continue
        b = cshogi.Board(r['sfen'])
        mv, sc, nodes = eng.go(b)
        if isinstance(mv, str):                 # 'declare_win' / 'declare_draw'
            wrong.append('%s -> %s' % (r['desc'], mv))
    n_lose = sum(1 for r in rows if r['cat'].startswith('lose'))
    check(not wrong, '宣言すれば負ける %d 局面で宣言しない (違反 %d)' % (n_lose, len(wrong)))
    for m in wrong:
        print('       %s' % m)

    missed = []
    for r in rows:
        if r['cat'] != 'win':
            continue
        mv, sc, nodes = eng.go(cshogi.Board(r['sfen']))
        if mv != 'declare_win':
            missed.append('%s -> %r' % (r['desc'], mv))
    n_win = sum(1 for r in rows if r['cat'] == 'win')
    check(not missed, '宣言勝ちの %d 局面で宣言する (見逃し %d)' % (n_win, len(missed)))
    for m in missed:
        print('       %s' % m)

    # 24〜30点は「宣言すれば指し直し」。宣言するか指し続けるかは戦略の問題なので
    # 正誤ではなく分布を出す。27点法のエンジンはここで宣言しがちになるはず。
    kinds = {}
    for r in rows:
        if r['cat'] != 'draw':
            continue
        mv, sc, nodes = eng.go(cshogi.Board(r['sfen']))
        k = mv if isinstance(mv, str) else '指し継ぐ'
        kinds[k] = kinds.get(k, 0) + 1
    print('  info 24〜30点の局面での選択: %s'
          % (', '.join('%s=%d' % kv for kv in sorted(kinds.items())) or 'なし'))
    print('       (どちらも合法。27点法の目的関数を持つエンジンはここで宣言しやすい)')
    print('  info 所要 %.1f 秒' % (time.perf_counter() - t0))


def load_real():
    rows = []
    with open(REAL, encoding='utf-8') as f:
        for ln in f:
            if ln.startswith('#') or not ln.strip():
                continue
            c = ln.rstrip('\n').split('\t')
            rows.append({'sfen': c[0],
                         'color': cshogi.BLACK if c[1] == 'b' else cshogi.WHITE,
                         'cat': c[2], 'want': c[3], 'p': int(c[5]),
                         'v27': c[10], 'desc': c[11]})
    return rows


def t_real(depth=1):
    """実戦由来の集合 (positions/conformance_real.tsv) でエンジンの挙動を測る。

    こちらは全局面が陽性側 (手番側が宣言できる) なので、測るのは
      - 24点法で宣言勝ちの局面で、実際に宣言するか
      - 27点法なら勝ちだが24点法では指し直しの帯 (判別帯) で、勝ちを宣言しないか
    後者が27点法のエンジンとの分かれ目である。
    """
    if not os.path.exists(REAL):
        print('\n[3] 実戦由来の集合 — %s が無いので省略' % os.path.relpath(REAL))
        print('    生成: python tools/fetch_conformance_real.py')
        return
    rows = load_real()
    print('\n[3] 実戦由来の集合 — %d 局面 (depth %d)' % (len(rows), depth))
    eng = DeclEngine24(max_depth=depth)
    t0 = time.perf_counter()
    groups = {'win': [], '判別draw': [], '一致draw': []}
    for r in rows:
        k = 'win' if r['want'] == 'win' else r['cat']
        groups.setdefault(k, []).append(r)

    missed = []
    for r in groups.get('win', []):
        mv, sc, nd = eng.go(cshogi.Board(r['sfen']))
        if mv != 'declare_win':
            missed.append(r['desc'])
    check(not missed, '24点法で宣言勝ちの %d 局面で宣言する (見逃し %d)'
          % (len(groups.get('win', [])), len(missed)))

    for k, title in (('判別draw', '判別帯 (27点法なら勝ち・24点法は指し直し)'),
                     ('一致draw', '両ルールとも勝ちでない帯')):
        rs = groups.get(k, [])
        if not rs:
            continue
        kinds = collections.Counter()
        wrong = []
        for r in rs:
            mv, sc, nd = eng.go(cshogi.Board(r['sfen']))
            kinds[mv if isinstance(mv, str) else '指し継ぐ'] += 1
            if mv == 'declare_win':
                wrong.append(r['desc'])
        if k == '判別draw':
            check(not wrong, '%s %d局面で宣言勝ちを主張しない (違反 %d)' % (title, len(rs), len(wrong)))
            for m in wrong[:5]:
                print('       %s' % m)
        print('  info %s %d局面の選択: %s'
              % (title, len(rs), ', '.join('%s=%d' % kv for kv in sorted(kinds.items()))))
    print('  info 所要 %.1f 秒' % (time.perf_counter() - t0))


if __name__ == '__main__':
    rows = load()
    t_suite(rows)
    t_declaration(rows)
    if '--no-engine' not in sys.argv:
        t_engine(rows)
        if '--real' in sys.argv:
            t_real()
    print('\n' + '=' * 60)
    for m in INFO:
        print(m)
    if INFO:
        print('-' * 60)
    if FAIL:
        print('失敗 %d 件:' % len(FAIL))
        for m in FAIL:
            print('  - %s' % m)
        sys.exit(1)
    print('すべて通過')
