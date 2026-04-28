"use client";

/**
 * Pokročilý editor pro generated_documents.
 *
 * Features (commit 17a):
 * - 4 view modes: Source (MD), Preview (rendered), Split (vedle sebe), WYSIWYG (TipTap)
 * - Toolbar s tlačítky: H1/H2/H3, Bold, Italic, UL, OL, Table, Link, HR
 * - Auto-save debounced 5 s s status indicatorem
 * - PDF download
 *
 * Source of truth = Markdown string. WYSIWYG mode konvertuje přes marked()
 * (MD→HTML) a turndown() (HTML→MD).
 */

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText, Save, Download, Trash2, Sparkles, Database, Loader2,
  Heading1, Heading2, Heading3, Bold, Italic, List, ListOrdered,
  Link as LinkIcon, Minus, Table as TableIcon,
  Code2, Eye, Columns2, Sparkle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Table from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableHeader from "@tiptap/extension-table-header";
import TableCell from "@tiptap/extension-table-cell";
import { marked } from "marked";
import TurndownService from "turndown";

import { api, ApiError } from "@/lib/api";
import type { GeneratedDocument, DocumentType } from "@/types/api";
import { DOCUMENT_TYPE_LABELS } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const TYPE_BADGES: Record<DocumentType, string> = {
  bozp_directive: "bg-purple-100 text-purple-700",
  training_outline: "bg-blue-100 text-blue-700",
  revision_schedule: "bg-emerald-100 text-emerald-700",
  risk_categorization: "bg-amber-100 text-amber-700",
  risk_assessment: "bg-rose-100 text-rose-700",
  operating_log_summary: "bg-cyan-100 text-cyan-700",
  imported: "bg-gray-100 text-gray-700",
};

type ViewMode = "source" | "preview" | "split" | "wysiwyg";

const AUTO_SAVE_DELAY_MS = 5000;

function errMsg(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Chyba serveru";
}

// ── Markdown ↔ HTML helpers (pro WYSIWYG mode) ──────────────────────────────

const turndown = new TurndownService({
  headingStyle: "atx",         // # H1 (ne === underline)
  bulletListMarker: "-",
  codeBlockStyle: "fenced",
  emDelimiter: "*",
});
// GFM rozšíření — turndown defaultně nezná tabulky
turndown.addRule("table", {
  filter: "table",
  replacement: (_content, node) => {
    const rows = Array.from((node as HTMLTableElement).rows);
    if (rows.length === 0) return "";
    const lines: string[] = [];
    rows.forEach((r, idx) => {
      const cells = Array.from(r.cells).map((c) => (c.textContent || "").trim());
      lines.push("| " + cells.join(" | ") + " |");
      if (idx === 0) {
        lines.push("| " + cells.map(() => "---").join(" | ") + " |");
      }
    });
    return "\n" + lines.join("\n") + "\n";
  },
});

function mdToHtml(md: string): string {
  return marked.parse(md, { async: false }) as string;
}

function htmlToMd(html: string): string {
  return turndown.turndown(html);
}

// ── Toolbar ─────────────────────────────────────────────────────────────────

interface ToolbarAction {
  icon: typeof Bold;
  title: string;
  apply: () => void;
}

