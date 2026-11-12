//! Writing PDFs: pages copied from immutable sources, or rasterised with redactions burnt in.
//! The source files are never changed; the result is published under a new name in one step.
use crate::pdf::{
    Dict, Document, Error, MAX_FILE, MAX_OBJECTS, MAX_STREAM, Outcome, Ref, Stream, Value,
};
use std::collections::HashMap;
use std::io::Write as _;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::rc::Rc;

const MAX_DEPTH: usize = 64;

fn bad<T>(text: &str) -> Outcome<T> {
    Err(Error::Pdf(text.into()))
}

fn unsupported<T>(text: &str) -> Outcome<T> {
    Err(Error::Unsupported(text.into()))
}

fn name(text: &str) -> Value {
    Value::Name(text.into())
}

fn dict(entries: Vec<(&str, Value)>) -> Dict {
    entries
        .into_iter()
        .map(|(key, value)| (key.to_string(), value))
        .collect()
}

fn write_name(out: &mut Vec<u8>, text: &str) -> Outcome<()> {
    out.push(b'/');
    for c in text.chars() {
        let Ok(byte) = u8::try_from(c as u32) else {
            return bad("Nicht serialisierbarer PDF-Wert.");
        };
        if (33..=126).contains(&byte) && !b"()<>[]{}/%#".contains(&byte) {
            out.push(byte);
        } else {
            out.extend_from_slice(format!("#{byte:02X}").as_bytes());
        }
    }
    Ok(())
}

fn write_dict(out: &mut Vec<u8>, entries: &Dict, depth: usize) -> Outcome<()> {
    out.extend_from_slice(b"<<");
    for (key, value) in entries {
        out.push(b' ');
        write_name(out, key)?;
        out.push(b' ');
        serialize(out, value, depth + 1)?;
    }
    out.extend_from_slice(b" >>");
    Ok(())
}

/// A value in PDF syntax. A stream gets the length of the bytes actually written.
pub fn serialize(out: &mut Vec<u8>, value: &Value, depth: usize) -> Outcome<()> {
    if depth > MAX_DEPTH {
        return bad("PDF-Ausgabe zu tief verschachtelt.");
    }
    match value {
        Value::Null => out.extend_from_slice(b"null"),
        Value::Bool(value) => out.extend_from_slice(if *value { b"true" } else { b"false" }),
        Value::Int(value) => out.extend_from_slice(value.to_string().as_bytes()),
        Value::Real(value) => {
            if !value.is_finite() {
                return bad("Ungültige PDF-Ausgabezahl.");
            }
            // Rust prints the shortest digits that read back as the same number, without an exponent.
            let text = value.to_string();
            if text.len() > 100 {
                return bad("PDF-Ausgabezahl außerhalb des darstellbaren Bereichs.");
            }
            out.extend_from_slice(text.as_bytes());
        }
        Value::Text(bytes) => {
            out.push(b'<');
            for byte in bytes.iter() {
                out.extend_from_slice(format!("{byte:02x}").as_bytes());
            }
            out.push(b'>');
        }
        Value::Name(text) => write_name(out, text)?,
        Value::Array(items) => {
            out.push(b'[');
            for (at, item) in items.iter().enumerate() {
                if at > 0 {
                    out.push(b' ');
                }
                serialize(out, item, depth + 1)?;
            }
            out.push(b']');
        }
        Value::Dict(entries) => write_dict(out, entries, depth)?,
        Value::Stream(stream) => {
            let mut attrs = stream.attrs.clone();
            attrs.insert("Length".into(), Value::Int(stream.raw.len() as i64));
            write_dict(out, &attrs, depth)?;
            out.extend_from_slice(b"\nstream\n");
            out.extend_from_slice(&stream.raw);
            out.extend_from_slice(b"\nendstream");
        }
        Value::Ref(reference) => {
            if reference.number < 1 || !(0..=65535).contains(&reference.generation) {
                return bad("Ungültige PDF-Ganzzahl oder überschrittenes Limit.");
            }
            out.extend_from_slice(
                format!("{} {} R", reference.number, reference.generation).as_bytes(),
            );
        }
        Value::Operator(_) => return bad("Nicht serialisierbarer PDF-Wert."),
    }
    Ok(())
}

/// A new PDF under construction. Sources are told apart by the number the caller gives them.
pub struct Writer {
    objects: Vec<Value>,
    page_refs: Vec<Ref>,
    imported: HashMap<(usize, Ref), Ref>,
    pending_pages: HashMap<(usize, Ref), Ref>,
    root: Ref,
    tree: Ref,
}

impl Default for Writer {
    fn default() -> Self {
        Writer::new()
    }
}

