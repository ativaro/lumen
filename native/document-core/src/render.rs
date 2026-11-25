//! Draws a PDF page: paths, text as glyph outlines, pictures, forms, opacity and clipping.
//! What is not drawn is refused by name instead of being drawn wrongly.
use std::collections::HashMap;
use std::rc::Rc;

use tiny_skia::{BlendMode, FillRule, Mask, Paint, PathBuilder, Pixmap, Shader, Stroke, Transform};

use crate::pdf::{Dict, Document, Error, Outcome, Stream, Syntax, Value, integer};
use crate::text::{Font, Matrix, Page, numbers, rectangle};

fn bad<T>(text: &str) -> Outcome<T> {
    Err(Error::Pdf(text.into()))
}

fn unsupported<T>(text: impl Into<String>) -> Outcome<T> {
    Err(Error::Unsupported(text.into()))
}

fn transform(matrix: Matrix) -> Transform {
    Transform::from_row(
        matrix.m11 as f32,
        matrix.m12 as f32,
        matrix.m21 as f32,
        matrix.m22 as f32,
        matrix.dx as f32,
        matrix.dy as f32,
    )
}

fn values(value: &Value, count: Option<usize>) -> Outcome<Vec<f64>> {
    let read: Option<Vec<f64>> = value.array().and_then(|list| {
        list.iter()
            .map(|v| v.number().filter(|n| n.is_finite()))
            .collect()
    });
    match read {
        Some(read) if count.is_none_or(|count| count == read.len()) => Ok(read),
        _ => bad("Ungültige PDF-Farbwerte."),
    }
}

/// A PDF function of types 0, 2 and 3 (sampled, exponential, stitching).
fn function(
    document: &Document,
    reference: &Value,
    inputs: &[f64],
    depth: usize,
) -> Outcome<Vec<f64>> {
    if depth > 32 {
        return bad("PDF-Farbfunktion zu tief.");
    }
    let object = document.resolve(reference)?;
    if let Value::Array(parts) = &object {
        return parts
            .iter()
            .map(|part| {
                Ok(function(document, part, inputs, depth + 1)?
                    .first()
                    .copied()
                    .unwrap_or(0.0))
            })
            .collect();
    }
    let (attrs, stream) = match &object {
        Value::Stream(stream) => (&stream.attrs, Some(stream)),
        Value::Dict(attrs) => (&**attrs, None),
        _ => return bad("PDF-Farbfunktion fehlt."),
    };
    let get = |key: &str| document.resolve(attrs.get(key).unwrap_or(&Value::Null));
    let domain = values(&get("Domain")?, None)?;
    if domain.len() != 2 * inputs.len() {
        return bad("PDF-Farbfunktion hat falsche Eingabezahl.");
    }
    let source: Vec<f64> = inputs
        .iter()
        .enumerate()
        .map(|(i, v)| domain[2 * i].max(domain[2 * i + 1].min(*v)))
        .collect();
    let limits = match get("Range")? {
        Value::Null => None,
        value => Some(values(&value, None)?)
            .filter(|limits| limits.len() % 2 == 0)
            .ok_or(Error::Pdf("Ungültiger PDF-Farbbereich.".into()))
            .map(Some)?,
    };
    let list = |key: &str, default: &[f64]| -> Outcome<Vec<f64>> {
        match get(key)? {
            Value::Null => Ok(default.to_vec()),
            value => values(&value, None),
        }
    };
    let mut result = match attrs
        .get("FunctionType")
        .and_then(Value::number)
        .map(|n| n as i64)
    {
        Some(2) => {
            if source.len() != 1 {
                return bad("PDF-Exponentialfunktion erwartet einen Wert.");
            }
            let first = list("C0", &[0.0])?;
            let last = list("C1", &[1.0])?;
            let Some(exponent) = attrs.get("N").and_then(Value::number) else {
                return bad("Ungültige PDF-Farbwerte.");
            };
            let factor = source[0].powf(exponent);
            if last.len() != first.len() || !factor.is_finite() {
                return bad("Ungültige PDF-Exponentialfunktion.");
            }
            first
                .iter()
                .zip(&last)
                .map(|(a, b)| a + factor * (b - a))
                .collect()
        }
        Some(3) => {
            let parts = get("Functions")?;
            let (bounds, encode) = (list("Bounds", &[])?, list("Encode", &[])?);
            let Some(parts) = parts.array().filter(|parts| {
                source.len() == 1
                    && !parts.is_empty()
                    && bounds.len() == parts.len() - 1
                    && encode.len() == 2 * parts.len()
            }) else {
                return bad("Ungültige zusammengesetzte PDF-Farbfunktion.");
            };
            let mut edges = vec![domain[0]];
            edges.extend(&bounds);
            edges.push(domain[1]);
            // Equal neighbouring bounds are common and leave an interval without width, which is never chosen for a value inside the domain.
            if edges.windows(2).any(|pair| pair[0] > pair[1]) || edges[0] >= edges[edges.len() - 1]
            {
                return bad("Ungültige PDF-Funktionsgrenzen.");
            }
            let index = bounds
                .iter()
                .filter(|bound| source[0] >= **bound)
                .count()
                .min(parts.len() - 1);
            let (a, b) = (edges[index], edges[index + 1]);
            let share = if b > a {
                (source[0] - a) / (b - a)
            } else {
                0.0
            };
            function(
                document,
                &parts[index],
                &[encode[index * 2] + share * (encode[index * 2 + 1] - encode[index * 2])],
                depth + 1,
            )?
        }
        Some(0) => {
            let (Some(stream), Some(limits)) = (stream, &limits) else {
                return bad("PDF-Abtastfunktion fehlt.");
            };
            let bits = integer(attrs.get("BitsPerSample").unwrap_or(&Value::Null), 1, 32)? as usize;
            let sizes = get("Size")?;
            let order = attrs.get("Order").and_then(Value::number).unwrap_or(1.0);
            let Some(sizes) = sizes
                .array()
                .filter(|sizes| sizes.len() == source.len() && sizes.len() <= 8 && order == 1.0)
            else {
                return bad("Ungültige PDF-Abtastfunktion.");
            };
            let sizes: Vec<usize> = sizes
                .iter()
                .map(|size| integer(size, 1, 65536).map(|s| s as usize))
                .collect::<Outcome<_>>()?;
            let channels = limits.len() / 2;
            let total = sizes.iter().product::<usize>() * channels;
            if total > 8_000_000 {
                return bad("PDF-Funktionsbudget überschritten.");
            }
            let raw = document.decode(stream)?;
            if raw.len() * 8 < total * bits {
                return bad("Unvollständige PDF-Funktionswerte.");
            }
            let default: Vec<f64> = sizes
                .iter()
                .flat_map(|size| [0.0, (*size - 1) as f64])
                .collect();
            let encode = list("Encode", &default)?;
            let decode = list("Decode", limits)?;
            if encode.len() != 2 * source.len() || decode.len() != 2 * channels {
                return bad("Ungültige PDF-Farbwerte.");
            }
            let mut points = Vec::new();
            for (i, x) in source.iter().enumerate() {
                let (low, high) = (domain[2 * i], domain[2 * i + 1]);
                if high <= low {
                    return bad("Ungültiger PDF-Funktionseingabebereich.");
                }
                let p = (encode[2 * i]
                    + (x - low) / (high - low) * (encode[2 * i + 1] - encode[2 * i]))
                    .clamp(0.0, (sizes[i] - 1) as f64);
                let floor = p as usize;
                points.push([
                    (floor, 1.0 - (p - floor as f64)),
                    ((floor + 1).min(sizes[i] - 1), p - floor as f64),
                ]);
            }
            let mut output = vec![0.0; channels];
            let maximum = ((1u64 << bits) - 1) as f64;
            for corner in 0..1usize << points.len() {
                let (mut offset, mut stride, mut weight) = (0, 1, 1.0);
                for (axis, pair) in points.iter().enumerate() {
                    let (index, factor) = pair[corner >> axis & 1];
                    offset += index * stride;
                    stride *= sizes[axis];
                    weight *= factor;
                }
                if weight == 0.0 {
                    continue;
                }
                for (channel, slot) in output.iter_mut().enumerate() {
                    let bit = (offset * channels + channel) * bits;
                    let (start, count) = (bit / 8, (bit % 8 + bits).div_ceil(8));
                    let chunk = raw[start..start + count]
                        .iter()
                        .fold(0u64, |sum, byte| sum << 8 | u64::from(*byte));
                    let sample = (chunk >> (count * 8 - bit % 8 - bits)) & ((1u64 << bits) - 1);
                    *slot += weight
                        * (decode[2 * channel]
                            + sample as f64 / maximum
                                * (decode[2 * channel + 1] - decode[2 * channel]));
                }
            }
            output
        }
        Some(4) => {
            let Some(stream) = stream else {
                return bad("Unbekannte PDF-Farbfunktion.");
            };
            crate::calculator::calculate(&document.decode(stream)?, &source)?
        }
        _ => return bad("Unbekannte PDF-Farbfunktion."),
    };
    if let Some(limits) = limits {
        if limits.len() != 2 * result.len() {
            return bad("PDF-Farbfunktion hat falsche Ausgabezahl.");
        }
        for (i, value) in result.iter_mut().enumerate() {
            *value = limits[2 * i].max(limits[2 * i + 1].min(*value));
        }
    }
    Ok(result)
}

/// A colour space, reduced to what turns its components into RGB.
#[derive(Clone)]
pub(crate) enum Space {
    Gray,
    Rgb,
    Cmyk,
    Indexed {
        base: Rc<Space>,
        high: usize,
        lookup: Rc<Vec<u8>>,
    },
    Tint {
        components: usize,
        base: Rc<Space>,
        function: Value,
    },
    Calibrated {
        kind: u8,
        attrs: Rc<Dict>,
    },
    Pattern,
    /// An ICC profile other than sRGB, converted to sRGB by colour management.
    Icc {
        components: usize,
        convert: Rc<IccConvert>,
    },
}

/// The conversions of an ICC profile to sRGB: one for single colours, one for whole images.
pub(crate) struct IccConvert {
    colours: std::sync::Arc<moxcms::TransformF32Executor>,
    pixels: std::sync::Arc<moxcms::Transform8BitExecutor>,
}

impl IccConvert {
    /// None when the profile cannot be read or does not have `components` channels.
    fn new(data: &[u8], components: usize) -> Option<IccConvert> {
        let profile = moxcms::ColorProfile::new_from_slice(data).ok()?;
        let layout = match (components, profile.color_space) {
            (1, moxcms::DataColorSpace::Gray) => moxcms::Layout::Gray,
            (3, moxcms::DataColorSpace::Rgb | moxcms::DataColorSpace::Lab) => moxcms::Layout::Rgb,
            (4, moxcms::DataColorSpace::Cmyk) => moxcms::Layout::Rgba,
            _ => return None,
        };
        let srgb = moxcms::ColorProfile::new_srgb();
        let options = moxcms::TransformOptions::default();
        Some(IccConvert {
            colours: profile
                .create_transform_f32(layout, &srgb, moxcms::Layout::Rgb, options)
                .ok()?,
            pixels: profile
                .create_transform_8bit(layout, &srgb, moxcms::Layout::Rgb, options)
                .ok()?,
        })
    }
}

impl Space {
    /// The space an ICC profile with 1, 3 or 4 components describes; an unreadable profile stands for the device
    /// space with as many components.
    fn profiled(data: &[u8], components: usize) -> Space {
        match IccConvert::new(data, components) {
            Some(convert) => Space::Icc {
                components,
                convert: Rc::new(convert),
            },
            None if components == 1 => Space::Gray,
            None if components == 4 => Space::Cmyk,
            None => Space::Rgb,
        }
    }

    pub(crate) fn parse(
        document: &Document,
        definition: &Value,
        resources: &Dict,
        depth: usize,
    ) -> Outcome<Space> {
        if depth > 16 {
            return bad("PDF-Farbraum zu tief.");
        }
        let mut definition = document.resolve(definition)?;
        if let Value::Name(name) = &definition
            && !matches!(
                &**name,
                "DeviceGray" | "G" | "DeviceRGB" | "RGB" | "DeviceCMYK" | "CMYK" | "Pattern"
            )
            && let Some(alias) = resources
                .get("ColorSpace")
                .map(|named| document.resolve(named))
                .transpose()?
                .as_ref()
                .and_then(Value::dict)
                .and_then(|named| named.get(&**name))
        {
            definition = document.resolve(alias)?;
        }
        let parts = match &definition {
            Value::Array(parts) if !parts.is_empty() => (**parts).clone(),
            Value::Array(_) => return bad("Leerer PDF-Farbraum."),
            other => vec![other.clone()],
        };
        let part = |index: usize| -> Outcome<Value> {
            document.resolve(parts.get(index).unwrap_or(&Value::Null))
        };
        let kind = part(0)?;
        match kind.name().unwrap_or("") {
            "DeviceGray" | "G" => Ok(Space::Gray),
            "DeviceRGB" | "RGB" => Ok(Space::Rgb),
            "DeviceCMYK" | "CMYK" => Ok(Space::Cmyk),
            "Pattern" => Ok(Space::Pattern),
            "ICCBased" => {
                let Value::Stream(profile) = part(1)? else {
                    return bad("PDF-ICC-Profil fehlt.");
                };
                // An sRGB profile describes the colours this renderer works in, so its values are used as they are.
                // Any other profile goes through colour management; one that cannot be read stands for the device
                // space with as many components.
                let components = integer(profile.attrs.get("N").unwrap_or(&Value::Null), 1, 4)?;
                let data = document.decode(&profile)?;
                let standard = data.windows(4).any(|window| window == b"sRGB");
                match components {
                    3 if standard => Ok(Space::Rgb),
                    1 | 3 | 4 => Ok(Space::profiled(&data, components as usize)),
                    _ => bad("Ungültige PDF-ICC-Komponenten."),
                }
            }
            "Indexed" | "I" => {
                if parts.len() != 4 {
                    return bad("Ungültige PDF-Farbpalette.");
                }
                let base = Space::parse(document, &parts[1], resources, depth + 1)?;
                let high = integer(&part(2)?, 0, 255)? as usize;
                let lookup = match part(3)? {
                    Value::Text(bytes) => (*bytes).clone(),
                    Value::Stream(stream) => document.decode(&stream)?,
                    _ => return bad("Unvollständige PDF-Farbpalette."),
                };
                if lookup.len() < (high + 1) * base.components() {
                    return bad("Unvollständige PDF-Farbpalette.");
                }
                Ok(Space::Indexed {
                    base: Rc::new(base),
                    high,
                    lookup: Rc::new(lookup),
                })
            }
            "Separation" | "DeviceN" => {
                if parts.len() < 4 {
                    return bad("Ungültiger PDF-Sonderfarbraum.");
                }
                let components = match part(1)? {
                    Value::Array(names) if !names.is_empty() && names.len() <= 32 => names.len(),
                    Value::Name(_) => 1,
                    _ => return bad("Ungültige PDF-Sonderfarben."),
                };
                Ok(Space::Tint {
                    components,
                    base: Rc::new(Space::parse(document, &parts[2], resources, depth + 1)?),
                    function: parts[3].clone(),
                })
            }
            kind @ ("CalGray" | "CalRGB" | "Lab") => {
                let Value::Dict(attrs) = part(1)? else {
                    return bad("PDF-Farbkalibrierung fehlt.");
                };
                let white = values(attrs.get("WhitePoint").unwrap_or(&Value::Null), Some(3))?;
                if white[0] <= 0.0 || white[1] != 1.0 || white[2] <= 0.0 {
                    return bad("Ungültiger PDF-Weißpunkt.");
                }
                Ok(Space::Calibrated {
                    kind: b"GRL"[["CalGray", "CalRGB", "Lab"]
                        .iter()
                        .position(|k| *k == kind)
                        .unwrap_or(0)],
                    attrs,
                })
            }
            other => bad(&format!("Unbekannter PDF-Farbraum: {other}")),
        }
    }

