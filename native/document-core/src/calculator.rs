//! Bounded PDF Type 4 calculator functions: no file system, no loops and no PostScript machine.
//! It follows `files/lumen_pdf_calculator.py`.
use crate::pdf::{Error, Outcome};

#[derive(Debug, Clone, PartialEq)]
enum Item {
    Whole(i64),
    Real(f64),
    Flag(bool),
    Block(Vec<Item>),
    Word(String),
}

fn bad<T>(text: &str) -> Outcome<T> {
    Err(Error::Pdf(text.into()))
}

fn parse(tokens: &[&[u8]], position: &mut usize, depth: usize) -> Outcome<Vec<Item>> {
    if depth > 32 {
        return bad("PDF-Rechenfunktion zu tief.");
    }
    let mut procedure = Vec::new();
    while *position < tokens.len() {
        let token = tokens[*position];
        *position += 1;
        match token {
            token if token.starts_with(b"%") => {}
            b"}" if depth == 0 => return bad("Unerwartetes Ende einer PDF-Rechenfunktion."),
            b"}" => return Ok(procedure),
            b"{" => procedure.push(Item::Block(parse(tokens, position, depth + 1)?)),
            token => {
                let text = String::from_utf8_lossy(token).into_owned();
                let real = token.contains(&b'.') || token.contains(&b'e') || token.contains(&b'E');
                procedure.push(match (real, text.parse::<i64>(), text.parse::<f64>()) {
                    (false, Ok(whole), _) => Item::Whole(whole),
                    (true, _, Ok(number)) => Item::Real(number),
                    _ if !text.is_ascii() => return bad("Ungültige PDF-Rechenfunktion."),
                    _ => Item::Word(text),
                });
            }
        }
    }
    if depth > 0 {
        return bad("PDF-Rechenfunktion nicht geschlossen.");
    }
    Ok(procedure)
}

struct Machine {
    stack: Vec<Item>,
    steps: usize,
}

impl Machine {
    fn pop(&mut self) -> Outcome<Item> {
        self.stack
            .pop()
            .ok_or(Error::Pdf("PDF-Rechenstack ist leer.".into()))
    }

    fn numeric(&mut self) -> Outcome<Item> {
        match self.pop()? {
            Item::Whole(value) => Ok(Item::Whole(value)),
            Item::Real(value) if value.is_finite() => Ok(Item::Real(value)),
            _ => bad("PDF-Rechenzahl erwartet."),
        }
    }

    fn whole(&mut self) -> Outcome<i64> {
        match self.pop()? {
            Item::Whole(value) => Ok(value),
            _ => bad("Ganze PDF-Rechenzahl erwartet."),
        }
    }