impl Writer {
    pub fn new() -> Writer {
        let (root, tree) = (
            Ref {
                number: 1,
                generation: 0,
            },
            Ref {
                number: 2,
                generation: 0,
            },
        );
        Writer {
            objects: vec![
                Value::Dict(Rc::new(dict(vec![
                    ("Type", name("Catalog")),
                    ("Pages", Value::Ref(tree)),
                ]))),
                Value::Null,
            ],
            page_refs: Vec::new(),
            imported: HashMap::new(),
            pending_pages: HashMap::new(),
            root,
            tree,
        }
    }

    fn add(&mut self, value: Value) -> Outcome<Ref> {
        if self.objects.len() as i64 >= MAX_OBJECTS {
            return bad("Zu viele PDF-Ausgabeobjekte.");
        }
        self.objects.push(value);
        Ok(Ref {
            number: self.objects.len() as i64,
            generation: 0,
        })
    }

    fn put(&mut self, reference: Ref, value: Value) {
        self.objects[reference.number as usize - 1] = value;
    }

    /// A new compressed stream.
    pub fn stream(&mut self, data: &[u8], mut attrs: Dict) -> Outcome<Ref> {
        if data.len() > MAX_STREAM {
            return bad("PDF-Datenstrom überschreitet das Limit.");
        }
        let mut packer =
            flate2::write::ZlibEncoder::new(Vec::new(), flate2::Compression::default());
        let raw = packer
            .write_all(data)
            .and_then(|_| packer.finish())
            .map_err(|_| Error::Pdf("PDF-Datenstrom konnte nicht geschrieben werden.".into()))?;
        attrs.insert("Filter".into(), name("FlateDecode"));
        self.add(Value::Stream(Rc::new(Stream { attrs, raw })))
    }

    /// A value of `document` with everything it refers to, each source object copied once.
    /// A reference to a page that was not selected stays open and fails the export.
    fn clone(
        &mut self,
        source: usize,
        document: &Document,
        value: &Value,
        depth: usize,
    ) -> Outcome<Value> {
        if depth > MAX_DEPTH {
            return bad("PDF-Kopierstruktur zu tief.");
        }
        Ok(match value {
            Value::Ref(reference) => {
                let key = (source, *reference);
                if let Some(known) = self.imported.get(&key) {
                    return Ok(Value::Ref(*known));
                }
                let new = self.add(Value::Null)?;
                self.imported.insert(key, new);
                let resolved = document.resolve(value)?;
                let page = resolved
                    .dict()
                    .is_some_and(|d| d.get("Type").and_then(Value::name) == Some("Page"));
                if page {
                    self.pending_pages.insert(key, new);
                } else {
                    let copy = self.clone(source, document, &resolved, depth + 1)?;
                    self.put(new, copy);
                }
                Value::Ref(new)
            }
            Value::Stream(stream) => Value::Stream(Rc::new(Stream {
                attrs: self.clone_dict(source, document, &stream.attrs, depth)?,
                raw: stream.raw.clone(),
            })),
            Value::Dict(entries) => {
                Value::Dict(Rc::new(self.clone_dict(source, document, entries, depth)?))
            }
            Value::Array(items) => Value::Array(Rc::new(
                items
                    .iter()
                    .map(|item| self.clone(source, document, item, depth + 1))
                    .collect::<Outcome<_>>()?,
            )),
            other => other.clone(),
        })
    }

    fn clone_dict(
        &mut self,
        source: usize,
        document: &Document,
        entries: &Dict,
        depth: usize,
    ) -> Outcome<Dict> {
        entries
            .iter()
            .map(|(key, value)| Ok((key.clone(), self.clone(source, document, value, depth + 1)?)))
            .collect()
    }

    /// A page made here, `width` by `height` points.
    pub fn add_page(
        &mut self,
        width: f64,
        height: f64,
        content: &[u8],
        resources: Dict,
    ) -> Outcome<Ref> {
        if ![width, height]
            .iter()
            .all(|v| v.is_finite() && *v > 0.0 && *v <= 1_000_000.0)
        {
            return bad("Ungültige PDF-Ausgabeseite.");
        }
        let contents = self.stream(content, Dict::new())?;
        let page = self.add(Value::Dict(Rc::new(dict(vec![
            ("Type", name("Page")),
            ("Parent", Value::Ref(self.tree)),
            (
                "MediaBox",
                Value::Array(Rc::new(vec![
                    Value::Int(0),
                    Value::Int(0),
                    Value::Real(width),
                    Value::Real(height),
                ])),
            ),
            ("Resources", Value::Dict(Rc::new(resources))),
            ("Contents", Value::Ref(contents)),
        ]))))?;
        self.page_refs.push(page);
        Ok(page)
    }

