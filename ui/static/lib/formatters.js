export function prettyStatus(status) {
  return (status || "unknown").replace(/_/g, " ");
}

export function pluralize(count, singular, plural) {
  return `${count} ${count === 1 ? singular : (plural || `${singular}s`)}`;
}

export function formatShortDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function compactUrl(value) {
  return (value || "")
    .replace(/^https?:\/\//, "")
    .replace(/\/$/, "");
}
