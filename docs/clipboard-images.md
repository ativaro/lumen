# Clipboard images in Lumen

Ctrl+V (or Paste) in Lumen chat and Search attaches a copied image through the
existing file-attachment path. Pasting does not send a message or replace the
text draft. Normal text paste and protected password-manager clipboard handling
remain unchanged. Other text editors remain text-only.

Qt images and raw PNG/JPEG/WebP/BMP clipboard formats are normalized to PNG.
Attachments are stored privately (directory 0700, files 0600) under
`$XDG_CACHE_HOME/lumen/clipboard` (default `~/.cache/lumen/clipboard`). Atomic
writes, a process lock and content hashes prevent partial files and duplicate
storage. Files remain available for restored drafts after restart.

Limits: 24 selected attachments, 32 million pixels and 32 MiB per image;
256 MiB total clipboard cache. A full cache reports an error and asks the user
to attach an image file instead; it does not silently delete draft attachments.

Verification: `test_clipboard_images` exercises native and QML keyboard paste,
text selection, image-plus-text MIME, raw PNG, deduplication, secret protection,
busy state, storage errors, quota and mocked message submission. It runs with a
synthetic profile and no provider request. The test failed against the previous
runtime and passed against the installed correction. Clipboard/privacy suite:
4 passing tests. Two unrelated Search scroll tests fail identically against the
previous runtime; they are not counted as passing. Real provider image analysis
was not tested.
