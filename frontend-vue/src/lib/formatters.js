export function compactUrl(value) {
  return (value || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
}

export function prettyStatus(value) {
  return (value || "unknown").replace(/_/g, " ");
}

export function pluralize(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
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

export function formatPercent(value, digits = 0) {
  const numeric = Number(value || 0);
  return `${(numeric * 100).toFixed(digits)}%`;
}
