# Using Lumen Desktop

## Ask Lumen

Open **Lumen** from the application menu, or use the conversation field in the Lumen topbar. Start with a concrete question, such as “Which process is using the most memory?” Continue in the same conversation if the next question depends on the answer. Reopen an earlier conversation to pick up its history.

- **Give Lumen the right material.** Attach the file, image or clipboard content you want to discuss. From Files, select one or more items and open the Lumen action from their context menu. Which contents Lumen can read depends on the format, installed tools and model.
- **Investigate first.** Use the read-only mode to inspect a problem. If you want a change, describe the specific result. For example, ask which package provides a missing command before asking to install it.
- **Check what happened.** The conversation shows tool requests, progress, requests for input and results. Review the target before granting permission. Installing software or changing a protected service can also open the desktop administrator prompt. Open the resulting file or check the reported service state to verify the outcome.
- **Speak if you prefer.** Set up local dictation or a voice in the setup wizard. Open the microphone controls in the conversation. Recognition and playback run locally. The transcribed question follows the same model settings as a typed one.

### Follow a task through to its result

Open a task from the topbar to see what is running, what needs an answer and what has finished. Open its details for the result or error. If you resume an interrupted task, ask Lumen to check the current state first. A file may already have been copied or a package installed before the interruption.

For a file operation, review its path and the proposed change. Some native operations offer undo when the target still matches the recorded result. For assistant-generated output, save or open the result file and inspect it. If you paste a screenshot into the conversation, Lumen attaches it to the draft. Press Send when you are ready to share it with the chosen model.

## Find something and open it

Open **Lumen Search** to launch an application, find a file by name or start a question. Select the result you want with the keyboard and press **Enter**. To search *inside* documents in a particular folder, open it in Files and press **Ctrl+Shift+F**. See [search and shortcuts](SEARCH-PREVIEW.md).

The Lumen topbar brings together the start menu, search, recent activity, notifications, network and sound. Open a menu with its button and click again to close it. Use the start menu to search installed applications, pin frequently used ones and return to recent items. The available controls depend on your panel layout. With Lumen’s desktop shortcuts active, **Super** opens Start and **Alt+Space** opens Lumen.

## Write with Compose

Open **Lumen Compose**, paste some text, then choose **Translate**, **Rewrite** or **Correct spelling**. Translation changes the language. Rewrite lets you change the style. Correction aims to keep the author's wording. Review the original and result side by side before copying the result. You can return to drafts and past results in the local library.

To translate a supported PDF with a text layer, use the PDF tab, check the page previews and export to a new file. Scans need OCR first. Forms, signatures and rotated text are examples the PDF workflow may refuse. Fonts and line breaks can change in a translation. See [document tools](files/README.md#work-with-pdfs).

## Notifications

Open the bell to inspect recent messages, revisit one later or archive it. The original notification can offer actions supplied by its application. **Discuss with Lumen** opens a conversation draft you can edit before sending. Game quiet mode can hold interruptions while a game is active. Local reminders need the panel running and can appear at the next start after a missed time.

## Inspect your system

Open **Lumen System** to see CPU and memory use, processes and drives. GPU, temperature and fan readings depend on the hardware and its drivers. To investigate a symptom, note the affected process and time, then ask Lumen to examine those observations or relevant logs. If the assistant itself is unavailable, open **Lumen Troubleshooter** in Settings and start a check. Its local checks cover core files, free space, the engine and services. Each finding points to a relevant next step. Select the **Sound** tab in Lumen System to manage audio by application. [Sound controls and rules](READER-SOUND.md#sound)

## Keep household records

1. Open **Lumen Digital Household** and choose **Add device / contract**. For a device, enter its model and serial number. For a contract, enter its provider and customer number.
2. Record the purchase or start date, the warranty or contract end date and any cancellation deadline. The record shows how many days remain or how long a date has been overdue. To receive a timed notification, ask Lumen separately to remind you on a specific date and time.
3. Choose **Add receipt** to attach a receipt or manual. Household keeps a local copy. When text extraction succeeds, a phrase from the attachment can find the record as well as its name or model.
4. Choose **Export overview** for a Markdown file with the record details, deadlines, notes and attachment names. The attachments themselves stay in your library.

## Get help with a window

Open **Lumen Companion**, choose the application window and enter your goal. Inspect the preview before sending it to a vision-capable model. An example question is “Which setting on this screen controls the microphone?” You perform the suggested steps in the application.

If you enable change monitoring, it uses a bounded series of window captures. Pause before entering passwords or showing private information. [Companion setup and limits](INSTALL.md#screen-companion)

## Make it yours

Open **Lumen Settings** to change the interface language, theme, model and optional tools. Reopen a window to pick up a new language. In the personality settings you can choose a preset, adjust how Lumen addresses you and preview a sample reply locally. For memory, decide independently whether to recall entries, learn from conversations or accept suggestions automatically. [Manage personal memory](WISSEN.md)

## Terminal shortcuts

Run `lumen-gitmsg` in a Git checkout to print a proposed commit message. It uses the staged diff, or the unstaged diff if nothing is staged, and sends a bounded excerpt to the configured model. Review sensitive changes before using it. The default invocation prints the suggestion and leaves the commit to you.

[Guide index](docs/README.md) · [Use a file in another app](docs/interop/USAGE.md) · [Install or update](INSTALL.md)
