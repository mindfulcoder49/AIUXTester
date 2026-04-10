<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import BracketStage from "../components/BracketStage.vue";
import EmptyState from "../components/EmptyState.vue";
import SectionCard from "../components/SectionCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { apiRequest, state } from "../lib/store.js";
import { compactUrl, formatPercent, formatShortDate, pluralize, prettyStatus } from "../lib/formatters.js";

const route = useRoute();
const router = useRouter();

const competition = ref(null);
const entries = ref([]);
const runs = ref([]);
const matches = ref([]);
const summary = ref({
  run_count: 0,
  completed_run_count: 0,
  running_run_count: 0,
  awaiting_round_count: 0,
  queued_run_count: 0,
  failed_run_count: 0,
  unique_champion_count: 0,
  pairing_coverage: 0,
  consensus_champion: null,
  leaderboard: [],
  top_rivalries: [],
});
const selectedRun = ref(null);
const judgeProvider = ref("openai");
const judgeModel = ref("");
const pairingStrategy = ref("balanced_random");
const progressionMode = ref("automatic");
const rerunCount = ref(5);
const running = ref(false);
const adminError = ref("");
let pollTimer = null;

const providers = computed(() => Object.keys(state.models || {}));
const judgeModels = computed(() => state.models?.[judgeProvider.value] || []);
const consensusLeader = computed(() => summary.value?.leaderboard?.[0] || null);
const completedRuns = computed(() => summary.value?.completed_run_count || 0);
const canRun = computed(() => state.user?.role === "admin" && (competition.value?.status !== "running"));
const activeManualRun = computed(() =>
  [...runs.value]
    .filter((run) => run.status === "awaiting_round")
    .sort((left, right) => left.run_number - right.run_number)[0] || null,
);
const runningRun = computed(() => runs.value.find((run) => run.status === "running") || null);
const nextManualRun = computed(() =>
  [...runs.value]
    .filter((run) => run.status === "queued" && run.progression_mode === "manual")
    .sort((left, right) => left.run_number - right.run_number)[0] || null,
);
const canAdvanceRound = computed(() => state.user?.role === "admin" && !!activeManualRun.value && !runningRun.value);
const canAdvanceBracket = computed(() => state.user?.role === "admin" && !activeManualRun.value && !!nextManualRun.value && !runningRun.value);

const heroMetrics = computed(() => [
  {
    label: "Runs",
    value: String(summary.value?.run_count || 0),
    detail: `${summary.value?.completed_run_count || 0} complete | ${summary.value?.running_run_count || 0} live | ${summary.value?.awaiting_round_count || 0} paused`,
  },
  {
    label: "Coverage",
    value: formatPercent(summary.value?.pairing_coverage || 0),
    detail: "Unique matchup coverage",
  },
  {
    label: "Consensus",
    value: consensusLeader.value ? formatPercent(consensusLeader.value.championship_share || 0) : "0%",
    detail: consensusLeader.value ? `${compactUrl(consensusLeader.value.label || "")} lead share` : "Waiting for results",
  },
]);

const selectedRunSummary = computed(() => {
  if (!selectedRun.value) return "No bracket run selected yet.";
  const seed = selectedRun.value.pairing_seed != null ? `Seed ${selectedRun.value.pairing_seed}` : "No seed";
  return `${prettyStatus(selectedRun.value.status)} | ${selectedRun.value.pairing_strategy.replace(/_/g, " ")} | ${selectedRun.value.progression_mode} pacing | ${seed}`;
});

const rivalryRows = computed(() => {
  const entryMap = Object.fromEntries(entries.value.map((entry) => [entry.id, entry]));
  return (summary.value?.top_rivalries || []).map((rivalry) => ({
    ...rivalry,
    labelA: compactUrl(entryMap[rivalry.entry_a_id]?.start_url || entryMap[rivalry.entry_a_id]?.session_id || `Entry ${rivalry.entry_a_id}`),
    labelB: compactUrl(entryMap[rivalry.entry_b_id]?.start_url || entryMap[rivalry.entry_b_id]?.session_id || `Entry ${rivalry.entry_b_id}`),
  }));
});

function entryLabel(entry) {
  return compactUrl(entry.start_url || entry.session_id);
}

async function loadCompetition(runId = null) {
  const suffix = runId ? `?run_id=${runId}` : "";
  const data = await apiRequest(`/competitions/${route.params.id}${suffix}`);
  competition.value = data.competition;
  entries.value = data.entries || [];
  runs.value = data.runs || [];
  matches.value = data.matches || [];
  summary.value = data.summary || summary.value;
  selectedRun.value = data.selected_run || null;
  running.value = competition.value?.status === "running";
}