    pub(crate) fn components(&self) -> usize {
        match self {
            Space::Gray | Space::Indexed { .. } => 1,
            Space::Rgb => 3,
            Space::Cmyk => 4,
            Space::Tint { components, .. } | Space::Icc { components, .. } => *components,
            Space::Calibrated { kind, .. } => {
                if *kind == b'G' {
                    1
                } else {
                    3
                }
            }
            Space::Pattern => 0,
        }
    }

    /// The colour a space starts with when it is selected.
    pub(crate) fn initial(&self) -> Vec<f64> {
        match self {
            Space::Cmyk => vec![0.0, 0.0, 0.0, 1.0],
            Space::Tint { components, .. } => vec![1.0; *components],
            other => vec![0.0; other.components()],
        }
    }

    fn ranges(&self) -> Vec<f64> {
        match self {
            Space::Indexed { high, .. } => vec![0.0, *high as f64],
            Space::Calibrated { kind: b'L', attrs } => {
                let range = attrs
                    .get("Range")
                    .and_then(|range| values(range, Some(4)).ok())
                    .unwrap_or(vec![-100.0, 100.0, -100.0, 100.0]);
                [vec![0.0, 100.0], range].concat()
            }
            other => [0.0, 1.0].repeat(other.components()),
        }
    }

    pub(crate) fn rgb(&self, document: &Document, samples: &[f64]) -> Outcome<[f64; 3]> {
        if samples.len() != self.components() || samples.iter().any(|v| !v.is_finite()) {
            return bad("Ungültige PDF-Farbwerte.");
        }
        let unit = |v: f64| v.clamp(0.0, 1.0);
        match self {
            Space::Gray => Ok([unit(samples[0]); 3]),
            Space::Rgb => Ok([unit(samples[0]), unit(samples[1]), unit(samples[2])]),
            Space::Cmyk => {
                let k = unit(samples[3]);
                Ok([
                    (1.0 - unit(samples[0])) * (1.0 - k),
                    (1.0 - unit(samples[1])) * (1.0 - k),
                    (1.0 - unit(samples[2])) * (1.0 - k),
                ])
            }
            Space::Icc { convert, .. } => {
                let source: Vec<f32> = samples.iter().map(|v| unit(*v) as f32).collect();
                let mut rgb = [0f32; 3];
                if convert.colours.transform(&source, &mut rgb).is_err() {
                    return bad("PDF-Farbprofil konnte nicht angewendet werden.");
                }
                Ok(rgb.map(|v| unit(f64::from(v))))
            }
            Space::Indexed { base, high, lookup } => {
                let index = ((samples[0] + 0.5).floor().max(0.0) as usize).min(*high);
                let (n, limits) = (base.components(), base.ranges());
                let inner: Vec<f64> = (0..n)
                    .map(|i| {
                        limits[2 * i]
                            + f64::from(lookup[index * n + i]) / 255.0
                                * (limits[2 * i + 1] - limits[2 * i])
                    })
                    .collect();
                base.rgb(document, &inner)
            }
            Space::Tint {
                base,
                function: tint,
                ..
            } => base.rgb(document, &function(document, tint, samples, 0)?),
            Space::Calibrated { kind, attrs } => {
                let white = values(attrs.get("WhitePoint").unwrap_or(&Value::Null), Some(3))?;
                let xyz: Vec<f64> = match kind {
                    b'G' => {
                        let gamma = attrs.get("Gamma").and_then(Value::number).unwrap_or(1.0);
                        white
                            .iter()
                            .map(|w| w * unit(samples[0]).powf(gamma))
                            .collect()
                    }
                    b'R' => {
                        let gamma = attrs
                            .get("Gamma")
                            .map(|g| values(g, Some(3)))
                            .transpose()?
                            .unwrap_or(vec![1.0; 3]);
                        let matrix = attrs
                            .get("Matrix")
                            .map(|m| values(m, Some(9)))
                            .transpose()?
                            .unwrap_or(vec![1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]);
                        let abc: Vec<f64> = samples
                            .iter()
                            .zip(&gamma)
                            .map(|(v, g)| unit(*v).powf(*g))
                            .collect();
                        (0..3)
                            .map(|i| (0..3).map(|j| matrix[i + 3 * j] * abc[j]).sum())
                            .collect()
                    }
                    _ => {
                        let y = (samples[0] + 16.0) / 116.0;
                        let lab = |v: f64| {
                            if v >= 6.0 / 29.0 {
                                v.powi(3)
                            } else {
                                108.0 / 841.0 * (v - 4.0 / 29.0)
                            }
                        };
                        vec![
                            white[0] * lab(y + samples[1] / 500.0),
                            white[1] * lab(y),
                            white[2] * lab(y - samples[2] / 200.0),
                        ]
                    }
                };
                // Bradford chromatic adaptation from the declared white to D65.
                let multiply = |m: &[[f64; 3]; 3], v: &[f64]| -> Vec<f64> {
                    m.iter()
                        .map(|row| row.iter().zip(v).map(|(a, b)| a * b).sum())
                        .collect()
                };
                let cone = [
                    [0.8951, 0.2664, -0.1614],
                    [-0.7502, 1.7135, 0.0367],
                    [0.0389, -0.0685, 1.0296],
                ];
                let (origin, target, seen) = (
                    multiply(&cone, &white),
                    multiply(&cone, &[0.95047, 1.0, 1.08883]),
                    multiply(&cone, &xyz),
                );
                let scaled: Vec<f64> = (0..3).map(|i| seen[i] * target[i] / origin[i]).collect();
                let adapted = multiply(
                    &[
                        [0.9869929, -0.1470543, 0.1599627],
                        [0.4323053, 0.5183603, 0.0492912],
                        [-0.0085287, 0.0400428, 0.9684867],
                    ],
                    &scaled,
                );
                let linear = multiply(
                    &[
                        [3.2404542, -1.5371385, -0.4985314],
                        [-0.969266, 1.8760108, 0.041556],
                        [0.0556434, -0.2040259, 1.0572252],
                    ],
                    &adapted,
                );
                let curve = |v: f64| {
                    unit(if v <= 0.0031308 {
                        12.92 * v
                    } else {
                        1.055 * v.powf(1.0 / 2.4) - 0.055
                    })
                };
                Ok([curve(linear[0]), curve(linear[1]), curve(linear[2])])
            }
            Space::Pattern => bad("Ungültige PDF-Farbwerte."),
        }
    }
}

/// A decoded picture: straight RGBA, row by row.
struct Picture {
    width: u32,
    height: u32,
    rgba: Vec<u8>,
}

/// One sample of `bits` bits at a bit position.
fn sample(row: &[u8], index: usize, bits: usize) -> u32 {
    let bit = index * bits;
    if bits == 16 {
        return u32::from(row[bit / 8]) << 8 | u32::from(row[bit / 8 + 1]);
    }
    u32::from(row[bit / 8] >> (8 - bits - bit % 8)) & ((1 << bits) - 1)
}