    /// Page `index` of `document` with its content, resources and annotations, turned by `rotation`.
    /// Attachments and actions of the catalog are deliberately not followed.
    pub fn copy_page(
        &mut self,
        source: usize,
        document: &Document,
        index: usize,
        rotation: i64,
    ) -> Outcome<()> {
        if index >= document.pages.len() {
            return bad("Ungültige PDF-Ganzzahl oder überschrittenes Limit.");
        }
        if ![0, 90, 180, 270].contains(&rotation) {
            return bad("Ungültige PDF-Drehung.");
        }
        if document
            .catalog
            .get("OCProperties")
            .is_some_and(Value::truthy)
        {
            return unsupported("Seiten mit PDF-Ebenen können noch nicht kopiert werden.");
        }
        if document
            .catalog
            .get("OutputIntents")
            .is_some_and(Value::truthy)
        {
            return unsupported(
                "PDF-Ausgabefarbprofile werden beim Kopieren noch nicht unterstützt.",
            );
        }
        let from = &document.pages[index];
        let key = (source, document.page_refs[index]);
        let reference = match self.pending_pages.remove(&key) {
            Some(open) => open,
            None => self.add(Value::Null)?,
        };
        self.imported.entry(key).or_insert(reference);
        let mut page = Dict::new();
        for kept in [
            "MediaBox",
            "CropBox",
            "TrimBox",
            "BleedBox",
            "ArtBox",
            "UserUnit",
            "Resources",
            "Contents",
            "Group",
        ] {
            if let Some(value) = from.get(kept).filter(|value| !value.is_null()) {
                page.insert(kept.into(), self.clone(source, document, value, 0)?);
            }
        }
        let turned = match from.get("Rotate") {
            Some(Value::Int(value)) => *value,
            Some(value) if value.truthy() => return bad("Ungültige PDF-Seitendrehung."),
            _ => 0,
        };
        page.insert("Type".into(), name("Page"));
        page.insert("Parent".into(), Value::Ref(self.tree));
        page.insert(
            "Rotate".into(),
            Value::Int((turned + rotation).rem_euclid(360)),
        );
        let annotations = match from.get("Annots") {
            Some(value) => document.resolve(value)?,
            None => Value::Null,
        };
        let annotations = match &annotations {
            Value::Array(items) => items.to_vec(),
            Value::Null => Vec::new(),
            _ => return bad("Ungültige PDF-Anmerkungsliste."),
        };
        let mut copied = Vec::new();
        for annotation in &annotations {
            let Value::Dict(entries) = document.resolve(annotation)? else {
                return bad("Ungültige PDF-Anmerkung.");
            };
            let mut entries = (*entries).clone();
            let action = match entries.get("A") {
                Some(value) => document.resolve(value)?,
                None => Value::Null,
            };
            let jump = action
                .dict()
                .filter(|a| a.get("S").and_then(Value::name) == Some("GoTo"))
                .cloned();
            let target = match (&jump, entries.get("Dest")) {
                (Some(action), _) => action.get("D").cloned(),
                (None, target) => target.cloned(),
            };
            let target = match target {
                Some(value) => document.resolve(&value)?,
                None => Value::Null,
            };
            // A named destination lives in the catalog, which is not copied: write it out in place.
            if matches!(target, Value::Name(_) | Value::Text(_)) {
                let Some(found) = document.destination(&target)? else {
                    return unsupported("Benanntes PDF-Seitenziel fehlt.");
                };
                let found = Value::Array(found);
                match jump {
                    Some(action) => {
                        let mut action = (*action).clone();
                        action.insert("D".into(), found);
                        entries.insert("A".into(), Value::Dict(Rc::new(action)));
                    }
                    None => {
                        entries.insert("Dest".into(), found);
                    }
                }
            }
            entries.remove("P");
            entries.remove("Parent");
            let copy = self.clone_dict(source, document, &entries, 0)?;
            copied.push(Value::Ref(self.add(Value::Dict(Rc::new(copy)))?));
        }
        if !copied.is_empty() {
            page.insert("Annots".into(), Value::Array(Rc::new(copied)));
        }
        self.put(reference, Value::Dict(Rc::new(page)));
        self.page_refs.push(reference);
        Ok(())
    }

    pub fn pages(&self) -> usize {
        self.page_refs.len()
    }

