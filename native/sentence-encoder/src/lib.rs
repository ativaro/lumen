//! Lumen's sentence encoder for memory search (paraphrase-multilingual-MiniLM-L12-v2, int8 ONNX),
//! used by the desktop's `lumen-service` and by the server.
//!
//! The model runs in ONNX Runtime, loaded once per process from the library the caller names.
//! Callers verify the checksums of model, tokenizer and library before `Encoder::load`. One
//! session runs one fragment at a time with a bounded thread count. Vectors equal the retired
//! Python encoder's bit for bit.
use std::path::Path;

pub const DIMENSIONS: usize = 384;
/// Fragments of 126 tokens, each starting 102 tokens after the previous one.
pub const WINDOW: usize = 126;
pub const STEP: usize = 102;
pub const MAX_CHARS: usize = 21000;

pub struct Encoder {
    session: ort::session::Session,
    tokenizer: tokenizers::Tokenizer,
    start: i64,
    end: i64,
    inputs: Vec<String>,
}

fn failed<E: std::fmt::Display>(error: E) -> String {
    error.to_string()
}

impl Encoder {
    /// Loads the model with `threads` ONNX Runtime threads. The first call decides which runtime
    /// library the process uses; later calls reuse it.
    pub fn load(
        model: &Path,
        tokenizer: &Path,
        runtime: &Path,
        threads: usize,
    ) -> Result<Encoder, String> {
        // ONNX Runtime 1.30 writes a device identifier and an upload queue below HOME as soon as
        // its environment exists, whatever `with_telemetry` says. Only this variable stops it, and
        // it has to be in the process environment before the library is loaded.
        if std::env::var_os("ORT_DISABLE_TELEMETRY").is_none_or(|value| value != "1") {
            return Err("ORT_DISABLE_TELEMETRY=1 is required".into());
        }
        static ENVIRONMENT: std::sync::Mutex<Option<ort::environment::Environment>> =
            std::sync::Mutex::new(None);
        let environment = {
            let mut slot = ENVIRONMENT.lock().map_err(failed)?;
            if slot.is_none() {
                *slot = Some(
                    ort::init_from(runtime)
                        .map_err(failed)?
                        .with_name("lumen-memory")
                        .with_telemetry(false)
                        .build()
                        .map_err(failed)?,
                );
            }
            slot.clone().ok_or("No ONNX Runtime environment")?
        };
        use ort::session::{Session, builder::GraphOptimizationLevel};
        // Same options as the retired Python encoder: no arena, no memory pattern.
        let session = (|| -> ort::Result<Session> {
            Session::builder(&environment)?
                .with_optimization_level(GraphOptimizationLevel::All)?
                .with_intra_threads(threads)?
                .with_inter_threads(1)?
                .with_memory_pattern(false)?
                .with_execution_providers([ort::ep::CPU::default().build()])?
                .commit_from_file(model)
        })()
        .map_err(failed)?;
        let inputs = session
            .inputs()
            .iter()
            .map(|i| i.name().to_owned())
            .collect();
        let mut tokenizer = tokenizers::Tokenizer::from_file(tokenizer).map_err(failed)?;
        // The file truncates to one window; long notes are split into windows here instead.
        tokenizer.with_truncation(None).map_err(failed)?;
        tokenizer.with_padding(None);
        let id = |token| {
            tokenizer
                .token_to_id(token)
                .map(i64::from)
                .ok_or("Tokenizer without sentence marks")
        };
        let (start, end) = (id("<s>")?, id("</s>")?);
        Ok(Encoder {
            session,
            tokenizer,
            start,
            end,
            inputs,
        })
    }

    fn tokens(&self, text: &str) -> Result<tokenizers::Encoding, String> {
        if text.chars().count() > MAX_CHARS {
            return Err("Memory embedding input exceeds budget".into());
        }
        self.tokenizer
            .encode_char_offsets(text, false)
            .map_err(failed)
    }

    /// Token ids of `text` and the start of each fragment from fragment `start` on.
    pub fn windows(&self, text: &str, start: usize) -> Result<(Vec<i64>, Vec<usize>), String> {
        let tokens: Vec<i64> = self
            .tokens(text)?
            .get_ids()
            .iter()
            .map(|&id| i64::from(id))
            .collect();
        let mut offsets = Vec::new();
        let mut offset = start * STEP;
        while offset < tokens.len().max(1) {
            offsets.push(offset);
            if offset + WINDOW >= tokens.len() {
                break;
            }
            offset += STEP;
        }
        Ok((tokens, offsets))
    }

