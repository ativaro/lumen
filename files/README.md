# Lumen Files

Open **Lumen Files** from the application menu, or run `lumen-files`. Start with the folder you want to work in. File operations and ordinary previews run on your computer. Connect a model when you want Lumen to explain or act on a selection.

## Navigate and open files

| Action | Shortcut or control |
| --- | --- |
| Enter a folder path | Ctrl+L |
| Open or close a tab | Ctrl+T / Ctrl+W |
| Go back or forward | Alt+Left / Alt+Right |
| Show hidden files | Ctrl+H |
| Preview the selected file | Space |
| Find a filename | Ctrl+F |
| Search file contents | Ctrl+Shift+F |
| Rename or inspect a selection | F2 / Alt+Enter |
| Create a folder | Ctrl+Shift+N |

Double-click to use the default application. To use a different one, right-click the file and choose **Open with**. Select an installed application for that file type. Set it as the default only if you want future opens to use it too. For a quick inspection, press **Space**.

## Find and organize

Search by name to locate a file you already know. For a phrase inside a document, start a content search in its folder. Supported plain text, code and PDFs with a text layer can return matching excerpts. Optical character recognition (OCR) and optional image-by-subject search are separate. The first subject search prepares a local index for the selected folder.

Use libraries and collections to keep related files reachable. A reference in a collection points to its original location. For bulk renaming or sorting, review the proposed names and destinations before applying the changes. Undo is available for supported batches when the recorded files still match and the old names are free. Use Properties to inspect file information or request a checksum. Disk analysis helps locate large folders before deciding what to keep.

## Work with PDFs

Enable the document workshop in Files settings under PDF editing and apply the setting. Select one or more PDFs and open the workshop from the context menu. Drag pages into order, rotate them or remove them from the working selection. Export selected pages to extract them, or export all pages to combine them into a new PDF.

For redaction, mark the area on the page preview and export. Affected pages are rebuilt from their visible content. Optional local OCR with Tesseract can add a new text layer to the result. Inspect the exported file before sharing it. The workshop operates on supported unencrypted PDFs. For reading, bookmarks and annotations, use [Lumen Reader](../READER-SOUND.md#reader).

## Work with photos

Open an image in the gallery to move between photos and inspect details. Rotate or mirror an image in the editor and review the save destination. Use the arrow keys to browse, R or Shift+R to rotate, H to mirror, Ctrl+Z to undo and Ctrl+S to save. Local preview caching helps when you return to the same files. The optional photo cleanup view suggests groups such as bursts and low-detail images. Review and select the photos yourself before moving any to the trash.

Subject search needs its optional local models. Set them up once in Settings, choose a folder, then describe what you want to find. A match indicates visual similarity. Text in a photographed receipt is a different task and requires OCR.

## Network folders and versions

Use a configured network location for shared folders. For cloud storage, add an account in Settings and open it in Files. Check that the remote location is connected before moving files. [Online accounts](../ONLINE-ACCOUNTS.md)

For a NAS folder you need when disconnected, prepare an offline copy while the share is reachable. Work in that local copy. While Files is open, it checks for changes about once a minute. If both copies changed, review the conflict before choosing which version to keep. Enable file versions per folder to keep earlier versions of supported files. Make a separate backup for recovery from a lost drive. If a network copy is interrupted, inspect its transfer entry and the destination before resuming.

## Ask about a file

Right-click a selection and choose **Open with Lumen** to ask your own question. Context actions can also explain a file, investigate an error or review a Git diff. Inspect the selected files, then send your request. Encrypted files, missing readers or a model's input limits can restrict what it can examine. For recurring actions, Files can keep a named action with your prompt. Tool permissions still apply when it runs.

## Lumen System

Open **Lumen System** for live process and hardware readings and its **Sound** tab for per-application audio. [Using Lumen Desktop](../LUMEN-GUIDE.md#inspect-your-system) · [Audio controls](../READER-SOUND.md#sound)

[Guide index](../docs/README.md) · [Use selected content in another app](../docs/interop/USAGE.md)