    /// The finished file.
    pub fn bytes(&mut self) -> Outcome<Vec<u8>> {
        if self.page_refs.is_empty() {
            return bad("Keine PDF-Ausgabeseiten.");
        }
        if !self.pending_pages.is_empty() {
            return unsupported(
                "PDF-Verweise führen auf nicht ausgewählte Seiten; diese Seiten ebenfalls exportieren.",
            );
        }
        let kids = self
            .page_refs
            .iter()
            .map(|page| Value::Ref(*page))
            .collect();
        self.put(
            self.tree,
            Value::Dict(Rc::new(dict(vec![
                ("Type", name("Pages")),
                ("Kids", Value::Array(Rc::new(kids))),
                ("Count", Value::Int(self.page_refs.len() as i64)),
            ]))),
        );
        let mut out = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n".to_vec();
        let mut offsets = Vec::new();
        for (at, value) in self.objects.iter().enumerate() {
            offsets.push(out.len());
            out.extend_from_slice(format!("{} 0 obj\n", at + 1).as_bytes());
            serialize(&mut out, value, 0)?;
            out.extend_from_slice(b"\nendobj\n");
            if out.len() > MAX_FILE {
                return bad("PDF-Ausgabe größer als 512 MiB.");
            }
        }
        let position = out.len();
        out.extend_from_slice(
            format!("xref\n0 {}\n0000000000 65535 f \n", offsets.len() + 1).as_bytes(),
        );
        for offset in &offsets {
            out.extend_from_slice(format!("{offset:010} 00000 n \n").as_bytes());
        }
        out.extend_from_slice(
            format!(
                "trailer\n<< /Size {} /Root {} 0 R >>\nstartxref\n{position}\n%%EOF\n",
                offsets.len() + 1,
                self.root.number
            )
            .as_bytes(),
        );
        Ok(out)
    }
}

/// Publishes `data` as `target` in one step. An existing file is never replaced.
fn publish(data: &[u8], target: &Path) -> Outcome<()> {
    let failed = || Error::Pdf("PDF-Zieldatei konnte nicht geschrieben werden.".into());
    let folder = target.parent().ok_or_else(failed)?;
    let staged = folder.join(format!(".lumen-pdf-{}.pdf", std::process::id()));
    let written = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&staged)
        .and_then(|mut file| {
            file.write_all(data)?;
            file.sync_all()
        })
        // A hard link fails if the name is taken, where a rename would replace the file.
        .and_then(|_| std::fs::hard_link(&staged, target));
    let _ = std::fs::remove_file(&staged);
    written.map_err(|error| {
        if error.kind() == std::io::ErrorKind::AlreadyExists {
            Error::Pdf("PDF-Zieldatei existiert bereits.".into())
        } else {
            failed()
        }
    })
}

/// Device, inode, size and both change times: what the caller saw when it listed the page.
pub fn signature(path: &Path) -> Outcome<[i64; 5]> {
    let info = std::fs::metadata(path).map_err(|_| {
        Error::Pdf("PDF-Original unverändert lassen; neue Zieldatei wählen.".into())
    })?;
    Ok([
        info.dev() as i64,
        info.ino() as i64,
        info.size() as i64,
        info.mtime() * 1_000_000_000 + info.mtime_nsec(),
        info.ctime() * 1_000_000_000 + info.ctime_nsec(),
    ])
}

/// One page of an export: where it comes from, how it is turned, and what is blacked out.
pub struct Item {
    pub path: PathBuf,
    pub page: usize,
    pub rotation: i64,
    /// Left, top, right and bottom as shares of the turned page.
    pub boxes: Vec<[f64; 4]>,
    pub stamp: [i64; 5],
}