    /// The mean-pooled, normalised vector of the fragment at token `offset`, computed like numpy:
    /// float32 model output, float64 pooling and norm, rounded to float32 at the end.
    pub fn vector(&mut self, tokens: &[i64], offset: usize) -> Result<Vec<f32>, String> {
        let ids: Vec<i64> = std::iter::once(self.start)
            .chain(
                tokens[offset.min(tokens.len())..(offset + WINDOW).min(tokens.len())]
                    .iter()
                    .copied(),
            )
            .chain([self.end])
            .collect();
        let n = ids.len();
        let (mask, types) = (vec![1i64; n], vec![0i64; n]);
        let mut values = Vec::new();
        for name in &self.inputs {
            let data = match name.as_str() {
                "input_ids" => &ids,
                "attention_mask" => &mask,
                "token_type_ids" => &types,
                _ => return Err("Unexpected memory model input".into()),
            };
            let tensor =
                ort::value::TensorRef::from_array_view(([1usize, n], &data[..])).map_err(failed)?;
            values.push((name.clone(), ort::session::SessionInputValue::from(tensor)));
        }
        let outputs = self.session.run(values).map_err(failed)?;
        let (shape, hidden) = outputs[0].try_extract_tensor::<f32>().map_err(failed)?;
        if **shape != [1, n as i64, DIMENSIONS as i64] {
            return Err("Invalid memory embedding output".into());
        }
        let mut pooled = [0f64; DIMENSIONS];
        for token in hidden.as_chunks::<DIMENSIONS>().0 {
            for (sum, value) in pooled.iter_mut().zip(token) {
                *sum += f64::from(*value);
            }
        }
        for value in &mut pooled {
            *value /= n as f64;
        }
        let squares: Vec<f64> = pooled.iter().map(|v| v * v).collect();
        let norm = pairwise(&squares).sqrt().max(1e-12);
        let vector: Vec<f32> = pooled.iter().map(|v| (v / norm) as f32).collect();
        if !vector.iter().all(|v| v.is_finite()) {
            return Err("Invalid memory embedding output".into());
        }
        Ok(vector)
    }

    /// Every fragment's vector from fragment `start` on.
    pub fn encode(&mut self, text: &str, start: usize) -> Result<Vec<Vec<f32>>, String> {
        let (tokens, offsets) = self.windows(text, start)?;
        offsets
            .iter()
            .map(|&offset| self.vector(&tokens, offset))
            .collect()
    }

    /// About 125 tokens of `text` from fragment `position`, at most 1600 characters.
    pub fn excerpt(&self, text: &str, position: usize) -> Result<String, String> {
        let encoding = self.tokens(text)?;
        let offsets = encoding.get_offsets();
        let start = position * STEP;
        if start >= offsets.len() {
            return Ok(String::new());
        }
        let (from, to) = (
            offsets[start].0,
            offsets[(start + WINDOW - 1).min(offsets.len() - 1)].1,
        );
        Ok(text
            .chars()
            .skip(from)
            .take(to.saturating_sub(from))
            .take(1600)
            .collect())
    }
}

/// numpy's pairwise float64 summation (`add.reduce` along a contiguous axis).
fn pairwise(values: &[f64]) -> f64 {
    let n = values.len();
    if n < 8 {
        values.iter().fold(0.0, |sum, v| sum + v)
    } else if n <= 128 {
        let mut r = [0f64; 8];
        r.copy_from_slice(&values[..8]);
        let whole = n - n % 8;
        for block in values[8..whole].as_chunks::<8>().0 {
            for (sum, value) in r.iter_mut().zip(block) {
                *sum += value;
            }
        }
        let mut sum = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for value in &values[whole..] {
            sum += value;
        }
        sum
    } else {
        let half = n / 2;
        let half = half - half % 8;
        pairwise(&values[..half]) + pairwise(&values[half..])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pairwise_matches_sequential_within_rounding() {
        let values: Vec<f64> = (0..384).map(|i| (i as f64 * 0.37).sin().powi(2)).collect();
        let sequential: f64 = values.iter().sum();
        assert!((pairwise(&values) - sequential).abs() < 1e-12);
        assert_eq!(pairwise(&values[..5]), values[..5].iter().sum::<f64>());
    }
}