fn picture(
    document: &Document,
    stream: &Stream,
    resources: &Dict,
    fill: [f64; 3],
    depth: usize,
    budget: &mut usize,
) -> Outcome<Picture> {
    if depth > 16 {
        return bad("Zyklische PDF-Bildmaske.");
    }
    let get = |key: &str| document.resolve(stream.attrs.get(key).unwrap_or(&Value::Null));
    let (w, h) = (
        integer(&get("Width")?, 1, crate::pdf::MAX_SIDE as i64)? as usize,
        integer(&get("Height")?, 1, crate::pdf::MAX_SIDE as i64)? as usize,
    );
    *budget += w * h;
    if w * h > crate::pdf::MAX_PIXELS || *budget > 80_000_000 {
        return bad("PDF-Bildbudget überschritten.");
    }
    let stencil = match get("ImageMask")? {
        Value::Null => false,
        Value::Bool(stencil) => stencil,
        _ => return bad("Ungültige PDF-Bildmaske."),
    };
    let filters = match get("Filter")? {
        Value::Null => Vec::new(),
        Value::Name(name) => vec![Value::Name(name)],
        Value::Array(filters) if filters.len() <= 8 => filters
            .iter()
            .map(|filter| document.resolve(filter))
            .collect::<Outcome<_>>()?,
        _ => return bad("Ungültige PDF-Bildfilterkette."),
    };
    // The encoded picture of a JPEG or JPEG 2000 image: the stream with all but its last filter applied.
    let leading = || -> Outcome<Vec<u8>> {
        let params = match get("DecodeParms")? {
            Value::Array(params) => (*params).clone(),
            Value::Dict(params) => vec![Value::Dict(params)],
            _ => Vec::new(),
        };
        let mut attrs = stream.attrs.clone();
        attrs.insert(
            "Filter".into(),
            Value::Array(Rc::new(filters[..filters.len() - 1].to_vec())),
        );
        attrs.insert(
            "DecodeParms".into(),
            Value::Array(Rc::new(params[..params.len().saturating_sub(1)].to_vec())),
        );
        document.decode(&Stream {
            attrs,
            raw: stream.raw.clone(),
        })
    };
    // JPEG 2000 carries its own depth and colour space; a ColorSpace entry overrides the latter.
    let mut jpx = if !stencil && filters.last().and_then(Value::name) == Some("JPXDecode") {
        let encoded = leading()?;
        let failed = || Error::Pdf("PDF-Bild konnte nicht dekodiert werden.".into());
        let image =
            hayro_jpeg2000::Image::new(&encoded, &hayro_jpeg2000::DecodeSettings::default())
                .map_err(|_| failed())?;
        if image.width() as usize != w || image.height() as usize != h {
            return bad("PDF-Bildkopf und Größe stimmen nicht überein.");
        }
        use hayro_jpeg2000::ColorSpace as Own;
        let own = match image.color_space() {
            Own::Gray => Space::Gray,
            Own::RGB => Space::Rgb,
            Own::CMYK => Space::Cmyk,
            Own::Icc {
                profile,
                num_channels,
            } if matches!(num_channels, 1 | 3 | 4) => {
                Space::profiled(profile, usize::from(*num_channels))
            }
            Own::Unknown { num_channels: 1 } => Space::Gray,
            Own::Unknown { num_channels: 3 } => Space::Rgb,
            Own::Unknown { num_channels: 4 } => Space::Cmyk,
            _ => return bad("Ungültige JPEG-/JPX-Farbkomponenten."),
        };
        let colour = usize::from(image.color_space().num_channels());
        let alpha = image.has_alpha();
        let mut context = hayro_jpeg2000::DecoderContext::default();
        let data = image.decode(&mut context).map_err(|_| failed())?.data_u8();
        Some((own, colour, alpha, data))
    } else {
        None
    };
    let mut bits = match get("BitsPerComponent")? {
        Value::Null if stencil => 1,
        Value::Null if jpx.is_some() => 8,
        Value::Int(bits @ (1 | 2 | 4 | 8 | 16)) if !stencil || bits == 1 => bits as usize,
        _ => return bad("Ungültige PDF-Bittiefe."),
    };
    let space = if stencil {
        Space::Gray
    } else if let Some((own, ..)) = jpx
        .as_ref()
        .filter(|_| get("ColorSpace").is_ok_and(|v| matches!(v, Value::Null)))
    {
        own.clone()
    } else {
        Space::parse(
            document,
            stream.attrs.get("ColorSpace").unwrap_or(&Value::Null),
            resources,
            0,
        )?
    };
    let channels = space.components();
    if channels == 0 {
        return bad("Ungültige PDF-Farbwerte.");
    }
    // A JPEG 2000 image ignores Decode (ISO 32000-1, 8.9.5.1).
    let custom = jpx.is_none() && !matches!(get("Decode")?, Value::Null);
    let decode = if custom {
        values(&get("Decode")?, Some(2 * channels))?
    } else {
        space.ranges()
    };
    let raw = match filters.last().and_then(Value::name) {
        Some("JPXDecode") => {
            let Some((_, colour, alpha, data)) = jpx.take() else {
                return bad("PDF-Bild konnte nicht dekodiert werden.");
            };
            if colour != channels || data.len() != w * h * (colour + usize::from(alpha)) {
                return bad("Ungültige JPEG-/JPX-Farbkomponenten.");
            }
            bits = 8;
            if alpha {
                // ponytail: the image's own alpha (SMaskInData) is dropped, honour it when a file needs it.
                data.chunks_exact(colour + 1)
                    .flat_map(|pixel| &pixel[..colour])
                    .copied()
                    .collect()
            } else {
                data
            }
        }
        Some("DCTDecode" | "DCT") => {
            let encoded = leading()?;
            let pixels = if channels == 4 {
                // Four channels (CMYK or YCCK) go to the decoder that returns them as CMYK samples.
                let mut decoder = jpeg_decoder::Decoder::new(&encoded[..]);
                let Ok(pixels) = decoder.decode() else {
                    return bad("PDF-Bild konnte nicht dekodiert werden.");
                };
                match decoder.info() {
                    Some(info) if info.pixel_format != jpeg_decoder::PixelFormat::CMYK32 => {
                        return bad("Ungültige JPEG-/JPX-Farbkomponenten.");
                    }
                    Some(info) if usize::from(info.width) == w && usize::from(info.height) == h => {
                    }
                    _ => return bad("PDF-Bildkopf und Größe stimmen nicht überein."),
                }
                // The decoder turns Adobe's inverted samples into plain ones. PDF applies its own Decode array,
                // so the convention of the file is restored first.
                if encoded[..encoded.len().min(65536)]
                    .windows(5)
                    .any(|window| window == b"Adobe")
                {
                    pixels.iter().map(|value| 255 - value).collect()
                } else {
                    pixels
                }
            } else {
                use zune_jpeg::zune_core::{colorspace::ColorSpace, options::DecoderOptions};
                let wanted = match channels {
                    1 => ColorSpace::Luma,
                    3 => ColorSpace::RGB,
                    _ => return bad("Ungültige JPEG-/JPX-Farbkomponenten."),
                };
                let mut decoder = zune_jpeg::JpegDecoder::new_with_options(
                    zune_jpeg::zune_core::bytestream::ZCursor::new(&encoded[..]),
                    DecoderOptions::default().jpeg_set_out_colorspace(wanted),
                );
                let Ok(pixels) = decoder.decode() else {
                    return bad("PDF-Bild konnte nicht dekodiert werden.");
                };
                if decoder
                    .info()
                    .is_none_or(|info| info.width as usize != w || info.height as usize != h)
                {
                    return bad("PDF-Bildkopf und Größe stimmen nicht überein.");
                }
                pixels
            };
            bits = 8;
            pixels
        }
        _ => document.decode(stream)?,
    };
    let stride = (w * channels * bits).div_ceil(8);
    // Bytes beyond the last row, such as a line end counted into the stream, are not pixels.
    if raw.len() < h * stride {
        return bad("PDF-Pixeldaten und Größe stimmen nicht überein.");
    }
    let maximum = ((1u32 << bits) - 1) as f64;
    let byte = |v: f64| (v.clamp(0.0, 1.0) * 255.0).round() as u8;
    let mut rgba = vec![255u8; w * h * 4];
    if stencil {
        if decode != [0.0, 1.0] && decode != [1.0, 0.0] {
            return bad("Ungültige PDF-Schablonendekodierung.");
        }
        let ink = [byte(fill[0]), byte(fill[1]), byte(fill[2])];
        for y in 0..h {
            for x in 0..w {
                let painted = decode[sample(&raw[y * stride..], x, 1) as usize] == 0.0;
                rgba[(y * w + x) * 4..(y * w + x) * 4 + 4].copy_from_slice(&[
                    ink[0],
                    ink[1],
                    ink[2],
                    if painted { 255 } else { 0 },
                ]);
            }
        }
    } else {
        // Indexed default Decode uses the sample's integer index, regardless of the palette's highest used entry (ISO 32000-1 table 89).
        let indexed = matches!(space, Space::Indexed { .. }) && !custom;
        let colour_of = |pixel: &[u32]| -> Outcome<[u8; 3]> {
            let decoded: Vec<f64> = pixel
                .iter()
                .enumerate()
                .map(|(i, v)| {
                    if indexed {
                        f64::from(*v)
                    } else {
                        decode[2 * i]
                            + f64::from(*v) / maximum * (decode[2 * i + 1] - decode[2 * i])
                    }
                })
                .collect();
            let rgb = space.rgb(document, &decoded)?;
            Ok([byte(rgb[0]), byte(rgb[1]), byte(rgb[2])])
        };
        // Whole bytes in a device space with the usual value range need no arithmetic per sample.
        let plain = bits == 8 && !custom;
        match &space {
            Space::Gray if plain => {
                for (target, value) in rgba.as_chunks_mut::<4>().0.iter_mut().zip(&raw) {
                    target[..3].copy_from_slice(&[*value; 3]);
                }
            }
            Space::Rgb if plain => {
                for (target, source) in rgba
                    .as_chunks_mut::<4>()
                    .0
                    .iter_mut()
                    .zip(raw.as_chunks::<3>().0)
                {
                    target[..3].copy_from_slice(source);
                }
            }
            Space::Cmyk if plain => {
                for (target, source) in rgba
                    .as_chunks_mut::<4>()
                    .0
                    .iter_mut()
                    .zip(raw.as_chunks::<4>().0)
                {
                    let key = 255 - u32::from(source[3]);
                    for channel in 0..3 {
                        target[channel] =
                            (((255 - u32::from(source[channel])) * key + 127) / 255) as u8;
                    }
                }
            }
            Space::Icc { convert, .. } if plain => {
                let mut rgb = vec![0u8; w * h * 3];
                if convert.pixels.transform(&raw, &mut rgb).is_err() {
                    return bad("PDF-Bildprofil konnte nicht angewendet werden.");
                }
                for (target, source) in rgba
                    .as_chunks_mut::<4>()
                    .0
                    .iter_mut()
                    .zip(rgb.as_chunks::<3>().0)
                {
                    target[..3].copy_from_slice(source);
                }
            }
            // One sample per pixel has at most 256 colours: each is worked out once.
            _ if channels == 1 && bits <= 8 => {
                let table: Vec<[u8; 3]> = (0..1u32 << bits)
                    .map(|value| colour_of(&[value]))
                    .collect::<Outcome<_>>()?;
                for y in 0..h {
                    let row = &raw[y * stride..(y + 1) * stride];
                    for x in 0..w {
                        rgba[(y * w + x) * 4..(y * w + x) * 4 + 3]
                            .copy_from_slice(&table[sample(row, x, bits) as usize]);
                    }
                }
            }
            _ => {
                // Pictures repeat colours; each distinct one is converted once.
                let mut known: HashMap<u64, [u8; 3]> = HashMap::new();
                let mut pixel = vec![0u32; channels];
                for y in 0..h {
                    let row = &raw[y * stride..(y + 1) * stride];
                    for x in 0..w {
                        let mut key = 0u64;
                        for (channel, slot) in pixel.iter_mut().enumerate() {
                            *slot = sample(row, x * channels + channel, bits);
                            key = key.wrapping_mul(65537).wrapping_add(u64::from(*slot));
                        }
                        let colour = match known.get(&key).filter(|_| channels <= 4) {
                            Some(colour) => *colour,
                            None => {
                                let colour = colour_of(&pixel)?;
                                if known.len() < 65536 && channels <= 4 {
                                    known.insert(key, colour);
                                }
                                colour
                            }
                        };
                        rgba[(y * w + x) * 4..(y * w + x) * 4 + 3].copy_from_slice(&colour);
                    }
                }
            }
        }
    }
    let soft = match get("SMask")? {
        Value::Stream(mask) => Some((mask, true)),
        _ => match get("Mask")? {
            Value::Stream(mask) => Some((mask, false)),
            Value::Array(keys) => {
                let keys = values(&Value::Array(keys), Some(channels * 2))?;
                for y in 0..h {
                    for x in 0..w {
                        let inside = (0..channels).all(|i| {
                            let v = f64::from(sample(&raw[y * stride..], x * channels + i, bits));
                            keys[2 * i] <= v && v <= keys[2 * i + 1]
                        });
                        if inside {
                            rgba[(y * w + x) * 4 + 3] = 0;
                        }
                    }
                }
                None
            }
            Value::Null => None,
            Value::Name(name) if &*name == "None" => None,
            _ => return bad("Ungültige PDF-Bildmaske."),
        },
    };
    if let Some((mask, luminous)) = soft {
        if luminous
            && !matches!(
                document
                    .resolve(mask.attrs.get("ColorSpace").unwrap_or(&Value::Null))?
                    .name(),
                Some("DeviceGray" | "G")
            )
        {
            return bad("PDF-Weichmaske benötigt Graustufen.");
        }
        // A picture stored already mixed with a matte colour is unmixed before its mask applies.
        let matte = match mask.attrs.get("Matte").filter(|_| luminous) {
            Some(matte) => Some(space.rgb(
                document,
                &values(&document.resolve(matte)?, Some(channels))?,
            )?),
            None => None,
        };
        let overlay = picture(document, &mask, resources, [0.0; 3], depth + 1, budget)?;
        for y in 0..h {
            for x in 0..w {
                // The mask is stretched to the picture by taking the nearest sample.
                let (mx, my) = (
                    x * overlay.width as usize / w,
                    y * overlay.height as usize / h,
                );
                let at = (my * overlay.width as usize + mx) * 4;
                let alpha = if luminous {
                    overlay.rgba[at]
                } else {
                    overlay.rgba[at + 3]
                };
                if let (Some(matte), true) = (matte, alpha > 0) {
                    let share = f64::from(alpha) / 255.0;
                    for (channel, backdrop) in matte.iter().enumerate() {
                        let mixed = f64::from(rgba[(y * w + x) * 4 + channel]) / 255.0;
                        rgba[(y * w + x) * 4 + channel] =
                            byte((mixed - (1.0 - share) * backdrop) / share);
                    }
                }
                let own = &mut rgba[(y * w + x) * 4 + 3];
                *own = (u16::from(*own) * u16::from(alpha) / 255) as u8;
            }
        }
    }
    Ok(Picture {
        width: w as u32,
        height: h as u32,
        rgba,
    })
}

/// The line settings of a graphics state.
fn line_style(state: &State) -> Stroke {
    let mut stroke = Stroke {
        width: state.width as f32,
        miter_limit: state.miter as f32,
        ..Stroke::default()
    };
    stroke.line_cap = [
        tiny_skia::LineCap::Butt,
        tiny_skia::LineCap::Round,
        tiny_skia::LineCap::Square,
    ][state.cap as usize];
    stroke.line_join = [
        tiny_skia::LineJoin::Miter,
        tiny_skia::LineJoin::Round,
        tiny_skia::LineJoin::Bevel,
    ][state.join as usize];
    if !state.dash.is_empty() {
        stroke.dash = tiny_skia::StrokeDash::new(
            state.dash.iter().map(|v| *v as f32).collect(),
            state.phase as f32,
        );
    }
    stroke
}

#[derive(Clone)]
struct State {
    ctm: Matrix,
    clip: Option<Rc<Mask>>,
    fill: [f64; 3],
    stroke: [f64; 3],
    fill_space: Space,
    stroke_space: Space,
    fill_alpha: f64,
    stroke_alpha: f64,
    blend: BlendMode,
    width: f64,
    cap: i64,
    join: i64,
    miter: f64,
    dash: Vec<f64>,
    phase: f64,
    font: Option<Rc<Font>>,
    size: f64,
    charspace: f64,
    wordspace: f64,
    scale: f64,
    leading: f64,
    rise: f64,
    mode: i64,
    /// Inside a knockout group: the backdrop the group started from, None for a transparent one.
    knockout: Option<Rc<Option<Pixmap>>>,
    /// What fills when the fill colour space is Pattern.
    filling: Option<Filling>,
    /// What strokes when the stroke colour space is Pattern.
    stroking: Option<Filling>,
    /// Stroke adjustment: lines are drawn on whole pixels, without smoothed edges.
    adjust: bool,
    /// The soft mask in force. It is already part of `clip`; `unveiled` keeps the clip without it.
    soft: Option<Rc<Mask>>,
    unveiled: Option<Option<Rc<Mask>>>,
}

impl State {
    /// The graphics state a content stream begins with.
    fn start() -> State {
        State {
            ctm: Matrix::IDENTITY,
            clip: None,
            fill: [0.0; 3],
            stroke: [0.0; 3],
            fill_space: Space::Gray,
            stroke_space: Space::Gray,
            fill_alpha: 1.0,
            stroke_alpha: 1.0,
            blend: BlendMode::SourceOver,
            width: 1.0,
            cap: 0,
            join: 0,
            miter: 10.0,
            dash: Vec::new(),
            phase: 0.0,
            font: None,
            size: 0.0,
            charspace: 0.0,
            wordspace: 0.0,
            scale: 1.0,
            leading: 0.0,
            rise: 0.0,
            mode: 0,
            knockout: None,
            filling: None,
            stroking: None,
            adjust: false,
            soft: None,
            unveiled: None,
        }
    }
}

/// A shading: where it runs, how far it continues and its colours along the way.
struct Shade {
    axial: bool,
    coords: Vec<f64>,
    extend: [bool; 2],
    stops: Vec<(f64, [f64; 3])>,
    frame: Option<[f64; 4]>,
    background: Option<[f64; 3]>,
}

#[derive(Clone)]
enum Filling {
    /// A shading and the map from its space to output pixels.
    Shade(Rc<Shade>, Matrix),
    /// A coloured tiling pattern and the map from pattern space to output pixels.
    Tile(Rc<Stream>, Matrix),
}