    fn execute(&mut self, code: &[Item], depth: usize) -> Outcome<()> {
        if depth > 32 {
            return bad("PDF-Rechenfunktion zu tief.");
        }
        let invalid = || Error::Pdf("Ungültige PDF-Rechenfunktion.".into());
        let float = |item: &Item| match item {
            Item::Whole(value) => *value as f64,
            Item::Real(value) => *value,
            _ => f64::NAN,
        };
        // A result stays whole where Python's arithmetic keeps an integer.
        let number = |value: f64, whole: bool| -> Outcome<Item> {
            if !value.is_finite() {
                return Err(invalid());
            }
            Ok(if whole && value.abs() < 9e15 {
                Item::Whole(value as i64)
            } else {
                Item::Real(value)
            })
        };
        for op in code {
            self.steps += 1;
            if self.steps > 10000 || self.stack.len() > 100 {
                return bad("PDF-Rechenbudget überschritten.");
            }
            let Item::Word(word) = op else {
                self.stack.push(op.clone());
                continue;
            };
            match word.as_str() {
                "true" | "false" => self.stack.push(Item::Flag(word == "true")),
                "abs" | "ceiling" | "floor" | "ln" | "log" | "neg" | "round" | "sin" | "cos"
                | "sqrt" | "truncate" | "cvi" | "cvr" => {
                    let a = self.numeric()?;
                    let (x, whole) = (float(&a), matches!(a, Item::Whole(_)));
                    self.stack.push(match word.as_str() {
                        "abs" => number(x.abs(), whole)?,
                        "neg" => number(-x, whole)?,
                        "ceiling" => number(x.ceil(), true)?,
                        "floor" => number(x.floor(), true)?,
                        "round" => number((x + 0.5).floor(), true)?,
                        "truncate" | "cvi" => number(x.trunc(), true)?,
                        "cvr" => Item::Real(x),
                        "ln" if x > 0.0 => Item::Real(x.ln()),
                        "log" if x > 0.0 => Item::Real(x.log10()),
                        "sqrt" if x >= 0.0 => Item::Real(x.sqrt()),
                        "sin" => Item::Real(x.to_radians().sin()),
                        "cos" => Item::Real(x.to_radians().cos()),
                        _ => return Err(invalid()),
                    });
                }
                "add" | "sub" | "mul" | "div" | "idiv" | "mod" | "exp" | "atan" => {
                    let (b, a) = (self.numeric()?, self.numeric()?);
                    let (x, y) = (float(&a), float(&b));
                    let whole = matches!((&a, &b), (Item::Whole(_), Item::Whole(_)));
                    self.stack.push(match word.as_str() {
                        "add" => number(x + y, whole)?,
                        "sub" => number(x - y, whole)?,
                        "mul" => number(x * y, whole)?,
                        "div" | "idiv" | "mod" if y == 0.0 => return Err(invalid()),
                        "div" => number(x / y, false)?,
                        "idiv" => number((x / y).trunc(), true)?,
                        "mod" => number(x - (x / y).trunc() * y, whole)?,
                        "exp" => number(x.powf(y), whole && y >= 0.0)?,
                        _ => number(x.atan2(y).to_degrees().rem_euclid(360.0), false)?,
                    });
                }
                "eq" | "ne" | "gt" | "ge" | "lt" | "le" => {
                    let (b, a) = (self.pop()?, self.pop()?);
                    let order = match (&a, &b) {
                        (Item::Flag(x), Item::Flag(y)) => x.partial_cmp(y),
                        (Item::Block(_), _)
                        | (_, Item::Block(_))
                        | (Item::Word(_), _)
                        | (_, Item::Word(_)) => {
                            if matches!(word.as_str(), "eq" | "ne") {
                                None
                            } else {
                                return Err(invalid());
                            }
                        }
                        _ => {
                            let as_number = |item: &Item| {
                                if let Item::Flag(flag) = item {
                                    f64::from(u8::from(*flag))
                                } else {
                                    float(item)
                                }
                            };
                            as_number(&a).partial_cmp(&as_number(&b))
                        }
                    };
                    use std::cmp::Ordering::{Equal, Greater, Less};
                    self.stack.push(Item::Flag(match word.as_str() {
                        "eq" => order == Some(Equal) || (order.is_none() && a == b),
                        "ne" => !(order == Some(Equal) || (order.is_none() && a == b)),
                        "gt" => order == Some(Greater),
                        "ge" => matches!(order, Some(Greater | Equal)),
                        "lt" => order == Some(Less),
                        _ => matches!(order, Some(Less | Equal)),
                    }));
                }
                "and" | "or" | "xor" => {
                    let (b, a) = (self.pop()?, self.pop()?);
                    self.stack.push(match (a, b, word.as_str()) {
                        (Item::Flag(x), Item::Flag(y), "and") => Item::Flag(x & y),
                        (Item::Flag(x), Item::Flag(y), "or") => Item::Flag(x | y),
                        (Item::Flag(x), Item::Flag(y), _) => Item::Flag(x ^ y),
                        (Item::Whole(x), Item::Whole(y), "and") => Item::Whole(x & y),
                        (Item::Whole(x), Item::Whole(y), "or") => Item::Whole(x | y),
                        (Item::Whole(x), Item::Whole(y), _) => Item::Whole(x ^ y),
                        _ => return bad("Ungültige PDF-Bitoperation."),
                    });
                }
                "not" => {
                    let negated = match self.pop()? {
                        Item::Flag(flag) => Item::Flag(!flag),
                        Item::Whole(value) => Item::Whole(!value),
                        _ => return bad("Ungültige PDF-Negation."),
                    };
                    self.stack.push(negated);
                }
                "bitshift" => {
                    let shift = self.whole()?;
                    let a = self.whole()? & 0xffff_ffff;
                    self.stack.push(Item::Whole(if shift.abs() >= 32 {
                        0
                    } else if shift >= 0 {
                        (a << shift) & 0xffff_ffff
                    } else {
                        a >> -shift
                    }));
                }
                "if" | "ifelse" => {
                    let alternate = if word == "ifelse" {
                        self.pop()?
                    } else {
                        Item::Block(Vec::new())
                    };
                    let (procedure, condition) = (self.pop()?, self.pop()?);
                    let (Item::Flag(condition), Item::Block(procedure), Item::Block(alternate)) =
                        (condition, procedure, alternate)
                    else {
                        return bad("Ungültige PDF-Rechenbedingung.");
                    };
                    self.execute(if condition { &procedure } else { &alternate }, depth + 1)?;
                }
                "dup" => {
                    let value = self.pop()?;
                    self.stack.extend([value.clone(), value]);
                }
                "exch" => {
                    let (b, a) = (self.pop()?, self.pop()?);
                    self.stack.extend([b, a]);
                }
                "pop" => {
                    self.pop()?;
                }
                "copy" | "index" => {
                    let n = self.whole()?;
                    let index = word == "index";
                    if n < 0 || n as usize + usize::from(index) > self.stack.len() {
                        return bad("Ungültiger PDF-Stackindex.");
                    }
                    let n = n as usize;
                    if index {
                        self.stack
                            .push(self.stack[self.stack.len() - n - 1].clone());
                    } else {
                        let top = self.stack[self.stack.len() - n..].to_vec();
                        self.stack.extend(top);
                    }
                }
                "roll" => {
                    let (count, n) = (self.whole()?, self.whole()?);
                    if n < 0 || n as usize > self.stack.len() {
                        return bad("Ungültige PDF-Stackrotation.");
                    }
                    if n > 0 {
                        let start = self.stack.len() - n as usize;
                        self.stack[start..].rotate_right(count.rem_euclid(n) as usize);
                    }
                }
                other => {
                    return Err(Error::Pdf(format!(
                        "Unbekannter PDF-Rechenoperator: {other}"
                    )));
                }
            }
        }
        Ok(())
    }
}

