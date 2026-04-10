import { computed, onMounted, reactive, ref, watch } from "../lib/vue-globals.js";
import { apiRequest, normalizeStartUrl, store } from "../lib/app-state.js";
import { compactUrl, formatShortDate, pluralize } from "../lib/formatters.js";
import { go } from "../lib/navigation.js";
import { EmptyState, MetricRail, StatusPill } from "../components/primitives.js";
import { filterConfigForTier } from "../app-utils.js";

const DEFAULT_CONFIG = () => ({
  mode: "desktop",
  max_steps: 50,
  stop_on_first_error: false,
  max_history_actions: 5,
  loop_detection_enabled: true,
  loop_detection_window: 8,
  postmortem_depth: "standard",
  custom_system_prompt_preamble: "",
});

export const Dashboard = {
  components: { StatusPill, EmptyState, MetricRail },
  template: `
    <div class="page page--dashboard">
      <section class="page-hero">
        <div>
          <p class="section-kicker">Control Center</p>
          <h1>Launch, replay, and compare runs from one command surface.</h1>
          <p class="page-hero__lead">
            Compose a new session, rerun a strong configuration, or jump straight into evidence from a previous test.
          </p>
        </div>
        <MetricRail :metrics="heroMetrics" />
      </section>

      <section class="dashboard-layout">
        <div class="panel-surface panel-surface--raised composer-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">New Session</p>
              <h2>Build the next run</h2>
            </div>
          </div>

          <form class="form-layout" @submit.prevent="createSession">
            <div class="field-stack">
              <label class="field-label">Goal</label>
              <input v-model="goal" placeholder="Create account, complete checkout, verify onboarding..." required />
            </div>

            <div class="field-stack">
              <label class="field-label">Start URL</label>
              <input v-model="start_url" placeholder="https://example.com" required />
            </div>

            <div class="field-grid field-grid--triple">
              <div class="field-stack">
                <label class="field-label">Mode</label>
                <select v-model="config.mode">
                  <option value="desktop">Desktop</option>
                  <option value="mobile">Mobile</option>
                </select>
              </div>

              <div class="field-stack">
                <label class="field-label">Provider</label>
                <select v-model="provider">
                  <option v-for="providerOption in providers" :key="providerOption" :value="providerOption">{{ providerOption }}</option>
                </select>
              </div>

              <div class="field-stack">
                <label class="field-label">Model</label>
                <select v-model="model">
                  <option v-for="modelOption in modelsForProvider" :key="modelOption" :value="modelOption">{{ modelOption }}</option>
                </select>
              </div>
            </div>

            <div class="control-block">
              <div class="panel-heading panel-heading--compact">
                <div>
                  <p class="section-kicker">Run Config</p>
                  <h3>Guardrails and depth</h3>
                </div>
              </div>

              <div class="field-grid field-grid--dual">
                <div class="field-stack">
                  <label class="field-label">Max Steps</label>
                  <input type="number" v-model.number="config.max_steps" />
                </div>
                <label class="toggle-row">
                  <input type="checkbox" v-model="config.stop_on_first_error" />
                  <span>Stop on first error</span>
                </label>
                <div v-if="tier !== 'free'" class="field-stack">
                  <label class="field-label">History Actions</label>
                  <input type="number" v-model.number="config.max_history_actions" />
                </div>
                <div v-if="tier !== 'free'" class="field-stack">
                  <label class="field-label">Loop Window</label>
                  <input type="number" v-model.number="config.loop_detection_window" />
                </div>
                <label v-if="tier !== 'free'" class="toggle-row">
                  <input type="checkbox" v-model="config.loop_detection_enabled" />
                  <span>Enable loop detection</span>
                </label>
                <div v-if="tier === 'pro'" class="field-stack">
                  <label class="field-label">Postmortem Depth</label>
                  <select v-model="config.postmortem_depth">
                    <option value="standard">Standard</option>
                    <option value="deep">Deep</option>
                  </select>
                </div>
              </div>

              <div v-if="tier === 'pro'" class="field-stack">
                <label class="field-label">Custom Prompt Preamble</label>
                <textarea v-model="config.custom_system_prompt_preamble" rows="4"></textarea>
              </div>
            </div>

            <button class="button button--primary button--large">Create and Start</button>
            <p class="form-feedback form-feedback--error" v-if="error">{{ error }}</p>
          </form>
        </div>

        <div class="stacked-panels">
          <section class="panel-surface">
            <div class="panel-heading">
              <div>
                <p class="section-kicker">Recent Sessions</p>
                <h2>Your run library</h2>
              </div>
              <button class="button button--ghost" @click="loadSessions">Refresh</button>
            </div>

            <EmptyState
              v-if="sessions.length === 0"
              title="No sessions yet"
              body="Launch a run from the composer and it will appear here with status, model, and quick rerun controls."
            />

            <div v-else class="session-card-grid">
              <article v-for="session in sessions" :key="session.id" class="session-card session-card--rich" @click="openSession(session.id)">
                <div class="session-card__head">
                  <div>
                    <strong>{{ session.goal }}</strong>
                    <p>{{ compactUrl(session.start_url) }}</p>
                  </div>
                  <StatusPill :status="session.status" />
                </div>
                <div class="session-card__meta">
                  <span>{{ session.provider }} / {{ session.model }}</span>
                  <span>{{ formatShortDate(session.created_at) }}</span>
                </div>
                <div class="session-card__footer">
                  <span>{{ session.end_reason || "Ready for replay" }}</span>
                  <button type="button" class="button button--ghost button--small" @click.stop="rerunFromSession(session)">Reuse config</button>
                </div>
              </article>
            </div>
          </section>

          <section class="panel-surface panel-surface--muted">
            <div class="panel-heading panel-heading--compact">
              <div>
                <p class="section-kicker">Tier Snapshot</p>
                <h2>{{ store.user?.tier }} access level</h2>
              </div>
            </div>
            <p class="callout-copy">
              {{ tierSummary }}
            </p>
          </section>
        </div>
      </section>
    </div>
  `,
  setup() {
    const sessions = ref([]);
    const goal = ref("");
    const start_url = ref("");
    const provider = ref("openai");
    const model = ref("");
    const config = reactive(DEFAULT_CONFIG());
    const error = ref("");

    const tier = computed(() => store.user?.tier || "free");
    const providers = computed(() => Object.keys(store.models || {}));
    const modelsForProvider = computed(() => store.models?.[provider.value] || []);

    const heroMetrics = computed(() => [
      { label: "Tier", value: store.user?.tier || "free", detail: store.user?.role || "user" },
      { label: "Sessions", value: String(sessions.value.length), detail: pluralize(sessions.value.length, "run") },
      { label: "Models", value: String(modelsForProvider.value.length || 0), detail: provider.value },
    ]);

    const tierSummary = computed(() => {
      if (tier.value === "pro") return "Full controls unlocked, including postmortem depth and custom prompt preambles.";
      if (tier.value === "basic") return "Expanded loop controls and history window tuning are available for this workspace.";
      return "Free tier keeps the composer lean with core run settings and a simplified model surface.";
    });

    const loadSessions = async () => {
      sessions.value = await apiRequest("/sessions");
    };

    const createSession = async () => {
      error.value = "";
      try {
        const filteredConfig = filterConfigForTier(config, tier.value);
        const result = await apiRequest("/sessions", {
          method: "POST",
          body: JSON.stringify({
            goal: goal.value,
            start_url: normalizeStartUrl(start_url.value),
            provider: provider.value,
            model: model.value || (modelsForProvider.value[0] || ""),
            config: filteredConfig,
          }),
        });
        await loadSessions();
        go(`/sessions/${result.session_id}`);
      } catch (err) {
        error.value = err.message || "Unable to create session";
      }
    };

    const rerunFromSession = (session) => {
      goal.value = session.goal || "";
      start_url.value = session.start_url || "";
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
      Object.assign(config, DEFAULT_CONFIG(), savedConfig);
      window.scrollTo({ top: 0, behavior: "smooth" });
    };

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

    return {
      store,
      sessions,
      goal,
      start_url,
      provider,
      model,
      config,
      error,
      tier,
      providers,
      modelsForProvider,
      heroMetrics,
      tierSummary,
      loadSessions,
      createSession,
      rerunFromSession,
      openSession: (id) => go(`/sessions/${id}`),
      formatShortDate,
      compactUrl,
    };
  },
};
