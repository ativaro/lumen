# Lumen Desktop

Lumen Desktop is a set of applications for KDE Plasma 6. You can work with files, read and annotate documents, edit text, manage audio and inspect your computer. The assistant works with the material you select. For example, you can ask it to explain a configuration file, find the cause of a failed service or suggest filenames for a batch of scans. You can review its evidence and proposed changes in the conversation.

Already installed? [Find a guide by task](docs/README.md).

## Install

Use **Arch Linux or CachyOS with KDE Plasma 6**. Open a terminal in your graphical session as your regular user. If Git is missing, install it with `sudo pacman -S --needed git`. From a directory where you want to create a new `lumen` folder, run:

```bash
git clone --branch main --single-branch https://github.com/ativaro/lumen.git && bash lumen/bootstrap.sh
```

The installer builds the native components and opens the setup wizard. Choose English or German, select a model if you want assistant answers, and add dictation or a reading voice if you need them. Applying the Lumen panel and theme is optional. You can keep your existing Plasma layout and open the apps from KDE's application menu. For an existing installation, use **Lumen Updater**. [Installation, updates and recovery](INSTALL.md)

## Conversations and desktop search

With Lumen's shortcuts active, **Super** opens the start menu and **Alt+Space** opens Lumen. Use Search to launch an installed application or find a file by name. Open a conversation when you want an explanation or an action. Past conversations can be reopened for follow-up questions.

To work from evidence, select a file in **Lumen Files** and choose **Open with Lumen**. For a configuration file, try “Which setting controls where logs are written? Quote the line.” You can also select several files or paste a screenshot into a draft. Review the selection before sending it. Images need a model that can interpret them. With local speech recognition installed, you can dictate a question or have a spoken conversation.

Use read-only mode to investigate first. If you ask Lumen to make a change, such as installing a package or restarting a service, the conversation shows the tool request, any required approval and the result. Lumen can present structured results such as a table of readings or a chart alongside the explanation.

