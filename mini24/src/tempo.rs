//! 宣言までの残り手数 T。このエンジンの「評価」はこれだけで、探索の中で直接使う。
//!
//! 宣言条件は「敵陣10枚」と「目標点数」。埋める手段は2つしかない。
//!   - 持ち駒を打つ    : 1手で枚数+1。点数は不変 (持ち駒の時点で計上済み)
//!   - 取り残しを運ぶ  : その駒の最短手数で 枚数+1・点数+駒点
//!
//! よって「どの取り残しを運ぶか」の小さなナップサック問題になる。
//!
//! 見積もりは駒のない盤での最短手数を使う。相手の妨害・合駒・二歩などの制約は見ないので、
//! 駒取りが無い限り実際の手数の下界になる。証明数探索の初期値として使う。
//! 駒取りで所有点数や持ち駒が増えると T は縮むので、厳密な下界ではない。

use std::sync::LazyLock;

use shunsai::Position;
use shunsai::shogi_core::{Color, PieceKind, Square};

use crate::rules::{DeclPoints, NEED_N, ZoneStats, in_zone, piece_points, zone_bb, zone_stats};

/// 到達不能 (所有点数が足りない等)
pub const UNREACHABLE: u16 = u16::MAX;

/// 先手から見た駒の動き (筋の差, 段の差)。段の差が負 = 前進。slide = 盤端まで走れるか。
fn moves_of(kind: PieceKind) -> (&'static [(i8, i8)], bool) {
    const FWD: &[(i8, i8)] = &[(0, -1)];
    const KNIGHT: &[(i8, i8)] = &[(-1, -2), (1, -2)];
    const SILVER: &[(i8, i8)] = &[(0, -1), (-1, -1), (1, -1), (-1, 1), (1, 1)];
    const GOLD: &[(i8, i8)] = &[(0, -1), (-1, -1), (1, -1), (-1, 0), (1, 0), (0, 1)];
    const DIAG: &[(i8, i8)] = &[(-1, -1), (1, -1), (-1, 1), (1, 1)];
    const ORTH: &[(i8, i8)] = &[(0, -1), (0, 1), (-1, 0), (1, 0)];
    const ALL: &[(i8, i8)] = &[
        (0, -1),
        (0, 1),
        (-1, 0),
        (1, 0),
        (-1, -1),
        (1, -1),
        (-1, 1),
        (1, 1),
    ];
    match kind {
        PieceKind::Pawn => (FWD, false),
        PieceKind::Lance => (FWD, true),
        PieceKind::Knight => (KNIGHT, false),
        PieceKind::Silver => (SILVER, false),
        PieceKind::Gold
        | PieceKind::ProPawn
        | PieceKind::ProLance
        | PieceKind::ProKnight
        | PieceKind::ProSilver => (GOLD, false),
        PieceKind::Bishop => (DIAG, true),
        PieceKind::Rook => (ORTH, true),
        // 馬・竜は「走る方向」と「1マスの方向」の両方を持つ。駒のない盤では
        // 1マスの動きは走りに含まれない方向だけ意味があるので ALL の1マスで足す
        PieceKind::King | PieceKind::ProBishop | PieceKind::ProRook => (ALL, false),
    }
}

/// 駒のない盤で sq から1手で行けるマス。
fn reach(color: Color, kind: PieceKind, sq: Square) -> Vec<Square> {
    let mut out = Vec::new();
    let sign: i8 = if color == Color::Black { 1 } else { -1 };
    let mut add = |dirs: &[(i8, i8)], slide: bool| {
        for &(df, dr) in dirs {
            let (mut f, mut r) = (sq.file() as i8, sq.rank() as i8);
            loop {
                f += df;
                r += dr * sign;
                match Square::new(f as u8, r as u8) {
                    Some(t) if (1..=9).contains(&f) && (1..=9).contains(&r) => out.push(t),
                    _ => break,
                }
                if !slide {
                    break;
                }
            }
        }
    };
    let (dirs, slide) = moves_of(kind);
    add(dirs, slide);
    match kind {
        PieceKind::ProBishop => add(moves_of(PieceKind::Bishop).0, true),
        PieceKind::ProRook => add(moves_of(PieceKind::Rook).0, true),
        _ => {}
    }
    out
}

