//! 宣言勝ちの証明探索 (df-pn)。評価関数は持たず、残り手数 T を証明数の初期値に使う。
//!
//! 詰将棋ソルバー (KomoringHeights など) と同じ構造で、ゴールを「詰み」から
//! 「宣言勝ち」に差し替えている。
//!   OR 節点 (攻め方 = 証明したい側の手番): どれか1手で宣言勝ちに届けばよい
//!   AND 節点 (受け方の手番): すべての応手に対して届かなければならない
//!
//! 24点法の構造的な性質: 先後の所有点数の合計は54なので、攻め方が所有31点以上なら
//! 受け方は23点以下で、無勝負 (24点) の宣言すらできない。受け方の防御は
//! 駒の取り返し・王手 (宣言を遅らせる)・詰み・手数上限・千日手に限られる。
//!
//! 終端:
//!   OR  で宣言勝ちが成立                 -> 証明
//!   AND で受け方が宣言できる              -> 反証 (24点法なら無勝負でも逃げられる)
//!   AND で受け方に合法手が無い (詰み)     -> 証明
//!   OR  で攻め方に合法手が無い (詰み)     -> 反証
//!   千日手 / 対局の手数上限               -> 反証 (引き分けは勝ちではない)
//!
//! 証明数の集約は Weak Proof-Number Search (Ueda et al. 2008) に倣い、
//! 和ではなく「最大値 + 未解決の子の数 - 1」にする。相入玉は持ち駒が多く
//! 応手が100を超えるので、単純な和だと証明数が爆発して探索が偏る。
//!
//! 健全性: 「証明」は全応手を調べた結果なので正しい (置換表の衝突と下記の千日手の扱いを除く)。
//! 「反証」は「この予算と手の制約では証明できなかった」以上の意味を持たせない。
//!
//! 既知の簡略化 (改良の余地):
//!   - 千日手は経路上の同一局面の再出現で即引き分けとし、連続王手の千日手を区別しない
//!   - 経路依存の値 (千日手) を置換表に入れてしまう (GHI 問題)

use std::collections::{HashMap, HashSet};
use std::hash::{BuildHasherDefault, Hasher};
use std::time::Instant;

use shunsai::Position;
use shunsai::shogi_core::{Color, Move};

use crate::rules::{DeclResult, Rule, declaration, thresholds};
use crate::tempo::{UNREACHABLE, plan, tempo};

pub const INF: u32 = 1 << 28;

/// Zobrist キーはもともと一様乱数なので、そのままハッシュ値に使う
#[derive(Default)]
struct KeyHasher(u64);
impl Hasher for KeyHasher {
    fn finish(&self) -> u64 {
        self.0
    }
    fn write(&mut self, _: &[u8]) {
        unreachable!("u64 のキーにしか使わない")
    }
    fn write_u64(&mut self, k: u64) {
        self.0 = k;
    }
}
type KeyBuild = BuildHasherDefault<KeyHasher>;
/// 証明数の初期値に使う T の上限
const TEMPO_CAP: u16 = 64;
/// T の1手を証明数いくつに換算するか。小さいと AND 節点の「未解決の子の数」の項に
/// 埋もれ、T を縮める手と縮めない手 (例: 宣言点数が足りないのに持ち駒を打つ) の
/// 区別がつかなくなって、攻め方の100通り近い手を横に舐め続ける。
const TEMPO_SCALE: u32 = 16;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Proof {
    /// 宣言勝ちが今すぐ成立する
    Declare,
    /// この手で宣言勝ちを強制できる
    Move(Move),
    /// 予算内では証明できなかった (反証を含む)
    Unknown,
}

#[derive(Copy, Clone, Debug)]
struct Entry {
    pn: u32,
    dn: u32,
}

pub struct Prover {
    pub rule: Rule,
    /// 対局の手数上限 (floodgate は512)。これを超えたら引き分け
    pub max_moves: u16,
    attacker: Color,
    tt: HashMap<u64, Entry, KeyBuild>,
    /// 対局開始から現在の探索節点までの局面 (千日手の判定用)
    path: HashSet<u64, KeyBuild>,
    pub expansions: u64,
    limit: u64,
    /// これを過ぎたら探索を打ち切る (持ち時間の管理)
    pub deadline: Option<Instant>,
    stopped: bool,
}

