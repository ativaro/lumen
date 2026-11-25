//! Lumen's memory search, one implementation for desktop and server: the entries a search may use,
//! the Unicode 16 word splitting and folding, the ranking of current rows and the fingerprint of
//! forgotten texts. Callers supply freshly authorized rows; neither text nor meaning scores ever
//! grant access to a source.
pub mod unicode;
use caseless::Caseless;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeSet, HashMap, HashSet};
use std::hash::Hash;

/// One authorized memory or note as a caller hands it to the search; unknown fields are refused.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Entry {
    pub id: String,
    pub title: String,
    pub text: String,
    pub revision: String,
    /// Whose memory it is (an account, the desktop's namespace).
    pub boundary: String,
    #[serde(default = "fact")]
    pub kind: String,
    /// Empty for a general entry.
    #[serde(default)]
    pub project: String,
    #[serde(default = "active")]
    pub status: String,
    #[serde(default)]
    pub allowed: bool,
    #[serde(default)]
    pub updated: f64,
    #[serde(default)]
    pub correction: bool,
    /// The id of the entry this one replaces.
    #[serde(default)]
    pub supersedes: String,
}
fn fact() -> String {
    "fact".into()
}
fn active() -> String {
    "active".into()
}

impl Entry {
    /// Identity, revision and boundary present, at most 500 title and 20000 text characters, a known
    /// kind and state.
    pub fn valid(&self) -> bool {
        !self.id.is_empty()
            && !self.revision.is_empty()
            && !self.boundary.is_empty()
            && self.text.chars().count() <= 20000
            && self.title.chars().count() <= 500
            && ["fact", "preference", "decision", "solution", "note"].contains(&self.kind.as_str())
            && ["active", "proposed", "replaced", "forgotten", "conflict"]
                .contains(&self.status.as_str())
    }
}

/// The current entries of one boundary and project: allowed, general or of that project, active and
/// not replaced by another active one of them. The order stays.
pub fn eligible(entries: Vec<Entry>, boundary: &str, project: &str) -> Vec<Entry> {
    let permitted: Vec<_> = entries
        .into_iter()
        .filter(|e| {
            e.boundary == boundary && e.allowed && (e.project.is_empty() || e.project == project)
        })
        .collect();
    let replaced: HashSet<_> = permitted
        .iter()
        .filter(|e| e.status == "active" && !e.supersedes.is_empty())
        .map(|e| e.supersedes.clone())
        .collect();
    permitted
        .into_iter()
        .filter(|e| e.status == "active" && !replaced.contains(&e.id))
        .collect()
}

/// The search terms of a text: its NFKC, case folded words without `_`, where a single `-`, `.` or `/`
/// between word characters joins them; a run of wide characters (unsegmented scripts) also yields its
/// character pairs. No language or intent word list.
pub fn terms(value: &str) -> Vec<String> {
    let normalized = unicode::search_fold(value);
    let chars: Vec<_> = normalized.char_indices().collect();
    let word = |c: char| unicode::word(c) && c != '_';
    let mut result = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        if !word(chars[i].1) {
            i += 1;
            continue;
        }
        let start = i;
        loop {
            while i < chars.len() && word(chars[i].1) {
                i += 1;
            }
            if i + 1 < chars.len() && matches!(chars[i].1, '-' | '.' | '/') && word(chars[i + 1].1)
            {
                i += 1;
            } else {
                break;
            }
        }
        let token = &normalized[chars[start].0..chars.get(i).map_or(normalized.len(), |v| v.0)];
        result.push(token.to_owned());
        if i - start > 1 && chars[start..i].iter().all(|(_, c)| unicode::wide(*c)) {
            for pair in chars[start..i].windows(2) {
                result.push(pair.iter().map(|(_, c)| c).collect());
            }
        }
    }
    result
}

/// Whether `text` already contains the trimmed `query`, both only case folded (no NFKC).
pub fn mentions(text: &str, query: &str) -> bool {
    text.chars()
        .default_case_fold()
        .collect::<String>()
        .contains(
            &query
                .trim_matches(unicode::whitespace)
                .chars()
                .default_case_fold()
                .collect::<String>(),
        )
}

