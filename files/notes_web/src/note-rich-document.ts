import { Extension, Node, type JSONContent } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import { Markdown, type MarkdownManager } from "@tiptap/markdown";
import { TableKit } from "@tiptap/extension-table";
import TaskList from "@tiptap/extension-task-list";
import TaskItem from "@tiptap/extension-task-item";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";

const parser = unified().use(remarkParse).use(remarkGfm);
const origins = Extension.create({
  name: "noteOrigins",
  addGlobalAttributes: () => [{types: ["paragraph", "heading", "blockquote", "bulletList", "orderedList", "taskList", "codeBlock", "horizontalRule", "table", "noteProtected"], attributes: {
    noteOrigin: {default: null, rendered: false, keepOnSplit: false},
  }}],
});
const protectedBlock = Node.create({
  name: "noteProtected", group: "block", atom: true,
  addAttributes: () => ({raw: {default: ""}, label: {default: ""}}),
  parseHTML: () => [{tag: "div[data-lumen-note-block]", getAttrs: element => ({raw: element.getAttribute("data-lumen-note-block"), label: element.textContent})}],
  renderHTML: ({node}) => ["div", {class: "note-preserved", "data-lumen-note-block": node.attrs.raw, contenteditable: "false", role: "note"}, node.attrs.label],
  renderMarkdown: node => node.attrs?.raw ?? "",
});
const wikiLink = Node.create({
  name: "noteWikiLink", group: "inline", inline: true, atom: true,
  addAttributes: () => ({raw: {default: ""}, label: {default: ""}}),
  parseHTML: () => [{tag: "span[data-lumen-note-link]", getAttrs: element => ({raw: element.getAttribute("data-lumen-note-link"), label: element.textContent})}],
  renderHTML: ({node}) => ["span", {class: "note-wikilink", "data-lumen-note-link": node.attrs.raw}, node.attrs.label],
  markdownTokenizer: {
    name: "noteWikiLink", level: "inline", start: src => src.indexOf("[["),
    tokenize(src) {
      const match = /^\[\[([^\]\n]+)\]\]/.exec(src);
      return match ? {type: "noteWikiLink", raw: match[0], text: match[1]} : undefined;
    },
  },
  parseMarkdown: token => ({type: "noteWikiLink", attrs: {raw: token.raw, label: String(token.text).split("|").at(-1)}}),
  renderMarkdown: node => node.attrs?.raw ?? "",
});
// Match Desktop's portable underline representation, rather than a new Markdown dialect.
const underline = Underline.extend({renderMarkdown: (node, helpers) => `<u>${helpers.renderChildren(node)}</u>`, markdownTokenizer: undefined});
export function noteExtensions() {
  return [StarterKit.configure({underline: false, trailingNode: false, link: {openOnClick: false, autolink: false}}),
    underline, TableKit.configure({table: {resizable: false}}), TaskList, TaskItem.configure({nested: true, a11y: {checkboxLabel: node => node.textContent}}), Markdown, origins, protectedBlock, wikiLink];
}
export function splitNote(text: string) {
  const header = /^---\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)/.exec(text)?.[0] ?? "";
  return {header, body: text.slice(header.length)};
}
function fingerprint(node: JSONContent): string {
  return JSON.stringify(node, (key, value) => key === "noteOrigin" ? undefined : value);
}
type SyntaxNode = {type: string; value?: string; children?: SyntaxNode[]; [key: string]: unknown};
function semantic(node: SyntaxNode): unknown {
  // Markdown spelling and list spacing can change without changing their meaning.
  return Object.fromEntries(Object.entries(node).filter(([key]) => !["position", "spread", "data"].includes(key))
    .map(([key, value]) => [key, key === "children" ? (value as SyntaxNode[]).map(semantic) : value]));
}
function hasUnknownHTML(node: SyntaxNode): boolean {
  return (node.type === "html" && !/^<\/?u>$/i.test(node.value ?? "")) || (node.children?.some(hasUnknownHTML) ?? false);
}
function syntax(text: string) { return JSON.stringify(semantic(parser.parse(text) as SyntaxNode)); }
function preview(node: SyntaxNode): string {
  if (node.type === "image") return String(node.alt ?? "");
  if (node.type === "html" || node.type === "definition") return "";
  return node.children?.map(preview).join(node.type === "root" || node.type === "list" ? "\n" : "") ?? node.value ?? "";
}
export function noteSummary(source: string) {
  return preview(parser.parse(splitNote(source).body.slice(0, 2000)) as SyntaxNode).replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_all, target, alias) => alias || target).replace(/\s+/g, " ").trim();
}
export class NoteRichDocument {
  header = "";
  body = "";
  original: JSONContent = {type: "doc", content: []};
  private blocks = new Map<string, {raw: string; gap: string; json: string}>();
  private leading = "";
  constructor(private markdown: MarkdownManager, private protectedLabel: string, private normalize: (node: JSONContent) => JSONContent = node => node) {}
  load(source: string): JSONContent {
    const {header, body} = splitNote(source); this.header = header; this.body = body;
    this.blocks.clear();
    const tree = parser.parse(body);
    this.leading = body.slice(0, tree.children[0]?.position?.start.offset ?? body.length);
    const content = tree.children.map((ast, index) => {
      const start = ast.position!.start.offset!, end = ast.position!.end.offset!;
      const raw = body.slice(start, end), gap = body.slice(end, tree.children[index + 1]?.position?.start.offset ?? body.length);
      let parsed: JSONContent | undefined;
      try {
        const supported = !hasUnknownHTML(ast as SyntaxNode) &&
          !/"type":"(?:image|imageReference|linkReference|footnoteReference|footnoteDefinition|definition)"/.test(JSON.stringify(ast)) &&
          !/!\[\[|%%|(?:^|\s)\^[\w-]+\s*$|^>\s*\[!|^\s*\$\$/m.test(raw);
        if (supported) {
          const result = this.markdown.parse(raw);
          // A structural roundtrip prevents an editor schema from silently dropping imported content.
          if (result.content?.length === 1 && syntax(raw) === syntax(this.markdown.serialize(result))) parsed = result.content[0];
        }
      } catch { /* Preserve unsupported syntax as one immutable block. */ }
      let node = parsed ?? {type: "noteProtected", attrs: {raw, label: preview(ast as SyntaxNode).replace(/%%[\s\S]*?%%/g, "").replace(/\[![^\]]+\]/g, "").replace(/\s+\^[\w-]+\s*$/, "").replace(/!\[\[/g, "[[").replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_all, target, alias) => alias || target).trim() || this.protectedLabel}};
      const key = String(index);
      node.attrs = {...node.attrs, noteOrigin: key};
      node = this.normalize({type: "doc", content: [node]}).content![0];
      this.blocks.set(key, {raw, gap, json: fingerprint(node)});
      return node;
    });
    this.original = this.normalize({type: "doc", content: content.length ? content : [{type: "paragraph"}]});
    return this.original;
  }
  save(doc: JSONContent): string {
    if (fingerprint(doc) === fingerprint(this.original)) return this.header + this.body;
    const content = doc.content ?? [];
    const used = new Set<string>();
    return this.header + this.leading + content.map((node, index) => {
      const key = node.attrs?.noteOrigin;
      const prior = used.has(key) ? undefined : this.blocks.get(key);
      used.add(key);
      const raw = prior?.json === fingerprint(node) ? prior.raw : this.markdown.serialize({type: "doc", content: [node]});
      const adjacent = content[index + 1]?.attrs?.noteOrigin === String(Number(key) + 1);
      const separator = /(?:\r?\n){2}/.test(prior?.gap ?? "") ? prior!.gap : (this.body.includes("\r\n") ? "\r\n\r\n" : "\n\n");
      const gap = index === content.length - 1 ? (prior?.gap ?? "") : adjacent && prior ? prior.gap : separator;
      return raw + gap;
    }).join("");
  }
}