fn wsum(xs: impl Iterator<Item = u32>) -> u32 {
    let mut max = 0;
    let mut live = 0u32;
    for x in xs {
        if x >= INF {
            return INF;
        }
        if x > 0 {
            live += 1;
            max = max.max(x);
        }
    }
    if live == 0 {
        0
    } else {
        (max + live - 1).min(INF - 1)
    }
}

impl Prover {
    pub fn new(rule: Rule, max_moves: u16) -> Self {
        Prover {
            rule,
            max_moves,
            attacker: Color::Black,
            tt: HashMap::default(),
            path: HashSet::default(),
            expansions: 0,
            limit: 0,
            deadline: None,
            stopped: false,
        }
    }

    /// pos の手番側が宣言勝ちを強制できるかを、展開数 limit の予算で調べる。
    /// history は対局開始からの局面キー (現局面を含む)。千日手の判定に使う。
    pub fn prove(&mut self, pos: &mut Position, history: &[u64], limit: u64) -> Proof {
        self.attacker = pos.side_to_move();
        if declaration(pos, self.rule) == DeclResult::Win {
            return Proof::Declare;
        }
        self.tt.clear();
        self.path.clear();
        self.path
            .extend(history.iter().copied().filter(|&k| k != pos.key()));
        self.expansions = 0;
        self.limit = limit;
        self.stopped = false;

        let (pn, _) = self.mid(pos, INF - 1, INF - 1);
        if pn != 0 {
            return Proof::Unknown;
        }
        // 証明済みの子 (pn = 0) を探す。初期値の時点で証明された子も置換表に入っている
        for mv in pos.legal_moves() {
            let u = pos.do_move(mv);
            let e = self.tt.get(&pos.key()).copied();
            pos.undo_move(mv, u);
            if e.is_some_and(|e| e.pn == 0) {
                return Proof::Move(mv);
            }
        }
        Proof::Unknown
    }

    fn out_of_budget(&mut self) -> bool {
        if !self.stopped
            && (self.expansions >= self.limit
                || (self.expansions.is_multiple_of(64)
                    && self.deadline.is_some_and(|d| Instant::now() >= d)))
        {
            self.stopped = true;
        }
        self.stopped
    }

    /// 展開せずに分かる終端。千日手は呼び出し側で見る。
    fn terminal(&self, pos: &Position) -> Option<Entry> {
        const PROVEN: Entry = Entry { pn: 0, dn: INF };
        const DISPROVEN: Entry = Entry { pn: INF, dn: 0 };
        let d = declaration(pos, self.rule);
        if pos.side_to_move() == self.attacker {
            if d == DeclResult::Win {
                return Some(PROVEN);
            }
        } else if d != DeclResult::NotAllowed {
            return Some(DISPROVEN); // 受け方が宣言して終局 (24点法なら無勝負で逃げる)
        }
        if pos.ply().saturating_sub(1) >= self.max_moves {
            return Some(DISPROVEN);
        }
        None
    }

    /// 未展開の節点の初期値。攻め方の T を証明数に、受け方が逃げるまでの T を反証数にする。
    fn heuristic(&self, pos: &Position) -> Entry {
        let att = self.attacker;
        let def = att.flip();
        let (win_att, _) = thresholds(self.rule, att);
        let (win_def, draw_def) = thresholds(self.rule, def);
        let t_att = tempo(&plan(pos, att), win_att).min(TEMPO_CAP);
        let t_def = tempo(&plan(pos, def), draw_def.unwrap_or(win_def)).min(TEMPO_CAP);
        let t_att = if t_att == UNREACHABLE {
            TEMPO_CAP
        } else {
            t_att
        };
        Entry {
            pn: 1 + TEMPO_SCALE * t_att as u32,
            dn: 1 + TEMPO_SCALE * t_def as u32,
        }
    }

    fn lookup_or_init(&mut self, pos: &Position) -> Entry {
        let key = pos.key();
        if self.path.contains(&key) {
            return Entry { pn: INF, dn: 0 }; // 千日手 = 引き分け
        }
        if let Some(e) = self.tt.get(&key) {
            return *e;
        }
        let e = self.terminal(pos).unwrap_or_else(|| self.heuristic(pos));
        self.tt.insert(key, e);
        e
    }

