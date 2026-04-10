import { computed, ref } from "../lib/vue-globals.js";
import {
  apiRequest,
  loadUser,
  normalizeEmailHandle,
  normalizeStartUrl,
  setToken,
  store,
} from "../lib/app-state.js";
import { go } from "../lib/navigation.js";
import { MetricRail } from "../components/primitives.js";

export const Home = {
  components: { MetricRail },
  template: `
    <div class="page page--home">
      <section class="hero-card">
        <div class="hero-card__copy">
          <p class="section-kicker">Autonomous UX Testing</p>
          <h1>Give the product a frontend that feels as sharp as the test engine behind it.</h1>
          <p class="hero-card__lead">
            Run exploratory browser tests, watch the agent think in real time, and turn every run into evidence your team can act on.
          </p>
          <div class="hero-card__actions">
            <button class="button button--primary button--large" @click="goPrimary">
              {{ store.token ? "Open Dashboard" : "Start a Test" }}
            </button>
            <button class="button button--ghost" @click="goDocs">Documentation</button>
            <button class="button button--ghost" @click="goCosts">Cost model</button>
          </div>
        </div>

        <div class="hero-card__side">
          <MetricRail :metrics="heroMetrics" />
          <div class="hero-card__signal">
            <strong>Trace every decision</strong>
            <p>Session timelines, screenshots, model reasoning, postmortems, and competition brackets live in one place.</p>
          </div>
        </div>
      </section>

      <section class="page-grid page-grid--home">
        <div id="launch-panel" class="panel-surface panel-surface--feature">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">Launch Flow</p>
              <h2>Start a run in three quick steps</h2>
            </div>
          </div>

          <div class="wizard-steps">
            <div v-for="wizardStep in wizardSteps" :key="wizardStep.id" class="wizard-step" :class="{ 'is-active': wizardStep.id === step, 'is-complete': wizardStep.id < step }">
              <span>{{ wizardStep.id }}</span>
              <strong>{{ wizardStep.label }}</strong>
            </div>
          </div>

          <form class="wizard-form" @submit.prevent="submitWizard">
            <div v-if="step === 1" class="field-stack">
              <label class="field-label">Website</label>
              <input v-model.trim="startUrl" placeholder="https://example.com" required />
              <p class="field-help">Point the agent at the page or product area you want pressure-tested first.</p>
            </div>

            <div v-if="step === 2" class="field-stack">
              <label class="field-label">Goal</label>
              <textarea v-model.trim="goal" rows="5" required></textarea>
              <p class="field-help">Describe the user intent you want the agent to pursue.</p>
            </div>

            <div v-if="step === 3 && !store.token" class="field-grid field-grid--dual">
              <div class="field-stack">
                <label class="field-label">Username or Email</label>
                <input v-model.trim="username" placeholder="name@example.com" required />
              </div>
              <div class="field-stack">
                <label class="field-label">Password</label>
                <input v-model="password" type="password" placeholder="Create a password" required />
              </div>
            </div>

            <div class="wizard-footer">
              <button type="button" class="button button--ghost" v-if="step > 1" @click="step -= 1">Back</button>
              <button type="submit" class="button button--primary" :disabled="loading">
                {{ loading ? "Launching..." : (step < maxStep ? "Continue" : "Start Test") }}
              </button>
            </div>

            <p class="form-feedback form-feedback--error" v-if="error">{{ error }}</p>
          </form>
        </div>

        <div class="stacked-panels">
          <section class="panel-surface">
            <div class="panel-heading">
              <div>
                <p class="section-kicker">Why it works</p>
                <h2>Evidence-first from the first click</h2>
              </div>
            </div>
            <div class="feature-list">
              <article class="feature-card" v-for="feature in features" :key="feature.title">
                <strong>{{ feature.title }}</strong>
                <p>{{ feature.body }}</p>
              </article>
            </div>
          </section>

          <section class="panel-surface panel-surface--muted">
            <div class="panel-heading">
              <div>
                <p class="section-kicker">Competition Mode</p>
                <h2>Runs can go head-to-head</h2>
              </div>
            </div>
            <p class="callout-copy">
              Submit finished runs to competitions, judge them round by round, and present the results like an actual bracket instead of a utility list.
            </p>
            <button class="button button--ghost" @click="goCompetitionTarget">
              {{ store.token ? "View Competitions" : "Sign in to Compete" }}
            </button>
          </section>
        </div>
      </section>
    </div>
  `,
  setup() {
    const step = ref(1);
    const maxStep = computed(() => (store.token ? 2 : 3));
    const startUrl = ref("");
    const goal = ref("Explore the site, identify the primary workflow, and attempt to complete it like a real user.");
    const username = ref("");
    const password = ref("");
    const loading = ref(false);
    const error = ref("");

    const heroMetrics = computed(() => [
      { label: "Providers", value: "3", detail: "OpenAI, Gemini, Claude" },
      { label: "Replay", value: "Live", detail: "Screenshots plus reasoning" },
      { label: "Output", value: "Structured", detail: "Postmortem and logs" },
    ]);

    const wizardSteps = [
      { id: 1, label: "Choose site" },
      { id: 2, label: "Define goal" },
      { id: 3, label: "Unlock workspace" },
    ];

    const features = [
      {
        title: "Transparent session playback",
        body: "Every step is paired with screenshots, intent, and reasoning so the run is debuggable instead of mysterious.",
      },
      {
        title: "Postmortems with evidence",
        body: "The analysis is grounded in stored page HTML, actions, logs, and outcomes rather than generic advice.",
      },
      {
        title: "Model and tier controls",
        body: "Choose provider, tune loop handling, and keep the experience aligned with user access levels.",
      },
    ];

    const ensureAuth = async () => {
      if (store.token) {
        if (!store.user) await loadUser();
        return;
      }

      const email = normalizeEmailHandle(username.value);
      try {
        const data = await apiRequest("/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password: password.value }),
        });
        setToken(data.access_token);
      } catch (_) {
        const data = await apiRequest("/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password: password.value }),
        });
        setToken(data.access_token);
      }
      await loadUser();
    };

    const startSession = async () => {
      const openaiModels = store.models?.openai || [];
      const model = openaiModels.includes("gpt-5-mini")
        ? "gpt-5-mini"
        : (openaiModels[0] || "gpt-5-mini");
      const result = await apiRequest("/sessions", {
        method: "POST",
        body: JSON.stringify({
          goal: goal.value,
          start_url: normalizeStartUrl(startUrl.value),
          provider: "openai",
          model,
          config: {
            mode: "desktop",
            max_steps: 50,
            stop_on_first_error: false,
          },
        }),
      });
      go(`/sessions/${result.session_id}`);
    };

    const submitWizard = async () => {
      error.value = "";
      if (step.value === 1) {
        step.value = 2;
        return;
      }
      if (step.value === 2 && !store.token) {
        step.value = 3;
        return;
      }
      loading.value = true;
      try {
        await ensureAuth();
        await startSession();
      } catch (err) {
        error.value = err.message || "Unable to launch test";
      } finally {
        loading.value = false;
      }
    };

    return {
      store,
      step,
      maxStep,
      wizardSteps,
      heroMetrics,
      startUrl,
      goal,
      username,
      password,
      loading,
      error,
      features,
      submitWizard,
      goPrimary: () => {
        if (store.token) {
          go("/app");
          return;
        }
        document.getElementById("launch-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
      },
      goDocs: () => go("/docs"),
      goCosts: () => go("/costs"),
      goCompetitionTarget: () => go(store.token ? "/competitions" : "/login"),
    };
  },
};