function MarkdownToolbar({
  textareaRef,
  onChange,
}: {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onChange: (md: string) => void;
}) {
  const wrap = (before: string, after: string = before, placeholder = "text") => () => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const value = ta.value;
    const selected = value.slice(start, end) || placeholder;
    const next = value.slice(0, start) + before + selected + after + value.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      ta.focus();
      ta.selectionStart = start + before.length;
      ta.selectionEnd = start + before.length + selected.length;
    });
  };

  const insertLine = (template: string) => () => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const value = ta.value;
    // Najdi začátek aktuálního řádku
    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    const before = value.slice(0, lineStart);
    const after = value.slice(lineStart);
    const next = before + template + after;
    onChange(next);
    requestAnimationFrame(() => {
      ta.focus();
      ta.selectionStart = ta.selectionEnd = lineStart + template.length;
    });
  };

  const insertAt = (text: string) => () => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const value = ta.value;
    const next = value.slice(0, start) + text + value.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      ta.focus();
      ta.selectionStart = ta.selectionEnd = start + text.length;
    });
  };

  const actions: ToolbarAction[] = [
    { icon: Heading1, title: "Nadpis 1", apply: insertLine("# ") },
    { icon: Heading2, title: "Nadpis 2", apply: insertLine("## ") },
    { icon: Heading3, title: "Nadpis 3", apply: insertLine("### ") },
    { icon: Bold, title: "Tučně", apply: wrap("**", "**", "tučný text") },
    { icon: Italic, title: "Kurzíva", apply: wrap("*", "*", "kurzíva") },
    { icon: List, title: "Seznam", apply: insertLine("- ") },
    { icon: ListOrdered, title: "Číslovaný seznam", apply: insertLine("1. ") },
    { icon: LinkIcon, title: "Odkaz",
      apply: wrap("[", "](https://example.cz)", "text odkazu") },
    { icon: Minus, title: "Horizontální čára", apply: insertAt("\n\n---\n\n") },
    { icon: TableIcon, title: "Tabulka",
      apply: insertAt(
        "\n\n| Sloupec 1 | Sloupec 2 | Sloupec 3 |\n" +
        "| --- | --- | --- |\n" +
        "| buňka | buňka | buňka |\n\n"
      ) },
  ];

  return (
    <div className="flex items-center gap-0.5 px-2 py-1 border-b border-gray-200 bg-gray-50/60">
      {actions.map((a, i) => (
        <button
          key={i}
          onClick={a.apply}
          title={a.title}
          type="button"
          className="rounded p-1.5 text-gray-600 hover:bg-blue-50 hover:text-blue-600 transition-colors"
        >
          <a.icon className="h-4 w-4" />
        </button>
      ))}
    </div>
  );
}

function WysiwygToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null;

  const btn = (active: boolean, onClick: () => void, Icon: typeof Bold, title: string) => (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        "rounded p-1.5 transition-colors",
        active
          ? "bg-blue-100 text-blue-700"
          : "text-gray-600 hover:bg-blue-50 hover:text-blue-600"
      )}
    >
      <Icon className="h-4 w-4" />
    </button>
  );

  return (
    <div className="flex items-center gap-0.5 px-2 py-1 border-b border-gray-200 bg-gray-50/60">
      {btn(editor.isActive("heading", { level: 1 }),
           () => editor.chain().focus().toggleHeading({ level: 1 }).run(),
           Heading1, "Nadpis 1")}
      {btn(editor.isActive("heading", { level: 2 }),
           () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
           Heading2, "Nadpis 2")}
      {btn(editor.isActive("heading", { level: 3 }),
           () => editor.chain().focus().toggleHeading({ level: 3 }).run(),
           Heading3, "Nadpis 3")}
      {btn(editor.isActive("bold"),
           () => editor.chain().focus().toggleBold().run(),
           Bold, "Tučně")}
      {btn(editor.isActive("italic"),
           () => editor.chain().focus().toggleItalic().run(),
           Italic, "Kurzíva")}
      {btn(editor.isActive("bulletList"),
           () => editor.chain().focus().toggleBulletList().run(),
           List, "Seznam")}
      {btn(editor.isActive("orderedList"),
           () => editor.chain().focus().toggleOrderedList().run(),
           ListOrdered, "Číslovaný seznam")}
      {btn(editor.isActive("link"),
           () => {
             const url = window.prompt("URL odkazu:", "https://");
             if (url) editor.chain().focus().setLink({ href: url }).run();
           },
           LinkIcon, "Odkaz")}
      {btn(false,
           () => editor.chain().focus().setHorizontalRule().run(),
           Minus, "Horizontální čára")}
      {btn(false,
           () => editor.chain().focus().insertTable({
             rows: 3, cols: 3, withHeaderRow: true,
           }).run(),
           TableIcon, "Tabulka 3×3")}
    </div>
  );
}

// ── Markdown preview komponent ──────────────────────────────────────────────