/// Copies, reorders and turns pages into the new file `target`. As soon as one page has a redaction,
/// every page is rasterised at `dpi`: a copied page could still share a resource that holds the hidden text.
/// With `ocr`, the Tesseract languages, a rasterised page and a page without text get a recognised, invisible text layer.
pub fn export(
    items: &[Item],
    target: &Path,
    dpi: u32,
    ocr: Option<&str>,
    progress: &mut dyn FnMut(usize, usize),
) -> Outcome<()> {
    if !(1..=2000).contains(&items.len()) || ![150, 200, 300].contains(&dpi) {
        return bad("Ungültige Seitenauswahl oder Qualität.");
    }
    if !target.is_absolute()
        || !target
            .extension()
            .is_some_and(|e| e.eq_ignore_ascii_case("pdf"))
    {
        return bad("Als PDF speichern.");
    }
    if target.symlink_metadata().is_ok() {
        return bad("Die PDF-Zieldatei existiert bereits.");
    }
    let rasterize = items.iter().any(|item| !item.boxes.is_empty());
    let mut writer = Writer::new();
    let mut font = None;
    let mut sources: Vec<(PathBuf, [i64; 5], Document)> = Vec::new();
    for (position, item) in items.iter().enumerate() {
        progress(position + 1, items.len());
        let plain = item
            .path
            .symlink_metadata()
            .is_ok_and(|info| info.file_type().is_file());
        if !item.path.is_absolute() || !plain || item.path == target {
            return bad("PDF-Original unverändert lassen; neue Zieldatei wählen.");
        }
        let stamp = signature(&item.path)?;
        if stamp != item.stamp {
            return bad("PDF-Quelle wurde verändert.");
        }
        let source = match sources.iter().position(|(path, ..)| *path == item.path) {
            Some(known) => known,
            None => {
                let document = Document::open(&item.path, "")?;
                if document.encrypted() {
                    return unsupported("Verschlüsselte PDFs werden hier noch nicht geschrieben.");
                }
                sources.push((item.path.clone(), stamp, document));
                sources.len() - 1
            }
        };
        if item.page >= sources[source].2.pages.len() {
            return bad("Ungültige PDF-Ganzzahl oder überschrittenes Limit.");
        }
        if ![0, 90, 180, 270].contains(&item.rotation) {
            return bad("Ungültige PDF-Drehung.");
        }
        if item.boxes.len() > 10000
            || item
                .boxes
                .iter()
                .any(|b| b.iter().any(|v| !(0.0..=1.0).contains(v)) || b[0] >= b[2] || b[1] >= b[3])
        {
            return bad("Ungültiger PDF-Schwärzungsbereich.");
        }
        if rasterize || ocr.is_some() {
            let document = &mut sources[source].2;
            let before = document.pages[item.page].get("Rotate").cloned();
            let turned = match &before {
                Some(Value::Int(value)) => *value,
                Some(value) if value.truthy() => return bad("Ungültige PDF-Seitendrehung."),
                _ => 0,
            };
            document.pages[item.page].insert("Rotate".into(), Value::Int(turned + item.rotation));
            // A page that already has text is copied as it is, unless a redaction forces the picture.
            let empty = if rasterize {
                Ok(true)
            } else {
                crate::text::Page::words(document, item.page).map(|(_, _, words)| words.is_empty())
            };
            let drawn = match empty {
                Ok(true) => raster(&mut writer, document, item, dpi, ocr, &mut font).map(|_| true),
                other => other,
            };
            match before {
                Some(value) => document.pages[item.page].insert("Rotate".into(), value),
                None => document.pages[item.page].remove("Rotate"),
            };
            if !drawn? {
                writer.copy_page(source, &sources[source].2, item.page, item.rotation)?;
            }
        } else {
            writer.copy_page(source, &sources[source].2, item.page, item.rotation)?;
        }
    }
    // Check the result and the sources once more before anything is published.
    let data = writer.bytes()?;
    if Document::new(data.clone())?.pages.len() != items.len() {
        return bad("PDF-Exportprüfung fehlgeschlagen.");
    }
    for (path, stamp, _) in &sources {
        if signature(path)? != *stamp {
            return bad("PDF-Quelle während des Exports verändert.");
        }
    }
    publish(&data, target)
}

/// The page as one picture with its redactions painted black, so that nothing under them remains in the file.
fn raster(
    writer: &mut Writer,
    document: &Document,
    item: &Item,
    dpi: u32,
    ocr: Option<&str>,
    font: &mut Option<Ref>,
) -> Outcome<()> {
    let (width, height) = {
        let page = crate::text::Page::prepare(document, item.page)?;
        (page.width, page.height)
    };
    let picture = crate::render::render(document, item.page, f64::from(dpi) / 72.0)?;
    let (w, h) = (picture.width() as usize, picture.height() as usize);
    if w * h * 3 > MAX_STREAM {
        return bad("Raster-PDF-Seite zu groß; niedrigere Auflösung wählen.");
    }
    let mut pixels: Vec<u8> = picture
        .data()
        .as_chunks::<4>()
        .0
        .iter()
        .flat_map(|pixel| [pixel[0], pixel[1], pixel[2]])
        .collect();
    for b in &item.boxes {
        let (left, top) = (
            (b[0] * w as f64).floor() as usize,
            (b[1] * h as f64).floor() as usize,
        );
        let right = ((b[2] * w as f64).ceil() as usize).min(w);
        let bottom = ((b[3] * h as f64).ceil() as usize).min(h);
        for row in top..bottom {
            pixels[(row * w + left) * 3..(row * w + right) * 3].fill(0);
        }
    }
    let image = writer.stream(
        &pixels,
        dict(vec![
            ("Type", name("XObject")),
            ("Subtype", name("Image")),
            ("Width", Value::Int(w as i64)),
            ("Height", Value::Int(h as i64)),
            ("ColorSpace", name("DeviceRGB")),
            ("BitsPerComponent", Value::Int(8)),
        ]),
    )?;
    let mut content = b"q ".to_vec();
    serialize(&mut content, &Value::Real(width), 0)?;
    content.extend_from_slice(b" 0 0 ");
    serialize(&mut content, &Value::Real(height), 0)?;
    content.extend_from_slice(b" 0 0 cm /LumenImage Do Q\n");
    let objects = dict(vec![("LumenImage", Value::Ref(image))]);
    let mut resources = dict(vec![("XObject", Value::Dict(Rc::new(objects)))]);
    if let Some(languages) = ocr {
        // The picture as it will be written, so that nothing under a redaction is recognised.
        let mut shown = tiny_skia::Pixmap::new(w as u32, h as u32)
            .ok_or_else(|| Error::Pdf("OCR-Bild konnte nicht gespeichert werden.".into()))?;
        for (to, from) in shown
            .data_mut()
            .as_chunks_mut::<4>()
            .0
            .iter_mut()
            .zip(pixels.as_chunks::<3>().0)
        {
            *to = [from[0], from[1], from[2], 255];
        }
        let words = recognise(&shown, languages, dpi)?;
        if !words.is_empty() {
            let face = match font {
                Some(face) => *face,
                None => *font.insert(text_font(writer)?),
            };
            resources.insert(
                "Font".into(),
                Value::Dict(Rc::new(dict(vec![("LumenOCR", Value::Ref(face))]))),
            );
            text_layer(&mut content, &words, width, height, f64::from(dpi))?;
        }
    }
    writer.add_page(width, height, &content, resources)?;
    Ok(())
}

