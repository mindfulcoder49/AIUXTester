import { reactive } from "./vue-globals.js";

export const store = reactive({
  token: localStorage.getItem("access_token") || "",
  user: null,
  models: {},
});

function extractErrorMessage(text) {
  if (!text) return "Request failed";
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed === "string") return parsed;
    if (parsed.detail) return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    if (parsed.message) return parsed.message;
  } catch (_) {
    return text;
  }
  return text;
}

export async function apiRequest(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (store.token) headers.Authorization = `Bearer ${store.token}`;
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(extractErrorMessage(text) || res.statusText);
  }
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res.text();
}

export async function loadUser() {
  if (!store.token) return;
  try {
    store.user = await apiRequest("/me");
    store.models = await apiRequest("/models");
  } catch (_) {
    logout();
  }
}

export function setToken(token) {
  store.token = token || "";
  if (token) {
    localStorage.setItem("access_token", token);
  } else {
    localStorage.removeItem("access_token");
  }
}

export function logout() {
  setToken("");
  store.user = null;
  store.models = {};
}

export function normalizeStartUrl(raw) {
  const value = (raw || "").trim();
  if (!value) return value;
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("/")) return value;
  return `https://${value}`;
}

export function formatPostmortemValue(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (_) {
    return String(value);
  }
}

export function normalizeEmailHandle(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return "";
  return trimmed.includes("@") ? trimmed : `${trimmed}@aiuxtester.local`;
}