/// STEPS[color][kind][sq] = 駒のない盤で敵陣三段目に入るまでの最短手数。敵陣内は0。
static STEPS: LazyLock<Box<[[[u8; 81]; 15]; 2]>> = LazyLock::new(|| {
    let mut t = Box::new([[[u8::MAX; 81]; 15]; 2]);
    for color in Color::all() {
        for kind in PieceKind::all() {
            let table = &mut t[color.array_index()][kind as usize];
            for sq in Square::all() {
                if in_zone(sq, color) {
                    table[sq.array_index()] = 0;
                }
            }
            // 収束するまで緩和する (81マス x 高々8回)
            loop {
                let mut changed = false;
                for sq in Square::all() {
                    let i = sq.array_index();
                    let best = reach(color, kind, sq)
                        .iter()
                        .map(|d| table[d.array_index()])
                        .filter(|&d| d != u8::MAX)
                        .map(|d| d + 1)
                        .fold(table[i], u8::min);
                    if best < table[i] {
                        table[i] = best;
                        changed = true;
                    }
                }
                if !changed {
                    break;
                }
            }
        }
    }
    t
});

#[inline]
pub fn steps(color: Color, kind: PieceKind, sq: Square) -> u8 {
    STEPS[color.array_index()][kind as usize][sq.array_index()]
}

/// 宣言に関わる量の一式。T の計算に使う。
#[derive(Clone, Debug)]
pub struct Plan {
    pub stats: ZoneStats,
    /// 玉が敵陣に入るまでの手数
    pub king_steps: u8,
    /// 敵陣外の自駒を、最短手数ごとに数えたもの (小駒 / 大駒)。手数は高々8
    small_by_steps: [u8; 16],
    big_by_steps: [u8; 16],
}

pub fn plan(pos: &Position, color: Color) -> Plan {
    let stats = zone_stats(pos, color);
    let king_steps = pos
        .king_square(color)
        .map_or(0, |k| steps(color, PieceKind::King, k));
    let mut small_by_steps = [0; 16];
    let mut big_by_steps = [0; 16];
    // 敵陣外の自駒だけを見る
    let mut bb = pos.player_bb(color) & !pos.piece_kind_bb(PieceKind::King) & !zone_bb(color);
    while let Some(sq) = bb.pop() {
        let (kind, _) = pos.piece_at(sq).unwrap().to_parts();
        let s = steps(color, kind, sq);
        if piece_points(kind) == 5 {
            big_by_steps[s as usize] += 1;
        } else {
            small_by_steps[s as usize] += 1;
        }
    }
    Plan {
        stats,
        king_steps,
        small_by_steps,
        big_by_steps,
    }
}

/// 手数の少ない順に並べた累積和 out[k] = 手数の少ない k 枚を運ぶ手数の合計。戻り値は枚数。
fn prefix(by_steps: &[u8; 16], out: &mut [u16; 39]) -> usize {
    let mut k = 0;
    out[0] = 0;
    for (st, &c) in by_steps.iter().enumerate() {
        for _ in 0..c {
            out[k + 1] = out[k] + st as u16;
            k += 1;
        }
    }
    k
}

/// 目標点数 target に、枚数10と合わせて到達するまでの最小手数。
///
/// 駒点は5点 (大駒) と1点 (小駒) の2種類しかなく、同じ点数の駒なら手数の少ない駒から
/// 運ぶのが常に最善。よって「大駒を b 枚・小駒を s 枚運ぶ」の全組み合わせを試せば厳密解になる
/// (一般のナップサックの動的計画法と同じ答え。tests::matches_reference_dp で照合している)。
#[allow(clippy::needless_range_loop)] // b, s は「運ぶ枚数」であって添字の走査ではない
pub fn tempo(p: &Plan, target: DeclPoints) -> u16 {
    if p.stats.owned.0 < target.0 {
        return UNREACHABLE; // 駒を取らない限り不可能
    }
    let need_p = target.0.saturating_sub(p.stats.decl.0) as usize;
    let need_n = NEED_N.saturating_sub(p.stats.n) as usize;
    let hand = p.stats.hand_cnt as usize;

    let mut ps = [0u16; 39];
    let mut pb = [0u16; 39];
    let n_small = prefix(&p.small_by_steps, &mut ps);
    let n_big = prefix(&p.big_by_steps, &mut pb);

    let mut best = u16::MAX;
    for b in 0..=n_big {
        let s_min = need_p.saturating_sub(5 * b);
        for s in s_min..=n_small {
            let carried = b + s;
            // 枚数の不足分は持ち駒を打って埋める (1枚1手、持ち駒の枚数が上限)
            let drops = need_n.saturating_sub(carried);
            if drops <= hand {
                best = best.min(pb[b] + ps[s] + drops as u16);
            }
            if carried >= need_n {
                break; // これ以上運んでも手数が増えるだけ
            }
        }
    }
    if best == u16::MAX {
        UNREACHABLE
    } else {
        best + p.king_steps as u16
    }
}

