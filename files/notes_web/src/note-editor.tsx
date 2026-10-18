import { useLayoutEffect, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import { EditorState } from "@tiptap/pm/state";
import { Bold, Italic, Underline, List, ListOrdered, ListTodo, Quote, Link, Table, Undo2, Redo2 } from "lucide-react";
import { tr, useLanguage } from "./i18n";
import { NoteRichDocument, noteExtensions, splitNote } from "./note-rich-document";

export function NoteEditor({value, readOnly, onChange}: {
  value: string; readOnly: boolean; onChange: (text: string) => void;
}) {
  const language = useLanguage();
  const current = useRef({value, readOnly, onChange}); current.current = {value, readOnly, onChange};
  const codec = useRef<NoteRichDocument | null>(null);
  const emitted = useRef(value);
  const [outline, setOutline] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState("");
  const editor = useEditor({
    extensions: noteExtensions(),
    shouldRerenderOnTransaction: true,
    editorProps: {attributes: {class: "note-rich-text markdown", role: "textbox", "aria-multiline": "true", "aria-label": tr("Notiztext")}},
    onUpdate({editor}) {
      if (current.current.readOnly || !codec.current) return;
      const next = codec.current.save(editor.getJSON());
      emitted.current = next;
      if (next !== current.current.value) current.current.onChange(next);
    },
  });
  useLayoutEffect(() => {
    if (!editor) return;
    editor.setEditable(!readOnly, false);
    editor.view.dom.setAttribute("aria-readonly", String(readOnly));
    editor.view.dom.setAttribute("aria-label", tr("Notiztext"));
    if (readOnly) setLink(null);
  }, [editor, readOnly, language]);
  useLayoutEffect(() => {
    if (!editor || (codec.current && emitted.current === value)) return;
    const next = splitNote(value);
    if (codec.current && splitNote(emitted.current).body === next.body) {
      // Tags edit frontmatter independently; retain the cursor and undo history in the body.
      codec.current.header = next.header;
    } else {
      const document = new NoteRichDocument(editor.markdown!, tr("Eingebetteter Inhalt · unverändert erhalten"), json => editor.schema.nodeFromJSON(json).toJSON());
      const json = document.load(value); codec.current = document;
      editor.view.updateState(EditorState.create({doc: editor.schema.nodeFromJSON(json), plugins: editor.state.plugins}));
      editor.commands.setMeta("addToHistory", false);
      setLink(null);
    }
    emitted.current = value;
  }, [editor, value]);
  if (!editor) return <p role="status">{tr("Notiz wird geladen …")}</p>;
  const headings: {position: number; title: string; level: number}[] = [];
  editor.state.doc.forEach((node, position) => {
    if (node.type.name === "heading") headings.push({position, title: node.textContent, level: node.attrs.level});
  });
  function button(label: string, icon: React.ReactNode, action: () => unknown, active?: boolean, disabled = false) {
    return <button type="button" title={tr(label)} aria-label={tr(label)} aria-pressed={active}
      disabled={readOnly || disabled} onMouseDown={e => e.preventDefault()} onClick={() => {setError(""); action();}}>{icon}</button>;
  }
  return <div className="note-editor">
    <div className="note-format-bar" role="group" aria-label={tr("Notiz formatieren")}>
      <select aria-label={tr("Textstil")} disabled={readOnly}
        value={editor.isActive("heading") ? String(editor.getAttributes("heading").level) : "0"}
        onChange={e => {
          const level = Number(e.target.value) as 1 | 2 | 3;
          if (level) editor.chain().focus().setHeading({level}).run();
          else editor.chain().focus().setParagraph().run();
        }}>
        <option value="0">{tr("Normaler Text")}</option>
        {[1,2,3,4,5,6].map(n => <option key={n} value={n}>{tr("Überschrift")} {n}</option>)}
      </select>
      {button("Fett", <Bold size={18}/>, () => editor.chain().focus().toggleBold().run(), editor.isActive("bold"))}
      {button("Kursiv", <Italic size={18}/>, () => editor.chain().focus().toggleItalic().run(), editor.isActive("italic"))}
      {button("Unterstrichen", <Underline size={18}/>, () => editor.chain().focus().toggleUnderline().run(), editor.isActive("underline"))}
      <span className="note-toolbar-separator"/>
      {button("Liste", <List size={18}/>, () => editor.chain().focus().toggleBulletList().run(), editor.isActive("bulletList"))}
      {button("Nummerierte Liste", <ListOrdered size={18}/>, () => editor.chain().focus().toggleOrderedList().run(), editor.isActive("orderedList"))}
      {button("Aufgabe", <ListTodo size={18}/>, () => editor.chain().focus().toggleTaskList().run(), editor.isActive("taskList"))}
      {button("Zitat", <Quote size={18}/>, () => editor.chain().focus().toggleBlockquote().run(), editor.isActive("blockquote"))}
      {button("Link bearbeiten", <Link size={18}/>, () => setLink(editor.getAttributes("link").href ?? ""), editor.isActive("link"))}
      {button("Tabelle", <Table size={18}/>, () => editor.chain().focus().insertTable({rows: 3, cols: 2, withHeaderRow: true}).run(), undefined, editor.isActive("table"))}
      <span className="note-toolbar-separator"/>
      {button("Rückgängig", <Undo2 size={18}/>, () => editor.chain().focus().undo().run(), undefined, !editor.can().undo())}
      {button("Wiederholen", <Redo2 size={18}/>, () => editor.chain().focus().redo().run(), undefined, !editor.can().redo())}
      <button type="button" aria-pressed={outline} onClick={() => setOutline(!outline)}>{tr("Gliederung")}</button>
    </div>
    {link !== null && <form className="inline-actions note-link-form" onSubmit={e => {
      e.preventDefault(); if (readOnly) return;
      const href = link.trim();
      if (href && !/^(https?:\/\/|mailto:)/i.test(href)) {setError(tr("Bitte eine https://-Adresse oder mailto:-Adresse eingeben.")); return;}
      if (href) {
        if (editor.state.selection.empty && !editor.isActive("link")) editor.chain().focus().insertContent({type: "text", text: href, marks: [{type: "link", attrs: {href}}]}).run();
        else editor.chain().focus().extendMarkRange("link").setLink({href}).run();
      } else editor.chain().focus().extendMarkRange("link").unsetLink().run();
      setError(""); setLink(null);
    }}>
      <label>{tr("Link-Adresse")}<input autoFocus type="text" value={link} onChange={e => setLink(e.target.value)} placeholder="https://" onKeyDown={e => {if(e.key === "Escape") {setLink(null); editor.commands.focus();}}}/></label>
      <button type="submit" disabled={readOnly}>{tr("Übernehmen")}</button>
      <button type="button" onClick={() => {setLink(null); editor.commands.focus();}}>{tr("Abbrechen")}</button>
    </form>}
    {error && <p role="alert">{error}</p>}
    {editor.isActive("table") && <div className="inline-actions note-table-actions" role="group" aria-label={tr("Tabelle bearbeiten")}>
      <button type="button" disabled={readOnly} onClick={() => editor.chain().focus().addRowAfter().run()}>{tr("Zeile hinzufügen")}</button>
      <button type="button" disabled={readOnly} onClick={() => editor.chain().focus().addColumnAfter().run()}>{tr("Spalte hinzufügen")}</button>
      <button type="button" disabled={readOnly} onClick={() => editor.chain().focus().deleteRow().run()}>{tr("Zeile entfernen")}</button>
      <button type="button" disabled={readOnly} onClick={() => editor.chain().focus().deleteColumn().run()}>{tr("Spalte entfernen")}</button>
      <button type="button" disabled={readOnly} onClick={() => editor.chain().focus().deleteTable().run()}>{tr("Tabelle entfernen")}</button>
    </div>}
    {outline && <nav aria-label={tr("Gliederung")} className="note-outline">{headings.length ? headings.map(h =>
      <button type="button" key={h.position} style={{paddingInlineStart: `${h.level}em`}} onClick={() => editor.chain().focus().setTextSelection(h.position + 1).scrollIntoView().run()}>{h.title}</button>
    ) : <p className="muted">{tr("Noch keine Überschriften")}</p>}</nav>}
    <EditorContent editor={editor}/>
    <p className="muted note-writing-hint">{readOnly ? tr("Diese Notiz ist schreibgeschützt.") : tr("Direkt schreiben · Text markieren und oben formatieren")}</p>
  </div>;
}