    fn mid(&mut self, pos: &mut Position, thpn: u32, thdn: u32) -> (u32, u32) {
        let key = pos.key();
        if let Some(e) = self.terminal(pos) {
            self.tt.insert(key, e);
            return (e.pn, e.dn);
        }
        self.expansions += 1;
        let is_or = pos.side_to_move() == self.attacker;

        let moves = pos.legal_moves();
        if moves.is_empty() {
            // 詰み: 攻め方が詰まされたら反証、受け方が詰まされたら証明
            let e = if is_or {
                Entry { pn: INF, dn: 0 }
            } else {
                Entry { pn: 0, dn: INF }
            };
            self.tt.insert(key, e);
            return (e.pn, e.dn);
        }

        let fresh = self.path.insert(key);
        let mut kids: Vec<(Move, Entry)> = Vec::with_capacity(moves.len());
        for mv in moves {
            let u = pos.do_move(mv);
            let e = self.lookup_or_init(pos);
            pos.undo_move(mv, u);
            kids.push((mv, e));
        }

        let (mut pn, mut dn);
        loop {
            if is_or {
                pn = kids.iter().map(|k| k.1.pn).min().unwrap();
                dn = wsum(kids.iter().map(|k| k.1.dn));
            } else {
                pn = wsum(kids.iter().map(|k| k.1.pn));
                dn = kids.iter().map(|k| k.1.dn).min().unwrap();
            }
            if pn >= thpn || dn >= thdn || self.out_of_budget() {
                break;
            }
            // 最良の子と次点。OR は証明数、AND は反証数が小さい子を選ぶ
            let val = |e: &Entry| if is_or { e.pn } else { e.dn };
            let mut best = 0;
            let mut second = INF;
            for i in 1..kids.len() {
                let v = val(&kids[i].1);
                if v < val(&kids[best].1) {
                    second = val(&kids[best].1);
                    best = i;
                } else if v < second {
                    second = v;
                }
            }
            let c = kids[best].1;
            let (cthpn, cthdn) = if is_or {
                (
                    thpn.min(second.saturating_add(1)),
                    (thdn - dn).saturating_add(c.dn).min(INF - 1),
                )
            } else {
                (
                    (thpn - pn).saturating_add(c.pn).min(INF - 1),
                    thdn.min(second.saturating_add(1)),
                )
            };
            let mv = kids[best].0;
            let u = pos.do_move(mv);
            let (cpn, cdn) = self.mid(pos, cthpn, cthdn);
            pos.undo_move(mv, u);
            kids[best].1 = Entry { pn: cpn, dn: cdn };
        }
        if fresh {
            self.path.remove(&key);
        }
        self.tt.insert(key, Entry { pn, dn });
        (pn, dn)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sfen::parse_sfen;

    fn prove(sfen: &str, limit: u64) -> Proof {
        let mut pos = parse_sfen(sfen).unwrap();
        let h = vec![pos.key()];
        Prover::new(Rule::Law24, 512).prove(&mut pos, &h, limit)
    }

    #[test]
    fn declare_now() {
        assert_eq!(
            prove("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 5P 1", 10),
            Proof::Declare
        );
    }

    #[test]
    fn one_drop_then_declare() {
        // 9枚・31点。歩を敵陣に打てば10枚になり、後手は王手も駒取りもできない
        match prove("RRBB+P+P+P+P+P/9/4K4/9/9/9/8k/9/9 b 6P 1", 1000) {
            Proof::Move(m) => assert!(m.is_drop()),
            p => panic!("証明できなかった: {p:?}"),
        }
    }

    #[test]
    fn carry_stranded_pawn() {
        // 10枚・30点。6段目の歩を3手で敵陣に運べば31点。後手は玉だけで間に合わない。
        // TEMPO_SCALE が小さいと、点数の増えない打つ手を横に舐めて証明できなくなる (回帰テスト)
        for sfen in [
            "RRBB+P+P+P+P+P/+P8/4K4/9/9/P8/8k/9/9 b 4P 1",
            "RRBB+P+P+P+P+P/+P8/4K4/9/9/9/P7k/9/9 b 4P 1",
        ] {
            match prove(sfen, 5000) {
                Proof::Move(Move::Normal { from, .. }) => assert_eq!(from.file(), 9, "{sfen}"),
                p => panic!("{sfen}: {p:?}"),
            }
        }
    }

    #[test]
    fn unreachable_points_cannot_be_proven() {
        // 所有30点では31点に届かない
        assert_eq!(
            prove("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 4P 1", 2000),
            Proof::Unknown
        );
    }
}