/// 一般のナップサックの動的計画法による参照実装 (テスト用)。
#[cfg(test)]
fn tempo_reference(p: &Plan, target: DeclPoints) -> u16 {
    if p.stats.owned.0 < target.0 {
        return UNREACHABLE;
    }
    let need_p = target.0.saturating_sub(p.stats.decl.0) as usize;
    let need_n = NEED_N.saturating_sub(p.stats.n) as usize;
    const INF: u16 = u16::MAX / 2;
    let mut dp = [[INF; NEED_N as usize + 1]; 32];
    dp[0][0] = 0;
    let mut stranded = vec![];
    for st in 0..16 {
        stranded.extend(std::iter::repeat_n(
            (1usize, st as u16),
            p.small_by_steps[st] as usize,
        ));
        stranded.extend(std::iter::repeat_n(
            (5usize, st as u16),
            p.big_by_steps[st] as usize,
        ));
    }
    for (pts, st) in stranded {
        for pt in (0..=need_p).rev() {
            for k in (0..=need_n).rev() {
                let cur = dp[pt][k];
                if cur == INF {
                    continue;
                }
                let np = (pt + pts).min(need_p);
                let nk = (k + 1).min(need_n);
                dp[np][nk] = dp[np][nk].min(cur + st);
            }
        }
    }
    let mut best = INF;
    for k in 0..=need_n {
        let drops = need_n - k;
        if drops <= p.stats.hand_cnt as usize && dp[need_p][k] != INF {
            best = best.min(dp[need_p][k] + drops as u16);
        }
    }
    if best == INF {
        UNREACHABLE
    } else {
        best + p.king_steps as u16
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sfen::parse_sfen;

    #[test]
    fn steps_table() {
        let sq = |f, r| Square::new(f, r).unwrap();
        assert_eq!(steps(Color::Black, PieceKind::Pawn, sq(5, 3)), 0);
        assert_eq!(steps(Color::Black, PieceKind::Pawn, sq(8, 6)), 3);
        assert_eq!(steps(Color::Black, PieceKind::Rook, sq(1, 9)), 1);
        assert_eq!(steps(Color::Black, PieceKind::Knight, sq(5, 9)), 3);
        assert_eq!(steps(Color::White, PieceKind::Pawn, sq(5, 1)), 6);
        assert_eq!(steps(Color::White, PieceKind::Gold, sq(5, 6)), 1);
    }

    #[test]
    fn tempo_zero_when_declarable() {
        let p = parse_sfen("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 5P 1").unwrap();
        assert_eq!(tempo(&plan(&p, Color::Black), DeclPoints(31)), 0);
    }

    #[test]
    fn tempo_counts_drops_and_carries() {
        // 9枚・31点・持ち駒の歩6枚 -> 1枚打てば宣言できる
        let p = parse_sfen("RRBB+P+P+P+P+P/9/4K4/9/9/9/8k/9/9 b 6P 1").unwrap();
        assert_eq!(tempo(&plan(&p, Color::Black), DeclPoints(31)), 1);
        // 10枚・30点、持ち駒なし、6段目の歩 (3手) で31点
        let p = parse_sfen("RRBB+P+P+P+P+P/+P8/4K4/9/9/P8/8k/9/9 b 4P 1").unwrap();
        assert_eq!(tempo(&plan(&p, Color::Black), DeclPoints(31)), 3);
        // 所有点数が足りなければ到達不能
        let p = parse_sfen("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 4P 1").unwrap();
        assert_eq!(tempo(&plan(&p, Color::Black), DeclPoints(31)), UNREACHABLE);
    }

    /// 実戦の相入玉1000局面 x 先後 x 目標2種で、参照実装の動的計画法と一致すること
    #[test]
    fn matches_reference_dp() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../positions/aiiru_bench.tsv");
        let text = std::fs::read_to_string(path).unwrap();
        let mut n = 0;
        for ln in text
            .lines()
            .filter(|l| !l.starts_with('#') && !l.trim().is_empty())
        {
            let pos = parse_sfen(ln.split('\t').next().unwrap()).unwrap();
            for c in Color::all() {
                let pl = plan(&pos, c);
                for t in [24, 27, 28, 31] {
                    assert_eq!(
                        tempo(&pl, DeclPoints(t)),
                        tempo_reference(&pl, DeclPoints(t)),
                        "{ln} {c:?} {t}"
                    );
                    n += 1;
                }
            }
        }
        assert!(n >= 8000, "{n}");
    }

    #[test]
    fn king_outside_adds_steps() {
        let p = parse_sfen("RRBB+P+P+P+P+P/+P8/9/9/4K4/9/8k/9/9 b 5P 1").unwrap();
        assert_eq!(tempo(&plan(&p, Color::Black), DeclPoints(31)), 2);
    }
}
