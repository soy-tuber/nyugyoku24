//! 1手の決め方。評価と探索を分けず、3つの問いに順に答える。
//!
//!   1. 自分は宣言勝ちを強制できるか            -> df-pn で証明できればその手
//!   2. この手を指すと相手に宣言勝ちを強制されるか -> 候補手ごとに相手側の df-pn (小予算)
//!   3. 残った安全な手の中で、競走で最も得な手
//!
//! 3 の「競走」は残り手数 T の比較と所有点数。所有点数は駒取りでしか動かず、
//! 24点法では所有31点を持った側の相手は宣言すらできないので、まず所有点数、次に T。
//! 相手の駒取りの応手だけは1手読んで最悪値を取る。

use std::time::{Duration, Instant};

use shunsai::Position;
use shunsai::shogi_core::{Color, Move};

use crate::dfpn::{Proof, Prover};
use crate::rules::{DeclResult, Rule, declaration, thresholds};
use crate::tempo::{UNREACHABLE, plan, tempo};

#[derive(Clone, Debug)]
pub struct Config {
    pub rule: Rule,
    pub max_moves: u16,
    /// 問い1の予算 (展開数)
    pub proof_nodes: u64,
    /// 問い2の予算 (候補手1つあたりの展開数)
    pub safety_nodes: u64,
    /// 1手に使ってよい時間。None なら展開数だけで止める
    pub time: Option<Duration>,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            rule: Rule::Law24,
            max_moves: 512,
            proof_nodes: 20_000,
            safety_nodes: 200,
            time: None,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Decision {
    DeclareWin,
    Move(Move),
    Resign,
}

#[derive(Clone, Debug, Default)]
pub struct Info {
    pub proven: bool,
    pub score: i32,
    pub expansions: u64,
    pub unsafe_moves: usize,
}

const RACE: i32 = 100; // 1手 = 100
const OWN: i32 = 60; //  1点 = 60
const T_CAP: u16 = 40;

/// 相手の手番の局面を、us から見て点数化する。
fn race_score(pos: &Position, us: Color, cfg: &Config) -> i32 {
    let them = us.flip();
    let played = pos.ply().saturating_sub(1);
    let rem = (cfg.max_moves.saturating_sub(played) / 2).min(T_CAP);
    let t = |c: Color| {
        let (win, _) = thresholds(cfg.rule, c);
        let v = tempo(&plan(pos, c), win);
        if v == UNREACHABLE || v > rem {
            T_CAP
        } else {
            v
        }
    };
    let own = |c: Color| {
        let (win, _) = thresholds(cfg.rule, c);
        let p = plan(pos, c);
        p.stats.owned.0.min(win.0) as i32
    };
    RACE * (t(them) as i32 - t(us) as i32) + OWN * (own(us) - own(them))
}

/// 相手の駒取りの応手を1手だけ読んだ最悪値。
fn score_after_captures(pos: &mut Position, us: Color, cfg: &Config) -> i32 {
    let mut worst = race_score(pos, us, cfg);
    for mv in pos.legal_moves() {
        let is_capture = matches!(mv, Move::Normal { to, .. } if pos.piece_at(to).is_some());
        if !is_capture {
            continue;
        }
        let u = pos.do_move(mv);
        worst = worst.min(race_score(pos, us, cfg));
        pos.undo_move(mv, u);
    }
    worst
}

pub fn think(pos: &mut Position, history: &[u64], cfg: &Config) -> (Decision, Info) {
    let mut info = Info::default();
    if declaration(pos, cfg.rule) == DeclResult::Win {
        info.proven = true;
        return (Decision::DeclareWin, info);
    }

    // 持ち時間: 問い1に6割、問い2に残りを使う。問い3は軽い
    let start = Instant::now();
    let proof_deadline = cfg.time.map(|t| start + t.mul_f64(0.6));
    let safety_deadline = cfg.time.map(|t| start + t.mul_f64(0.95));

    // 1. 自分の宣言勝ちの証明
    let mut prover = Prover::new(cfg.rule, cfg.max_moves);
    prover.deadline = proof_deadline;
    let proof = prover.prove(pos, history, cfg.proof_nodes);
    info.expansions += prover.expansions;
    match proof {
        Proof::Declare => {
            info.proven = true;
            return (Decision::DeclareWin, info);
        }
        Proof::Move(m) => {
            info.proven = true;
            return (Decision::Move(m), info);
        }
        Proof::Unknown => {}
    }

    // 2 + 3. 相手に宣言勝ちを強制されない手の中で、競走の点数が最大の手
    let us = pos.side_to_move();
    let moves = pos.legal_moves();
    if moves.is_empty() {
        return (Decision::Resign, info);
    }
    let mut hist = history.to_vec();
    prover.deadline = safety_deadline;
    let mut best: Option<(bool, i32, Move)> = None;
    for mv in moves {
        let u = pos.do_move(mv);
        hist.push(pos.key());
        // 時間切れ後は安全確認を省く (予算0で即 Unknown = 安全とみなす)
        let budget = if safety_deadline.is_some_and(|d| Instant::now() >= d) {
            0
        } else {
            cfg.safety_nodes
        };
        let unsafe_ = budget > 0
            && matches!(
                prover.prove(pos, &hist, budget),
                Proof::Declare | Proof::Move(_)
            );
        info.expansions += prover.expansions;
        let score = score_after_captures(pos, us, cfg);
        hist.pop();
        pos.undo_move(mv, u);
        if unsafe_ {
            info.unsafe_moves += 1;
        }
        let key = (!unsafe_, score);
        if best.is_none_or(|(s, v, _)| key > (s, v)) {
            best = Some((!unsafe_, score, mv));
        }
    }
    let (_, score, mv) = best.unwrap();
    info.score = score;
    (Decision::Move(mv), info)
}
