import { API_BASE_URL } from "../../api/client";

export function renderRichContent(markdown: string) {
  return markdown
    .split(/\n{2,}/)
    .map((block) => {
      const escaped = escapeHtml(block.trim());
      if (!escaped) return "";
      if (escaped.startsWith("- ")) {
        const items = escaped
          .split("\n")
          .map((line) => `<li>${renderInline(line.replace(/^- /, ""))}</li>`)
          .join("");
        return `<ul>${items}</ul>`;
      }
      return `<p>${renderInline(escaped).replace(/\n/g, "<br />")}</p>`;
    })
    .join("");
}

export function normalizeAttachmentUrl(url: string) {
  const readableUrl = url.replace(/&amp;/g, "&");
  if (readableUrl.includes("/api/v1/attachments/") || readableUrl.includes("/api/v1/task-assets/images/")) {
    return readableUrl;
  }
  const attachmentObject = readableUrl.match(/\/(?:featurevote\/)?(attachments\/[^?#]+)/)?.[1];
  if (attachmentObject) {
    return `${API_BASE_URL}/attachments/${attachmentObject}`;
  }
  const taskImageObject = readableUrl.match(/\/(?:featurevote\/)?(task-images\/[^?#]+)/)?.[1];
  if (taskImageObject) {
    return `${API_BASE_URL}/task-assets/images/${taskImageObject}`;
  }
  return url;
}

function renderInline(value: string) {
  const urlPattern = "((?:https?:\\/\\/|\\/)[^)]+)";
  const withImages = value.replace(
    new RegExp(`!\\[([^\\]]*)\\]\\(${urlPattern}\\)`, "g"),
    (_match: string, alt: string, url: string) => `<img src="${normalizeAttachmentUrl(url)}" alt="${alt}" />`,
  );
  const withLinks = withImages.replace(
    new RegExp(`\\[([^\\]]+)\\]\\(${urlPattern}\\)`, "g"),
    (_match: string, label: string, url: string) =>
      `<a href="${normalizeAttachmentUrl(url)}" target="_blank" rel="noreferrer">${label}</a>`,
  );
  const withBold = withLinks.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return withBold.replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
