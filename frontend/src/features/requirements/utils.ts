export function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(value));
}

export function normalize(value: string) {
  return value.trim().toLowerCase();
}
