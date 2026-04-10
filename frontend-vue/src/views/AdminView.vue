<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import EmptyState from "../components/EmptyState.vue";
import PageHero from "../components/PageHero.vue";
import SectionCard from "../components/SectionCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { apiRequest, state } from "../lib/store.js";
import { pluralize } from "../lib/formatters.js";

const router = useRouter();

const tabs = [
  { key: "users", label: "Users" },
  { key: "sessions", label: "Sessions" },
  { key: "memory", label: "Memory" },
  { key: "logs", label: "Logs" },
  { key: "queue", label: "Queue" },
];

const activeTab = ref("users");
const users = ref([]);
const settingPasswordFor = ref(null); // user id
const newPassword = ref("");
const passwordError = ref("");
const passwordSuccess = ref("");
const sessions = ref([]);
const sessionSearch = ref("");
const sessionStatus = ref("");
const sessionLimit = ref(50);
const memory = ref(null);
const memorySessionId = ref("");
const memoryError = ref("");
const logs = ref([]);
const logsSessionId = ref("");
const logsLevel = ref("");
const logsError = ref("");
const queue = ref(null);

const heroMetrics = computed(() => [
  { label: "Role", value: state.user?.role || "admin", detail: state.user?.tier || "pro" },
  { label: "Users", value: String(users.value.length), detail: pluralize(users.value.length, "account") },
  { label: "Sessions", value: String(sessions.value.length), detail: "loaded slice" },
]);

const filteredSessions = computed(() => {
  const query = sessionSearch.value.toLowerCase();
  if (!query) return sessions.value;
  return sessions.value.filter((session) =>
    (session.email || "").toLowerCase().includes(query) ||
    (session.start_url || "").toLowerCase().includes(query) ||
    (session.goal || "").toLowerCase().includes(query)
  );
});

const filteredLogs = computed(() => {
  if (!logsLevel.value) return logs.value;
  return logs.value.filter((entry) => (entry.level || "info") === logsLevel.value);
});

async function loadUsers() {
  users.value = await apiRequest("/admin/users");
}

async function updateTier(user) {
  await apiRequest(`/admin/users/${user.id}/tier`, {
    method: "PATCH",
    body: JSON.stringify({ tier: user.tier }),
  });
}

function openSetPassword(user) {
  settingPasswordFor.value = user.id;
  newPassword.value = "";
  passwordError.value = "";
  passwordSuccess.value = "";
}

async function submitSetPassword(user) {
  passwordError.value = "";
  passwordSuccess.value = "";
  try {
    await apiRequest(`/admin/users/${user.id}/password`, {
      method: "PATCH",
      body: JSON.stringify({ password: newPassword.value }),
    });
    passwordSuccess.value = "Password updated.";
    newPassword.value = "";
  } catch (err) {
    passwordError.value = err.message || "Failed to update password.";
  }
}

async function loadSessions() {
  const params = new URLSearchParams();
  if (sessionStatus.value) params.set("status", sessionStatus.value);
  params.set("limit", String(sessionLimit.value));
  sessions.value = await apiRequest(`/admin/sessions?${params.toString()}`);
}

async function loadMemory() {
  memoryError.value = "";
  memory.value = null;
  if (!memorySessionId.value.trim()) return;
  try {
    memory.value = await apiRequest(`/admin/sessions/${memorySessionId.value.trim()}/memory`);
  } catch (err) {
    memoryError.value = err.message || "Unable to load memory";
  }
}

async function loadLogs() {
  logsError.value = "";
  logs.value = [];
  if (!logsSessionId.value.trim()) return;
  try {
    logs.value = await apiRequest(`/sessions/${logsSessionId.value.trim()}/logs`);
  } catch (err) {
    logsError.value = err.message || "Unable to load logs";
  }
}

async function loadQueue() {
  queue.value = await apiRequest("/admin/queue");
}

async function switchTab(key) {
  activeTab.value = key;
  if (key === "users" && !users.value.length) await loadUsers();
  if (key === "sessions" && !sessions.value.length) await loadSessions();
  if (key === "queue" && !queue.value) await loadQueue();
}

