import { computed, reactive } from "vue";

export const state = reactive({
  token: localStorage.getItem("access_token") || "",
  user: null,
  models: {},
  authBootstrapped: false,
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
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(extractErrorMessage(text) || response.statusText);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

export function setToken(token) {
  state.token = token || "";
  if (token) {
    localStorage.setItem("access_token", token);
  } else {
    localStorage.removeItem("access_token");
  }
}

export function clearAuth() {
  setToken("");
  state.user = null;
  state.models = {};
}

export async function loadUser() {
  if (!state.token) {
    state.authBootstrapped = true;
    return;
  }
  try {
    state.user = await apiRequest("/me");
    state.models = await apiRequest("/models");
  } catch (_) {
    clearAuth();
  } finally {
    state.authBootstrapped = true;
  }
}

export async function bootstrapAuth() {
  if (state.authBootstrapped) return;
  await loadUser();
}

export async function ensureUserLoaded() {
  if (!state.authBootstrapped) {
    await loadUser();
  }
}

export function normalizeStartUrl(raw) {
  const value = (raw || "").trim();
  if (!value) return value;
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("/")) return value;
  return `https://${value}`;
}

export function normalizeEmailHandle(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) return "";
  return trimmed.includes("@") ? trimmed : `${trimmed}@aiuxtester.local`;
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

export const isAdmin = computed(() => state.user?.role === "admin");