/// A recognised word: its text and its box in picture pixels from the top left.
struct Seen {
    text: String,
    left: f64,
    top: f64,
    width: f64,
    height: f64,
}

/// Runs Tesseract on the picture. The text never leaves this computer.
fn recognise(picture: &tiny_skia::Pixmap, languages: &str, dpi: u32) -> Outcome<Vec<Seen>> {
    use std::io::Read;
    let failed = || Error::Pdf("Texterkennung fehlgeschlagen.".into());
    if languages.is_empty()
        || !languages
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"+_".contains(&b))
    {
        return Err(failed());
    }
    let png = picture
        .encode_png()
        .map_err(|_| Error::Pdf("OCR-Bild konnte nicht gespeichert werden.".into()))?;
    let mut child = std::process::Command::new("tesseract")
        .args([
            "stdin",
            "stdout",
            "-l",
            languages,
            "--dpi",
            &dpi.to_string(),
            "tsv",
        ])
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|_| failed())?;
    let mut input = child.stdin.take().ok_or_else(failed)?;
    let feeder = std::thread::spawn(move || input.write_all(&png));
    let mut table = Vec::new();
    let read = child
        .stdout
        .take()
        .ok_or_else(failed)?
        .take(4 * 1024 * 1024 + 1)
        .read_to_end(&mut table);
    let fed = feeder.join();
    if read.is_err() || table.len() > 4 * 1024 * 1024 {
        let _ = child.kill();
        let _ = child.wait();
        return bad("OCR-Ergebnis zu groß.");
    }
    if !child.wait().is_ok_and(|status| status.success()) || !matches!(fed, Ok(Ok(()))) {
        return Err(failed());
    }
    let table = String::from_utf8(table).map_err(|_| failed())?;
    let mut words = Vec::new();
    // level, page, block, paragraph, line, word, left, top, width, height, confidence, text
    for row in table.lines().skip(1) {
        let cells: Vec<&str> = row.splitn(12, '\t').collect();
        if cells.len() != 12 || cells[0] != "5" || cells[11].trim().is_empty() {
            continue;
        }
        let side = |at: usize| cells[at].parse::<f64>().map_err(|_| failed());
        words.push(Seen {
            text: cells[11].to_string(),
            left: side(6)?,
            top: side(7)?,
            width: side(8)?,
            height: side(9)?,
        });
    }
    Ok(words)
}

