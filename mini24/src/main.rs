//! USI エンジン本体と、検証用のサブコマンド。
//!
//!   nyugyoku-mini                      USI エンジンとして起動
//!   nyugyoku-mini stats  < sfen.txt    1行1局面の SFEN について宣言関連の量を出力 (Python 版との照合用)
//!   nyugyoku-mini prove  <limit> < sfen.txt   各局面で手番側の宣言勝ちを証明できるか
//!   nyugyoku-mini think  < sfen.txt    各局面での指し手

use std::io::{self, BufRead, Write};
use std::time::{Duration, Instant};

use nyugyoku_mini::dfpn::{Proof, Prover};
use nyugyoku_mini::rules::thresholds;
use nyugyoku_mini::rules::{DeclResult, Rule, declaration, zone_stats};
use nyugyoku_mini::sfen::{move_to_usi, parse_position_cmd, parse_sfen};
use nyugyoku_mini::tempo::{plan, tempo};
use nyugyoku_mini::think::{Config, Decision, think};
use shunsai::shogi_core::Color;

fn decl_str(d: DeclResult) -> &'static str {
    match d {
        DeclResult::Win => "win",
        DeclResult::Draw => "draw",
        DeclResult::NotAllowed => "-",
    }
}

fn sfen_lines() -> impl Iterator<Item = String> {
    io::stdin()
        .lock()
        .lines()
        .map_while(Result::ok)
        .filter(|l| !l.trim().is_empty() && !l.starts_with('#'))
        .map(|l| l.split('\t').next().unwrap().trim().to_string())
        .collect::<Vec<_>>()
        .into_iter()
}

fn cmd_stats() {
    // 列: sfen  [先手 n decl owned king_in T31 T24] [後手 同]  手番側の宣言(24点法) 同(27点法)
    for s in sfen_lines() {
        let pos = match parse_sfen(&s) {
            Ok(p) => p,
            Err(e) => {
                println!("{s}\tERROR {e}");
                continue;
            }
        };
        let mut out = vec![s.clone()];
        for c in [Color::Black, Color::White] {
            let z = zone_stats(&pos, c);
            let pl = plan(&pos, c);
            let t31 = tempo(&pl, thresholds(Rule::Law24, c).0);
            let t24 = tempo(&pl, thresholds(Rule::Law24, c).1.unwrap());
            out.push(format!(
                "{}\t{}\t{}\t{}\t{}\t{}",
                z.n,
                z.decl.0,
                z.owned.0,
                z.king_in as u8,
                t31 as i32 - if t31 == u16::MAX { 65536 } else { 0 },
                t24 as i32 - if t24 == u16::MAX { 65536 } else { 0 }
            ));
        }
        out.push(decl_str(declaration(&pos, Rule::Law24)).into());
        out.push(decl_str(declaration(&pos, Rule::Law27)).into());
        println!("{}", out.join("\t"));
    }
}

fn cmd_prove(limit: u64) {
    let mut prover = Prover::new(Rule::Law24, 512);
    let (mut proven, mut total) = (0, 0);
    let t0 = Instant::now();
    for s in sfen_lines() {
        let mut pos = parse_sfen(&s).expect("SFEN");
        let h = vec![pos.key()];
        let t = Instant::now();
        let r = prover.prove(&mut pos, &h, limit);
        let r_s = match r {
            Proof::Declare => {
                proven += 1;
                "declare".to_string()
            }
            Proof::Move(m) => {
                proven += 1;
                format!("move {}", move_to_usi(m))
            }
            Proof::Unknown => "unknown".to_string(),
        };
        total += 1;
        println!(
            "{s}\t{r_s}\t{} expansions\t{:.2}s",
            prover.expansions,
            t.elapsed().as_secs_f64()
        );
    }
    eprintln!(
        "証明 {proven}/{total}  ({:.1}s)",
        t0.elapsed().as_secs_f64()
    );
}

fn cmd_think(cfg: &Config) {
    for s in sfen_lines() {
        let mut pos = parse_sfen(&s).expect("SFEN");
        let h = vec![pos.key()];
        let t = Instant::now();
        let (d, info) = think(&mut pos, &h, cfg);
        let d_s = match d {
            Decision::DeclareWin => "win".into(),
            Decision::Move(m) => move_to_usi(m),
            Decision::Resign => "resign".into(),
        };
        println!(
            "{s}\t{d_s}\tproven={} score={} unsafe={} exp={}\t{:.2}s",
            info.proven,
            info.score,
            info.unsafe_moves,
            info.expansions,
            t.elapsed().as_secs_f64()
        );
    }
}