/// The identity of a forgotten text: SHA-256 (hex) of its case folded words (`_` included), joined by
/// single spaces.
pub fn fingerprint(text: &str) -> String {
    let folded = caseless::default_case_fold_str(text);
    let words = folded
        .split(|c| !unicode::word(c))
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    Sha256::digest(words.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

pub struct Candidate<K> {
    /// The caller's identity of the row (the server: id and revision): the last tie-breaker, ascending,
    /// and the key of its meaning score.
    pub key: K,
    updated: f64,
    counts: Vec<u32>,
    title_terms: Vec<bool>,
    exact_title: bool,
    literal: bool,
    text_digest: [u8; 32],
    correction: bool,
    /// The text contains the query (`mentions`).
    pub literal_body: bool,
}

/// One search over the current rows a caller is allowed to use.
pub struct Ranking<K> {
    query: String,
    needle: Vec<String>,
    pub rows: Vec<Candidate<K>>,
}

impl<K: Ord + Hash> Ranking<K> {
    /// The query counts with its first 6000 characters.
    pub fn new(query: &str) -> Self {
        let needle = BTreeSet::from_iter(terms(&query.chars().take(6000).collect::<String>()))
            .into_iter()
            .collect();
        Self {
            query: query.trim_matches(unicode::whitespace).to_owned(),
            needle,
            rows: Vec::new(),
        }
    }

    /// Adds a row; `updated` orders equal scores (newer first), a `correction` wins over them.
    pub fn push(&mut self, key: K, title: &str, text: &str, updated: f64, correction: bool) {
        let mut counts = HashMap::<String, u32>::new();
        for term in terms(&format!("{title} {text}")) {
            *counts.entry(term).or_default() += 1;
        }
        let title_terms: BTreeSet<_> = terms(title).into_iter().collect();
        let literal = unicode::search_fold(&self.query);
        let body = unicode::search_fold(text);
        self.rows.push(Candidate {
            key,
            updated,
            correction,
            counts: self
                .needle
                .iter()
                .map(|t| counts.get(t).copied().unwrap_or(0))
                .collect(),
            title_terms: self
                .needle
                .iter()
                .map(|t| title_terms.contains(t))
                .collect(),
            exact_title: !self.query.is_empty() && unicode::search_fold(title).contains(&literal),
            literal: unicode::search_fold(&format!("{title}\n{text}")).contains(&literal),
            text_digest: Sha256::digest(body.trim_matches(unicode::whitespace).as_bytes()).into(),
            literal_body: mentions(text, &self.query),
        });
    }

    /// The rows to show, best first, as indices into `rows`. Rows whose folded, trimmed text equals
    /// an earlier one's are left out.
    ///
    /// - `semantic`: meaning scores by key, fused by reciprocal rank with the word ranking, where
    ///   rows containing the trimmed query come first; a score outside 0.35..=1.00001 or not finite
    ///   counts as absent. `None` leaves the word ranking (the server passes `None` for no scores).
    /// - `first`: rows placed before the ranking (the desktop's reserved preferences; the server: none).
    /// - `browse`: an empty query lists every row, newest first, with equal texts (the server);
    ///   otherwise an empty query yields only `first`.
    pub fn ordered(
        &self,
        semantic: Option<&HashMap<K, f64>>,
        first: &[usize],
        browse: bool,
    ) -> Vec<usize> {
        let recent = |a: usize, b: usize| {
            self.rows[b]
                .updated
                .total_cmp(&self.rows[a].updated)
                .then_with(|| self.rows[a].key.cmp(&self.rows[b].key))
        };
        if self.query.is_empty() && browse {
            let mut order: Vec<_> = (0..self.rows.len()).collect();
            order.sort_by(|a, b| recent(*a, *b));
            return order;
        }
        let frequencies: Vec<_> = (0..self.needle.len())
            .map(|i| self.rows.iter().filter(|r| r.counts[i] > 0).count())
            .collect();
        let mut scores = Vec::new();
        for (i, row) in self.rows.iter().enumerate() {
            let matches = row.counts.iter().filter(|v| **v > 0).count();
            if matches == 0 {
                continue;
            }
            let score = row
                .counts
                .iter()
                .enumerate()
                .filter(|(_, n)| **n > 0)
                .map(|(j, n)| {
                    (1.0 + (self.rows.len() + 1) as f64 / (frequencies[j] + 1) as f64).ln()
                        * if row.title_terms[j] { 3.0 } else { 1.0 }
                        * (1.0 + f64::from(*n).ln())
                })
                .sum::<f64>()
                * matches as f64
                / self.needle.len().max(1) as f64
                + if row.exact_title { 4.0 } else { 0.0 };
            scores.push((i, score));
        }
        scores.sort_by(|(a, x), (b, y)| {
            y.total_cmp(x)
                .then_with(|| self.rows[*b].correction.cmp(&self.rows[*a].correction))
                .then_with(|| recent(*a, *b))
        });
        if let Some(semantic) = semantic.filter(|_| !self.needle.is_empty()) {
            let mut combined: HashMap<usize, f64> = scores
                .iter()
                .enumerate()
                .map(|(rank, (i, _))| (*i, 1.0 / (61 + rank) as f64))
                .collect();
            let mut vectors: Vec<_> = self
                .rows
                .iter()
                .enumerate()
                .filter_map(|(i, r)| {
                    semantic
                        .get(&r.key)
                        .filter(|s| s.is_finite() && **s >= 0.35 && **s <= 1.00001)
                        .map(|s| (i, *s))
                })
                .collect();
            vectors.sort_by(|(a, x), (b, y)| {
                y.total_cmp(x)
                    .then_with(|| self.rows[*a].key.cmp(&self.rows[*b].key))
            });
            for (rank, (i, _)) in vectors.into_iter().enumerate() {
                *combined.entry(i).or_default() += 1.0 / (61 + rank) as f64;
            }
            scores = combined.into_iter().collect();
            scores.sort_by(|(a, x), (b, y)| {
                self.rows[*b]
                    .literal
                    .cmp(&self.rows[*a].literal)
                    .then_with(|| y.total_cmp(x))
                    .then_with(|| self.rows[*b].correction.cmp(&self.rows[*a].correction))
                    .then_with(|| recent(*a, *b))
            });
        }
        let mut seen = HashSet::new();
        first
            .iter()
            .copied()
            .chain(
                scores
                    .into_iter()
                    .map(|(i, _)| i)
                    .filter(|i| !first.contains(i)),
            )
            .filter(|i| seen.insert(self.rows[*i].text_digest))
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn current_unicode_terms_and_ordered_dedup() {
        assert_eq!(
            terms("ＣＡＦÉ Straße_2 日本語"),
            ["café", "strasse", "2", "日本語", "日本", "本語"]
        );
        let mut ranking = Ranking::new("strasse");
        ranking.push(1, "Straße", "Older text", 1.0, false);
        ranking.push(2, "strasse", "Newer text", 2.0, false);
        ranking.push(3, "Other", "Newer text", 3.0, false);
        assert_eq!(ranking.ordered(None, &[], true), [1, 0]);
        let scores = HashMap::from([(3, 0.9)]);
        assert_eq!(ranking.ordered(Some(&scores), &[], true), [1, 0]);
        assert_eq!(ranking.ordered(Some(&scores), &[2], false), [2, 0]);
    }
}