fn shading(document: &Document, reference: &Value, resources: &Dict) -> Outcome<Shade> {
    let Value::Dict(attrs) = document.resolve(reference)? else {
        return bad("PDF-Verlauf fehlt.");
    };
    let get = |key: &str| document.resolve(attrs.get(key).unwrap_or(&Value::Null));
    let kind = attrs
        .get("ShadingType")
        .and_then(Value::number)
        .unwrap_or(0.0) as i64;
    let coords = values(&get("Coords")?, Some(if kind == 2 { 4 } else { 6 }))?;
    let space = Space::parse(
        document,
        attrs.get("ColorSpace").unwrap_or(&Value::Null),
        resources,
        0,
    )?;
    let domain = match get("Domain")? {
        Value::Null => vec![0.0, 1.0],
        value => values(&value, Some(2))?,
    };
    if domain[0] >= domain[1] {
        return bad("Ungültiger PDF-Verlaufsbereich.");
    }
    let extend = match get("Extend")? {
        Value::Null => [false, false],
        Value::Array(pair) => match pair.as_slice() {
            [Value::Bool(first), Value::Bool(second)] => [*first, *second],
            _ => return bad("Ungültige PDF-Verlaufsfortsetzung."),
        },
        _ => return bad("Ungültige PDF-Verlaufsfortsetzung."),
    };
    match kind {
        2 if coords[0] == coords[2] && coords[1] == coords[3] => {
            return bad("PDF-Verlauf hat keine Achse.");
        }
        2 => {}
        3 => {
            if coords[2].min(coords[5]) < 0.0 || coords[..3] == coords[3..] {
                return bad("Ungültige PDF-Verlaufskreise.");
            }
            let nested = (coords[3] - coords[0]).powi(2) + (coords[4] - coords[1]).powi(2)
                <= (coords[5] - coords[2]).powi(2);
            if !nested && !(extend[0] && extend[1]) {
                return unsupported(
                    "Nicht eingeschlossener radialer PDF-Verlauf ohne Fortsetzung.",
                );
            }
        }
        other => return unsupported(format!("PDF-Verlaufstyp noch nicht unterstützt: {other}")),
    }
    // Sample the colour function and include stitching boundaries so plateaus
    // and discontinuities keep their positions in the gradient table.
    let mut places: Vec<f64> = (0..256).map(|i| f64::from(i) / 255.0).collect();
    let spec = get("Function")?;
    if let Some(spec) = spec
        .dict()
        .filter(|spec| spec.get("FunctionType").and_then(Value::number) == Some(3.0))
    {
        let bounds = match spec.get("Bounds") {
            Some(bounds) => values(&document.resolve(bounds)?, None)?,
            None => Vec::new(),
        };
        for bound in bounds {
            let t = (bound - domain[0]) / (domain[1] - domain[0]);
            if t > 0.0 && t < 1.0 {
                places.extend([(t - 1e-7).max(0.0), t]);
            }
        }
    }
    places.sort_by(f64::total_cmp);
    places.dedup();
    let function_value = attrs.get("Function").cloned().unwrap_or(Value::Null);
    let mut stops = Vec::with_capacity(places.len());
    for t in places {
        let colour = function(
            document,
            &function_value,
            &[domain[0] + t * (domain[1] - domain[0])],
            0,
        )?;
        stops.push((t, space.rgb(document, &colour)?));
    }
    // The rasteriser walks every stop for every pixel. Stops that lie on the straight line between their
    // neighbours, within half a colour level, say nothing new and are left out.
    let mut kept: Vec<(f64, [f64; 3])> = Vec::with_capacity(8);
    let mut from = 0;
    while from < stops.len() {
        kept.push(stops[from]);
        let mut to = from + 1;
        while to + 1 < stops.len() {
            let (start, end) = (stops[from], stops[to + 1]);
            let straight = stops[from + 1..=to].iter().all(|(t, colour)| {
                let share = if end.0 > start.0 {
                    (t - start.0) / (end.0 - start.0)
                } else {
                    0.0
                };
                (0..3).all(|c| {
                    (start.1[c] + share * (end.1[c] - start.1[c]) - colour[c]).abs() <= 0.5 / 255.0
                })
            });
            if !straight {
                break;
            }
            to += 1;
        }
        from = to;
        if from + 1 == stops.len() {
            kept.push(stops[from]);
            break;
        }
    }
    let stops = kept;
    let frame = match attrs.get("BBox") {
        Some(frame) => {
            let c = values(&document.resolve(frame)?, Some(4))?;
            if c[2] <= c[0] || c[3] <= c[1] {
                return bad("Leeres PDF-Rechteck.");
            }
            Some([c[0], c[1], c[2], c[3]])
        }
        None => None,
    };
    let background = match attrs.get("Background") {
        Some(colour) => Some(space.rgb(document, &values(&document.resolve(colour)?, None)?)?),
        None => None,
    };
    Ok(Shade {
        axial: kind == 2,
        coords,
        extend,
        stops,
        frame,
        background,
    })
}

fn rect_path(x0: f64, y0: f64, x1: f64, y1: f64) -> Option<tiny_skia::Path> {
    let mut path = PathBuilder::new();
    path.move_to(x0 as f32, y0 as f32);
    path.line_to(x1 as f32, y0 as f32);
    path.line_to(x1 as f32, y1 as f32);
    path.line_to(x0 as f32, y1 as f32);
    path.close();
    path.finish()
}

impl Shade {
    /// The gradient as a shader in shading space, moved by `local`.
    fn shader(&self, alpha: f64, local: Matrix) -> Outcome<Shader<'static>> {
        let colour = |rgb: &[f64; 3]| {
            tiny_skia::Color::from_rgba(
                rgb[0] as f32,
                rgb[1] as f32,
                rgb[2] as f32,
                alpha.clamp(0.0, 1.0) as f32,
            )
            .unwrap_or(tiny_skia::Color::BLACK)
        };
        let point = |x: f64, y: f64| tiny_skia::Point::from_xy(x as f32, y as f32);
        let c = &self.coords;
        let made = if self.axial {
            let stops = self
                .stops
                .iter()
                .map(|(t, rgb)| tiny_skia::GradientStop::new(*t as f32, colour(rgb)))
                .collect();
            tiny_skia::LinearGradient::new(
                point(c[0], c[1]),
                point(c[2], c[3]),
                stops,
                tiny_skia::SpreadMode::Pad,
                transform(local),
            )
        } else {
            // Two circles span a cone. Its apex, where the radius reaches zero, is the focal point, the larger
            // circle is the end, and each colour sits at its radius relative to the larger one.
            let (mut r0, r1) = (c[2], c[5]);
            if r0 == r1 {
                // ponytail: equal radii (a cylinder) have no apex; a 0.1 % smaller start circle moves it far
                // away and keeps the radius error below a thousandth. Exact cylinders need a per-pixel shader.
                r0 *= 0.999;
            }
            let largest = r0.max(r1);
            if largest <= 0.0 {
                return bad("Ungültige PDF-Verlaufskreise.");
            }
            let apex = -r0 / (r1 - r0);
            let mut placed: Vec<(f64, [f64; 3])> = self
                .stops
                .iter()
                .map(|(t, rgb)| ((r0 + t * (r1 - r0)) / largest, *rgb))
                .collect();
            if r1 < r0 {
                placed.reverse();
            }
            let stops = placed
                .iter()
                .map(|(t, rgb)| tiny_skia::GradientStop::new(*t as f32, colour(rgb)))
                .collect();
            let end = if r1 >= r0 { (c[3], c[4]) } else { (c[0], c[1]) };
            tiny_skia::RadialGradient::new(
                point(c[0] + apex * (c[3] - c[0]), c[1] + apex * (c[4] - c[1])),
                0.0,
                point(end.0, end.1),
                largest as f32,
                stops,
                tiny_skia::SpreadMode::Pad,
                transform(local),
            )
        };
        made.ok_or(Error::Pdf("Ungültige PDF-Verlaufsachse.".into()))
    }

    /// Narrows a mask to where the shading shows: between its ends unless it continues, and inside its box.
    fn limit(&self, mask: &mut Mask, space: Matrix) {
        const FAR: f64 = 1e4;
        let c = &self.coords;
        let matrix = transform(space);
        if self.axial {
            let (dx, dy) = (c[2] - c[0], c[3] - c[1]);
            let (from, to) = (
                if self.extend[0] { -FAR } else { 0.0 },
                if self.extend[1] { FAR } else { 1.0 },
            );
            let at = |t: f64, s: f64| {
                (
                    (c[0] + t * dx - s * dy) as f32,
                    (c[1] + t * dy + s * dx) as f32,
                )
            };
            let mut band = PathBuilder::new();
            for (index, (t, s)) in [(from, -FAR), (to, -FAR), (to, FAR), (from, FAR)]
                .into_iter()
                .enumerate()
            {
                let (x, y) = at(t, s);
                if index == 0 {
                    band.move_to(x, y)
                } else {
                    band.line_to(x, y)
                }
            }
            band.close();
            if let Some(band) = band.finish() {
                mask.intersect_path(&band, FillRule::Winding, true, matrix);
            }
        } else {
            let circle = |x: f64, y: f64, r: f64| {
                let mut path = PathBuilder::new();
                path.push_circle(x as f32, y as f32, r.max(1e-6) as f32);
                path
            };
            // The smaller circle may be left out, the larger one may bound the shading.
            let (small, large, keep_inside, keep_outside) = if c[5] >= c[2] {
                (
                    (c[0], c[1], c[2]),
                    (c[3], c[4], c[5]),
                    self.extend[0],
                    self.extend[1],
                )
            } else {
                (
                    (c[3], c[4], c[5]),
                    (c[0], c[1], c[2]),
                    self.extend[1],
                    self.extend[0],
                )
            };
            if !keep_outside && let Some(path) = circle(large.0, large.1, large.2).finish() {
                mask.intersect_path(&path, FillRule::Winding, true, matrix);
            }
            if !keep_inside && small.2 > 0.0 {
                let mut path = circle(small.0, small.1, small.2);
                let reach = (FAR * large.2.max(1.0)) as f32;
                if let Some(everything) = tiny_skia::Rect::from_ltrb(
                    small.0 as f32 - reach,
                    small.1 as f32 - reach,
                    small.0 as f32 + reach,
                    small.1 as f32 + reach,
                ) {
                    path.push_rect(everything);
                }
                if let Some(path) = path.finish() {
                    mask.intersect_path(&path, FillRule::EvenOdd, true, matrix);
                }
            }
        }
        if let Some(frame) = self.frame
            && let Some(path) = rect_path(frame[0], frame[1], frame[2], frame[3])
        {
            mask.intersect_path(&path, FillRule::Winding, true, matrix);
        }
    }
}

/// Collects a glyph outline, given in font units, as a path.
struct Outline(PathBuilder);

impl ttf_parser::OutlineBuilder for Outline {
    fn move_to(&mut self, x: f32, y: f32) {
        self.0.move_to(x, y);
    }
    fn line_to(&mut self, x: f32, y: f32) {
        self.0.line_to(x, y);
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        self.0.quad_to(x1, y1, x, y);
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        self.0.cubic_to(x1, y1, x2, y2, x, y);
    }
    fn close(&mut self) {
        self.0.close();
    }
}

struct Renderer<'d> {
    document: &'d Document,
    page: Page<'d>,
    /// From PDF units to output pixels.
    base: Matrix,
    operations: usize,
    image_pixels: usize,
    layer_pixels: std::cell::Cell<usize>,
    tiles: HashMap<(usize, u32, u32), Rc<Pixmap>>,
    /// Above zero while a soft mask's group is being drawn.
    masking: usize,
}

const BLENDS: &[(&str, BlendMode)] = &[
    ("Normal", BlendMode::SourceOver),
    ("Compatible", BlendMode::SourceOver),
    ("Multiply", BlendMode::Multiply),
    ("Screen", BlendMode::Screen),
    ("Overlay", BlendMode::Overlay),
    ("Darken", BlendMode::Darken),
    ("Lighten", BlendMode::Lighten),
    ("ColorDodge", BlendMode::ColorDodge),
    ("ColorBurn", BlendMode::ColorBurn),
    ("HardLight", BlendMode::HardLight),
    ("SoftLight", BlendMode::SoftLight),
    ("Difference", BlendMode::Difference),
    ("Exclusion", BlendMode::Exclusion),
];

