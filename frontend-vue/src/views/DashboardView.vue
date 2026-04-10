<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import EmptyState from "../components/EmptyState.vue";
import PageHero from "../components/PageHero.vue";
import SectionCard from "../components/SectionCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { apiRequest, normalizeStartUrl, state } from "../lib/store.js";
import { compactUrl, formatShortDate, pluralize } from "../lib/formatters.js";
import { filterConfigForTier } from "../lib/session-config.js";

const router = useRouter();
const sessions = ref([]);
const goal = ref("");
const startUrl = ref("");
const provider = ref("openai");
const model = ref("");
const error = ref("");

const config = reactive({
  mode: "desktop",
  max_steps: 50,
  stop_on_first_error: false,
  max_history_actions: 5,
  loop_detection_enabled: true,
  loop_detection_window: 8,
  postmortem_depth: "standard",
  custom_system_prompt_preamble: "",
});

const tier = computed(() => state.user?.tier || "free");
const providers = computed(() => Object.keys(state.models || {}));
const modelsForProvider = computed(() => state.models?.[provider.value] || []);

const heroMetrics = computed(() => [
  { label: "Tier", value: state.user?.tier || "free", detail: state.user?.role || "user" },
  { label: "Sessions", value: String(sessions.value.length), detail: pluralize(sessions.value.length, "run") },
  { label: "Models", value: String(modelsForProvider.value.length || 0), detail: provider.value },
]);

async function loadSessions() {
  sessions.value = await apiRequest("/sessions");
}

async function createSession() {
  error.value = "";
  try {
    const filteredConfig = filterConfigForTier(config, tier.value);
    const result = await apiRequest("/sessions", {
      method: "POST",
      body: JSON.stringify({
        goal: goal.value,
        start_url: normalizeStartUrl(startUrl.value),
        provider: provider.value,
        model: model.value || (modelsForProvider.value[0] || ""),
        config: filteredConfig,
      }),
    });
    await loadSessions();
    router.push(`/sessions/${result.session_id}`);
  } catch (err) {
    error.value = err.message || "Unable to create session";
  }
}

function rerunFromSession(session) {
  goal.value = session.goal || "";
  startUrl.value = session.start_url || "";
  provider.value = session.provider || provider.value;
  model.value = session.model || model.value;

  let savedConfig = {};
  if (session.config_json) {
    try {
      savedConfig = JSON.parse(session.config_json);
    } catch (_) {
      savedConfig = {};
    }
  }
  Object.assign(config, {
    mode: "desktop",
    max_steps: 50,
    stop_on_first_error: false,
    max_history_actions: 5,
    loop_detection_enabled: true,
    loop_detection_window: 8,
    postmortem_depth: "standard",
    custom_system_prompt_preamble: "",
    ...savedConfig,
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

watch(provider, () => {
  if (!modelsForProvider.value.includes(model.value)) {
    model.value = modelsForProvider.value[0] || "";
  }
});

onMounted(async () => {
  await loadSessions();
  if (!model.value && modelsForProvider.value.length) {
    model.value = modelsForProvider.value[0];
  }
});
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Control center"
      title="Launch, rerun, and review sessions in a single vertical flow."
      body="This dashboard deliberately avoids the old split-pane layout. Compose first, then scroll straight into your recent session library."
      :metrics="heroMetrics"
    />

    <SectionCard
      kicker="New session"
      title="Build the next run"
      body="The composer stays in one stacked card so it behaves the same on desktop and mobile."
    >
      <form class="space-y-5" @submit.prevent="createSession">
        <div>
          <label class="field-label">Goal</label>
          <input v-model="goal" class="field-input" placeholder="Create account, complete checkout, verify onboarding..." required />
        </div>

        <div>
          <label class="field-label">Start URL</label>
          <input v-model="startUrl" class="field-input" placeholder="https://example.com" required />
        </div>

        <div class="grid gap-4 sm:grid-cols-3">
          <div>
            <label class="field-label">Mode</label>
            <select v-model="config.mode" class="field-input">
              <option value="desktop">Desktop</option>
              <option value="mobile">Mobile</option>
            </select>
          </div>
          <div>
            <label class="field-label">Provider</label>
            <select v-model="provider" class="field-input">
              <option v-for="providerOption in providers" :key="providerOption" :value="providerOption">
                {{ providerOption }}
              </option>
            </select>
          </div>
          <div>
            <label class="field-label">Model</label>
            <select v-model="model" class="field-input">
              <option v-for="modelOption in modelsForProvider" :key="modelOption" :value="modelOption">
                {{ modelOption }}
              </option>
            </select>
          </div>
        </div>

        <div class="surface-muted p-4">
          <p class="section-kicker">Run config</p>
          <div class="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label class="field-label">Max steps</label>
              <input v-model.number="config.max_steps" type="number" class="field-input" />
            </div>
            <label class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
              <input v-model="config.stop_on_first_error" type="checkbox" class="rounded border-slate-300 text-brand-500 focus:ring-brand-300" />
              Stop on first error
            </label>
            <template v-if="tier !== 'free'">
              <div>
                <label class="field-label">History actions</label>
                <input v-model.number="config.max_history_actions" type="number" class="field-input" />
              </div>
              <div>
                <label class="field-label">Loop window</label>
                <input v-model.number="config.loop_detection_window" type="number" class="field-input" />
              </div>
              <label class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                <input v-model="config.loop_detection_enabled" type="checkbox" class="rounded border-slate-300 text-brand-500 focus:ring-brand-300" />
                Enable loop detection
              </label>
            </template>
            <div v-if="tier === 'pro'">
              <label class="field-label">Postmortem depth</label>
              <select v-model="config.postmortem_depth" class="field-input">
                <option value="standard">Standard</option>
                <option value="deep">Deep</option>
              </select>
            </div>
          </div>
          <div v-if="tier === 'pro'" class="mt-4">
            <label class="field-label">Custom prompt preamble</label>
            <textarea v-model="config.custom_system_prompt_preamble" class="field-input min-h-32" rows="4" />
          </div>
        </div>

        <button class="primary-button">Create and start</button>
        <p v-if="error" class="text-sm font-medium text-rose-600">{{ error }}</p>
      </form>
    </SectionCard>

    <SectionCard
      kicker="Recent sessions"
      title="Your session library"
      body="Runs stay in one vertical list so the scan path stays predictable."
    >
      <template #actions>
        <button class="ghost-button" @click="loadSessions">Refresh</button>
      </template>

      <EmptyState
        v-if="sessions.length === 0"
        title="No sessions yet"
        body="Launch a session above and it will appear here with status, model, and a quick way to reuse its configuration."
      />

      <div v-else class="space-y-4">
        <article
          v-for="session in sessions"
          :key="session.id"
          class="surface-muted cursor-pointer p-4 transition hover:border-brand-200 hover:bg-white"
          @click="router.push(`/sessions/${session.id}`)"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <h3 class="font-display text-2xl font-semibold text-slate-900">{{ session.goal }}</h3>
              <p class="mt-2 text-sm text-slate-500">{{ compactUrl(session.start_url) }}</p>
              <p class="mt-2 text-sm text-slate-500">{{ session.provider }} / {{ session.model }} | {{ formatShortDate(session.created_at) }}</p>
              <p class="mt-3 text-sm leading-6 text-slate-600">{{ session.end_reason || "Open the session to review screenshots, logs, and postmortem output." }}</p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <StatusBadge :status="session.status" />
              <button class="ghost-button" @click.stop="rerunFromSession(session)">Reuse config</button>
            </div>
          </div>
        </article>
      </div>
    </SectionCard>
  </div>
</template>