The task view keeps the steps, status and errors. You can pause or cancel work, reopen the related conversation and save a result as a file. A completed task can become a reusable file action. Each time you use it, you can review the new selection. [Conversation and task guide](LUMEN-GUIDE.md#ask-lumen)

## Lumen Files

**Find and inspect.** Open folders in tabs. Use **Ctrl+F** when you know part of a filename and **Ctrl+Shift+F** when you remember a phrase inside a document. Content matches include surrounding text so you can judge their relevance. Press **Space** for a preview or use **Open with** to choose an installed application. File properties can calculate a checksum on request. Disk analysis shows which folders take up the most space.

**Organize across folders.** A library brings several source folders into one view. The **Shelf** collects references to individual files. Use it to gather items from different locations before copying a selection to one destination. For **Smart rename** or **Organize files**, select the files, describe your naming or sorting rule and review the proposed names and destinations. You can edit individual suggestions before applying them. These suggestions use your model and can include text excerpts or image previews from the selected files.

**Work across drives.** Browse SMB, SFTP or WebDAV locations, or add a Google Drive, OneDrive or Dropbox account. For a NAS folder you need offline, prepare its local copy while connected. Files checks for changes while it is open and preserves conflicts for review. You can also enable version history for selected folders, compare a saved text version with the current file and restore it. For an interrupted copy with a saved transfer state, you can ask Lumen to notify you when it can be resumed. [Files guide](files/README.md) · [Online accounts](ONLINE-ACCOUNTS.md)

### Photos and scanned documents

Browse local photos in the gallery, inspect full-size previews, rotate or mirror an image and save your edit. To search by what a photo shows, install the optional image-search models, choose a folder and describe the subject. The index and similarity search run locally. The cleanup view groups candidates such as bursts, screenshots and low-detail images. You decide which items to move to the trash. [Photo tools](files/README.md#work-with-photos)

Enable the **document workshop** in Files settings to combine PDFs, extract selected pages, reorder or rotate pages and export the result to a new PDF. For redaction, mark the sensitive area before exporting. The workshop rebuilds the affected page from its visible content. For a scan, optional local OCR can add selectable text. Open the exported file to check the result before sharing it. [PDF workshop](files/README.md#work-with-pdfs)

## Reader and Compose

**Lumen Reader** keeps a reading copy of a PDF, EPUB, text, Markdown, HTML or supported Office document, including DOCX, XLSX, PPTX and OpenDocument files. It can also save the readable text of a web article from its URL. Search within a document, jump through its outline, bookmark a page, highlight a passage or add a margin note. Reader remembers your place. You can export annotations as Markdown or use a local voice to read the selection or current page aloud. Image-only pages need a text layer for highlighting and speech. [Reader guide](READER-SOUND.md#reader)

**Lumen Compose** gives you the original and a proposed revision side by side. Paste text or pass a selection from Reader. Choose **Translate** for a different language, **Rewrite** for a different style, or **Correct spelling** for smaller edits. Drafts and results are kept in the local library. For a supported text-based PDF, you can translate the document, compare page previews and export a new file. Check line breaks and font sizes where translated text takes more space. [Compose guide](LUMEN-GUIDE.md#write-with-compose)

## System diagnostics and audio

Open **Lumen System** to inspect processor and memory use, storage, processes and available hardware readings. If something stops working, the **Lumen Troubleshooter** checks the installation, writable storage, selected engine and relevant services locally. It can point you to the setup or update screen even when the model cannot answer. You can copy the diagnostic report and review it before sharing. [Troubleshooting](INSTALL.md#troubleshooting)

In **Sound**, start playback in the application you want to adjust. You can change its stream volume, mute it or send it to another output. For example, route a music player to speakers and a call to a headset. Save a per-app rule to reuse the choice. To lower music during calls, assign the music and call roles and enable the automation for one login or future logins. Detection depends on the audio streams the calling app exposes. [Sound controls and rules](READER-SOUND.md#sound)

## Notifications, household records and screen help

- **Notifications.** Open the bell to find a recent notification, use the originating app's action or archive an item. You can also ask Lumen to remind you at a specific time. **Discuss with Lumen** prepares a draft from the notification for you to review and send. Game quiet mode can defer interruptions during recognized games. [Notifications guide](LUMEN-GUIDE.md#notifications)
- **Digital Household.** Keep a device's serial number, purchase receipt, manual and warranty end date in one record. For a contract, record the provider, customer number and cancellation deadline. Search by name, model or indexed receipt text, then export a record overview as Markdown. The household view shows upcoming and overdue dates. For a timed alert, set a separate reminder. [Household guide](LUMEN-GUIDE.md#keep-household-records)
- **Lumen Companion.** Select one application window, inspect the capture and ask a vision-capable model to explain what is on screen. For example, show an unfamiliar export dialog and ask which setting determines the file format. You operate the window. Optional monitoring can send stable changes during a bounded session. Pausing or minimizing Companion stops capture. [Companion controls](INSTALL.md#screen-companion)

## Model, memory and permissions

File browsing, reading, PDF editing in the workshop, household records and system checks work without an assistant model. Conversations, Compose revisions and model-assisted file organization use the provider you select in setup. A remote provider receives the submitted prompt and context. Local dictation converts speech to text on the computer. Sending the transcription follows the same provider setting as typing a question.

In Settings, you can choose a local-only model connection or allow configured remote providers. Local-only mode requires a service on the same machine. A local service that forwards requests elsewhere has its own routing. You can also choose how Lumen addresses you and preview its conversational style before applying it.

Memory has separate controls for recalling stored entries, learning from conversations and accepting suggestions automatically. You can inspect a suggestion and its source, edit a saved preference or forget it. Open **Settings → Capabilities & extensions** to inspect configured tool connections, OpenCode plugins and available skills. Tools that change files or the system follow their configured permissions. [Personal memory](WISSEN.md) · [Desktop tool access](MCP.md)

[All desktop guides](docs/README.md) · [License](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