impl Renderer<'_> {
    fn paint<'a>(&self, colour: [f64; 3], alpha: f64, blend: BlendMode) -> Paint<'a> {
        let colour = tiny_skia::Color::from_rgba(
            colour[0] as f32,
            colour[1] as f32,
            colour[2] as f32,
            alpha.clamp(0.0, 1.0) as f32,
        )
        .unwrap_or(tiny_skia::Color::BLACK);
        Paint {
            shader: Shader::SolidColor(colour),
            blend_mode: blend,
            anti_alias: true,
            force_hq_pipeline: false,
            colorspace: tiny_skia::ColorSpace::Linear,
        }
    }

    /// In a knockout group an opaque object already replaces what lies under it; only a transparent one needs the group's backdrop.
    fn replacing(state: &State, alpha: f64) -> bool {
        state.knockout.is_some() && (alpha < 1.0 || state.blend != BlendMode::SourceOver)
    }

    /// Puts an object, drawn alone at full opacity on `object`, into a knockout group: it is composited with
    /// the group's initial backdrop, and that result replaces everything drawn so far inside the object's shape.
    fn replace(
        &self,
        target: &mut Pixmap,
        state: &State,
        object: Pixmap,
        alpha: f64,
    ) -> Outcome<()> {
        let plain = |blend_mode| tiny_skia::PixmapPaint {
            opacity: 1.0,
            blend_mode,
            quality: tiny_skia::FilterQuality::Nearest,
        };
        let mut result = match state.knockout.as_deref() {
            Some(Some(backdrop)) => {
                self.count(target)?;
                backdrop.clone()
            }
            _ => self.layer(target)?,
        };
        let over = tiny_skia::PixmapPaint {
            opacity: alpha as f32,
            ..plain(state.blend)
        };
        result.draw_pixmap(0, 0, object.as_ref(), &over, Transform::identity(), None);
        result.draw_pixmap(
            0,
            0,
            object.as_ref(),
            &plain(BlendMode::DestinationIn),
            Transform::identity(),
            None,
        );
        target.draw_pixmap(
            0,
            0,
            object.as_ref(),
            &plain(BlendMode::DestinationOut),
            Transform::identity(),
            None,
        );
        target.draw_pixmap(
            0,
            0,
            result.as_ref(),
            &plain(BlendMode::Plus),
            Transform::identity(),
            None,
        );
        Ok(())
    }

    /// The current clip as a mask of its own, to be narrowed further.
    fn mask(&self, target: &Pixmap, state: &State) -> Outcome<Mask> {
        if let Some(clip) = &state.clip {
            return Ok((**clip).clone());
        }
        let too_large = || Error::Pdf("PDF-Vorschaubild zu groß oder ungültig.".into());
        let mut mask = Mask::new(target.width(), target.height()).ok_or_else(too_large)?;
        if let Some(all) = rect_path(
            0.0,
            0.0,
            f64::from(target.width()),
            f64::from(target.height()),
        ) {
            mask.fill_path(&all, FillRule::Winding, false, Transform::identity());
        }
        Ok(mask)
    }

    /// Paints a shading: over a path of the current space, or over everything the clip leaves.
    fn shade(
        &self,
        target: &mut Pixmap,
        state: &State,
        shade: &Shade,
        space: Matrix,
        object: Option<(&tiny_skia::Path, FillRule)>,
    ) -> Outcome<()> {
        let mut mask = self.mask(target, state)?;
        let device = state.ctm.then(self.base);
        if let (Some(background), Some((path, rule))) = (shade.background, object) {
            target.fill_path(
                path,
                &self.paint(background, state.fill_alpha, state.blend),
                rule,
                transform(device),
                Some(&mask),
            );
        }
        shade.limit(&mut mask, space);
        match object {
            Some((path, rule)) => {
                let paint = Paint {
                    shader: shade.shader(state.fill_alpha, space.then(device.inverted()))?,
                    blend_mode: state.blend,
                    anti_alias: true,
                    force_hq_pipeline: false,
                    colorspace: tiny_skia::ColorSpace::Linear,
                };
                target.fill_path(path, &paint, rule, transform(device), Some(&mask));
            }
            None => {
                let paint = Paint {
                    shader: shade.shader(state.fill_alpha, space)?,
                    blend_mode: state.blend,
                    anti_alias: true,
                    force_hq_pipeline: false,
                    colorspace: tiny_skia::ColorSpace::Linear,
                };
                if let Some(all) = rect_path(
                    0.0,
                    0.0,
                    f64::from(target.width()),
                    f64::from(target.height()),
                ) {
                    target.fill_path(
                        &all,
                        &paint,
                        FillRule::Winding,
                        Transform::identity(),
                        Some(&mask),
                    );
                }
            }
        }
        Ok(())
    }

    /// One cell of a coloured tiling pattern, drawn once at the output resolution, and the map from its pixels to output pixels.
    fn tile(&mut self, pattern: &Rc<Stream>, space: Matrix) -> Outcome<(Rc<Pixmap>, Matrix)> {
        let document = self.document;
        let get = |key: &str| document.resolve(pattern.attrs.get(key).unwrap_or(&Value::Null));
        let matrix = match get("Matrix")? {
            Value::Null => Matrix::IDENTITY,
            value => Matrix::new(&numbers(
                value
                    .array()
                    .ok_or(Error::Pdf("Ungültige PDF-Grafikoperanden.".into()))?,
                Some(6),
            )?),
        };
        let whole = matrix.then(space);
        let frame = rectangle(&get("BBox")?)?;
        let steps = numbers(&[get("XStep")?, get("YStep")?], Some(2))?;
        let (xstep, ystep) = (steps[0].abs(), steps[1].abs());
        if xstep == 0.0 || ystep == 0.0 {
            return bad("Ungültiges PDF-Kachelmuster.");
        }
        let (w, h) = (
            (xstep * whole.m11.hypot(whole.m12)).ceil(),
            (ystep * whole.m21.hypot(whole.m22)).ceil(),
        );
        if !(1.0..=4096.0).contains(&w) || !(1.0..=4096.0).contains(&h) {
            return unsupported("PDF-Kachelmuster in dieser Größe noch nicht unterstützt.");
        }
        let placed = Matrix::new(&[xstep / w, 0.0, 0.0, ystep / h, frame.x, frame.y]).then(whole);
        let key = (Rc::as_ptr(pattern) as usize, w as u32, h as u32);
        if let Some(cell) = self.tiles.get(&key) {
            return Ok((cell.clone(), placed));
        }
        if self.tiles.len() >= 64 {
            return bad("PDF-Transparenzbudget überschritten.");
        }
        let mut cell = Pixmap::new(w as u32, h as u32).ok_or(Error::Pdf(
            "PDF-Transparenzfläche konnte nicht angelegt werden.".into(),
        ))?;
        self.count(&cell)?;
        let own = match document.resolve(pattern.attrs.get("Resources").unwrap_or(&Value::Null))? {
            Value::Dict(own) => own,
            _ => Rc::new(Dict::new()),
        };
        let data = document.decode(pattern)?;
        let outer = std::mem::replace(
            &mut self.base,
            Matrix::new(&[
                w / xstep,
                0.0,
                0.0,
                h / ystep,
                -frame.x * w / xstep,
                -frame.y * h / ystep,
            ]),
        );
        let mut inner = State::start();
        let framed = match rect_path(frame.x, frame.y, frame.x + frame.w, frame.y + frame.h) {
            Some(path) => self.clipped(&cell, &inner, &path, FillRule::Winding),
            None => Ok(None),
        };
        let result = framed.and_then(|clip| {
            inner.clip = clip;
            self.interpret(
                &mut cell,
                &data,
                &own,
                &mut vec![Rc::as_ptr(pattern) as usize],
                1,
                inner,
            )
        });
        self.base = outer;
        result?;
        let cell = Rc::new(cell);
        self.tiles.insert(key, cell.clone());
        Ok((cell, placed))
    }

    fn fill(
        &mut self,
        target: &mut Pixmap,
        path: &tiny_skia::Path,
        rule: FillRule,
        state: &State,
    ) -> Outcome<()> {
        if self.page.hidden > 0 {
            return Ok(());
        }
        let matrix = transform(state.ctm.then(self.base));
        match state
            .filling
            .clone()
            .filter(|_| matches!(state.fill_space, Space::Pattern))
        {
            Some(Filling::Shade(shade, space)) => {
                return self.shade(target, state, &shade, space, Some((path, rule)));
            }
            Some(Filling::Tile(pattern, space)) => {
                let (cell, placed) = self.tile(&pattern, space)?;
                let local = placed.then(state.ctm.then(self.base).inverted());
                let shader = tiny_skia::Pattern::new(
                    cell.as_ref().as_ref(),
                    tiny_skia::SpreadMode::Repeat,
                    tiny_skia::FilterQuality::Bilinear,
                    state.fill_alpha as f32,
                    transform(local),
                );
                let paint = Paint {
                    shader,
                    blend_mode: state.blend,
                    anti_alias: true,
                    force_hq_pipeline: false,
                    colorspace: tiny_skia::ColorSpace::Linear,
                };
                target.fill_path(path, &paint, rule, matrix, state.clip.as_deref());
                return Ok(());
            }
            None => {}
        }
        if Self::replacing(state, state.fill_alpha) {
            let mut object = self.layer(target)?;
            object.fill_path(
                path,
                &self.paint(state.fill, 1.0, BlendMode::SourceOver),
                rule,
                matrix,
                state.clip.as_deref(),
            );
            return self.replace(target, state, object, state.fill_alpha);
        }
        target.fill_path(
            path,
            &self.paint(state.fill, state.fill_alpha, state.blend),
            rule,
            matrix,
            state.clip.as_deref(),
        );
        Ok(())
    }

    /// Fills and strokes a path as the operator asks. With `cover`, the stroke replaces what the fill drew beneath it.
    fn draw_path(
        &mut self,
        target: &mut Pixmap,
        path: &tiny_skia::Path,
        rule: FillRule,
        op: &str,
        state: &State,
        cover: bool,
    ) -> Outcome<()> {
        let mut stroking = state.clone();
        if cover {
            stroking.blend = BlendMode::Source;
        }
        let stroking = &stroking;
        let pattern = |space: &Space| matches!(space, Space::Pattern);
        if matches!(op, "f" | "F" | "f*" | "B" | "B*" | "b" | "b*") {
            self.fill(target, path, rule, state)?;
        }
        if matches!(op, "S" | "s" | "B" | "B*" | "b" | "b*") {
            if pattern(&state.stroke_space) {
                // A patterned line is its outline filled with the pattern.
                let scale = tiny_skia::PathStroker::compute_resolution_scale(&transform(
                    state.ctm.then(self.base),
                ));
                let style = line_style(state);
                let dashed = match &style.dash {
                    Some(dash) => path.dash(dash, scale),
                    None => Some(path.clone()),
                };
                if let Some(outline) = dashed.and_then(|dashed| dashed.stroke(&style, scale)) {
                    let mut filled = stroking.clone();
                    filled.filling = state.stroking.clone();
                    filled.fill_space = Space::Pattern;
                    filled.fill_alpha = state.stroke_alpha;
                    self.fill(target, &outline, FillRule::Winding, &filled)?;
                }
            } else {
                self.stroke(target, path, stroking)?;
            }
        }
        Ok(())
    }

    fn stroke(&self, target: &mut Pixmap, path: &tiny_skia::Path, state: &State) -> Outcome<()> {
        if self.page.hidden > 0 {
            return Ok(());
        }
        let stroke = line_style(state);
        let matrix = transform(state.ctm.then(self.base));
        if Self::replacing(state, state.stroke_alpha) {
            let mut object = self.layer(target)?;
            object.stroke_path(
                path,
                &Paint {
                    anti_alias: !state.adjust,
                    ..self.paint(state.stroke, 1.0, BlendMode::SourceOver)
                },
                &stroke,
                matrix,
                state.clip.as_deref(),
            );
            return self.replace(target, state, object, state.stroke_alpha);
        }
        target.stroke_path(
            path,
            &Paint {
                anti_alias: !state.adjust,
                ..self.paint(state.stroke, state.stroke_alpha, state.blend)
            },
            &stroke,
            matrix,
            state.clip.as_deref(),
        );
        Ok(())
    }

    /// The clip narrowed to a path, which is given in user space.
    fn clipped(
        &self,
        target: &Pixmap,
        state: &State,
        path: &tiny_skia::Path,
        rule: FillRule,
    ) -> Outcome<Option<Rc<Mask>>> {
        MASKS.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let matrix = transform(state.ctm.then(self.base));
        let mask = match &state.clip {
            Some(clip) => {
                let mut mask = (**clip).clone();
                mask.intersect_path(path, rule, true, matrix);
                mask
            }
            None => {
                let mut mask = Mask::new(target.width(), target.height())
                    .ok_or(Error::Pdf("PDF-Vorschaubild zu groß oder ungültig.".into()))?;
                mask.fill_path(path, rule, true, matrix);
                mask
            }
        };
        Ok(Some(Rc::new(mask)))
    }

    /// Narrows the clip to a path, or to nothing. Under a soft mask the clip without the mask is narrowed alongside.
    fn narrow(
        &self,
        target: &Pixmap,
        state: &mut State,
        path: Option<&tiny_skia::Path>,
        rule: FillRule,
    ) -> Outcome<()> {
        let narrowed = |clip: &Option<Rc<Mask>>| -> Outcome<Option<Rc<Mask>>> {
            match path {
                Some(path) => self.clipped(
                    target,
                    &State {
                        clip: clip.clone(),
                        ..state.clone()
                    },
                    path,
                    rule,
                ),
                None => Ok(Some(Rc::new(
                    Mask::new(target.width(), target.height())
                        .ok_or(Error::Pdf("PDF-Vorschaubild zu groß oder ungültig.".into()))?,
                ))),
            }
        };
        let effective = narrowed(&state.clip)?;
        let pure = match &state.unveiled {
            Some(pure) => Some(narrowed(pure)?),
            None => None,
        };
        (state.clip, state.unveiled) = (effective, pure);
        Ok(())
    }

    /// A soft mask as coverage: the alpha or the luminance of its group, drawn where the graphics state stood.
    fn soft_mask(
        &mut self,
        target: &Pixmap,
        attrs: &Dict,
        state: &State,
        resources: &Rc<Dict>,
    ) -> Outcome<Mask> {
        let document = self.document;
        let form = match document.resolve(attrs.get("G").unwrap_or(&Value::Null))? {
            Value::Stream(form)
                if form.attrs.get("Subtype").and_then(Value::name) == Some("Form") =>
            {
                form
            }
            _ => return bad("PDF-Weichmaskengruppe fehlt."),
        };
        let luminous = match attrs.get("S").and_then(Value::name) {
            Some("Alpha") => false,
            Some("Luminosity") => true,
            _ => return bad("Ungültige PDF-Weichmaske."),
        };
        let mut surface = self.layer(target)?;
        if luminous {
            let group = document.resolve(form.attrs.get("Group").unwrap_or(&Value::Null))?;
            let space = Space::parse(
                document,
                group
                    .dict()
                    .and_then(|group| group.get("CS"))
                    .unwrap_or(&Value::Name("DeviceRGB".into())),
                resources,
                0,
            )?;
            let backdrop = match attrs.get("BC") {
                Some(colour) => values(&document.resolve(colour)?, Some(space.components()))?,
                None => vec![0.0; space.components()],
            };
            let colour = space.rgb(document, &backdrop)?;
            surface.fill(
                tiny_skia::Color::from_rgba(
                    colour[0] as f32,
                    colour[1] as f32,
                    colour[2] as f32,
                    1.0,
                )
                .unwrap_or(tiny_skia::Color::BLACK),
            );
        }
        let mut inner = state.clone();
        (inner.fill_alpha, inner.stroke_alpha, inner.blend) = (1.0, 1.0, BlendMode::SourceOver);
        (inner.clip, inner.soft, inner.unveiled, inner.knockout) = (None, None, None, None);
        self.masking += 1;
        let drawn = self.form(&mut surface, &form, resources, &mut Vec::new(), 0, &inner);
        self.masking -= 1;
        drawn?;
        let mut cover: Vec<u8> = surface
            .data()
            .as_chunks::<4>()
            .0
            .iter()
            .map(|p| {
                if luminous {
                    ((30 * u32::from(p[0]) + 59 * u32::from(p[1]) + 11 * u32::from(p[2]) + 50)
                        / 100) as u8
                } else {
                    p[3]
                }
            })
            .collect();
        let transfer =
            document.resolve(attrs.get("TR").unwrap_or(&Value::Name("Identity".into())))?;
        if transfer.name() != Some("Identity") {
            let mut table = [0u8; 256];
            for (level, slot) in table.iter_mut().enumerate() {
                let mapped = function(document, &transfer, &[level as f64 / 255.0], 0)?
                    .first()
                    .copied()
                    .unwrap_or(0.0);
                *slot = (mapped.clamp(0.0, 1.0) * 255.0).round() as u8;
            }
            for value in &mut cover {
                *value = table[*value as usize];
            }
        }
        tiny_skia::IntSize::from_wh(surface.width(), surface.height())
            .and_then(|size| Mask::from_vec(cover, size))
            .ok_or(Error::Pdf(
                "PDF-Transparenzfläche konnte nicht angelegt werden.".into(),
            ))
    }

    /// Counts one more surface of the output's size against the transparency budget.
    fn count(&self, target: &Pixmap) -> Outcome<()> {
        LAYERS.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        self.layer_pixels
            .set(self.layer_pixels.get() + (target.width() * target.height()) as usize);
        if self.layer_pixels.get() > 160_000_000 {
            return bad("PDF-Transparenzbudget überschritten.");
        }
        Ok(())
    }

    fn layer(&self, target: &Pixmap) -> Outcome<Pixmap> {
        self.count(target)?;
        Pixmap::new(target.width(), target.height()).ok_or(Error::Pdf(
            "PDF-Transparenzfläche konnte nicht angelegt werden.".into(),
        ))
    }

    #[allow(clippy::too_many_arguments)]
    fn show(
        &mut self,
        target: &mut Pixmap,
        data: &[u8],
        state: &State,
        matrix: &mut Matrix,
        in_text: bool,
        resources: &Rc<Dict>,
        forms: &mut Vec<usize>,
        depth: usize,
    ) -> Outcome<()> {
        let Some(font) = state.font.clone().filter(|_| in_text && state.size > 0.0) else {
            return bad("PDF-Text ohne Schrift oder Textobjekt.");
        };
        for glyph in font.glyphs(data)? {
            let advance = (glyph.width / 1000.0 * state.size
                + state.charspace
                + if glyph.cid == 32 && !font.composite {
                    state.wordspace
                } else {
                    0.0
                })
                * state.scale;
            let mut outline = Outline(PathBuilder::new());
            if let (Some((space, _, own)), true) = (&font.drawn, state.mode != 3) {
                // A Type 3 glyph is a piece of page content, drawn in the font's glyph space.
                if let Some(procedure) = font.procedure(self.document, glyph.cid)? {
                    let mut inner = state.clone();
                    let sized = [
                        state.size * state.scale,
                        0.0,
                        0.0,
                        state.size,
                        0.0,
                        state.rise,
                    ];
                    inner.ctm = space
                        .then(Matrix::new(&sized))
                        .then(*matrix)
                        .then(state.ctm);
                    let content = self.document.decode(&procedure)?;
                    let own = own.as_ref().unwrap_or(resources);
                    self.interpret(target, &content, own, forms, depth + 1, inner)?;
                }
            } else if state.mode != 3
                && let Some(units) = font.program.outline(glyph.gid, &mut outline)
                && let Some(path) = outline.0.finish()
            {
                // Font units, y up, to user space; the stroke width then counts in user space as for any path.
                let placed = Matrix::new(&[
                    state.size * state.scale / units,
                    0.0,
                    0.0,
                    state.size / units,
                    0.0,
                    state.rise,
                ])
                .then(*matrix);
                if let Some(path) = path.transform(transform(placed)) {
                    if state.mode == 0 || state.mode == 2 {
                        self.fill(target, &path, FillRule::Winding, state)?;
                    }
                    if state.mode == 1 || state.mode == 2 {
                        self.stroke(target, &path, state)?;
                    }
                }
            }
            *matrix = Matrix::new(&[1.0, 0.0, 0.0, 1.0, advance, 0.0]).then(*matrix);
        }
        Ok(())
    }

    fn image(
        &mut self,
        target: &mut Pixmap,
        stream: &Stream,
        resources: &Dict,
        state: &State,
    ) -> Outcome<()> {
        let decoded = picture(
            self.document,
            stream,
            resources,
            state.fill,
            0,
            &mut self.image_pixels,
        )?;
        if self.page.hidden > 0 {
            return Ok(());
        }
        let mut data = decoded.rgba;
        for pixel in data.as_chunks_mut::<4>().0 {
            let alpha = u16::from(pixel[3]);
            for channel in &mut pixel[..3] {
                *channel = ((u16::from(*channel) * alpha + 127) / 255) as u8;
            }
        }
        let Some(source) = tiny_skia::IntSize::from_wh(decoded.width, decoded.height)
            .and_then(|size| Pixmap::from_vec(data, size))
        else {
            return bad("PDF-Bild konnte nicht dekodiert werden.");
        };
        let placed = Matrix::new(&[
            1.0 / f64::from(decoded.width),
            0.0,
            0.0,
            -1.0 / f64::from(decoded.height),
            0.0,
            1.0,
        ])
        .then(state.ctm)
        .then(self.base);
        let paint = tiny_skia::PixmapPaint {
            opacity: state.fill_alpha as f32,
            blend_mode: state.blend,
            quality: tiny_skia::FilterQuality::Bilinear,
        };
        if Self::replacing(state, state.fill_alpha) {
            let mut object = self.layer(target)?;
            let full = tiny_skia::PixmapPaint {
                opacity: 1.0,
                blend_mode: BlendMode::SourceOver,
                ..paint
            };
            object.draw_pixmap(
                0,
                0,
                source.as_ref(),
                &full,
                transform(placed),
                state.clip.as_deref(),
            );
            return self.replace(target, state, object, state.fill_alpha);
        }
        target.draw_pixmap(
            0,
            0,
            source.as_ref(),
            &paint,
            transform(placed),
            state.clip.as_deref(),
        );
        Ok(())
    }

    fn form(
        &mut self,
        target: &mut Pixmap,
        stream: &Rc<Stream>,
        resources: &Rc<Dict>,
        forms: &mut Vec<usize>,
        depth: usize,
        state: &State,
    ) -> Outcome<()> {
        let identity = Rc::as_ptr(stream) as usize;
        if forms.contains(&identity) {
            return bad("Zyklische PDF-Form.");
        }
        let Some(corners) = self
            .document
            .resolve(stream.attrs.get("BBox").unwrap_or(&Value::Null))?
            .array()
            .cloned()
        else {
            return bad("Ungültiges PDF-Rechteck.");
        };
        let c = numbers(&corners, Some(4))?;
        if c[0] == c[2] || c[1] == c[3] {
            return Ok(()); // a form without area shows nothing
        }
        let group = match self
            .document
            .resolve(stream.attrs.get("Group").unwrap_or(&Value::Null))?
        {
            Value::Null => None,
            Value::Dict(group) if group.get("S").and_then(Value::name) == Some("Transparency") => {
                Some(group)
            }
            _ => return bad("Ungültige PDF-Transparenzgruppe."),
        };
        if let Some(group) = &group {
            let space = self
                .document
                .resolve(group.get("CS").unwrap_or(&Value::Name("DeviceRGB".into())))?;
            match space.name() {
                Some("DeviceRGB") => {}
                // Grey only matters for an isolated group: a non-isolated one blends in its parent's space, and a mask
                // group in grey has the same luminance in colour.
                Some("DeviceGray") => {}
                _ => return unsupported("PDF-Gruppenfarbraum noch nicht unterstützt."),
            }
        }
        let matrix = match stream.attrs.get("Matrix") {
            None => Matrix::IDENTITY,
            Some(value) => match self.document.resolve(value)?.array() {
                Some(list) => Matrix::new(&numbers(list, Some(6))?),
                None => return bad("Ungültige PDF-Grafikoperanden."),
            },
        };
        let own = match stream.attrs.get("Resources") {
            None => resources.clone(),
            Some(value) => match self.document.resolve(value)? {
                Value::Dict(own) => own,
                _ => Rc::new(Dict::new()),
            },
        };
        let mut inner = state.clone();
        inner.ctm = matrix.then(state.ctm);
        let mut frame = PathBuilder::new();
        frame.move_to(c[0] as f32, c[1] as f32);
        frame.line_to(c[2] as f32, c[1] as f32);
        frame.line_to(c[2] as f32, c[3] as f32);
        frame.line_to(c[0] as f32, c[3] as f32);
        frame.close();
        if let Some(frame) = frame.finish() {
            self.narrow(target, &mut inner, Some(&frame), FillRule::Winding)?;
        }
        let data = self.document.decode(stream)?;
        forms.push(identity);
        // A group is composited as one object: drawn on its own surface when the outside applies opacity or a blend mode.
        let knocking = group
            .as_ref()
            .is_some_and(|group| matches!(group.get("K"), Some(Value::Bool(true))));
        let isolated = group
            .as_ref()
            .is_some_and(|group| matches!(group.get("I"), Some(Value::Bool(true))));
        let outside =
            state.fill_alpha != 1.0 || state.blend != BlendMode::SourceOver || state.soft.is_some();
        // A group is one object. It gets its own surface when it is isolated, when the outside applies opacity or a
        // blend mode, or when it is itself an object of a knockout group.
        let apart = group.is_some() && (isolated || outside || state.knockout.is_some());
        if group.is_some() {
            (
                inner.fill_alpha,
                inner.stroke_alpha,
                inner.blend,
                inner.knockout,
            ) = (1.0, 1.0, BlendMode::SourceOver, None);
        }
        if group.is_some() {
            // A soft mask applies to the group as one object, not to each thing inside it.
            inner.soft = None;
            if let Some(pure) = inner.unveiled.take() {
                inner.clip = pure;
            }
        }
        let result = if apart {
            if knocking {
                inner.knockout = Some(Rc::new(None));
            }
            let mut surface = self.layer(target)?;
            let result = self.interpret(&mut surface, &data, &own, forms, depth + 1, inner);
            let grey_group = isolated
                && self.masking == 0
                && group.as_ref().is_some_and(|group| {
                    self.document
                        .resolve(group.get("CS").unwrap_or(&Value::Null))
                        .is_ok_and(|space| space.name() == Some("DeviceGray"))
                });
            if grey_group {
                grey(&mut surface);
            }
            if result.is_ok() && self.page.hidden == 0 {
                if Self::replacing(state, state.fill_alpha) {
                    self.replace(target, state, surface, state.fill_alpha)?;
                } else {
                    let paint = tiny_skia::PixmapPaint {
                        opacity: state.fill_alpha as f32,
                        blend_mode: state.blend,
                        quality: tiny_skia::FilterQuality::Nearest,
                    };
                    target.draw_pixmap(
                        0,
                        0,
                        surface.as_ref(),
                        &paint,
                        Transform::identity(),
                        state.soft.as_deref(),
                    );
                }
            }
            result
        } else {
            if knocking {
                // A group that was not given its own surface starts from what is already on the page.
                self.count(target)?;
                inner.knockout = Some(Rc::new(Some(target.clone())));
            }
            self.interpret(target, &data, &own, forms, depth + 1, inner)
        };
        forms.pop();
        result
    }

    fn graphics_state(
        &mut self,
        target: &Pixmap,
        resources: &Rc<Dict>,
        settings: &Dict,
        state: &mut State,
    ) -> Outcome<()> {
        for (key, value) in settings.iter() {
            let value = self.document.resolve(value)?;
            let number = |value: &Value| numbers(std::slice::from_ref(value), None).map(|n| n[0]);
            match key.as_str() {
                "ca" | "CA" => {
                    let alpha = number(&value)?;
                    if !(0.0..=1.0).contains(&alpha) {
                        return bad("Ungültige PDF-Deckkraft.");
                    }
                    if key == "ca" {
                        state.fill_alpha = alpha
                    } else {
                        state.stroke_alpha = alpha
                    }
                }
                "BM" => {
                    let modes = match &value {
                        Value::Array(modes) => (**modes).clone(),
                        other => vec![other.clone()],
                    };
                    let chosen = modes.iter().find_map(|mode| {
                        BLENDS
                            .iter()
                            .find(|known| Some(known.0) == mode.name())
                            .map(|known| known.1)
                    });
                    match chosen {
                        Some(chosen) => state.blend = chosen,
                        None => return unsupported("PDF-Mischmodus noch nicht unterstützt."),
                    }
                }
                "SMask" => {
                    if let Some(pure) = state.unveiled.take() {
                        state.clip = pure;
                    }
                    state.soft = None;
                    match &value {
                        Value::Name(name) if &**name == "None" => {}
                        Value::Dict(mask) => {
                            let veil = Rc::new(self.soft_mask(target, mask, state, resources)?);
                            let covered = match &state.clip {
                                None => (*veil).clone(),
                                Some(clip) => {
                                    let mut covered = (**clip).clone();
                                    for (own, other) in
                                        covered.data_mut().iter_mut().zip(veil.data())
                                    {
                                        *own = ((u16::from(*own) * u16::from(*other) + 127) / 255)
                                            as u8;
                                    }
                                    covered
                                }
                            };
                            state.unveiled = Some(state.clip.take());
                            state.clip = Some(Rc::new(covered));
                            state.soft = Some(veil);
                        }
                        _ => return bad("Ungültige PDF-Weichmaske."),
                    }
                }
                "SA" if matches!(value, Value::Bool(_)) => {
                    state.adjust = matches!(value, Value::Bool(true))
                }
                "AIS" => match value {
                    // Alpha as shape only changes the result inside a knockout group.
                    Value::Bool(true) if state.knockout.is_some() => {
                        return unsupported(
                            "PDF-Alpha als Form in Knockout-Gruppe noch nicht unterstützt.",
                        );
                    }
                    Value::Bool(_) => {}
                    _ => return unsupported("PDF-Grafikzustand noch nicht unterstützt: AIS"),
                },
                "SM" => {
                    if !(0.0..=1.0).contains(&number(&value)?) {
                        return bad("Ungültige PDF-Kurvenglättung.");
                    }
                }
                // The same line settings as the w, J, j and M operators.
                "LW" | "ML" => {
                    let size = number(&value)?;
                    if size < 0.0 || key == "ML" && size < 1.0 {
                        return bad("Ungültige PDF-Linienangabe.");
                    }
                    if key == "LW" {
                        state.width = size
                    } else {
                        state.miter = size
                    }
                }
                "LC" => state.cap = integer(&value, 0, 2)?,
                "LJ" => state.join = integer(&value, 0, 2)?,
                // Overprint only changes separations on a press; on screen without overprint preview it draws as usual.
                "OP" | "op" if matches!(value, Value::Bool(_)) => {}
                "OPM" if matches!(value, Value::Int(0 | 1)) => {}
                "Type" if value.name() == Some("ExtGState") => {}
                "TK" if matches!(value, Value::Bool(true)) => {}
                other => {
                    return unsupported(format!(
                        "PDF-Grafikzustand noch nicht unterstützt: {other}"
                    ));
                }
            }
        }
        Ok(())
    }

    fn interpret(
        &mut self,
        target: &mut Pixmap,
        data: &[u8],
        resources: &Rc<Dict>,
        forms: &mut Vec<usize>,
        depth: usize,
        mut state: State,
    ) -> Outcome<()> {
        if depth > 32 {
            return bad("PDF-Formen zu tief verschachtelt.");
        }
        // Patterns are placed in the space this content stream starts in.
        let default = state.ctm.then(self.base);
        let mut syntax = Syntax::new(data, 0);
        let (mut operands, mut stack): (Vec<Value>, Vec<State>) = (Vec::new(), Vec::new());
        let mut marks: Vec<bool> = Vec::new();
        let (mut path, mut open) = (PathBuilder::new(), false);
        let mut clipping: Option<FillRule> = None;
        let (mut in_text, mut matrix, mut line) = (false, Matrix::IDENTITY, Matrix::IDENTITY);
        loop {
            syntax.skip();
            if syntax.pos == data.len() {
                break;
            }
            let value = syntax.value()?;
            let Value::Operator(operator) = &value else {
                operands.push(value);
                if operands.len() > 100_000 {
                    return bad("Zu viele PDF-Operanden.");
                }
                continue;
            };
            let a = std::mem::take(&mut operands);
            self.operations += 1;
            if self.operations > 1_000_000 {
                return bad("PDF-Grafikbudget überschritten.");
            }
            let op = &**operator;
            match op {
                "q" => {
                    numbers(&a, Some(0))?;
                    stack.push(state.clone());
                    if stack.len() > 64 {
                        return bad("PDF-Grafikstack zu tief.");
                    }
                }
                "Q" => {
                    if open {
                        return unsupported(
                            "PDF-Grafikzustandswechsel innerhalb eines offenen Pfads noch nicht unterstützt.",
                        );
                    }
                    numbers(&a, Some(0))?;
                    let Some(saved) = stack.pop() else {
                        return bad("PDF-Grafikstack ist leer.");
                    };
                    state = saved;
                }
                "cm" => {
                    if open {
                        return unsupported(
                            "PDF-Koordinatenwechsel innerhalb eines offenen Pfads noch nicht unterstützt.",
                        );
                    }
                    state.ctm = Matrix::new(&numbers(&a, Some(6))?).then(state.ctm);
                }
                "m" | "l" => {
                    let p = numbers(&a, Some(2))?;
                    if op == "m" {
                        path.move_to(p[0] as f32, p[1] as f32)
                    } else {
                        path.line_to(p[0] as f32, p[1] as f32)
                    }
                    open = true;
                }
                "c" => {
                    let p = numbers(&a, Some(6))?;
                    path.cubic_to(
                        p[0] as f32,
                        p[1] as f32,
                        p[2] as f32,
                        p[3] as f32,
                        p[4] as f32,
                        p[5] as f32,
                    );
                    open = true;
                }
                "v" => {
                    let p = numbers(&a, Some(4))?;
                    let current = path
                        .last_point()
                        .unwrap_or(tiny_skia::Point::from_xy(0.0, 0.0));
                    path.cubic_to(
                        current.x,
                        current.y,
                        p[0] as f32,
                        p[1] as f32,
                        p[2] as f32,
                        p[3] as f32,
                    );
                    open = true;
                }
                "y" => {
                    let p = numbers(&a, Some(4))?;
                    path.cubic_to(
                        p[0] as f32,
                        p[1] as f32,
                        p[2] as f32,
                        p[3] as f32,
                        p[2] as f32,
                        p[3] as f32,
                    );
                    open = true;
                }
                "h" => {
                    numbers(&a, Some(0))?;
                    path.close();
                }
                "re" => {
                    // Writers use enormous rectangles for 'everything'; they are cut to a size the rasteriser handles.
                    if a.len() != 4 || a.iter().any(|v| !v.number().is_some_and(f64::is_finite)) {
                        return bad("Ungültige PDF-Grafikoperanden.");
                    }
                    let v: Vec<f64> = a.iter().filter_map(Value::number).collect();
                    let cut = |n: f64| n.clamp(-1e7, 1e7) as f32;
                    let (x0, y0, x1, y1) =
                        (cut(v[0]), cut(v[1]), cut(v[0] + v[2]), cut(v[1] + v[3]));
                    path.move_to(x0, y0);
                    path.line_to(x1, y0);
                    path.line_to(x1, y1);
                    path.line_to(x0, y1);
                    path.close();
                    open = true;
                }
                "W" | "W*" => {
                    numbers(&a, Some(0))?;
                    clipping = Some(if op == "W*" {
                        FillRule::EvenOdd
                    } else {
                        FillRule::Winding
                    });
                }
                "n" | "S" | "s" | "f" | "F" | "f*" | "B" | "B*" | "b" | "b*" => {
                    numbers(&a, Some(0))?;
                    if matches!(op, "s" | "b" | "b*") {
                        path.close();
                    }
                    let rule = if op.contains('*') {
                        FillRule::EvenOdd
                    } else {
                        FillRule::Winding
                    };
                    let finished = std::mem::replace(&mut path, PathBuilder::new()).finish();
                    open = false;
                    if let Some(finished) = &finished {
                        let both = matches!(op, "B" | "B*" | "b" | "b*");
                        if both
                            && (state.fill_alpha < 1.0 || state.stroke_alpha < 1.0)
                            && self.page.hidden == 0
                        {
                            // Fill and stroke are one object: where they overlap the stroke covers the fill.
                            let mut object = self.layer(target)?;
                            let mut inner = state.clone();
                            (inner.blend, inner.knockout, inner.soft) =
                                (BlendMode::SourceOver, None, None);
                            if let Some(pure) = inner.unveiled.take() {
                                inner.clip = pure;
                            }
                            self.draw_path(&mut object, finished, rule, op, &inner, true)?;
                            if Self::replacing(&state, 1.0) {
                                self.replace(target, &state, object, 1.0)?;
                            } else {
                                let paint = tiny_skia::PixmapPaint {
                                    opacity: 1.0,
                                    blend_mode: state.blend,
                                    quality: tiny_skia::FilterQuality::Nearest,
                                };
                                target.draw_pixmap(
                                    0,
                                    0,
                                    object.as_ref(),
                                    &paint,
                                    Transform::identity(),
                                    state.soft.as_deref(),
                                );
                            }
                        } else {
                            self.draw_path(target, finished, rule, op, &state, false)?;
                        }
                        if let Some(rule) = clipping {
                            self.narrow(target, &mut state, Some(finished), rule)?;
                        }
                    } else if clipping.is_some() {
                        // Clipping to an empty path leaves nothing visible.
                        self.narrow(target, &mut state, None, FillRule::Winding)?;
                    }
                    clipping = None;
                }
                "w" | "M" => {
                    let size = numbers(&a, Some(1))?[0];
                    if size < 0.0 {
                        return bad("Negative PDF-Linienbreite.");
                    }
                    if op == "w" {
                        state.width = size
                    } else {
                        state.miter = size
                    }
                }
                "J" | "j" => {
                    let style = integer(
                        a.first().filter(|_| a.len() == 1).unwrap_or(&Value::Null),
                        0,
                        2,
                    )?;
                    if op == "J" {
                        state.cap = style
                    } else {
                        state.join = style
                    }
                }
                "d" => {
                    let Some(pattern) = a.first().and_then(Value::array).filter(|_| a.len() == 2)
                    else {
                        return bad("Ungültiges PDF-Strichmuster.");
                    };
                    let dash = numbers(pattern, None)?;
                    state.phase = numbers(&a[1..], None)?[0];
                    if dash.len() > 64
                        || dash.iter().any(|v| *v < 0.0)
                        || !dash.is_empty() && dash.iter().all(|v| *v == 0.0)
                    {
                        return bad("Ungültiges PDF-Strichmuster.");
                    }
                    state.dash = if dash.len() % 2 == 1 {
                        [dash.clone(), dash].concat()
                    } else {
                        dash
                    };
                }
                "g" | "rg" | "k" | "G" | "RG" | "K" => {
                    let space = match op.to_lowercase().as_str() {
                        "g" => Space::Gray,
                        "rg" => Space::Rgb,
                        _ => Space::Cmyk,
                    };
                    let colour = space.rgb(
                        self.document,
                        &numbers(&a, Some(space.components()))
                            .map_err(|_| Error::Pdf("Ungültige PDF-Farbwerte.".into()))?,
                    )?;
                    if op.chars().all(char::is_lowercase) {
                        (state.fill, state.fill_space) = (colour, space);
                    } else {
                        (state.stroke, state.stroke_space) = (colour, space);
                    }
                }
                "cs" | "CS" => {
                    let (Some(Value::Name(name)), 1) = (a.first(), a.len()) else {
                        return bad("Ungültiger PDF-Farbraum.");
                    };
                    let space = match &**name {
                        "Pattern" => Space::Pattern,
                        "DeviceGray" | "DeviceRGB" | "DeviceCMYK" => {
                            Space::parse(self.document, &a[0], resources, 0)?
                        }
                        other => Space::parse(
                            self.document,
                            &self.page.resource(resources, "ColorSpace", other)?,
                            resources,
                            0,
                        )?,
                    };
                    let colour = if matches!(space, Space::Pattern) {
                        [0.0; 3]
                    } else {
                        space.rgb(self.document, &space.initial())?
                    };
                    if op == "cs" {
                        (state.fill, state.fill_space) = (colour, space);
                    } else {
                        (state.stroke, state.stroke_space) = (colour, space);
                    }
                }
                "sc" | "SC" | "scn" | "SCN" => {
                    let lower = op.chars().all(char::is_lowercase);
                    let space = if lower {
                        state.fill_space.clone()
                    } else {
                        state.stroke_space.clone()
                    };
                    if matches!(space, Space::Pattern) {
                        let (Some(Value::Name(name)), 1) = (a.first(), a.len()) else {
                            return bad("Ungültige PDF-Musterfarbe.");
                        };
                        let chosen = Some(
                            match self.page.resource(resources, "Pattern", name)? {
                                Value::Stream(pattern)
                                    if pattern.attrs.get("PatternType").and_then(Value::number)
                                        == Some(1.0) =>
                                {
                                    if pattern.attrs.get("PaintType").and_then(Value::number)
                                        != Some(1.0)
                                        || forms.contains(&(Rc::as_ptr(&pattern) as usize))
                                    {
                                        return unsupported(
                                            "Ungefärbtes PDF-Kachelmuster noch nicht unterstützt.",
                                        );
                                    }
                                    Filling::Tile(pattern, default)
                                }
                                Value::Dict(pattern)
                                    if pattern.get("PatternType").and_then(Value::number)
                                        == Some(2.0) =>
                                {
                                    if pattern.contains_key("ExtGState") {
                                        return unsupported(
                                            "PDF-Verlaufsmuster mit eigenem Grafikzustand noch nicht unterstützt.",
                                        );
                                    }
                                    let matrix = match pattern.get("Matrix") {
                                        None => Matrix::IDENTITY,
                                        Some(value) => Matrix::new(&numbers(
                                            self.document.resolve(value)?.array().ok_or(
                                                Error::Pdf("Ungültige PDF-Grafikoperanden.".into()),
                                            )?,
                                            Some(6),
                                        )?),
                                    };
                                    Filling::Shade(
                                        Rc::new(shading(
                                            self.document,
                                            pattern.get("Shading").unwrap_or(&Value::Null),
                                            resources,
                                        )?),
                                        matrix.then(default),
                                    )
                                }
                                _ => return bad("Ungültiges PDF-Muster."),
                            },
                        );
                        if lower {
                            state.filling = chosen
                        } else {
                            state.stroking = chosen
                        }
                        continue;
                    }
                    let colour = space.rgb(
                        self.document,
                        &numbers(&a, None)
                            .map_err(|_| Error::Pdf("Ungültige PDF-Farbwerte.".into()))?,
                    )?;
                    if lower {
                        state.fill = colour
                    } else {
                        state.stroke = colour
                    }
                }
                "BT" => {
                    numbers(&a, Some(0))?;
                    if in_text {
                        return bad("Verschachteltes PDF-Textobjekt.");
                    }
                    (in_text, matrix, line) = (true, Matrix::IDENTITY, Matrix::IDENTITY);
                }
                "ET" => {
                    numbers(&a, Some(0))?;
                    if !in_text {
                        return bad("PDF-Textende ohne Beginn.");
                    }
                    in_text = false;
                }
                "Tf" => {
                    let (Some(Value::Name(name)), 2) = (a.first(), a.len()) else {
                        return bad("Ungültige PDF-Schriftauswahl.");
                    };
                    state.size = numbers(&a[1..], None)?[0];
                    state.font = Some(self.page.font(resources, name)?);
                }
                "Tc" | "Tw" | "Tz" | "TL" | "Ts" => {
                    let amount = numbers(&a, Some(1))?[0];
                    match op {
                        "Tc" => state.charspace = amount,
                        "Tw" => state.wordspace = amount,
                        "Tz" => state.scale = amount / 100.0,
                        "TL" => state.leading = amount,
                        _ => state.rise = amount,
                    }
                }
                "Tr" => {
                    if a.len() != 1 {
                        return bad("Ungültiger PDF-Textmodus.");
                    }
                    state.mode = integer(&a[0], 0, 7)?;
                    if state.mode >= 4 {
                        return unsupported("PDF-Text-Clipping noch nicht unterstützt.");
                    }
                }
                "Tm" => {
                    matrix = Matrix::new(&numbers(&a, Some(6))?);
                    line = matrix;
                }
                "Td" | "TD" => {
                    let by = numbers(&a, Some(2))?;
                    if op == "TD" {
                        state.leading = -by[1];
                    }
                    line = Matrix::new(&[1.0, 0.0, 0.0, 1.0, by[0], by[1]]).then(line);
                    matrix = line;
                }
                "T*" => {
                    numbers(&a, Some(0))?;
                    line = Matrix::new(&[1.0, 0.0, 0.0, 1.0, 0.0, -state.leading]).then(line);
                    matrix = line;
                }
                "Tj" | "TJ" | "'" | "\"" => {
                    let mut a = a;
                    if op == "'" || op == "\"" {
                        if op == "\"" {
                            if a.len() != 3 {
                                return bad("Ungültiger PDF-Textoperator.");
                            }
                            let spacing = numbers(&a[..2], None)?;
                            (state.wordspace, state.charspace) = (spacing[0], spacing[1]);
                            a.drain(..2);
                        }
                        line = Matrix::new(&[1.0, 0.0, 0.0, 1.0, 0.0, -state.leading]).then(line);
                        matrix = line;
                    }
                    if a.len() != 1 {
                        return bad("Ungültiger PDF-Textoperator.");
                    }
                    let spaced = op == "TJ";
                    let chunks: Vec<Value> = match &a[0] {
                        Value::Array(chunks) if spaced => (**chunks).clone(),
                        _ => a,
                    };
                    for chunk in &chunks {
                        match chunk {
                            Value::Text(text) => self.show(
                                target,
                                text,
                                &state,
                                &mut matrix,
                                in_text,
                                resources,
                                forms,
                                depth,
                            )?,
                            Value::Int(_) | Value::Real(_) if spaced => {
                                let shift = numbers(std::slice::from_ref(chunk), None)?[0];
                                matrix = Matrix::new(&[
                                    1.0,
                                    0.0,
                                    0.0,
                                    1.0,
                                    -shift / 1000.0 * state.size * state.scale,
                                    0.0,
                                ])
                                .then(matrix);
                            }
                            _ => return bad("Ungültiger PDF-Textoperator."),
                        }
                    }
                }
                "Do" => {
                    let (Some(Value::Name(name)), 1) = (a.first(), a.len()) else {
                        return bad("Ungültiges PDF-XObject.");
                    };
                    let Value::Stream(object) = self.page.resource(resources, "XObject", name)?
                    else {
                        return bad("PDF-XObject ist kein Stream.");
                    };
                    if !self.page.visible(object.attrs.get("OC"))? {
                        continue;
                    }
                    match object.attrs.get("Subtype").and_then(Value::name) {
                        Some("Image") => self.image(target, &object, resources, &state)?,
                        Some("Form") => {
                            self.form(target, &object, resources, forms, depth, &state)?
                        }
                        _ => return unsupported("PDF-XObject-Typ noch nicht unterstützt."),
                    }
                }
                "BMC" => marks.push(false),
                "BDC" => {
                    if a.len() != 2 {
                        return bad("Ungültige PDF-Inhaltsmarkierung.");
                    }
                    let properties = match &a[1] {
                        Value::Name(name) => self.page.resource(resources, "Properties", name)?,
                        other => other.clone(),
                    };
                    let Some(properties) = properties.dict().filter(|_| marks.len() < 64) else {
                        return bad("Ungültige PDF-Inhaltsmarkierung.");
                    };
                    let hide = a[0].name() == Some("OC")
                        && !self.page.visible(Some(&Value::Dict(properties.clone())))?;
                    self.page.hidden += usize::from(hide);
                    marks.push(hide);
                }
                "EMC" => {
                    if let Some(hide) = marks.pop() {
                        self.page.hidden -= usize::from(hide);
                    }
                }
                "gs" => {
                    let (Some(Value::Name(name)), 1) = (a.first(), a.len()) else {
                        return bad("Ungültiger PDF-Grafikzustand.");
                    };
                    let Value::Dict(settings) = self.page.resource(resources, "ExtGState", name)?
                    else {
                        return bad("Ungültiger PDF-Grafikzustand.");
                    };
                    self.graphics_state(target, resources, &settings, &mut state)?;
                }
                "sh" => {
                    let (Some(Value::Name(name)), 1) = (a.first(), a.len()) else {
                        return bad("Ungültiger PDF-Verlauf.");
                    };
                    let found = self.page.resource(resources, "Shading", name)?;
                    if self.page.hidden == 0 {
                        let shade = shading(self.document, &found, resources)?;
                        self.shade(target, &state, &shade, state.ctm.then(self.base), None)?;
                    }
                }
                "ID" => {
                    let image = crate::text::inline_image(&mut syntax, &a)?;
                    self.image(target, &image, resources, &state)?;
                }
                // A Type 3 glyph begins with its width; an inline image with its attributes.
                "BX" | "EX" | "MP" | "DP" | "ri" | "i" | "BI" | "d0" | "d1" => {}
                other => {
                    return unsupported(format!(
                        "PDF-Grafikoperator noch nicht unterstützt: {other}"
                    ));
                }
            }
        }
        if !operands.is_empty() || in_text {
            return bad("Unvollständiger PDF-Grafikstream.");
        }
        self.page.hidden -= marks.iter().filter(|hide| **hide).count();
        Ok(())
    }

    fn annotations(&mut self, target: &mut Pixmap, state: &State) -> Outcome<()> {
        let attrs = &self.document.pages[self.index()];
        let list = match attrs.get("Annots") {
            None => return Ok(()),
            Some(value) => self.document.resolve(value)?,
        };
        let Some(list) = list.array().filter(|list| list.len() <= 10000).cloned() else {
            return bad("Ungültige PDF-Anmerkungsliste.");
        };
        for reference in list.iter() {
            let Value::Dict(note) = self.document.resolve(reference)? else {
                return bad("Ungültige PDF-Anmerkung.");
            };
            let flags = note.get("F").and_then(Value::number).unwrap_or(0.0) as i64;
            if flags & (1 | 2 | 32) != 0 || !self.page.visible(note.get("OC"))? {
                continue;
            }
            let area = rectangle(
                &self
                    .document
                    .resolve(note.get("Rect").unwrap_or(&Value::Null))?,
            )?;
            let mut appearance = match self
                .document
                .resolve(note.get("AP").unwrap_or(&Value::Null))?
            {
                Value::Dict(appearance) => self
                    .document
                    .resolve(appearance.get("N").unwrap_or(&Value::Null))?,
                _ => Value::Null,
            };
            if let Value::Dict(states) = &appearance {
                appearance = match note
                    .get("AS")
                    .and_then(Value::name)
                    .and_then(|chosen| states.get(chosen))
                {
                    Some(chosen) => self.document.resolve(chosen)?,
                    None => Value::Null,
                };
            }
            if let Value::Stream(look) = &appearance {
                let matrix = match look.attrs.get("Matrix") {
                    None => Matrix::IDENTITY,
                    Some(value) => Matrix::new(&numbers(
                        self.document
                            .resolve(value)?
                            .array()
                            .ok_or(Error::Pdf("Ungültige PDF-Grafikoperanden.".into()))?,
                        Some(6),
                    )?),
                };
                let frame = matrix.map_rect(rectangle(
                    &self
                        .document
                        .resolve(look.attrs.get("BBox").unwrap_or(&Value::Null))?,
                )?);
                if frame.w <= 0.0 || frame.h <= 0.0 {
                    return bad("Leere PDF-Anmerkungsdarstellung.");
                }
                let fit = Matrix::new(&[
                    area.w / frame.w,
                    0.0,
                    0.0,
                    area.h / frame.h,
                    area.x - frame.x * area.w / frame.w,
                    area.y - frame.y * area.h / frame.h,
                ]);
                let mut inner = state.clone();
                inner.ctm = fit.then(state.ctm);
                let resources = Rc::new(Dict::new());
                self.form(target, look, &resources, &mut Vec::new(), 0, &inner)?;
                continue;
            }
            let kind = note.get("Subtype").and_then(Value::name).unwrap_or("");
            let default: &[f64] = if kind == "Link" {
                &[0.0, 0.0, 0.0]
            } else {
                &[1.0, 1.0, 0.0]
            };
            let components = match note.get("C") {
                None => default.to_vec(),
                Some(value) => numbers(
                    self.document
                        .resolve(value)?
                        .array()
                        .ok_or(Error::Pdf("Ungültige PDF-Farbwerte.".into()))?,
                    None,
                )?,
            };
            let space = match components.len() {
                1 => Space::Gray,
                3 => Space::Rgb,
                4 => Space::Cmyk,
                _ => return unsupported("PDF-Farbraum noch nicht unterstützt: None"),
            };
            let mut inner = state.clone();
            inner.fill = space.rgb(self.document, &components)?;
            inner.stroke = inner.fill;
            let mut frame = PathBuilder::new();
            match kind {
                "Link" => {
                    let border = note
                        .get("Border")
                        .and_then(Value::array)
                        .map(|b| numbers(b, None))
                        .transpose()?
                        .unwrap_or(vec![0.0, 0.0, 1.0]);
                    let style = self
                        .document
                        .resolve(note.get("BS").unwrap_or(&Value::Null))?;
                    let width = style
                        .dict()
                        .and_then(|style| style.get("W"))
                        .and_then(Value::number)
                        .unwrap_or(if border.len() >= 3 { border[2] } else { 1.0 });
                    if width > 0.0 {
                        inner.width = width;
                        frame.push_rect(
                            tiny_skia::Rect::from_xywh(
                                area.x as f32,
                                area.y as f32,
                                area.w as f32,
                                area.h as f32,
                            )
                            .ok_or(Error::Pdf("Leeres PDF-Rechteck.".into()))?,
                        );
                        if let Some(frame) = frame.finish() {
                            self.stroke(target, &frame, &inner)?;
                        }
                    }
                }
                "Text" => {
                    frame.push_rect(
                        tiny_skia::Rect::from_xywh(
                            area.x as f32,
                            area.y as f32,
                            area.w as f32,
                            area.h as f32,
                        )
                        .ok_or(Error::Pdf("Leeres PDF-Rechteck.".into()))?,
                    );
                    if let Some(frame) = frame.finish() {
                        self.fill(target, &frame, FillRule::Winding, &inner)?;
                    }
                }
                "Highlight" => {
                    let points = note
                        .get("QuadPoints")
                        .and_then(Value::array)
                        .map(|p| numbers(p, None))
                        .transpose()?
                        .unwrap_or_default();
                    if points.len() % 8 != 0 {
                        return bad("Ungültige PDF-Markierung.");
                    }
                    inner.fill_alpha = 0.35;
                    for q in points.chunks(8) {
                        let mut quad = PathBuilder::new();
                        quad.move_to(q[0] as f32, q[1] as f32);
                        for i in [2, 6, 4] {
                            quad.line_to(q[i] as f32, q[i + 1] as f32);
                        }
                        quad.close();
                        if let Some(quad) = quad.finish() {
                            self.fill(target, &quad, FillRule::Winding, &inner)?;
                        }
                    }
                }
                other => {
                    return unsupported(format!(
                        "PDF-Anmerkungsdarstellung fehlt: {}",
                        if other.is_empty() { "None" } else { other }
                    ));
                }
            }
        }
        Ok(())
    }

    fn index(&self) -> usize {
        self.page.index
    }
}