async function closeEntries() {
  adminError.value = "";
  try {
    await apiRequest(`/competitions/${competition.value.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "closed" }),
    });
    await loadCompetition(selectedRun.value?.id || null);
  } catch (err) {
    adminError.value = err.message || "Unable to close entries";
  }
}

async function queueRuns() {
  adminError.value = "";
  try {
    await apiRequest(`/competitions/${competition.value.id}/runs`, {
      method: "POST",
      body: JSON.stringify({
        provider: judgeProvider.value,
        model: judgeModel.value,
        pairing_strategy: pairingStrategy.value,
        progression_mode: progressionMode.value,
        count: rerunCount.value,
      }),
    });
    await loadCompetition();
    startPoll();
  } catch (err) {
    adminError.value = err.message || "Unable to queue bracket runs";
  }
}

async function selectRun(runId) {
  await loadCompetition(runId);
}

async function startNextRound() {
  adminError.value = "";
  try {
    await apiRequest(`/competitions/${competition.value.id}/next-round`, { method: "POST" });
    await loadCompetition(activeManualRun.value?.id || null);
    startPoll();
  } catch (err) {
    adminError.value = err.message || "Unable to start the next round";
  }
}

async function startNextBracket() {
  adminError.value = "";
  try {
    await apiRequest(`/competitions/${competition.value.id}/next-bracket`, { method: "POST" });
    await loadCompetition(nextManualRun.value?.id || null);
    startPoll();
  } catch (err) {
    adminError.value = err.message || "Unable to start the next bracket";
  }
}

function startPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    await loadCompetition(selectedRun.value?.id || null);
    if (competition.value?.status !== "running") {
      clearInterval(pollTimer);
      running.value = false;
    }
  }, 3000);
}

watch(judgeProvider, () => {
  if (!judgeModels.value.includes(judgeModel.value)) {
    judgeModel.value = judgeModels.value[0] || "";
  }
});

onMounted(async () => {
  await loadCompetition();
  if (!judgeModels.value.includes(judgeModel.value)) {
    judgeModel.value = judgeModels.value[0] || "";
  }
  if (competition.value?.status === "running") {
    startPoll();
  }
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<template>
  <div class="page-shell space-y-6">
    <section class="olympics-hero">
      <div class="olympics-hero__grid">
        <div class="olympics-hero__copy">
          <p class="arena-eyebrow">VibeCode Olympics Arena</p>
          <h1>{{ competition?.name || "Competition" }}</h1>
          <p class="olympics-hero__body">{{ competition?.description || "No description provided." }}</p>
          <div class="olympics-hero__actions">
            <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15" @click="router.push('/competitions')">
              Back to competitions
            </button>
            <button
              v-if="competition?.status === 'complete'"
              class="ghost-button border-amber-400/30 bg-amber-400/10 text-amber-200 hover:bg-amber-400/20"
              @click="router.push(`/competitions/${competition.id}/recap`)"
            >
              View recap
            </button>
            <StatusBadge v-if="competition" :status="competition.status" />
            <button
              v-if="state.user?.role === 'admin' && competition?.status === 'open'"
              class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15"
              @click="closeEntries"
            >
              Close entries
            </button>
          </div>
        </div>

        <div class="olympics-hero__scoreboard">
          <article v-for="metric in heroMetrics" :key="metric.label" class="olympics-score-tile">
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
            <p>{{ metric.detail }}</p>
          </article>
        </div>
      </div>
    </section>

    <section v-if="summary.consensus_champion" class="olympics-victory-card">
      <div class="olympics-victory-card__trophy">
        <span>Most stable winner</span>
        <strong>{{ compactUrl(summary.consensus_champion.label || "") }}</strong>
      </div>
      <div class="olympics-victory-card__copy">
        <p>
          Won {{ summary.consensus_champion.championships }} of {{ completedRuns }} completed runs and reached
          {{ summary.consensus_champion.finals }} finals. This is the audience-confidence signal across repeated brackets.
        </p>
        <div class="flex flex-wrap items-center gap-3 text-sm text-slate-300">
          <span>{{ formatPercent(summary.consensus_champion.championship_share || 0) }} title share</span>
          <span>{{ summary.unique_champion_count }} distinct champions</span>
          <span>{{ formatPercent(summary.pairing_coverage || 0) }} matchup coverage</span>
        </div>
      </div>
    </section>

    <SectionCard
      kicker="Confidence board"
      title="How stable is the result?"
      body="Every run is preserved as a separate bracket so the audience can compare outcomes instead of trusting a single pairing draw."
    >
      <div v-if="summary.completed_run_count === 0" class="space-y-4">
        <EmptyState
          title="No completed runs yet"
          body="Queue one or more bracket runs below. Once results come in, this panel will show consensus, rivalry coverage, and a championship table."
        />
      </div>

      <div v-else class="confidence-grid">
        <section class="confidence-panel">
          <div class="confidence-panel__header">
            <div>
              <p class="section-kicker">Championship table</p>
              <h3>Leaderboard across all runs</h3>
            </div>
            <p>{{ summary.completed_run_count }} completed {{ summary.completed_run_count === 1 ? "run" : "runs" }}</p>
          </div>

          <div class="mt-4 space-y-3">
            <article v-for="entry in summary.leaderboard.slice(0, 6)" :key="entry.entry_id" class="confidence-row">
              <div class="confidence-row__copy">
                <strong>{{ compactUrl(entry.label || "") }}</strong>
                <span>{{ entry.championships }} titles | {{ entry.finals }} finals</span>
              </div>
              <div class="confidence-row__bar">
                <div class="confidence-row__fill" :style="{ width: formatPercent(entry.championship_share || 0, 2) }" />
              </div>
              <p>{{ formatPercent(entry.championship_share || 0) }}</p>
            </article>
          </div>
        </section>

        <section class="confidence-panel">
          <div class="confidence-panel__header">
            <div>
              <p class="section-kicker">Rivalries</p>
              <h3>Most-tested matchups</h3>
            </div>
            <p>{{ formatPercent(summary.pairing_coverage || 0) }} coverage</p>
          </div>

          <div v-if="rivalryRows.length" class="mt-4 space-y-3">
            <article v-for="rivalry in rivalryRows.slice(0, 5)" :key="`${rivalry.entry_a_id}-${rivalry.entry_b_id}`" class="rivalry-card">
              <div>
                <strong>{{ rivalry.labelA }}</strong>
                <span>vs</span>
                <strong>{{ rivalry.labelB }}</strong>
              </div>
              <p>{{ rivalry.meetings }} meetings | {{ rivalry.wins_a }} - {{ rivalry.wins_b }}</p>
            </article>
          </div>
          <EmptyState
            v-else
            title="Rivalries will appear here"
            body="Once there are completed runs with multiple matchups, the most repeated pairings will show up here."
          />
        </section>
      </div>
    </SectionCard>

    <SectionCard
      v-if="canRun"
      kicker="Replay controls"
      title="Run this bracket again"
      body="Queue multiple bracket executions at once to explore different pairing combinations without changing the entrant field."
    >
      <div class="grid gap-4 xl:grid-cols-[1fr_1fr_1fr_1fr_auto]">
        <div>
          <label class="field-label">Judge provider</label>
          <select v-model="judgeProvider" class="field-input">
            <option v-for="provider in providers" :key="provider" :value="provider">{{ provider }}</option>
          </select>
        </div>
        <div>
          <label class="field-label">Judge model</label>
          <select v-model="judgeModel" class="field-input">
            <option v-for="modelOption in judgeModels" :key="modelOption" :value="modelOption">{{ modelOption }}</option>
          </select>
        </div>
        <div>
          <label class="field-label">Pairing strategy</label>
          <select v-model="pairingStrategy" class="field-input">
            <option value="balanced_random">Balanced random</option>
            <option value="random">Pure random</option>
            <option value="submitted_order">Submitted order</option>
          </select>
        </div>
        <div>
          <label class="field-label">Broadcast pacing</label>
          <select v-model="progressionMode" class="field-input">
            <option value="automatic">Automatic</option>
            <option value="manual">Manual: pause between rounds and brackets</option>
          </select>
        </div>
        <div>
          <label class="field-label">Run count</label>
          <input v-model.number="rerunCount" type="number" min="1" max="50" class="field-input" />
        </div>
      </div>

      <div class="mt-4 flex flex-wrap gap-3">
        <button class="primary-button" :disabled="running || rerunCount < 1" @click="queueRuns">
          {{ competition?.status === "open" ? `Close entries and run ${rerunCount}` : `Run ${rerunCount} more ${rerunCount === 1 ? "time" : "times"}` }}
        </button>
        <p class="text-sm text-slate-500">
          Recommended: use `balanced random` for matchup variety, and `manual` pacing when you want time to read results to the audience before advancing.
        </p>
      </div>
      <p v-if="adminError" class="mt-4 text-sm font-medium text-rose-600">{{ adminError }}</p>
    </SectionCard>

    <SectionCard
      v-if="state.user?.role === 'admin' && (canAdvanceRound || canAdvanceBracket || runningRun)"
      kicker="Broadcast controls"
      title="Advance the event on your cue"
      body="Manual pacing pauses after each round and between brackets so the host can read the verdict before the next result lands."
    >
      <div class="flex flex-wrap items-center gap-3">
        <button v-if="canAdvanceRound" class="primary-button" @click="startNextRound">
          Start next round
        </button>
        <button v-if="canAdvanceBracket" class="primary-button" @click="startNextBracket">
          Start next bracket
        </button>
        <p v-if="runningRun" class="text-sm text-slate-500">
          Run {{ runningRun.run_number }} is judging live now.
        </p>
        <p v-else-if="activeManualRun" class="text-sm text-slate-500">
          Run {{ activeManualRun.run_number }} is paused after round results.
        </p>
        <p v-else-if="nextManualRun" class="text-sm text-slate-500">
          Run {{ nextManualRun.run_number }} is queued and waiting for the next-bracket trigger.
        </p>
      </div>
      <p v-if="adminError" class="mt-4 text-sm font-medium text-rose-600">{{ adminError }}</p>
    </SectionCard>

    <SectionCard
      kicker="Run history"
      title="Every bracket execution"
      body="Pick a run to inspect its bracket. Completed competitions can always be replayed again with new pairing seeds."
    >
      <EmptyState
        v-if="runs.length === 0"
        title="No runs yet"
        body="Once you start the bracket, each execution will appear here as a durable run record with its own status and champion."
      />

      <div v-else class="run-history-grid">
        <button
          v-for="run in runs"
          :key="run.id"
          type="button"
          class="run-history-card"
          :class="{ 'is-selected': selectedRun?.id === run.id }"
          @click="selectRun(run.id)"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="section-kicker">Run {{ run.run_number }}</p>
              <h3>Seed {{ run.pairing_seed ?? "n/a" }}</h3>
            </div>
            <StatusBadge :status="run.status" />
          </div>
          <p class="mt-3 text-sm text-slate-600">{{ run.pairing_strategy.replace(/_/g, " ") }} | {{ run.match_count }} matches</p>
          <p class="mt-2 text-sm text-slate-500">{{ prettyStatus(run.progression_mode) }} pacing</p>
          <p class="mt-2 text-sm text-slate-500">
            {{ run.champion_label ? `Champion: ${compactUrl(run.champion_label)}` : "Champion pending" }}
          </p>
          <p class="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">{{ formatShortDate(run.updated_at || run.created_at) }}</p>
        </button>
      </div>
    </SectionCard>

    <SectionCard
      kicker="Selected run"
      :title="selectedRun ? `Run ${selectedRun.run_number}` : 'Bracket preview'"
      :body="selectedRunSummary"
    >
      <template #actions>
        <div class="flex flex-wrap items-center gap-3">
          <StatusBadge v-if="selectedRun" :status="selectedRun.status" />
          <span v-if="selectedRun?.champion_label" class="text-sm text-slate-500">Champion: {{ compactUrl(selectedRun.champion_label) }}</span>
        </div>
      </template>
      <BracketStage
        :entries="entries"
        :matches="matches"
        :competition-status="selectedRun?.status || competition?.status || ''"
        :live-mode="selectedRun?.status === 'running'"
      />
    </SectionCard>

    <SectionCard
      kicker="Entrants"
      :title="pluralize(entries.length, 'entry')"
      body="The entrant field stays fixed while you replay the bracket, so all confidence comes from repeated pairings rather than changing the competitors."
    >
      <EmptyState
        v-if="entries.length === 0"
        title="No entries yet"
        body="Finished runs submitted into this competition will appear here before judging starts."
      />

      <div v-else class="space-y-4">
        <article v-for="entry in entries" :key="entry.id" class="surface-muted p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <button class="text-left font-display text-2xl font-semibold text-slate-900 hover:text-brand-700" @click="router.push(`/sessions/${entry.session_id}`)">
                {{ entryLabel(entry) }}
              </button>
              <p class="mt-2 text-sm leading-6 text-slate-600">{{ entry.goal || "No goal summary available." }}</p>
              <p class="mt-3 text-sm text-slate-500">{{ entry.email }} | {{ entry.action_count || 0 }} actions</p>
              <p v-if="entry.note" class="mt-3 text-sm leading-6 text-slate-500">{{ entry.note }}</p>
            </div>
            <StatusBadge :status="entry.session_status || 'unknown'" />
          </div>
        </article>
      </div>
    </SectionCard>
  </div>
</template>
