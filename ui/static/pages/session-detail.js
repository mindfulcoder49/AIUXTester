import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  useRoute,
} from "../lib/vue-globals.js";
import {
  apiRequest,
  formatPostmortemValue,
  store,
} from "../lib/app-state.js";
import { compactUrl, prettyStatus, pluralize } from "../lib/formatters.js";
import { back } from "../lib/navigation.js";
import { EmptyState, MetricRail, StatusPill } from "../components/primitives.js";

const TERMINAL_STATUSES = new Set(["completed", "failed", "stopped", "loop_detected"]);

export const SessionDetail = {
  components: { StatusPill, MetricRail, EmptyState },
  template: `
    <div class="page page--session-detail">
      <section class="page-hero page-hero--detail">
        <div>
          <button class="button button--ghost button--small" @click="backToApp">Back to dashboard</button>
          <p class="section-kicker">Session Replay</p>
          <h1>{{ session?.goal || "Session detail" }}</h1>
          <p class="page-hero__lead">
            {{ compactUrl(session?.start_url || "") }} | {{ session?.provider || "-" }} / {{ session?.model || "-" }}
          </p>
        </div>
        <div class="hero-actions">
          <StatusPill :status="session?.status || 'running'" />
          <button class="button button--ghost" @click="stop" :disabled="!session || isTerminal">Stop</button>
          <button class="button button--primary" v-if="isTerminal" @click="openSubmitModal">Submit to competition</button>
        </div>
      </section>

      <MetricRail :metrics="runMetrics" />

      <div class="detail-layout">
        <section class="panel-surface panel-surface--raised">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">Live Stream</p>
              <h2>Action timeline</h2>
            </div>
          </div>

          <EmptyState
            v-if="steps.length === 0"
            title="Waiting for first step"
            body="As soon as the agent captures evidence, the timeline will populate with screenshots, intent, and reasoning."
          />

          <div v-else class="step-timeline">
            <article v-for="step in steps" :key="step.id || ('step-' + step.step + '-' + step.action)" class="step-card">
              <div class="step-card__header">
                <div class="step-card__summary">
                  <span class="step-card__index">Step {{ step.step }}</span>
                  <strong>{{ step.action }}</strong>
                </div>
                <span class="step-card__url">{{ compactUrl(step.url || "") }}</span>
              </div>
              <div class="step-card__body" v-if="step.intent || step.reasoning">
                <p v-if="step.intent"><strong>Intent</strong> {{ step.intent }}</p>
                <p v-if="step.reasoning"><strong>Reasoning</strong> {{ step.reasoning }}</p>
              </div>
              <div class="step-card__image" v-if="step.image">
                <img :src="step.image" :alt="'Step ' + step.step + ' screenshot'" />
              </div>
            </article>
          </div>
        </section>

        <aside class="detail-sidebar">
          <section class="panel-surface" v-if="postmortem">
            <div class="panel-heading panel-heading--compact">
              <div>
                <p class="section-kicker">Postmortem</p>
                <h2>Structured analysis</h2>
              </div>
            </div>
            <div class="postmortem-stack">
              <article class="postmortem-card">
                <strong>Run analysis</strong>
                <pre>{{ formatPostmortemValue(postmortem.run_analysis) }}</pre>
              </article>
              <article class="postmortem-card">
                <strong>HTML analysis</strong>
                <pre>{{ formatPostmortemValue(postmortem.html_analysis) }}</pre>
              </article>
              <article class="postmortem-card">
                <strong>Recommendations</strong>
                <pre>{{ formatPostmortemValue(postmortem.recommendations) }}</pre>
              </article>
            </div>
          </section>

          <section class="panel-surface">
            <div class="panel-heading panel-heading--compact">
              <div>
                <p class="section-kicker">Run Logs</p>
                <h2>Execution trace</h2>
              </div>
            </div>
            <div class="log-feed" v-if="logs.length">
              <article v-for="(log, index) in logs" :key="index" class="log-card" :data-level="log.level">
                <div class="log-card__header">
                  <strong>{{ log.level || "info" }}</strong>
                  <span>step {{ log.step ?? "-" }}</span>
                </div>
                <p>{{ log.message }}</p>
                <p class="log-card__details" v-if="log.details && !log.isPrompt">{{ log.details }}</p>
                <details v-if="log.isPrompt" class="log-card__prompt">
                  <summary>Show full prompt</summary>
                  <pre>{{ log.details }}</pre>
                </details>
              </article>
            </div>
            <EmptyState
              v-else
              title="No logs yet"
              body="The runtime trace will appear here as the worker publishes progress and warnings."
            />
          </section>
        </aside>
      </div>

      <div class="modal-overlay" v-if="showSubmitModal" @click.self="showSubmitModal = false">
        <div class="modal-card">
          <div class="panel-heading panel-heading--compact">
            <div>
              <p class="section-kicker">Competition Submission</p>
              <h2>Send this session into the bracket</h2>
            </div>
          </div>

          <div v-if="openCompetitions.length === 0" class="empty-state">
            <strong>No open competitions</strong>
            <p>Create or reopen a competition before submitting this run.</p>
          </div>

          <template v-else>
            <div class="field-stack">
              <label class="field-label">Competition</label>
              <select v-model="submitCompetitionId">
                <option v-for="competition in openCompetitions" :key="competition.id" :value="competition.id">{{ competition.name }}</option>
              </select>
            </div>
            <div class="field-stack">
              <label class="field-label">Note</label>
              <textarea v-model="submitNote" rows="4" placeholder="What made this run worth submitting?"></textarea>
            </div>
            <div class="modal-card__actions">
              <button class="button button--primary" @click="submitToCompetition" :disabled="!submitCompetitionId">Submit</button>
              <button class="button button--ghost" @click="showSubmitModal = false">Cancel</button>
            </div>
          </template>

          <p class="form-feedback form-feedback--error" v-if="submitError">{{ submitError }}</p>
          <p class="form-feedback form-feedback--success" v-if="submitSuccess">Submitted successfully.</p>
        </div>
      </div>
    </div>
  `,
  setup() {
    const route = useRoute();
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
    let eventSource = null;
    let refreshTimer = null;

    const isTerminal = computed(() => TERMINAL_STATUSES.has(session.value?.status));
    const runMetrics = computed(() => [
      { label: "Status", value: prettyStatus(session.value?.status || "running"), detail: session.value?.end_reason || "In progress" },
      { label: "Steps", value: String(steps.value.length), detail: pluralize(steps.value.length, "capture") },
      { label: "Logs", value: String(logs.value.length), detail: postmortem.value ? "Postmortem ready" : "Analysis pending" },
    ]);

    const mapLog = (entry) => ({
      level: entry.level,
      message: entry.message,
      details: entry.details,
      step: entry.step_number ?? entry.step ?? null,
      isPrompt: entry.message === "LLM prompt payload",
    });

    const setStepsFromPayload = (data) => {
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
        image: `/screenshots/${shot.id}?token=${store.token}`,
      }));
    };

    const pushStep = (candidate) => {
      const existing = steps.value.find((step) => String(step.id) === String(candidate.id));
      if (existing) return;
      steps.value.push(candidate);
    };

    const loadSession = async () => {
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
    };

    const connectStream = () => {
      if (eventSource) eventSource.close();
      eventSource = new EventSource(`/sessions/${route.params.id}/stream?token=${store.token}`);
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
            image: `/screenshots/${message.data.screenshot_id}?token=${store.token}`,
          });
        }
        if (message.type === "postmortem") {
          postmortem.value = message.data;
        }
        if (message.type === "status" && session.value) {
          session.value.status = message.data.status;
          session.value.end_reason = message.data.end_reason;
          logs.value.push(mapLog({
            level: "info",
            message: `Session status changed to ${message.data.status}`,
            details: message.data.end_reason || "",
          }));
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
    };

    const startRefresh = () => {
      if (refreshTimer) clearInterval(refreshTimer);
      refreshTimer = setInterval(async () => {
        if (!session.value || TERMINAL_STATUSES.has(session.value.status)) return;
        try {
          await loadSession();
        } catch (_) {}
      }, 3000);
    };

    const openSubmitModal = async () => {
      submitError.value = "";
      submitSuccess.value = false;
      submitNote.value = "";
      const competitions = await apiRequest("/competitions");
      openCompetitions.value = competitions.filter((competition) => competition.status === "open");
      submitCompetitionId.value = openCompetitions.value[0]?.id || "";
      showSubmitModal.value = true;
    };

    const submitToCompetition = async () => {
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
    };

    const stop = async () => {
      if (!session.value) return;
      await apiRequest(`/sessions/${session.value.id}/stop`, { method: "POST" });
    };

    onMounted(async () => {
      await loadSession();
      connectStream();
      startRefresh();
    });

    onBeforeUnmount(() => {
      if (eventSource) eventSource.close();
      if (refreshTimer) clearInterval(refreshTimer);
    });

    return {
      session,
      steps,
      postmortem,
      logs,
      showSubmitModal,
      openCompetitions,
      submitCompetitionId,
      submitNote,
      submitError,
      submitSuccess,
      isTerminal,
      runMetrics,
      openSubmitModal,
      submitToCompetition,
      stop,
      compactUrl,
      formatPostmortemValue,
      backToApp: () => back("/app"),
    };
  },
};