onMounted(async () => {
  await loadUsers();
  await loadSessions();
});
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Admin surface"
      title="Operational visibility without relying on dense split-pane dashboards."
      body="The admin experience stays fully stacked: pick a tab, review one operational slice, then move on."
      :metrics="heroMetrics"
    >
      <template #actions>
        <div class="mb-5 flex flex-wrap gap-3">
          <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="router.push('/app')">
            Back
          </button>
        </div>
      </template>
    </PageHero>

    <SectionCard kicker="Admin tabs" title="Choose a view" body="Only one operational section is shown at a time, which keeps the screen readable on mobile.">
      <div class="flex flex-wrap gap-2">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="rounded-full px-4 py-2 text-sm font-medium transition"
          :class="activeTab === tab.key ? 'bg-brand-500 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>
    </SectionCard>

    <SectionCard v-if="activeTab === 'users'" kicker="Users" :title="`${users.length} accounts`" body="Review account tiers and promote or demote access levels in place.">
      <div class="space-y-4">
        <article v-for="user in users" :key="user.id" class="surface-muted p-4">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div class="min-w-0 flex-1">
              <h3 class="truncate font-display text-2xl font-semibold text-slate-900">{{ user.email }}</h3>
              <p class="mt-2 text-sm text-slate-500">{{ user.role }} | joined {{ (user.created_at || '').slice(0, 10) }}</p>
            </div>
            <div class="flex flex-wrap items-center gap-3 shrink-0">
              <select v-model="user.tier" class="field-input max-w-[9rem]" @change="updateTier(user)">
                <option value="free">free</option>
                <option value="basic">basic</option>
                <option value="pro">pro</option>
              </select>
              <button
                v-if="user.email !== state.user?.email"
                class="ghost-button text-sm"
                @click="settingPasswordFor === user.id ? settingPasswordFor = null : openSetPassword(user)"
              >
                {{ settingPasswordFor === user.id ? 'Cancel' : 'Set password' }}
              </button>
            </div>
          </div>

          <!-- Inline set-password form -->
          <div v-if="settingPasswordFor === user.id" class="mt-4 flex flex-wrap items-center gap-3">
            <input
              v-model="newPassword"
              type="password"
              class="field-input max-w-xs"
              placeholder="New password (min 8 chars)"
              @keyup.enter="submitSetPassword(user)"
            />
            <button class="primary-button" @click="submitSetPassword(user)">Save</button>
            <p v-if="passwordError" class="text-sm font-medium text-rose-600 w-full">{{ passwordError }}</p>
            <p v-if="passwordSuccess" class="text-sm font-medium text-emerald-600 w-full">{{ passwordSuccess }}</p>
          </div>
        </article>
      </div>
    </SectionCard>

    <SectionCard v-if="activeTab === 'sessions'" kicker="Sessions" title="Inspect run inventory" body="Search and filter the stored session list before jumping into a specific replay.">
      <template #actions>
        <button class="ghost-button" @click="loadSessions">Refresh</button>
      </template>

      <div class="grid gap-4 sm:grid-cols-3">
        <input v-model="sessionSearch" class="field-input sm:col-span-2" placeholder="Filter by email, URL, or goal" />
        <select v-model="sessionStatus" class="field-input" @change="loadSessions">
          <option value="">all statuses</option>
          <option value="running">running</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
          <option value="stopped">stopped</option>
          <option value="loop_detected">loop_detected</option>
        </select>
        <select v-model="sessionLimit" class="field-input max-w-xs" @change="loadSessions">
          <option :value="25">25</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="250">250</option>
        </select>
      </div>

      <EmptyState
        v-if="filteredSessions.length === 0"
        class="mt-5"
        title="No sessions match"
        body="Change the search or filters to inspect a different slice of session history."
      />

      <div v-else class="mt-5 space-y-4">
        <article
          v-for="session in filteredSessions"
          :key="session.id"
          class="surface-muted cursor-pointer p-4 transition hover:border-brand-200 hover:bg-white"
          @click="router.push(`/sessions/${session.id}`)"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <h3 class="font-display text-2xl font-semibold text-slate-900">{{ session.goal }}</h3>
              <p class="mt-2 text-sm text-slate-500">{{ session.start_url }}</p>
              <p class="mt-2 text-sm text-slate-500">{{ session.email }} | {{ session.provider }} / {{ session.model }}</p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <StatusBadge :status="session.status" />
              <span class="text-sm text-slate-500">{{ session.action_count }} actions</span>
            </div>
          </div>
        </article>
      </div>
    </SectionCard>

    <SectionCard v-if="activeTab === 'memory'" kicker="Agent memory" title="Load one session's saved memory" body="The memory view stays separate so you can inspect key-value state without the rest of the admin UI competing for space.">
      <div class="flex flex-wrap gap-3">
        <input v-model="memorySessionId" class="field-input min-w-[18rem] flex-1" placeholder="Session ID" @keyup.enter="loadMemory" />
        <button class="primary-button" @click="loadMemory">Load</button>
      </div>
      <div v-if="memory !== null && Object.keys(memory).length" class="mt-5 space-y-3">
        <article v-for="(value, key) in memory" :key="key" class="surface-muted p-4">
          <p class="section-kicker">{{ key }}</p>
          <pre class="mono-copy mt-3">{{ value }}</pre>
        </article>
      </div>
      <EmptyState
        v-else-if="memory !== null"
        class="mt-5"
        title="No memory saved"
        body="This session has not persisted any explicit memory keys."
      />
      <p v-if="memoryError" class="mt-4 text-sm font-medium text-rose-600">{{ memoryError }}</p>
    </SectionCard>

    <SectionCard v-if="activeTab === 'logs'" kicker="Run logs" title="Inspect a session log stream" body="Admin log review uses the same vertical rhythm as the main replay flow.">
      <div class="grid gap-4 sm:grid-cols-3">
        <input v-model="logsSessionId" class="field-input sm:col-span-2" placeholder="Session ID" @keyup.enter="loadLogs" />
        <select v-model="logsLevel" class="field-input">
          <option value="">all levels</option>
          <option value="error">error</option>
          <option value="warning">warning</option>
          <option value="info">info</option>
        </select>
      </div>
      <div class="mt-4">
        <button class="primary-button" @click="loadLogs">Load logs</button>
      </div>
      <div v-if="filteredLogs.length" class="mt-5 space-y-3">
        <article
          v-for="(entry, index) in filteredLogs"
          :key="index"
          class="rounded-2xl border p-4"
          :class="entry.level === 'error'
            ? 'border-rose-200 bg-rose-50'
            : entry.level === 'warning'
              ? 'border-amber-200 bg-amber-50'
              : 'border-slate-200 bg-slate-50'"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <p class="font-medium text-slate-900">{{ entry.level || "info" }}</p>
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">step {{ entry.step_number ?? "-" }}</p>
          </div>
          <p class="mt-3 text-sm leading-6 text-slate-700">{{ entry.message }}</p>
          <p v-if="entry.details" class="mt-2 text-sm leading-6 text-slate-500">{{ entry.details }}</p>
        </article>
      </div>
      <p v-if="logsError" class="mt-4 text-sm font-medium text-rose-600">{{ logsError }}</p>
    </SectionCard>

    <SectionCard v-if="activeTab === 'queue'" kicker="Queue health" title="Redis and worker status" body="Queue metrics stay isolated so they are easy to read on smaller screens.">
      <template #actions>
        <button class="ghost-button" @click="loadQueue">Refresh</button>
      </template>

      <div v-if="queue" class="metric-strip">
        <article class="metric-tile">
          <p class="section-kicker">Redis</p>
          <p class="mt-2 font-display text-3xl font-bold text-slate-900">{{ queue.available ? "yes" : "no" }}</p>
        </article>
        <article v-if="queue.available" class="metric-tile">
          <p class="section-kicker">Queued</p>
          <p class="mt-2 font-display text-3xl font-bold text-slate-900">{{ queue.queued }}</p>
        </article>
        <article v-if="queue.available" class="metric-tile">
          <p class="section-kicker">Active</p>
          <p class="mt-2 font-display text-3xl font-bold text-slate-900">{{ queue.active }}</p>
        </article>
        <article v-if="queue.available" class="metric-tile">
          <p class="section-kicker">Failed</p>
          <p class="mt-2 font-display text-3xl font-bold text-slate-900">{{ queue.failed }}</p>
        </article>
      </div>
      <p v-if="queue?.error" class="mt-4 text-sm font-medium text-rose-600">{{ queue.error }}</p>
    </SectionCard>
  </div>
</template>