pub static LAYERS: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
pub static MASKS: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);

/// Turns premultiplied colour into grey of the same luminance, as a group in DeviceGray shows it.
fn grey(pixmap: &mut Pixmap) {
    for pixel in pixmap.data_mut().as_chunks_mut::<4>().0 {
        let level =
            ((30 * u32::from(pixel[0]) + 59 * u32::from(pixel[1]) + 11 * u32::from(pixel[2]) + 50)
                / 100) as u8;
        pixel[..3].fill(level);
    }
}

/// The page as an opaque picture on white, `scale` output pixels per page pixel.
pub fn render(document: &Document, index: usize, scale: f64) -> Outcome<Pixmap> {
    rows(document, index, scale, 0, u32::MAX)
}

/// The same picture, turned by a further `turn` degrees, drawn as horizontal bands on several processor cores. Each band reads the file
/// itself, since a document's objects are not shared between threads.
pub fn render_file(
    path: &std::path::Path,
    password: &str,
    index: usize,
    scale: f64,
    turn: i64,
) -> Outcome<Pixmap> {
    let mut document = Document::open(path, password)?;
    document.turn(index, turn)?;
    let page = Page::prepare(&document, index)?;
    let (w, h) = ((page.width * scale).ceil(), (page.height * scale).ceil());
    if !(scale > 0.0 && w > 0.0 && h > 0.0 && w * h <= 40_000_000.0) {
        return bad("PDF-Vorschaubild zu groß oder ungültig.");
    }
    let (w, h) = (w as u32, h as u32);
    let cores = std::thread::available_parallelism().map_or(1, |n| n.get() as u32);
    let most = std::env::var("LUMEN_DOCUMENT_BANDS")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(BANDS);
    let bands = cores.min(most).min(h / 128).max(1);
    if bands == 1 {
        return render(&document, index, scale);
    }
    let step = h.div_ceil(bands);
    let drawn: Vec<Outcome<Pixmap>> = std::thread::scope(|scope| {
        let workers: Vec<_> = (1..bands)
            .map(|band| {
                scope.spawn(move || {
                    let mut document = Document::open(path, password)?;
                    document.turn(index, turn)?;
                    rows(
                        &document,
                        index,
                        scale,
                        band * step,
                        ((band + 1) * step).min(h),
                    )
                })
            })
            .collect();
        let first = rows(&document, index, scale, 0, step.min(h));
        std::iter::once(first)
            .chain(workers.into_iter().map(|worker| {
                worker
                    .join()
                    .unwrap_or_else(|_| bad("PDF-Seite konnte nicht gezeichnet werden."))
            }))
            .collect()
    });
    let mut whole = Pixmap::new(w, h)
        .ok_or_else(|| Error::Pdf("PDF-Vorschaubild zu groß oder ungültig.".into()))?;
    let mut at = 0;
    for band in drawn {
        let band = band?;
        let data = band.data();
        whole.data_mut()[at..at + data.len()].copy_from_slice(data);
        at += data.len();
    }
    Ok(whole)
}

