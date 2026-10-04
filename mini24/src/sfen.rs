//! SFEN と USI 指し手の入出力。shunsai は棋譜入出力を範囲外としているので最小限をここに置く。

use shunsai::Position;
use shunsai::shogi_core::{Color, Move, PartialPosition, Piece, PieceKind, Square, ToUsi};

pub const STARTPOS: &str = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1";

fn kind_of(c: char) -> Option<PieceKind> {
    Some(match c.to_ascii_uppercase() {
        'P' => PieceKind::Pawn,
        'L' => PieceKind::Lance,
        'N' => PieceKind::Knight,
        'S' => PieceKind::Silver,
        'G' => PieceKind::Gold,
        'B' => PieceKind::Bishop,
        'R' => PieceKind::Rook,
        'K' => PieceKind::King,
        _ => return None,
    })
}

fn color_of(c: char) -> Color {
    if c.is_ascii_uppercase() {
        Color::Black
    } else {
        Color::White
    }
}

/// "board turn hand ply" 形式の SFEN を読む (先頭の "sfen " は付けない)。
pub fn parse_sfen(sfen: &str) -> Result<Position, String> {
    let f: Vec<&str> = sfen.split_whitespace().collect();
    if f.len() < 3 {
        return Err(format!("SFEN のフィールドが足りない: {sfen}"));
    }
    let mut p = PartialPosition::empty();

    let rows: Vec<&str> = f[0].split('/').collect();
    if rows.len() != 9 {
        return Err(format!("段の数が9でない: {}", f[0]));
    }
    for (r, row) in rows.iter().enumerate() {
        let rank = r as u8 + 1;
        let mut file: i32 = 9;
        let mut promote = false;
        for c in row.chars() {
            if let Some(d) = c.to_digit(10) {
                file -= d as i32;
            } else if c == '+' {
                promote = true;
            } else {
                let kind = kind_of(c).ok_or_else(|| format!("不明な駒: {c}"))?;
                let mut piece = Piece::new(kind, color_of(c));
                if promote {
                    piece = piece.promote().ok_or_else(|| format!("成れない駒: +{c}"))?;
                    promote = false;
                }
                let sq = Square::new(file as u8, rank).ok_or("筋が範囲外")?;
                p.piece_set(sq, Some(piece));
                file -= 1;
            }
        }
        if file != 0 {
            return Err(format!("{rank}段目の筋の数が9でない: {row}"));
        }
    }

    p.side_to_move_set(match f[1] {
        "b" => Color::Black,
        "w" => Color::White,
        t => return Err(format!("手番が不明: {t}")),
    });

    if f[2] != "-" {
        let mut count: u32 = 0;
        for c in f[2].chars() {
            if let Some(d) = c.to_digit(10) {
                count = count * 10 + d;
                continue;
            }
            let kind = kind_of(c).ok_or_else(|| format!("不明な持ち駒: {c}"))?;
            let hand = p.hand_of_a_player_mut(color_of(c));
            for _ in 0..count.max(1) {
                *hand = hand.added(kind).ok_or("持ち駒が多すぎる")?;
            }
            count = 0;
        }
    }

    let ply: u16 = f
        .get(3)
        .map_or(Ok(1), |s| s.parse())
        .map_err(|_| "手数が数でない")?;
    if !p.ply_set(ply) {
        return Err(format!("手数が範囲外: {ply}"));
    }
    Ok(Position::new(p))
}

pub fn move_to_usi(mv: Move) -> String {
    mv.to_usi_owned()
}

/// USI 表記の指し手を、合法手の中から探して返す (合法でなければ None)。
pub fn parse_usi_move(pos: &Position, s: &str) -> Option<Move> {
    pos.legal_moves()
        .into_iter()
        .find(|m| m.to_usi_owned() == s)
}

/// "position" コマンドの引数 ("startpos moves ..." / "sfen ... moves ...") から局面と経路を作る。
/// 経路 (各局面の Zobrist キー) は千日手の判定に使う。
pub fn parse_position_cmd(args: &str) -> Result<(Position, Vec<u64>), String> {
    let (base, moves) = match args.find(" moves") {
        Some(i) => (
            &args[..i],
            args[i + 6..].split_whitespace().collect::<Vec<_>>(),
        ),
        None => (args, vec![]),
    };
    let base = base.trim();
    let mut pos = if base == "startpos" {
        parse_sfen(STARTPOS)?
    } else if let Some(s) = base.strip_prefix("sfen ") {
        parse_sfen(s)?
    } else {
        return Err(format!("position の形式が不明: {args}"));
    };
    let mut history = vec![pos.key()];
    for m in moves {
        let mv = parse_usi_move(&pos, m).ok_or_else(|| format!("非合法手: {m}"))?;
        let _ = pos.do_move(mv);
        history.push(pos.key());
    }
    Ok((pos, history))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn startpos_has_30_moves() {
        assert_eq!(parse_sfen(STARTPOS).unwrap().legal_moves().len(), 30);
    }

    #[test]
    fn ply_and_hand() {
        let p = parse_sfen("RRBB+P+P+P+P+P/+P8/4K4/9/9/9/8k/9/9 b 5P 500").unwrap();
        assert_eq!(p.ply(), 500);
        assert_eq!(p.hand(Color::Black).count(PieceKind::Pawn), Some(5));
        assert_eq!(
            p.piece_at(Square::new(9, 1).unwrap()),
            Some(Piece::new(PieceKind::Rook, Color::Black))
        );
        assert_eq!(
            p.piece_at(Square::new(1, 1).unwrap()),
            Some(Piece::new(PieceKind::Pawn, Color::Black).promote().unwrap())
        );
    }

    #[test]
    fn position_cmd_applies_moves() {
        let (p, h) = parse_position_cmd("startpos moves 7g7f 3c3d").unwrap();
        assert_eq!(h.len(), 3);
        assert_eq!(p.side_to_move(), Color::Black);
    }
}
