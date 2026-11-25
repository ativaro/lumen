//! JSON text as Python's `json.dumps` writes it, for digests and stamps that Python code wrote
//! first and that must stay byte-identical.
use serde_json::{Value, json};

/// `json.dumps(value)`: `", "` and `": "` between items, floats as Python prints them. Objects
/// keep the order of the `Value`.
pub fn python_json(value: &Value) -> String {
    python_encode(value, false)
}

/// `json.dumps(value, separators=(",", ":"))`.
pub fn python_compact(value: &Value) -> String {
    python_encode(value, true)
}

fn python_encode(value: &Value, compact: bool) -> String {
    let comma = if compact { "," } else { ", " };
    let colon = if compact { ":" } else { ": " };
    match value {
        Value::Object(fields) => format!(
            "{{{}}}",
            fields
                .iter()
                .map(|(k, v)| format!("{}{colon}{}", json!(k), python_encode(v, compact)))
                .collect::<Vec<_>>()
                .join(comma)
        ),
        Value::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(|v| python_encode(v, compact))
                .collect::<Vec<_>>()
                .join(comma)
        ),
        Value::Number(n) if n.is_f64() => {
            let text = format!("{:?}", n.as_f64().expect("finite JSON number"));
            if let Some((mantissa, exponent)) = text.split_once('e') {
                format!(
                    "{mantissa}e{:+03}",
                    exponent.parse::<i32>().expect("formatted exponent")
                )
            } else {
                text
            }
        }
        _ => value.to_string(),
    }
}

/// Python's default `ensure_ascii=True`: every character beyond `~` as `\uXXXX` UTF-16 units.
pub fn python_ascii(text: &str) -> String {
    let mut ascii = String::new();
    for c in text.chars() {
        if c <= '~' {
            ascii.push(c);
        } else {
            for unit in c.encode_utf16(&mut [0; 2]).iter() {
                ascii.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    ascii
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_python_json_dumps() {
        // python3 -c 'import json; print(json.dumps(["a", {"b": [1, 2.5, 1e-07, None, True]}, "ü😀"]))'
        let value = json!(["a", {"b": [1, 2.5, 1e-7, null, true]}, "ü😀"]);
        assert_eq!(
            python_ascii(&python_json(&value)),
            r#"["a", {"b": [1, 2.5, 1e-07, null, true]}, "\u00fc\ud83d\ude00"]"#
        );
        assert_eq!(python_compact(&json!({"a": [1, "x"]})), r#"{"a":[1,"x"]}"#);
    }
}
