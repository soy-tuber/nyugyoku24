//! 入玉宣言法 (24点法/27点法) 専用のミニエンジン。
//!
//! 構成 (評価と探索を分けない):
//!   rules  宣言判定と点数。唯一「厳密でなければならない」部分
//!   tempo  宣言までの残り手数 T (= このエンジンの評価)
//!   dfpn   宣言勝ちの証明探索。T を証明数の初期値に使う
//!   think  1手の決め方 (証明 -> 安全確認 -> 競走)
//!   sfen   SFEN / USI 指し手の入出力

pub mod dfpn;
pub mod rules;
pub mod sfen;
pub mod tempo;
pub mod think;