/// "go btime X wtime Y byoyomi Z binc A winc B" から1手の使用時間を決める。
/// 残り時間の 1/30 + 加算 or 秒読みの 8割。最低 100ms、通信の余裕に 200ms 引く。
fn time_for_move(args: &str, black: bool) -> Duration {
    let f: Vec<&str> = args.split_whitespace().collect();
    let get = |k: &str| {
        f.iter()
            .position(|&x| x == k)
            .and_then(|i| f.get(i + 1))
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(0)
    };
    let (rem, inc) = if black {
        (get("btime"), get("binc"))
    } else {
        (get("wtime"), get("winc"))
    };
    let byoyomi = get("byoyomi");
    if let Some(i) = f.iter().position(|&x| x == "movetime") {
        return Duration::from_millis(f.get(i + 1).and_then(|v| v.parse().ok()).unwrap_or(1000));
    }
    let ms = rem / 30 + (inc + byoyomi) * 8 / 10;
    let ms = ms.min(rem + byoyomi).saturating_sub(200).max(100);
    Duration::from_millis(ms)
}

fn usi_loop() {
    let mut cfg = Config::default();
    let mut state = parse_position_cmd("startpos").unwrap();
    let stdout = io::stdout();
    for line in io::stdin().lock().lines().map_while(Result::ok) {
        let line = line.trim();
        let mut out = stdout.lock();
        let (cmd, rest) = line.split_once(' ').unwrap_or((line, ""));
        match cmd {
            "usi" => {
                writeln!(out, "id name nyugyoku-mini {}", env!("CARGO_PKG_VERSION")).ok();
                writeln!(out, "id author nyugyoku24 contributors").ok();
                writeln!(out, "option name EnteringKingRule type combo default CSARule24 var CSARule24 var CSARule27").ok();
                writeln!(
                    out,
                    "option name MaxMovesToDraw type spin default 512 min 0 max 100000"
                )
                .ok();
                writeln!(
                    out,
                    "option name ProofNodes type spin default 20000 min 1 max 100000000"
                )
                .ok();
                writeln!(
                    out,
                    "option name SafetyNodes type spin default 200 min 0 max 1000000"
                )
                .ok();
                writeln!(out, "usiok").ok();
            }
            "isready" => {
                writeln!(out, "readyok").ok();
            }
            "setoption" => {
                // setoption name <id> value <x>
                let f: Vec<&str> = rest.split_whitespace().collect();
                if let (Some(n), Some(v)) = (f.get(1), f.get(3)) {
                    match *n {
                        "EnteringKingRule" => {
                            cfg.rule = if v.contains("27") {
                                Rule::Law27
                            } else {
                                Rule::Law24
                            }
                        }
                        "MaxMovesToDraw" => cfg.max_moves = v.parse().unwrap_or(512),
                        "ProofNodes" => cfg.proof_nodes = v.parse().unwrap_or(cfg.proof_nodes),
                        "SafetyNodes" => cfg.safety_nodes = v.parse().unwrap_or(cfg.safety_nodes),
                        _ => {}
                    }
                }
            }
            "usinewgame" => {}
            "position" => match parse_position_cmd(rest) {
                Ok(s) => state = s,
                Err(e) => {
                    writeln!(out, "info string {e}").ok();
                }
            },
            "go" => {
                let (pos, hist) = &mut state;
                let t = Instant::now();
                let mut c = cfg.clone();
                c.time = Some(time_for_move(rest, pos.side_to_move() == Color::Black));
                c.proof_nodes = u64::MAX; // 時間で止める
                let (d, info) = think(pos, hist, &c);
                writeln!(
                    out,
                    "info string proven={} score={} unsafe={} expansions={} time={}ms",
                    info.proven,
                    info.score,
                    info.unsafe_moves,
                    info.expansions,
                    t.elapsed().as_millis()
                )
                .ok();
                let bm = match d {
                    Decision::DeclareWin => "win".to_string(),
                    Decision::Move(m) => move_to_usi(m),
                    Decision::Resign => "resign".to_string(),
                };
                writeln!(out, "bestmove {bm}").ok();
            }
            "quit" => break,
            _ => {}
        }
        out.flush().ok();
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("stats") => cmd_stats(),
        Some("prove") => cmd_prove(args.get(2).and_then(|s| s.parse().ok()).unwrap_or(20_000)),
        Some("think") => cmd_think(&Config::default()),
        _ => usi_loop(),
    }
}