/// Runs a calculator function on its inputs and returns what is left on the stack.
pub fn calculate(data: &[u8], inputs: &[f64]) -> Outcome<Vec<f64>> {
    if data.len() > 1_000_000 {
        return bad("PDF-Rechenfunktion zu groß.");
    }
    let mut tokens: Vec<&[u8]> = Vec::new();
    let blank = |byte: u8| matches!(byte, 0 | b'\t' | b'\n' | 0x0c | b'\r' | b' ');
    let mut at = 0;
    while at < data.len() {
        let start = at;
        match data[at] {
            byte if blank(byte) => {
                at += 1;
                continue;
            }
            b'%' => {
                at = data[at..]
                    .iter()
                    .position(|b| *b == b'\r' || *b == b'\n')
                    .map_or(data.len(), |end| at + end)
            }
            b'{' | b'}' => at += 1,
            _ => {
                at = data[at..]
                    .iter()
                    .position(|b| blank(*b) || *b == b'{' || *b == b'}')
                    .map_or(data.len(), |end| at + end)
            }
        }
        tokens.push(&data[start..at]);
    }
    let code = parse(&tokens, &mut 0, 0)?;
    let [Item::Block(body)] = code.as_slice() else {
        return bad("PDF-Rechenfunktion benötigt einen Block.");
    };
    let mut machine = Machine {
        stack: inputs.iter().map(|value| Item::Real(*value)).collect(),
        steps: 0,
    };
    machine.execute(body, 0)?;
    machine
        .stack
        .iter()
        .map(|item| match item {
            Item::Whole(value) => Ok(*value as f64),
            Item::Real(value) if value.is_finite() => Ok(*value),
            _ => bad("Ungültige PDF-Rechenausgabe."),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn calculator_functions_compute_and_stay_bounded() {
        assert_eq!(calculate(b"{ 2 mul 1 add }", &[0.25]).unwrap(), vec![1.5]);
        assert_eq!(
            calculate(b"{ dup 0.5 gt { pop 1 } { 2 mul } ifelse }", &[0.25]).unwrap(),
            vec![0.5]
        );
        assert_eq!(
            calculate(b"{ dup 0.5 gt { pop 1 } { 2 mul } ifelse }", &[0.75]).unwrap(),
            vec![1.0]
        );
        assert_eq!(
            calculate(b"{ 1 exch sub % invert\n 3 1 roll }", &[0.1, 0.2, 0.3]).unwrap(),
            vec![0.7, 0.1, 0.2]
        );
        assert_eq!(
            calculate(b"{ 7 2 idiv 7 2 mod 1 index }", &[]).unwrap(),
            vec![3.0, 1.0, 3.0]
        );
        assert_eq!(
            calculate(b"{ 90 sin 5 3 bitshift 6 3 and }", &[]).unwrap(),
            vec![1.0, 40.0, 2.0]
        );
        assert!(calculate(b"{ 1 0 div }", &[]).is_err());
        assert!(calculate(b"{ pop pop }", &[1.0]).is_err());
        assert!(calculate(b"{ run }", &[]).is_err());
        assert!(calculate(b"{ 1 ", &[]).is_err());
        assert!(calculate(b"1 2 add", &[]).is_err());
    }
}
