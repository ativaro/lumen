//! The encoder against vectors the same model gave in ONNX Runtime when the runtime was chosen
//! (284 notes, long notes and questions; the first fragment of each).
//!
//! Runs with `LUMEN_TEST_MEMORY_HOME` pointing at an installation (`model/` and `runtime/`).
//! `LUMEN_TEST_REFERENCE` may name a file with all 284 vectors (little-endian f32) instead of the
//! four kept in `fixtures/`; then only the direction is checked, so another runtime's vectors can
//! be compared too.
use lumen_sentence_encoder::{DIMENSIONS, Encoder, STEP, WINDOW};
use std::path::Path;

const KEPT: [usize; 4] = [0, 200, 240, 283];

fn texts() -> Vec<String> {
    let topics = [
        "Rechnung",
        "Urlaub",
        "Projektplan",
        "Arzttermin",
        "Steuer",
        "Garten",
        "Fahrrad",
        "Rezept",
    ];
    let mut texts: Vec<String> = (0..200)
        .map(|n| {
            format!(
                "{} {n}\nNotiz {n} zum Thema {}: Größe, Maß und Termin wurden am Tag {} festgehalten.",
                topics[n % 8],
                topics[n % 8],
                n % 28 + 1
            )
        })
        .collect();
    texts.extend((0..40).map(|n| {
        (0..30)
            .map(|k| {
                format!(
                    "Absatz {k} der langen Notiz {n} über {}: Die Lieferung verzögert sich, der Vertrag wird am {}. geprüft und die Übergabe neu geplant.",
                    topics[(n + k) % 8],
                    (n * k) % 28 + 1
                )
            })
            .collect::<Vec<_>>()
            .join(" ")
    }));
    texts.extend((0..40).map(|n| format!("Was steht zu {} {n}?", topics[n % 8])));
    texts.extend(
        [
            "Wann war der Arzttermin?",
            "When is the invoice due?",
            "Où est le plan du projet ?",
            "自転車の修理はいつですか",
        ]
        .map(String::from),
    );
    texts
}

#[test]
fn vectors_match_the_reference() {
    let Some(home) = std::env::var_os("LUMEN_TEST_MEMORY_HOME") else {
        return;
    };
    let home = Path::new(&home);
    let mut encoder = Encoder::load(
        &home.join("model/model.onnx"),
        &home.join("model/tokenizer.json"),
        &home.join("runtime/libonnxruntime.so.1.30.0"),
        1,
    )
    .unwrap();
    let texts = texts();
    let (reference, picks, exact) = match std::env::var_os("LUMEN_TEST_REFERENCE") {
        Some(path) => (
            std::fs::read(path).unwrap(),
            (0..texts.len()).collect(),
            false,
        ),
        None => (
            include_bytes!("fixtures/reference-vectors.bin").to_vec(),
            KEPT.to_vec(),
            true,
        ),
    };
    assert_eq!(reference.len(), picks.len() * DIMENSIONS * 4);
    let (mut worst, mut lowest, mut sum, mut identical) = (0f32, 1f64, 0f64, 0);
    for (&pick, expected) in picks.iter().zip(reference.chunks(DIMENSIONS * 4)) {
        let (tokens, _) = encoder.windows(&texts[pick], 0).unwrap();
        let vector = encoder.vector(&tokens, 0).unwrap();
        let expected: Vec<f32> = expected
            .as_chunks::<4>()
            .0
            .iter()
            .map(|bytes| f32::from_le_bytes(*bytes))
            .collect();
        let cosine: f64 = vector
            .iter()
            .zip(&expected)
            .map(|(a, b)| f64::from(*a) * f64::from(*b))
            .sum();
        for (a, b) in vector.iter().zip(&expected) {
            worst = worst.max((a - b).abs());
        }
        identical += usize::from(vector == expected);
        lowest = lowest.min(cosine);
        sum += cosine;
    }
    eprintln!(
        "sentence encoder: {} vectors, {identical} bit-identical, max deviation {worst:e}, cosine min {lowest:.6} mean {:.6}",
        picks.len(),
        sum / picks.len() as f64
    );
    assert!(lowest > 0.99, "cosine {lowest}");
    assert!(!exact || worst <= 1e-6, "max deviation {worst:e}");
}

/// A long note is cut into overlapping fragments, and each fragment has its vector and excerpt.
#[test]
fn long_notes_are_cut_into_fragments() {
    let Some(home) = std::env::var_os("LUMEN_TEST_MEMORY_HOME") else {
        return;
    };
    let home = Path::new(&home);
    let mut encoder = Encoder::load(
        &home.join("model/model.onnx"),
        &home.join("model/tokenizer.json"),
        &home.join("runtime/libonnxruntime.so.1.30.0"),
        1,
    )
    .unwrap();
    let text = &texts()[200];
    let (tokens, offsets) = encoder.windows(text, 0).unwrap();
    assert!(tokens.len() > 2 * WINDOW);
    assert_eq!(offsets[..3], [0, STEP, 2 * STEP]);
    assert!(offsets.last().unwrap() + WINDOW >= tokens.len());
    let vectors = encoder.encode(text, 0).unwrap();
    assert_eq!(vectors.len(), offsets.len());
    assert_eq!(vectors[1], encoder.vector(&tokens, STEP).unwrap());
    assert_eq!(encoder.encode(text, 2).unwrap()[..], vectors[2..]);
    for vector in &vectors {
        let norm: f32 = vector.iter().map(|v| v * v).sum();
        assert!(vector.len() == DIMENSIONS && (norm - 1.0).abs() < 1e-5);
    }
    assert!(text.starts_with(&encoder.excerpt(text, 0).unwrap()));
    assert!(text.contains(encoder.excerpt(text, 1).unwrap().as_str()));
    assert_eq!(encoder.excerpt(text, offsets.len() + 1).unwrap(), "");
    // An empty text still has one fragment: the sentence marks alone.
    assert_eq!(encoder.encode("", 0).unwrap().len(), 1);
    assert!(encoder.windows(&"x".repeat(21001), 0).is_err());
}

/// Runs where the variable is not set (the reference runs above need it set).
#[test]
fn nothing_is_loaded_without_the_telemetry_switch() {
    if std::env::var_os("ORT_DISABLE_TELEMETRY").is_some_and(|value| value == "1") {
        return;
    }
    let missing = Path::new("/nonexistent");
    let error = Encoder::load(missing, missing, missing, 1).err().unwrap();
    assert_eq!(error, "ORT_DISABLE_TELEMETRY=1 is required");
}