function MarkdownPreview({ md }: { md: string }) {
  return (
    <div className="prose prose-sm max-w-none px-6 py-4 overflow-auto h-full bg-white">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="text-2xl font-bold mt-4 mb-3 text-gray-900">{children}</h1>,
          h2: ({ children }) => <h2 className="text-xl font-bold mt-4 mb-2 text-gray-900">{children}</h2>,
          h3: ({ children }) => <h3 className="text-lg font-semibold mt-3 mb-2 text-gray-800">{children}</h3>,
          p: ({ children }) => <p className="my-2 text-sm text-gray-700 leading-relaxed">{children}</p>,
          ul: ({ children }) => <ul className="list-disc ml-5 my-2 text-sm text-gray-700">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal ml-5 my-2 text-sm text-gray-700">{children}</ol>,
          li: ({ children }) => <li className="my-0.5">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          a: ({ href, children }) => (
            <a href={href} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          hr: () => <hr className="my-4 border-gray-200" />,
          table: ({ children }) => (
            <div className="overflow-x-auto my-3">
              <table className="min-w-full border border-gray-200 text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
          th: ({ children }) => <th className="border border-gray-200 px-2 py-1 text-left font-semibold">{children}</th>,
          td: ({ children }) => <td className="border border-gray-200 px-2 py-1 align-top">{children}</td>,
        }}
      >
        {md}
      </ReactMarkdown>
    </div>
  );
}

// ── WYSIWYG (TipTap) panel ──────────────────────────────────────────────────

function WysiwygPanel({
  initialMd,
  onChange,
}: {
  initialMd: string;
  onChange: (md: string) => void;
}) {
  const initialHtml = useMemo(() => mdToHtml(initialMd), [initialMd]);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Link.configure({ openOnClick: false }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: initialHtml,
    immediatelyRender: false,
    onUpdate: ({ editor }) => {
      const html = editor.getHTML();
      const md = htmlToMd(html);
      onChange(md);
    },
    editorProps: {
      attributes: {
        class: "prose prose-sm max-w-none px-6 py-4 focus:outline-none min-h-full",
      },
    },
  });

  // Pokud se externe MD změní (např. po regen), updatuj WYSIWYG content
  useEffect(() => {
    if (!editor) return;
    const currentMd = htmlToMd(editor.getHTML()).trim();
    if (currentMd !== initialMd.trim()) {
      editor.commands.setContent(mdToHtml(initialMd));
    }
  }, [initialMd, editor]);

  if (!editor) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <WysiwygToolbar editor={editor} />
      <div className="flex-1 overflow-auto bg-white">
        <EditorContent editor={editor} className="h-full" />
      </div>
    </div>
  );
}

// ── Hlavní editor ───────────────────────────────────────────────────────────

