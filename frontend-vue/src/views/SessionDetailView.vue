<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import EmptyState from "../components/EmptyState.vue";
import PageHero from "../components/PageHero.vue";
import SectionCard from "../components/SectionCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import {
  apiRequest,
  formatPostmortemValue,
  state,
} from "../lib/store.js";
import { compactUrl, prettyStatus, pluralize } from "../lib/formatters.js";

const route = useRoute();
const router = useRouter();

const session = ref(null);
const steps = ref([]);
const postmortem = ref(null);
const logs = ref([]);
const showSubmitModal = ref(false);
const openCompetitions = ref([]);
const submitCompetitionId = ref("");
const submitNote = ref("");
const submitError = ref("");
const submitSuccess = ref(false);

const showExportModal = ref(false);
const exportAppName = ref("");
const exportAppDescription = ref("");
const exportLoading = ref(false);
const exportError = ref("");
const exportSuccess = ref(false);

const terminalStatuses = new Set(["completed", "failed", "stopped", "loop_detected"]);
const isTerminal = computed(() => terminalStatuses.has(session.value?.status));

const heroMetrics = computed(() => [
  { label: "Status", value: prettyStatus(session.value?.status || "running"), detail: session.value?.end_reason || "In progress" },
  { label: "Steps", value: String(steps.value.length), detail: pluralize(steps.value.length, "capture") },
  { label: "Logs", value: String(logs.value.length), detail: postmortem.value ? "Postmortem ready" : "Analysis pending" },
]);

let eventSource = null;
let refreshTimer = null;

function mapLog(entry) {
  return {
    level: entry.level,
    message: entry.message,
    details: entry.details,
    step: entry.step_number ?? entry.step ?? null,
    isPrompt: entry.message === "LLM prompt payload",
  };
}

function setStepsFromPayload(data) {
  const actionByStep = {};
  (data.actions || []).forEach((action) => {
    actionByStep[action.step_number] = action;
  });
  steps.value = (data.screenshots || []).map((shot) => ({
    id: shot.id,
    step: shot.step_number,
    action: shot.action_taken,
    url: shot.url,
    intent: actionByStep[shot.step_number]?.intent || "",
    reasoning: actionByStep[shot.step_number]?.reasoning || "",
    image: `/screenshots/${shot.id}?token=${state.token}`,
  }));
}

function pushStep(candidate) {
  const existing = steps.value.find((step) => String(step.id) === String(candidate.id));
  if (!existing) {
    steps.value.push(candidate);
  }
}

async function loadSession() {
  const data = await apiRequest(`/sessions/${route.params.id}`);
  session.value = data.session;
  setStepsFromPayload(data);
  logs.value = (data.logs || []).map(mapLog);
  try {
    const report = await apiRequest(`/sessions/${route.params.id}/postmortem`);
    postmortem.value = report
      ? {
          run_analysis: report.run_analysis || "",
          html_analysis: report.html_analysis || "",
          recommendations: report.recommendations || "",
        }
      : null;
  } catch (_) {
    postmortem.value = null;
  }
}

