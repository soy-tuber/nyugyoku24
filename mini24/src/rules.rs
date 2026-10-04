//! 入玉宣言法の規則。このクレートで唯一「厳密でなければならない」部分。
//!
//! 条件を1つでも欠いた宣言は宣言側の負けになる (日本将棋連盟 入玉宣言法 第5項)。
//! 判定が甘い方向に壊れると反則負けを量産し、厳しい方向に壊れると勝ちを逃す。
//!
//! 点数は2種類あり、型で分けている。混同するとコンパイルが通らない。
//!   DeclPoints  宣言点数 = 持ち駒 + 敵陣三段目以内の自駒 (入玉宣言法が数える量)
//!   OwnedPoints 所有点数 = 持ち駒 + 盤上どこでも自駒     (先後合計54の保存量)
//! 持将棋 (合意) の点数はこのエンジンでは扱わないので型自体を作らない。

use std::sync::LazyLock;

use shunsai::shogi_core::{Color, Hand, PieceKind, Square};
use shunsai::{Bitboard, Position};

/// 宣言点数。持ち駒 + 敵陣三段目以内の自駒 (大駒5・小駒1・玉0)。
#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct DeclPoints(pub u8);

/// 所有点数。持ち駒 + 盤上どこでも自駒。先後の合計は常に54。
#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct OwnedPoints(pub u8);

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Rule {
    /// 日本将棋連盟 24点法: 31点以上で勝ち、24〜30点で無勝負。手数500未満でのみ使える
    Law24,
    /// CSA 27点法: 先手28点・後手27点以上で勝ち (floodgate はこちら)
    Law27,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum DeclResult {
    Win,
    /// 24点法の無勝負 (指し直し)。27点法では発生しない
    Draw,
    /// 宣言すると負けになる
    NotAllowed,
}

/// 宣言に必要な点数。(勝ち, 無勝負)。27点法に無勝負は無い。
pub fn thresholds(rule: Rule, color: Color) -> (DeclPoints, Option<DeclPoints>) {
    match rule {
        Rule::Law24 => (DeclPoints(31), Some(DeclPoints(24))),
        Rule::Law27 => match color {
            Color::Black => (DeclPoints(28), None),
            Color::White => (DeclPoints(27), None),
        },
    }
}

pub const NEED_N: u8 = 10;
/// 24点法 第5項: 手数が500手に満たない場合に使用できる
pub const LAW24_MAX_PLAYED: u16 = 500;

/// 駒点。成っても変わらない。
pub const fn piece_points(kind: PieceKind) -> u8 {
    match kind {
        PieceKind::Bishop | PieceKind::Rook | PieceKind::ProBishop | PieceKind::ProRook => 5,
        PieceKind::King => 0,
        _ => 1,
    }
}

/// 敵陣三段目以内か (color から見て)。
#[inline]
pub fn in_zone(sq: Square, color: Color) -> bool {
    sq.relative_rank(color) <= 3
}

/// 敵陣三段目以内のマス (先手, 後手)
static ZONE_BB: LazyLock<[Bitboard; 2]> = LazyLock::new(|| {
    let mut z = [Bitboard::EMPTY; 2];
    for c in Color::all() {
        for sq in Square::all().filter(|&sq| in_zone(sq, c)) {
            z[c.array_index()] |= Bitboard::single(sq);
        }
    }
    z
});

#[inline]
pub fn zone_bb(color: Color) -> Bitboard {
    ZONE_BB[color.array_index()]
}

/// 盤上の大駒 (5点の駒) 。先後とも
#[inline]
pub fn big_bb(pos: &Position) -> Bitboard {
    pos.piece_kind_bb(PieceKind::Bishop)
        | pos.piece_kind_bb(PieceKind::Rook)
        | pos.piece_kind_bb(PieceKind::ProBishop)
        | pos.piece_kind_bb(PieceKind::ProRook)
}

pub fn hand_points(hand: Hand) -> (u8, u8) {
    let mut pts = 0;
    let mut cnt = 0;
    for kind in Hand::all_hand_pieces() {
        let c = hand.count(kind).unwrap_or(0);
        pts += c * piece_points(kind);
        cnt += c;
    }
    (pts, cnt)
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct ZoneStats {
    /// 敵陣三段目以内の自駒の枚数 (玉を除く)。持ち駒は数えない
    pub n: u8,
    pub decl: DeclPoints,
    pub owned: OwnedPoints,
    pub king_in: bool,
    /// 持ち駒の枚数。打てば1手で n を1増やせる
    pub hand_cnt: u8,
}

pub fn zone_stats(pos: &Position, color: Color) -> ZoneStats {
    // 駒1枚ずつではなくビットボードで数える (探索の葉で子局面ごとに呼ばれるため)
    let pieces = pos.player_bb(color) & !pos.piece_kind_bb(PieceKind::King);
    let big = big_bb(pos);
    let zone = pieces & zone_bb(color);
    let n = zone.count() as u8;
    // 大駒5点 = 1 + 4、小駒1点
    let zone_pts = n + 4 * (zone & big).count() as u8;
    let board_pts = pieces.count() as u8 + 4 * (pieces & big).count() as u8;
    let (hp, hc) = hand_points(pos.hand(color));
    ZoneStats {
        n,
        decl: DeclPoints(zone_pts + hp),
        owned: OwnedPoints(board_pts + hp),
        king_in: pos.king_square(color).is_some_and(|k| in_zone(k, color)),
        hand_cnt: hc,
    }
}

/// 手番側が今この瞬間に宣言したらどうなるか。
///
/// 条件 (24点法の条文順):
///   (1) 宣言側の手番である            … 手番側についてしか問わないので常に満たす
///   (2) 玉が敵陣三段目以内
///   (3) 玉を除く10枚以上が敵陣三段目以内
///   (4) 王手がかかっていない
///   (5) 点数 (宣言点数)
///   第5項: 手数が500手に満たない (24点法のみ。SFEN の手数欄 m なら指了 m-1 手)
/// 持ち時間は USI 側の責任なのでここでは見ない。
pub fn declaration(pos: &Position, rule: Rule) -> DeclResult {
    let us = pos.side_to_move();
    if rule == Rule::Law24 && pos.ply().saturating_sub(1) >= LAW24_MAX_PLAYED {
        return DeclResult::NotAllowed;
    }
    let s = zone_stats(pos, us);
    if !s.king_in || s.n < NEED_N || pos.in_check() {
        return DeclResult::NotAllowed;
    }
    let (win, draw) = thresholds(rule, us);
    if s.decl >= win {
        DeclResult::Win
    } else if draw.is_some_and(|d| s.decl >= d) {
        DeclResult::Draw
    } else {
        DeclResult::NotAllowed
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sfen::parse_sfen;

    fn decl(sfen: &str) -> DeclResult {
        declaration(&parse_sfen(sfen).unwrap(), Rule::Law24)
    }

    #[test]
    fn points_and_invariants() {
        let p = parse_sfen(crate::sfen::STARTPOS).unwrap();
        let b = zone_stats(&p, Color::Black);
        let w = zone_stats(&p, Color::White);
        assert_eq!(b.owned.0 + w.owned.0, 54);
        assert_eq!(b.owned, OwnedPoints(27));
        assert!(b.decl.0 <= b.owned.0);
        assert_eq!(piece_points(PieceKind::ProRook), 5);
        assert_eq!(piece_points(PieceKind::ProPawn), 1);
    }

    #[test]
    fn each_condition_is_necessary() {
        // 31点・10枚ちょうど
        assert_eq!(
            decl("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 5P 1"),
            DeclResult::Win
        );
        // 30点 -> 無勝負、23点以下 -> 不可
        assert_eq!(
            decl("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 4P 1"),
            DeclResult::Draw
        );
        assert_eq!(
            decl("RR+P+P+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b - 1"),
            DeclResult::NotAllowed
        );
        // 9枚
        assert_eq!(
            decl("RRBB+P+P+P+P+P/9/4K4/9/9/9/8k/9/9 b 6P 1"),
            DeclResult::NotAllowed
        );
        // 玉が敵陣外
        assert_eq!(
            decl("RRBB+P+P+P+P+P/+P8/9/4K4/9/9/8k/9/9 b 5P 1"),
            DeclResult::NotAllowed
        );
        // 手番でない側は判定されない: 後手番なら後手について問う
        assert_eq!(
            decl("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 w 5P 1"),
            DeclResult::NotAllowed
        );
        // 第5項: 500手目は可、501手目は不可
        assert_eq!(
            decl("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 5P 500"),
            DeclResult::Win
        );
        assert_eq!(
            decl("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 5P 501"),
            DeclResult::NotAllowed
        );
    }

    #[test]
    fn law27_thresholds() {
        let p = parse_sfen("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 2P 1").unwrap(); // 28点
        assert_eq!(declaration(&p, Rule::Law27), DeclResult::Win);
        assert_eq!(declaration(&p, Rule::Law24), DeclResult::Draw);
        let p = parse_sfen("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b P 1").unwrap(); // 27点
        assert_eq!(declaration(&p, Rule::Law27), DeclResult::NotAllowed);
    }

    /// positions/conformance.tsv (条文から書き起こした期待値) と全件一致すること。
    /// Python 版が未実装の第5項 (ply 分類) も含めて一致を要求する。
    #[test]
    fn conformance_suite() {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../positions/conformance.tsv");
        let text = std::fs::read_to_string(path).expect("positions/conformance.tsv が読めない");
        let mut rows = 0;
        for ln in text
            .lines()
            .filter(|l| !l.starts_with('#') && !l.trim().is_empty())
        {
            let c: Vec<&str> = ln.split('\t').collect();
            let pos = parse_sfen(c[0]).unwrap();
            let color = if c[1] == "b" {
                Color::Black
            } else {
                Color::White
            };
            assert_eq!(pos.side_to_move(), color, "{}", c[9]);
            let want = match c[3] {
                "win" => DeclResult::Win,
                "draw" => DeclResult::Draw,
                _ => DeclResult::NotAllowed,
            };
            assert_eq!(declaration(&pos, Rule::Law24), want, "{} ({})", c[9], c[2]);
            let s = zone_stats(&pos, color);
            assert_eq!(
                (s.n, s.decl.0, s.king_in, pos.in_check(), pos.ply()),
                (
                    c[4].parse().unwrap(),
                    c[5].parse().unwrap(),
                    c[6] == "1",
                    c[7] == "1",
                    c[8].parse().unwrap()
                ),
                "{}",
                c[9]
            );
            rows += 1;
        }
        assert_eq!(rows, 46);
    }
}