export function DocumentEditor({ docId }: { docId: string }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [contentMd, setContentMd] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("split");

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);

  const { data: doc, isLoading } = useQuery<GeneratedDocument>({
    queryKey: ["document", docId],
    queryFn: () => api.get(`/documents/${docId}`),
  });

  useEffect(() => {
    if (doc) {
      setTitle(doc.title);
      setContentMd(doc.content_md);
      setDirty(false);
      setSaveStatus("idle");
      setSaveError(null);
    }
  }, [doc]);

  const save = useMutation({
    mutationFn: () =>
      api.patch<GeneratedDocument>(`/documents/${docId}`, {
        title,
        content_md: contentMd,
      }),
    onSuccess: () => {
      setDirty(false);
      setSaveStatus("saved");
      setSaveError(null);
      qc.invalidateQueries({ queryKey: ["documents"] });
      // Reset na "idle" po 2s
      setTimeout(() => setSaveStatus((s) => (s === "saved" ? "idle" : s)), 2000);
    },
    onError: (err) => {
      setSaveStatus("error");
      setSaveError(errMsg(err));
    },
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/documents/${docId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.removeQueries({ queryKey: ["document", docId] });
    },
  });

  const triggerAutoSave = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      setSaveStatus("saving");
      save.mutate();
    }, AUTO_SAVE_DELAY_MS);
  }, [save]);

  const handleContentChange = useCallback((next: string) => {
    setContentMd(next);
    setDirty(true);
    triggerAutoSave();
  }, [triggerAutoSave]);

  const handleTitleChange = (next: string) => {
    setTitle(next);
    setDirty(true);
    triggerAutoSave();
  };

  // Cleanup timer při unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  if (isLoading || !doc) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  // Save status badge
  const statusBadge = (() => {
    if (saveStatus === "saving") {
      return (
        <span className="text-xs text-gray-500 flex items-center gap-1">
          <Loader2 className="h-3 w-3 animate-spin" />
          Ukládá se…
        </span>
      );
    }
    if (saveStatus === "saved") {
      return <span className="text-xs text-green-600">✓ Uloženo</span>;
    }
    if (saveStatus === "error") {
      return <span className="text-xs text-red-600">✗ Chyba uložení</span>;
    }
    if (dirty) {
      return <span className="text-xs text-amber-600">● Změny nejsou uloženy</span>;
    }
    return <span className="text-xs text-gray-400">Auto-save aktivní</span>;
  })();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-4 py-3 flex items-center gap-3">
        <FileText className="h-5 w-5 text-gray-400 shrink-0" />
        <Input
          value={title}
          onChange={(e) => handleTitleChange(e.target.value)}
          className="flex-1 font-semibold border-transparent hover:border-gray-200 focus:border-blue-500"
          placeholder="Název dokumentu"
        />
        <span className={cn(
          "rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
          TYPE_BADGES[doc.document_type]
        )}>
          {DOCUMENT_TYPE_LABELS[doc.document_type].split("(")[0].trim()}
        </span>
      </div>

      {/* Toolbar — view modes + actions */}
      <div className="border-b border-gray-100 bg-gray-50/50 px-4 py-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {/* View mode switcher */}
          <div className="flex items-center rounded-md border border-gray-200 overflow-hidden">
            {([
              { key: "source", label: "MD", icon: Code2 },
              { key: "split",  label: "Split", icon: Columns2 },
              { key: "preview", label: "Náhled", icon: Eye },
              { key: "wysiwyg", label: "WYSIWYG", icon: Sparkle },
            ] as { key: ViewMode; label: string; icon: typeof Bold }[]).map((m) => (
              <button
                key={m.key}
                onClick={() => setViewMode(m.key)}
                className={cn(
                  "flex items-center gap-1 px-2.5 py-1 text-xs font-medium transition-colors",
                  viewMode === m.key
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100"
                )}
              >
                <m.icon className="h-3.5 w-3.5" />
                {m.label}
              </button>
            ))}
          </div>

          <span className="text-xs text-gray-500 truncate">
            {doc.ai_input_tokens != null ? (
              <>
                <Sparkles className="inline h-3 w-3 mr-1 text-blue-500" />
                AI · {doc.ai_input_tokens} in / {doc.ai_output_tokens} out
              </>
            ) : (
              <>
                <Database className="inline h-3 w-3 mr-1 text-emerald-500" />
                Z dat (bez AI)
              </>
            )}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {statusBadge}
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              window.open(`/api/v1/documents/${docId}/pdf?download=true`, "_blank")
            }
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            PDF
          </Button>
          <Button
            size="sm"
            disabled={!dirty || save.isPending}
            loading={save.isPending}
            onClick={() => {
              if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
              setSaveStatus("saving");
              save.mutate();
            }}
          >
            <Save className="h-3.5 w-3.5 mr-1" />
            Uložit
          </Button>
          <button
            onClick={() => {
              if (confirm("Opravdu smazat tento dokument?")) remove.mutate();
            }}
            className="rounded p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
            title="Smazat"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {saveError && (
        <div className="bg-red-50 border-b border-red-200 px-4 py-2 text-sm text-red-700">
          {saveError}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {viewMode === "source" && (
          <div className="h-full flex flex-col">
            <MarkdownToolbar textareaRef={textareaRef} onChange={handleContentChange} />
            <textarea
              ref={textareaRef}
              value={contentMd}
              onChange={(e) => handleContentChange(e.target.value)}
              className="flex-1 w-full px-6 py-4 text-sm font-mono leading-relaxed resize-none focus:outline-none bg-white"
              placeholder="Markdown obsah…"
              spellCheck={false}
            />
          </div>
        )}

        {viewMode === "preview" && (
          <MarkdownPreview md={contentMd} />
        )}

        {viewMode === "split" && (
          <div className="h-full grid grid-cols-2 divide-x divide-gray-200">
            <div className="flex flex-col min-w-0">
              <MarkdownToolbar textareaRef={textareaRef} onChange={handleContentChange} />
              <textarea
                ref={textareaRef}
                value={contentMd}
                onChange={(e) => handleContentChange(e.target.value)}
                className="flex-1 w-full px-4 py-3 text-xs font-mono leading-relaxed resize-none focus:outline-none bg-white"
                placeholder="Markdown obsah…"
                spellCheck={false}
              />
            </div>
            <div className="overflow-hidden min-w-0">
              <MarkdownPreview md={contentMd} />
            </div>
          </div>
        )}

        {viewMode === "wysiwyg" && (
          <WysiwygPanel
            initialMd={contentMd}
            onChange={handleContentChange}
          />
        )}
      </div>
    </div>
  );
}