/// A TrueType file whose glyph 1 is empty and half an em wide. Readers ask for an embedded file even where
/// nothing is painted.
fn blank_font() -> Vec<u8> {
    fn words(values: &[i32]) -> Vec<u8> {
        values
            .iter()
            .flat_map(|v| (*v as i16).to_be_bytes())
            .collect()
    }
    fn checksum(data: &[u8]) -> u32 {
        data.chunks(4).fold(0u32, |sum, chunk| {
            let mut unit = [0u8; 4];
            unit[..chunk.len()].copy_from_slice(chunk);
            sum.wrapping_add(u32::from_be_bytes(unit))
        })
    }
    let mut head = vec![0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0x5F, 0x0F, 0x3C, 0xF5];
    head.extend(words(&[0x000B, 1000])); // flags, units per em
    head.extend([0u8; 16]); // created, modified
    head.extend(words(&[0, -200, 500, 800, 0, 8, 2, 0, 0])); // box, style, smallest size, direction, short offsets, format
    let mut hhea = vec![0, 1, 0, 0];
    hhea.extend(words(&[
        800, -200, 0, 500, 0, 0, 500, 1, 0, 0, 0, 0, 0, 0, 0, 1,
    ]));
    let mut maxp = vec![0, 1, 0, 0];
    maxp.extend(words(&[2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0]));
    let mut cmap = words(&[0, 1, 3, 1, 0, 12]); // one Windows Unicode table at offset 12
    cmap.extend(words(&[4, 32, 0, 2, 2, 0, 0, 0xFFFF, 0, 0xFFFF, 1, 0])); // format 4 with only the closing segment
    let mut post = vec![0, 3, 0, 0];
    post.extend([0u8; 28]);
    post[15] = 1; // fixed pitch
    let mut tables: Vec<(&[u8; 4], Vec<u8>)> = vec![
        (b"cmap", cmap),
        (b"glyf", words(&[0; 10])), // the missing-glyph slot and one glyph, both without contours
        (b"head", head),
        (b"hhea", hhea),
        (b"hmtx", words(&[500, 0, 0])),
        (b"loca", words(&[0, 5, 10])),
        (b"maxp", maxp),
        (b"name", words(&[0, 0, 6])),
        (b"post", post),
    ];
    for (_, data) in &mut tables {
        data.resize(data.len().div_ceil(4) * 4, 0);
    }
    let count = tables.len() as u16;
    let mut file = vec![0, 1, 0, 0];
    file.extend(
        [count, 128, 3, count * 16 - 128]
            .iter()
            .flat_map(|v| v.to_be_bytes()),
    );
    let mut offset = 12 + tables.len() * 16;
    let mut head_at = 0;
    for (tag, data) in &tables {
        if *tag == b"head" {
            head_at = offset;
        }
        file.extend_from_slice(*tag);
        file.extend(checksum(data).to_be_bytes());
        file.extend((offset as u32).to_be_bytes());
        file.extend((data.len() as u32).to_be_bytes());
        offset += data.len();
    }
    for (_, data) in &tables {
        file.extend_from_slice(data);
    }
    let adjustment = 0xB1B0_AFBAu32.wrapping_sub(checksum(&file));
    file[head_at + 8..head_at + 12].copy_from_slice(&adjustment.to_be_bytes());
    file
}

/// A font without outlines for the invisible text: every character is half an em wide, its code is its
/// UTF-16 unit, and the text is stretched to the width of the word that was seen.
fn text_font(writer: &mut Writer) -> Outcome<Ref> {
    let mut map = b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /LumenUnicode def /CMapType 2 def 1 begincodespacerange <0000> <ffff> endcodespacerange\n".to_vec();
    // A range may not cross a first byte, so the identity takes one range per first byte. The halves of
    // a surrogate pair are no characters and stay unmapped.
    let highs: Vec<u32> = (0..256)
        .filter(|high| !(0xd8..=0xdf).contains(high))
        .collect();
    for batch in highs.chunks(100) {
        map.extend_from_slice(format!("{} beginbfrange\n", batch.len()).as_bytes());
        for high in batch {
            map.extend_from_slice(
                format!("<{high:02x}00> <{high:02x}ff> <{high:02x}00>\n").as_bytes(),
            );
        }
        map.extend_from_slice(b"endbfrange\n");
    }
    map.extend_from_slice(b"endcmap CMapName currentdict /CMap defineresource pop end end");
    let unicode = writer.stream(&map, Dict::new())?;
    let whole = |value: i64| Value::Int(value);
    let file = blank_font();
    let length = file.len() as i64;
    let file = writer.stream(&file, dict(vec![("Length1", whole(length))]))?;
    // Every character code shows the empty glyph 1; glyph 0 would mean that the character is missing.
    let glyphs = writer.stream(&[0u8, 1].repeat(65536), Dict::new())?;
    let descriptor = writer.add(Value::Dict(Rc::new(dict(vec![
        ("Type", name("FontDescriptor")),
        ("FontName", name("LumenOCR")),
        ("Flags", whole(4)),
        (
            "FontBBox",
            Value::Array(Rc::new(vec![whole(0), whole(-200), whole(500), whole(800)])),
        ),
        ("ItalicAngle", whole(0)),
        ("Ascent", whole(800)),
        ("Descent", whole(-200)),
        ("CapHeight", whole(700)),
        ("StemV", whole(80)),
        ("FontFile2", Value::Ref(file)),
    ]))))?;
    let system = dict(vec![
        ("Registry", Value::Text(Rc::new(b"Adobe".to_vec()))),
        ("Ordering", Value::Text(Rc::new(b"Identity".to_vec()))),
        ("Supplement", whole(0)),
    ]);
    let child = writer.add(Value::Dict(Rc::new(dict(vec![
        ("Type", name("Font")),
        ("Subtype", name("CIDFontType2")),
        ("BaseFont", name("LumenOCR")),
        ("CIDSystemInfo", Value::Dict(Rc::new(system))),
        ("FontDescriptor", Value::Ref(descriptor)),
        ("DW", whole(500)),
        ("CIDToGIDMap", Value::Ref(glyphs)),
    ]))))?;
    writer.add(Value::Dict(Rc::new(dict(vec![
        ("Type", name("Font")),
        ("Subtype", name("Type0")),
        ("BaseFont", name("LumenOCR")),
        ("Encoding", name("Identity-H")),
        (
            "DescendantFonts",
            Value::Array(Rc::new(vec![Value::Ref(child)])),
        ),
        ("ToUnicode", Value::Ref(unicode)),
    ]))))
}