/// The most bands a page is cut into; beyond this the repeated reading of the page costs more than it
/// saves. `LUMEN_DOCUMENT_BANDS` overrides it, 1 draws the page in one piece.
const BANDS: u32 = 8;

/// Rows drawn beyond each side of a band and thrown away: edge smoothing and picture filtering look
/// at neighbouring rows, which a band cut exactly at its border would not have.
const MARGIN: u32 = 8;

/// Output rows `top..bottom` of the page picture.
fn rows(document: &Document, index: usize, scale: f64, top: u32, bottom: u32) -> Outcome<Pixmap> {
    let (from, to) = (top.saturating_sub(MARGIN), bottom.saturating_add(MARGIN));
    let wide = widened(document, index, scale, from, to)?;
    let rows = bottom.min(from + wide.height()) - top;
    if top == from && rows == wide.height() {
        return Ok(wide);
    }
    let too_large = || Error::Pdf("PDF-Vorschaubild zu groß oder ungültig.".into());
    let mut exact = Pixmap::new(wide.width(), rows).ok_or_else(too_large)?;
    let start = ((top - from) * wide.width() * 4) as usize;
    let length = exact.data().len();
    exact
        .data_mut()
        .copy_from_slice(&wide.data()[start..start + length]);
    Ok(exact)
}

