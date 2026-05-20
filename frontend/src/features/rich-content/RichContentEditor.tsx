import { useRef, useState } from "react";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "tiptap-markdown";

import { uploadAttachment, type AttachmentUploadResponse } from "./api";
import { renderRichContent } from "./render";

type Mode = "rich" | "markdown";
type MarkdownCapableEditor = {
  storage: {
    markdown: {
      getMarkdown: () => string;
    };
  };
};

interface RichContentEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  minRows?: number;
  uploadFile?: (file: File) => Promise<AttachmentUploadResponse>;
}

export function RichContentEditor({
  value,
  onChange,
  placeholder = "Write content, paste images, or attach files.",
  disabled = false,
  minRows = 8,
  uploadFile = uploadAttachment,
}: RichContentEditorProps) {
  const [mode, setMode] = useState<Mode>("rich");
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Link.configure({ autolink: true, openOnClick: false }),
      Image,
      Placeholder.configure({ placeholder }),
      Markdown.configure({ html: false }),
    ],
    content: value,
    editable: !disabled,
    onUpdate({ editor }) {
      onChange((editor as unknown as MarkdownCapableEditor).storage.markdown.getMarkdown());
    },
    editorProps: {
      handlePaste(_view, event) {
        const files = Array.from(event.clipboardData?.files ?? []);
        if (!files.length) {
          return false;
        }
        files.forEach((file) => insertFile(file));
        return true;
      },
    },
  });

  function syncEditor(nextValue: string) {
    if (editor && (editor as unknown as MarkdownCapableEditor).storage.markdown.getMarkdown() !== nextValue) {
      editor.commands.setContent(nextValue);
    }
  }

  async function insertFile(file: File) {
    setUploadError("");
    try {
      const uploaded = await uploadFile(file);
      const isImage = uploaded.is_image || file.type.startsWith("image/");
      if (mode === "markdown" || !editor) {
        const markdown = isImage ? `![${file.name}](${uploaded.url})` : `[${file.name}](${uploaded.url})`;
        onChange(`${value}${value ? "\n\n" : ""}${markdown}`);
        return;
      }
      if (isImage) {
        editor.chain().focus().setImage({ src: uploaded.url, alt: file.name }).run();
        return;
      }
      editor.chain().focus().insertContent([
        {
          type: "text",
          text: uploaded.filename || file.name,
          marks: [{ type: "link", attrs: { href: uploaded.url, target: "_blank", rel: "noopener noreferrer nofollow" } }],
        },
      ]).run();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed.");
    }
  }

  function wrapMarkdown(prefix: string, suffix = prefix) {
    onChange(`${value}${value ? "\n" : ""}${prefix}text${suffix}`);
  }

  function insertLink() {
    const href = window.prompt("URL");
    if (!href) {
      return;
    }
    if (mode === "markdown" || !editor) {
      onChange(`${value}${value ? "\n" : ""}[link](${href})`);
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
  }

  return (
    <section className="rich-content-editor">
      <div className="rich-editor-toolbar">
        <button type="button" className={mode === "rich" ? "active" : ""} onClick={() => { setMode("rich"); syncEditor(value); }}>
          Rich
        </button>
        <button type="button" className={mode === "markdown" ? "active" : ""} onClick={() => setMode("markdown")}>
          Markdown
        </button>
        <button type="button" onClick={() => mode === "rich" ? editor?.chain().focus().toggleBold().run() : wrapMarkdown("**")}>
          B
        </button>
        <button type="button" onClick={() => mode === "rich" ? editor?.chain().focus().toggleItalic().run() : wrapMarkdown("*")}>
          I
        </button>
        <button type="button" onClick={() => mode === "rich" ? editor?.chain().focus().toggleBulletList().run() : wrapMarkdown("- ", "")}>
          List
        </button>
        <button type="button" onClick={insertLink}>
          Link
        </button>
        <button type="button" onClick={() => imageInputRef.current?.click()}>
          Image
        </button>
        <button type="button" onClick={() => fileInputRef.current?.click()}>
          File
        </button>
        <input ref={imageInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void insertFile(file);
          event.target.value = "";
        }} />
        <input ref={fileInputRef} type="file" onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void insertFile(file);
          event.target.value = "";
        }} />
      </div>
      {mode === "rich" ? (
        <EditorContent editor={editor} className="rich-editor-surface" />
      ) : (
        <textarea
          className="rich-markdown-textarea"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          rows={minRows}
          placeholder={placeholder}
          disabled={disabled}
        />
      )}
      {uploadError ? <small className="field-error">{uploadError}</small> : null}
    </section>
  );
}

export function RichContentPreview({ markdown, className = "" }: { markdown: string; className?: string }) {
  const html = renderRichContent(markdown);
  return <div className={`rich-content-preview ${className}`} dangerouslySetInnerHTML={{ __html: html }} />;
}