/// The words as text that is not painted, each at the place and width it has in the picture.
fn text_layer(
    content: &mut Vec<u8>,
    words: &[Seen],
    width: f64,
    height: f64,
    dpi: f64,
) -> Outcome<()> {
    let number = |out: &mut Vec<u8>, value: f64| serialize(out, &Value::Real(value), 0);
    for word in words {
        let scale = 72.0 / dpi;
        let (x, y, w, h) = (
            word.left * scale,
            word.top * scale,
            word.width * scale,
            word.height * scale,
        );
        if x.min(y) < 0.0 || w <= 0.0 || h <= 0.0 || x + w > width + 1.0 || y + h > height + 1.0 {
            return bad("Ungültige OCR-Textposition.");
        }
        // Characters outside the basic plane have no single code in this font and are left out.
        let units: Vec<u8> = word
            .text
            .chars()
            .filter(|c| (*c as u32) < 0x10000)
            .flat_map(|c| (c as u16).to_be_bytes())
            .collect();
        if units.is_empty() {
            continue;
        }
        let natural = (units.len() / 2) as f64 * 0.5 * h;
        content.extend_from_slice(b"BT 3 Tr /LumenOCR ");
        number(content, h)?;
        content.extend_from_slice(b" Tf ");
        number(content, 100.0 * w / natural)?;
        content.extend_from_slice(b" Tz 1 0 0 1 ");
        number(content, x)?;
        content.push(b' ');
        // The font's descent is a fifth of its size, so this puts its box on the word's box.
        number(content, height - y - 0.8 * h)?;
        content.extend_from_slice(b" Tm ");
        serialize(content, &Value::Text(Rc::new(units)), 0)?;
        content.extend_from_slice(b" Tj ET\n");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text(value: &Value) -> String {
        let mut out = Vec::new();
        serialize(&mut out, value, 0).unwrap();
        String::from_utf8(out).unwrap()
    }

    #[test]
    fn values_are_written_in_pdf_syntax() {
        assert_eq!(text(&name("A B#/")), "/A#20B#23#2F");
        assert_eq!(text(&Value::Real(0.1)), "0.1");
        assert_eq!(text(&Value::Real(595.0)), "595");
        assert_eq!(text(&Value::Real(1e21)), "1000000000000000000000");
        assert_eq!(text(&Value::Text(Rc::new(vec![0, 255]))), "<00ff>");
        let nested = Value::Array(Rc::new(vec![
            Value::Null,
            Value::Bool(true),
            Value::Ref(Ref {
                number: 3,
                generation: 0,
            }),
        ]));
        assert_eq!(text(&nested), "[null true 3 0 R]");
        assert!(serialize(&mut Vec::new(), &Value::Real(f64::NAN), 0).is_err());
    }

    #[test]
    fn a_written_page_reads_back() {
        let mut writer = Writer::new();
        writer
            .add_page(200.0, 100.0, b"0 0 m\n", Dict::new())
            .unwrap();
        let document = Document::new(writer.bytes().unwrap()).unwrap();
        assert_eq!(document.pages.len(), 1);
        let page = crate::text::Page::prepare(&document, 0).unwrap();
        assert_eq!((page.width, page.height), (200.0, 100.0));
        assert!(Writer::new().bytes().is_err());
    }

    #[test]
    fn the_blank_font_is_a_font_and_recognised_words_keep_their_place() {
        let font = blank_font();
        let face = ttf_parser::Face::parse(&font, 0).unwrap();
        assert_eq!(face.number_of_glyphs(), 2);
        assert_eq!(face.glyph_hor_advance(ttf_parser::GlyphId(1)), Some(500));
        let word = |text: &str, left| Seen {
            text: text.into(),
            left,
            top: 100.0,
            width: 200.0,
            height: 40.0,
        };
        let mut content = Vec::new();
        text_layer(
            &mut content,
            &[word("Öl", 100.0), word("😀", 400.0)],
            400.0,
            400.0,
            144.0,
        )
        .unwrap();
        // 20 points high, two characters of 10 points stretched to 100: five times as wide. The emoji is left out.
        assert_eq!(
            String::from_utf8(content).unwrap(),
            "BT 3 Tr /LumenOCR 20 Tf 500 Tz 1 0 0 1 50 334 Tm <00d6006c> Tj ET\n"
        );
        assert!(text_layer(&mut Vec::new(), &[word("x", 700.0)], 400.0, 400.0, 144.0).is_err());
    }
}