fn widened(
    document: &Document,
    index: usize,
    scale: f64,
    top: u32,
    bottom: u32,
) -> Outcome<Pixmap> {
    let page = Page::prepare(document, index)?;
    let (w, h) = ((page.width * scale).ceil(), (page.height * scale).ceil());
    if !(scale > 0.0 && w > 0.0 && h > 0.0 && w * h <= 40_000_000.0) {
        return bad("PDF-Vorschaubild zu groß oder ungültig.");
    }
    let bottom = bottom.min(h as u32);
    if top >= bottom {
        return bad("PDF-Vorschaubild zu groß oder ungültig.");
    }
    let h = f64::from(bottom - top);
    let too_large = || Error::Pdf("PDF-Vorschaubild zu groß oder ungültig.".into());
    let mut surface = Pixmap::new(w as u32, h as u32).ok_or_else(too_large)?;
    let base = page
        .transform
        .then(Matrix::new(&[scale, 0.0, 0.0, scale, 0.0, 0.0]))
        .then(Matrix::new(&[1.0, 0.0, 0.0, 1.0, 0.0, -f64::from(top)]));
    let resources = match document.resolve(
        document.pages[index]
            .get("Resources")
            .unwrap_or(&Value::Null),
    )? {
        Value::Dict(resources) => resources,
        _ => Rc::new(Dict::new()),
    };
    let state = State::start();
    let content = document.contents(index)?;
    let mut renderer = Renderer {
        document,
        page,
        base,
        operations: 0,
        image_pixels: 0,
        layer_pixels: std::cell::Cell::new(0),
        tiles: HashMap::new(),
        masking: 0,
    };
    renderer.interpret(
        &mut surface,
        &content,
        &resources,
        &mut Vec::new(),
        0,
        state.clone(),
    )?;
    if let Value::Dict(group) =
        document.resolve(document.pages[index].get("Group").unwrap_or(&Value::Null))?
        && document
            .resolve(group.get("CS").unwrap_or(&Value::Null))?
            .name()
            == Some("DeviceGray")
    {
        grey(&mut surface);
    }
    renderer.annotations(&mut surface, &state)?;
    let mut paper = Pixmap::new(w as u32, h as u32).ok_or_else(too_large)?;
    paper.fill(tiny_skia::Color::WHITE);
    paper.draw_pixmap(
        0,
        0,
        surface.as_ref(),
        &tiny_skia::PixmapPaint::default(),
        Transform::identity(),
        None,
    );
    Ok(paper)
}