function connectStream() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/sessions/${route.params.id}/stream?token=${state.token}`);
  eventSource.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "step") {
      pushStep({
        id: message.data.screenshot_id,
        step: message.data.step,
        action: message.data.action,
        url: message.data.url,
        intent: message.data.intent || "",
        reasoning: message.data.reasoning || "",
        image: `/screenshots/${message.data.screenshot_id}?token=${state.token}`,
      });
    }
    if (message.type === "postmortem") {
      postmortem.value = message.data;
    }
    if (message.type === "status" && session.value) {
      session.value.status = message.data.status;
      session.value.end_reason = message.data.end_reason;
    }
    if (message.type === "log") {
      logs.value.push(mapLog({
        level: message.data.level || "info",
        message: message.data.message,
        details: message.data.details || "",
        step: message.data.step,
      }));
    }
    if (message.type === "error") {
      logs.value.push(mapLog({
        level: "error",
        message: "Runtime error",
        details: message.data.message || "",
      }));
    }
  };
}

function startRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(async () => {
    if (!session.value || terminalStatuses.has(session.value.status)) return;
    try {
      await loadSession();
    } catch (_) {}
  }, 3000);
}

async function openSubmitModal() {
  submitError.value = "";
  submitSuccess.value = false;
  submitNote.value = "";
  const competitions = await apiRequest("/competitions");
  openCompetitions.value = competitions.filter((competition) => competition.status === "open");
  submitCompetitionId.value = openCompetitions.value[0]?.id || "";
  showSubmitModal.value = true;
}

async function submitToCompetition() {
  submitError.value = "";
  submitSuccess.value = false;
  try {
    await apiRequest(`/competitions/${submitCompetitionId.value}/entries`, {
      method: "POST",
      body: JSON.stringify({ session_id: session.value.id, note: submitNote.value }),
    });
    submitSuccess.value = true;
  } catch (err) {
    submitError.value = err.message || "Unable to submit session";
  }
}

async function stop() {
  if (!session.value || isTerminal.value) return;
  await apiRequest(`/sessions/${session.value.id}/stop`, { method: "POST" });
}

function openExportModal() {
  exportAppName.value = "";
  exportAppDescription.value = "";
  exportError.value = "";
  exportSuccess.value = false;
  showExportModal.value = true;
}

async function exportToVibecode() {
  exportError.value = "";
  exportSuccess.value = false;
  exportLoading.value = true;
  try {
    await apiRequest(`/sessions/${session.value.id}/export-to-vibecode`, {
      method: "POST",
      body: JSON.stringify({
        app_name: exportAppName.value.trim() || null,
        app_description: exportAppDescription.value.trim() || null,
      }),
    });
    exportSuccess.value = true;
  } catch (err) {
    exportError.value = err.message || "Export failed";
  } finally {
    exportLoading.value = false;
  }
}

onMounted(async () => {
  await loadSession();
  if (!isTerminal.value) {
    connectStream();
    startRefresh();
  }
});

onBeforeUnmount(() => {
  if (eventSource) eventSource.close();
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Session replay"
      :title="session?.goal || 'Session detail'"
      :body="`${compactUrl(session?.start_url || '')} | ${session?.provider || '-'} / ${session?.model || '-'}`"
      :metrics="heroMetrics"
    >
      <template #actions>
        <div class="mb-5 flex flex-wrap gap-3">
          <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="router.push('/app')">
            Back to dashboard
          </button>
          <StatusBadge v-if="session" :status="session.status" />
          <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="stop" :disabled="!session || isTerminal">
            Stop
          </button>
          <button v-if="isTerminal" class="primary-button" @click="openSubmitModal">
            Submit to competition
          </button>
          <button v-if="isTerminal" class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="openExportModal">
            Export to VibeCode
          </button>
        </div>
      </template>
    </PageHero>

    <SectionCard
      kicker="Live stream"
      title="Action timeline"
      body="The replay stays in a single stack so the reasoning, screenshot, and current URL stay aligned while you scroll."
    >
      <EmptyState
        v-if="steps.length === 0"
        title="Waiting for first step"
        body="As soon as the agent captures evidence, the timeline will populate with screenshots, intent, and reasoning."
      />

      <div v-else class="space-y-4">
        <article v-for="step in steps" :key="step.id || `step-${step.step}-${step.action}`" class="surface-muted overflow-hidden">
          <div class="border-b border-slate-200 px-5 py-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p class="section-kicker">Step {{ step.step }}</p>
                <h3 class="mt-1 font-display text-2xl font-semibold text-slate-900">{{ step.action }}</h3>
              </div>
              <p class="text-sm text-slate-500">{{ compactUrl(step.url || "") }}</p>
            </div>
            <div v-if="step.intent || step.reasoning" class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <p v-if="step.intent"><strong class="mr-2 text-slate-800">Intent:</strong>{{ step.intent }}</p>
              <p v-if="step.reasoning"><strong class="mr-2 text-slate-800">Reasoning:</strong>{{ step.reasoning }}</p>
            </div>
          </div>
          <div v-if="step.image" class="bg-white p-4">
            <img :src="step.image" :alt="`Step ${step.step} screenshot`" class="w-full rounded-2xl border border-slate-200 shadow-sm" />
          </div>
        </article>
      </div>
    </SectionCard>

    <SectionCard
      v-if="postmortem"
      kicker="Postmortem"
      title="Structured analysis"
      body="The replay and analysis remain separate sections so the narrative stays easy to follow."
    >
      <div class="space-y-4">
        <article class="surface-muted p-4">
          <h3 class="font-display text-xl font-semibold text-slate-900">Run analysis</h3>
          <pre class="mono-copy mt-3">{{ formatPostmortemValue(postmortem.run_analysis) }}</pre>
        </article>
        <article class="surface-muted p-4">
          <h3 class="font-display text-xl font-semibold text-slate-900">HTML analysis</h3>
          <pre class="mono-copy mt-3">{{ formatPostmortemValue(postmortem.html_analysis) }}</pre>
        </article>
        <article class="surface-muted p-4">
          <h3 class="font-display text-xl font-semibold text-slate-900">Recommendations</h3>
          <pre class="mono-copy mt-3">{{ formatPostmortemValue(postmortem.recommendations) }}</pre>
        </article>
      </div>
    </SectionCard>

    <SectionCard
      kicker="Runtime trace"
      title="Run logs"
      body="Logs stay below the replay so deeper debugging is available without crowding the main timeline."
    >
      <EmptyState
        v-if="logs.length === 0"
        title="No logs yet"
        body="The worker trace will appear here as the runtime emits progress, warnings, and prompt payloads."
      />

      <div v-else class="space-y-3">
        <article
          v-for="(log, index) in logs"
          :key="index"
          class="rounded-2xl border p-4"
          :class="log.level === 'error'
            ? 'border-rose-200 bg-rose-50'
            : log.level === 'warning'
              ? 'border-amber-200 bg-amber-50'
              : 'border-slate-200 bg-slate-50'"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <p class="font-medium text-slate-900">{{ log.level || "info" }}</p>
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">step {{ log.step ?? "-" }}</p>
          </div>
          <p class="mt-3 text-sm leading-6 text-slate-700">{{ log.message }}</p>
          <p v-if="log.details && !log.isPrompt" class="mt-2 text-sm leading-6 text-slate-500">{{ log.details }}</p>
          <details v-if="log.isPrompt" class="mt-3">
            <summary class="cursor-pointer text-sm font-medium text-slate-700">Show full prompt</summary>
            <pre class="mono-copy mt-3 rounded-2xl bg-white p-3">{{ log.details }}</pre>
          </details>
        </article>
      </div>
    </SectionCard>

    <div v-if="showExportModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 backdrop-blur-sm">
      <div class="w-full max-w-xl surface-card p-6">
        <p class="section-kicker">VibeCode International</p>
        <h2 class="mt-2 font-display text-3xl font-bold text-slate-900">Export session to VibeCode</h2>
        <p class="mt-2 text-sm text-slate-500">This run will be added to your Victor profile on vibecodeinternational.com. Optionally give it an app name so it groups with your other runs.</p>

        <div v-if="exportSuccess" class="mt-5 rounded-2xl bg-emerald-50 border border-emerald-200 p-4">
          <p class="text-sm font-medium text-emerald-700">Exported successfully! Your run will appear on VibeCode International shortly.</p>
          <button class="ghost-button mt-4" @click="showExportModal = false">Close</button>
        </div>

        <div v-else class="mt-5 space-y-4">
          <div>
            <label class="field-label">App name <span class="text-slate-400 font-normal">(optional)</span></label>
            <input v-model="exportAppName" type="text" class="field-input" placeholder="e.g. My Portfolio Site" />
          </div>
          <div>
            <label class="field-label">App description <span class="text-slate-400 font-normal">(optional)</span></label>
            <textarea v-model="exportAppDescription" class="field-input min-h-20" rows="3" placeholder="What does this app do?" />
          </div>
          <div class="flex flex-wrap gap-3">
            <button class="primary-button" :disabled="exportLoading" @click="exportToVibecode">
              {{ exportLoading ? "Exporting…" : "Export" }}
            </button>
            <button class="ghost-button" :disabled="exportLoading" @click="showExportModal = false">Cancel</button>
          </div>
          <p v-if="exportError" class="text-sm font-medium text-rose-600">{{ exportError }}</p>
        </div>
      </div>
    </div>

    <div v-if="showSubmitModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 backdrop-blur-sm">
      <div class="w-full max-w-xl surface-card p-6">
        <p class="section-kicker">Competition submission</p>
        <h2 class="mt-2 font-display text-3xl font-bold text-slate-900">Send this session into a bracket</h2>

        <EmptyState
          v-if="openCompetitions.length === 0"
          class="mt-5"
          title="No open competitions"
          body="Create or reopen a competition before submitting this run."
        />

        <div v-else class="mt-5 space-y-4">
          <div>
            <label class="field-label">Competition</label>
            <select v-model="submitCompetitionId" class="field-input">
              <option v-for="competition in openCompetitions" :key="competition.id" :value="competition.id">
                {{ competition.name }}
              </option>
            </select>
          </div>

          <div>
            <label class="field-label">Note</label>
            <textarea v-model="submitNote" class="field-input min-h-32" rows="4" placeholder="What made this run worth submitting?" />
          </div>

          <div class="flex flex-wrap gap-3">
            <button class="primary-button" :disabled="!submitCompetitionId" @click="submitToCompetition">Submit</button>
            <button class="ghost-button" @click="showSubmitModal = false">Cancel</button>
          </div>

          <p v-if="submitError" class="text-sm font-medium text-rose-600">{{ submitError }}</p>
          <p v-if="submitSuccess" class="text-sm font-medium text-emerald-600">Submitted successfully.</p>
        </div>
      </div>
    </div>
  </div>
</template>
