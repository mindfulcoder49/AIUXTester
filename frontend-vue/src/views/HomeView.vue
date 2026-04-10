<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import PageHero from "../components/PageHero.vue";
import SectionCard from "../components/SectionCard.vue";
import { apiRequest, loadUser, normalizeEmailHandle, normalizeStartUrl, setToken, state } from "../lib/store.js";

const router = useRouter();
const step = ref(1);
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

const features = [
  {
    title: "Transparent session playback",
    body: "Each step carries the screenshot, intent, reasoning, and logs you need to understand what the agent actually did.",
  },
  {
    title: "Grounded analysis",
    body: "Postmortems are backed by saved HTML, action history, and runtime artifacts instead of generic summaries.",
  },
  {
    title: "Competition-ready runs",
    body: "Completed sessions can be submitted into tournament-style comparisons once you want to evaluate them head to head.",
  },
];

const maxStep = computed(() => (state.token ? 2 : 3));

async function ensureAuth() {
  if (state.token) {
    await loadUser();
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
}

async function startSession() {
  const openaiModels = state.models?.openai || [];
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
  router.push(`/sessions/${result.session_id}`);
}

async function submitWizard() {
  error.value = "";
  if (step.value === 1) {
    step.value = 2;
    return;
  }
  if (step.value === 2 && !state.token) {
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
}

function scrollToLaunch() {
  document.getElementById("launch-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
}
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Autonomous UX testing"
      title="A second frontend designed to stay practical on both desktop and mobile."
      body="This version keeps the product stack readable by treating the app as one continuous workflow instead of splitting everything into side-by-side columns."
      :metrics="heroMetrics"
    >
      <template #actions>
        <div class="mb-5 flex flex-wrap gap-3">
          <button class="primary-button" @click="state.token ? router.push('/app') : scrollToLaunch()">
            {{ state.token ? "Open dashboard" : "Start a test" }}
          </button>
          <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="router.push('/docs')">
            Documentation
          </button>
          <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="router.push('/competitions')">
            Competitions
          </button>
          <template v-if="!state.token">
            <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="router.push('/login')">
              Login
            </button>
            <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="router.push('/register')">
              Register
            </button>
          </template>
        </div>
      </template>
    </PageHero>

    <SectionCard
      id="launch-card"
      kicker="Launch flow"
      title="Start a run in three steps"
      body="The flow stays linear by design: point the agent at the site, define the goal, then authenticate only if needed."
    >
      <div class="flex flex-wrap gap-2">
        <div
          v-for="wizardStep in 3"
          :key="wizardStep"
          class="rounded-full px-4 py-2 text-sm font-medium"
          :class="wizardStep === step
            ? 'bg-brand-500 text-white'
            : wizardStep < step
              ? 'bg-emerald-100 text-emerald-700'
              : 'bg-slate-100 text-slate-500'"
        >
          Step {{ wizardStep }}
        </div>
      </div>

      <form class="mt-6 space-y-5" @submit.prevent="submitWizard">
        <div v-if="step === 1">
          <label class="field-label">Website</label>
          <input v-model.trim="startUrl" class="field-input" placeholder="https://example.com" required />
          <p class="mt-2 text-sm text-slate-500">Paste the product URL or page entry point you want the agent to explore.</p>
        </div>

        <div v-if="step === 2">
          <label class="field-label">Goal</label>
          <textarea v-model.trim="goal" class="field-input min-h-36" rows="5" required />
          <p class="mt-2 text-sm text-slate-500">Describe what a user should attempt, not the exact clicks you expect.</p>
        </div>

        <div v-if="step === 3 && !state.token" class="space-y-4">
          <div>
            <label class="field-label">Username or email</label>
            <input v-model.trim="username" class="field-input" placeholder="name@example.com" required />
          </div>
          <div>
            <label class="field-label">Password</label>
            <input v-model="password" type="password" class="field-input" placeholder="Create a password" required />
          </div>
        </div>

        <div class="flex flex-wrap gap-3">
          <button v-if="step > 1" type="button" class="ghost-button" @click="step -= 1">Back</button>
          <button class="primary-button" :disabled="loading">
            {{ loading ? "Launching..." : (step < maxStep ? "Continue" : "Start test") }}
          </button>
        </div>

        <p v-if="error" class="text-sm font-medium text-rose-600">{{ error }}</p>
      </form>
    </SectionCard>

    <SectionCard
      kicker="Why this version works better"
      title="Everything important stays in one reading column"
      body="The new frontend still supports the full backend feature set, but it prioritizes vertical flow and device-agnostic reading."
    >
      <div class="space-y-4">
        <article v-for="feature in features" :key="feature.title" class="surface-muted p-4">
          <h3 class="font-display text-xl font-semibold text-slate-900">{{ feature.title }}</h3>
          <p class="mt-2 text-sm leading-6 text-slate-600">{{ feature.body }}</p>
        </article>
      </div>
    </SectionCard>
  </div>
</template>
