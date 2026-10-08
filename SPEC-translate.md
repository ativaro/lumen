# Lumen Translate

## Objective and capability map

Native translation as part of Lumen, using the existing configured provider/model and privacy policy. User priority: text and selections, with translation, style rewriting and spelling/grammar-only correction; PDF layout translation is secondary. No automatic sending when a file, selection or handoff is opened.

| Module | Responsibility | Depends on |
| --- | --- | --- |
| translate-core | Language/style validation, bounded batches, strict model result validation | Existing OpenCode backend |
| translate-pdf | Isolated PDF text extraction, layout-aware replacement, safe new-file export | translate-core |
| translate-ui | Two-pane text and PDF previews, cancel, local drafts/history | core, pdf |
| translate-integration | Apps/settings/search launcher, Files and app handoffs, MCP, installation | core, pdf, UI |

Build order: core → PDF → UI → integration.

## Contract

- Three text modes: translate, rewrite in the same language, correct spelling/grammar/punctuation while preserving style. Auto-detect source; target language for translation only. Neutral, professional, casual, friendly and concise styles; correction ignores style.
- Model receives explicitly supplied content only, without tools or memory context. A visible Translate action sends it; no clipboard monitoring or automatic translation.
- PDF originals remain unchanged. Work from a private import; preserve page boxes, pictures and vector lines. Replace horizontal text blocks in their original rectangles; fit text within a bounded minimum scale and report downsizing. Refuse unreadable scans, interactive/signed PDFs and unsupported rotated text rather than claim a complete translation.
- Preview original/result pages side by side. New-file export must not overwrite an existing file or original. No silent truncation or partial-success export. Changing source/options invalidates the previous result.
- History/drafts remain local like the other native apps; users can archive records. PDF processing uses Lumen’s own engine in a separate process (see SPEC-pdf-core.md).
- MCP: language catalogue, bounded text translation (no local history writes), PDF translation to an explicitly supplied new output path behind the existing action gate. Tools are disabled for model calls to avoid recursion. Existing action and privacy flags remain unchanged.
- Integrate a PDF/text handoff target and a translation source so selected content from Wissen, Reader, Inbox etc. can enter Translate, and results can return to Wissen/Inbox/projects. Integrate AppCenter, app-specific defaults in settings, Files context menu, desktop launcher, setup dependency discovery and installers.
- German and English UI. Existing themes and Qt 6 runtime. No new credentials or providers.

## Implementation / verification

Modules in `files/translate_data.py`, `translate_pdf.py`, `tools_translate.py`; tests in `files/test_translate.py`. Follow native ToolWindow/Job, Library, Registry and preference writer patterns. Test with the shared `bin/lumen-python`, isolated XDG directories, `QT_QPA_PLATFORM=offscreen` and `python -m unittest test_translate test_mcp_native test_app_center test_interop test_i18n` (select existing interop test modules). Validate input/output bounds, cancellation, model failures, mismatched IDs, unchanged originals, export collisions, page geometry/images/vector lines and native activation. Render a representative translated PDF and the DE/EN UI for visual review. Never commit local content, settings or provider tokens.

Out of scope for this increment: OCR, layout translation of Office documents, live microphone interpreting and replacement of text embedded in images. These limits are visible in the PDF import UI.


PDF format reference: https://pdfa.org/resource/iso-32000-1/
(text-only redactions; bounded `insert_htmlbox` fitting). Existing link annotations
are restored when text redaction removes them. Source files are fingerprinted before
and after processing; new output publication uses an exclusive same-directory link.
