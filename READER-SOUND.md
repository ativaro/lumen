# Reader and Sound

## Reader

Open **Lumen Reader** or right-click a document in Files and choose **Open with → Lumen Reader**. You can also run `lumen-reader "/path/to/book.epub"`. Reader imports a copy into your private library and remembers your position. Importing a changed original creates a new library entry.

- **Read and navigate.** Open a PDF, EPUB, text, Markdown, HTML or supported Office document. Use the outline, search, zoom or page-width controls. Reading mode hides the sidebars. A PDF keeps its page layout. An imported web article is saved as readable text.
- **Mark a passage.** Select text on a page or in text view and choose Highlight. Add a margin note or bookmark the current page. Export notes as Markdown when you want a copy outside the library.
- **Listen.** Select a passage or open a page and choose Read aloud. Set up a local Piper voice first. Pause or stop playback from Reader.
- **Read a scan.** Image-only pages can display, but highlighting, text search and speech require readable text. Create a searchable copy in the [Files document workshop](files/README.md#work-with-pdfs).

Reader's library lives under `$XDG_DATA_HOME/lumen-tools/reader`, usually `~/.local/share/lumen-tools/reader`. A password entered for a PDF stays in memory for the open session. The imported copy keeps its encryption. Notes you write about it can contain readable excerpts. Archiving an item keeps it in the library.

## Sound

Open **Lumen System → Sound** or run `lumen-sound`. Start playback in the application you want to adjust so its stream appears.

1. Select the application stream. Change its volume, mute it or choose an available output.
2. To reuse those choices, save a rule for that app. Several tabs in a browser can share the same application identity.
3. To lower music during a call, give the player the music role and the calling app the call role, then choose the reduction. Activate and apply the rules for this login or for every login.

Automatic rules are off initially. Call detection uses audio-stream metadata such as an active recording stream. It does not record your call. If an app leaves its microphone open, the reduction can last longer than the call. Disabling the automation restores temporarily lowered music. Explicit volume and output changes stay in effect.

[Guide index](docs/README.md)
