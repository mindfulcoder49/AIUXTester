<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import EmptyState from "../components/EmptyState.vue";
import SectionCard from "../components/SectionCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { apiRequest, state } from "../lib/store.js";
import { compactUrl, formatShortDate, pluralize } from "../lib/formatters.js";

const route = useRoute();
const router = useRouter();

// ── state ────────────────────────────────────────────────────────────────────

const competition = ref(null);
const entries = ref([]);
const matches = ref([]);
const runs = ref([]);
const recap = ref(null);
const recapLoading = ref(true);
const generating = ref(false);
const generateError = ref("");
const generateProvider = ref("openai");
const generateModel = ref("");
const copied = ref(false);

// ── derived ──────────────────────────────────────────────────────────────────

const isAdmin = computed(() => state.user?.role === "admin");
const providers = computed(() => Object.keys(state.models || {}));
const generateModels = computed(() => state.models?.[generateProvider.value] || []);

const championEntryId = computed(() => {
  // Pick the entry that won the most runs (majority vote)
  const counts = {};
  for (const r of runs.value) {
    if (r.status === "complete" && r.champion_entry_id) {
      counts[r.champion_entry_id] = (counts[r.champion_entry_id] || 0) + 1;
    }
  }
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return sorted.length ? Number(sorted[0][0]) : null;
});

const championEntry = computed(() =>
  entries.value.find((e) => e.id === championEntryId.value) || null,
);

// For each entry: which round did they exit? (max round they appeared in, per match data)
const entryExitRound = computed(() => {
  const result = {};
  const maxRound = matches.value.reduce((m, match) => Math.max(m, match.round_number), 0);
  for (const entry of entries.value) {
    let lastRound = 0;
    let won = false;
    for (const match of matches.value) {
      let eids = [];
      try { eids = JSON.parse(match.entry_ids || "[]"); } catch (_) {}
      if (!eids.includes(entry.id)) continue;
      if (match.round_number > lastRound) {
        lastRound = match.round_number;
        won = match.winner_entry_id === entry.id;
      }
    }
    if (entry.id === championEntryId.value) {
      result[entry.id] = { label: "Champion", isChampion: true, round: maxRound };
    } else if (lastRound === 0) {
      result[entry.id] = { label: "No matches", isChampion: false, round: 0 };
    } else if (won) {
      result[entry.id] = { label: `Won Round ${lastRound}`, isChampion: false, round: lastRound };
    } else {
      result[entry.id] = { label: `Round ${lastRound}`, isChampion: false, round: lastRound };
    }
  }
  return result;
});

// Entries sorted: champion first, then by round reached descending
const sortedEntries = computed(() =>
  [...entries.value].sort((a, b) => {
    const ra = entryExitRound.value[a.id] || { round: 0, isChampion: false };
    const rb = entryExitRound.value[b.id] || { round: 0, isChampion: false };
    if (ra.isChampion) return -1;
    if (rb.isChampion) return 1;
    return rb.round - ra.round;
  }),
);

const entryMap = computed(() =>
  Object.fromEntries(entries.value.map((e) => [e.id, e])),
);

// Matches grouped by run, then by round within each run
const runGroups = computed(() => {
  const runOrder = runs.value.map((r) => r.id);
  const byRun = {};
  for (const match of matches.value) {
    const rid = match.run_id;
    if (!byRun[rid]) byRun[rid] = {};
    const rn = match.round_number;
    if (!byRun[rid][rn]) byRun[rid][rn] = [];
    byRun[rid][rn].push(match);
  }
  return runOrder
    .filter((rid) => byRun[rid])
    .map((rid, idx) => ({
      runId: rid,
      runIndex: idx + 1,
      rounds: Object.keys(byRun[rid])
        .map(Number)
        .sort((a, b) => a - b)
        .map((n) => ({ number: n, matches: byRun[rid][n] })),
    }));
});

// Rounds per bracket (max round_number in a single run, not total across all runs)
const totalRounds = computed(() => {
  if (matches.value.length === 0) return 0;
  return Math.max(...matches.value.map((m) => m.round_number));
});

const totalMatches = computed(() =>
  matches.value.filter((m) => m.status === "complete").length,
);

const totalActions = computed(() =>
  entries.value.reduce((sum, e) => sum + (e.action_count || 0), 0),
);

const linkedinPost = computed(() => {
  if (!competition.value) return "";
  const n = entries.value.length;
  const champion = championEntry.value;
  const championUrl = champion ? compactUrl(champion.start_url || champion.session_id) : "TBD";
  const narrative = recap.value?.overall_narrative || "";
  const date = formatShortDate(competition.value.updated_at || competition.value.created_at);
  return (
    `${competition.value.name}\n\n` +
    `${n} apps competed. ${totalRounds.value} rounds. ${runs.value.length} runs. ${totalMatches.value} AI-judged matches.\n\n` +
    (narrative ? `${narrative}\n\n` : "") +
    `Champion: ${championUrl}\n\n` +
    `Built with AIUXTester — an AI agent that stress-tests your app's UX and scores it head-to-head against other apps.\n\n` +
    `(${date})`
  );
});

// ── screenshot URL helper ────────────────────────────────────────────────────

function screenshotUrl(entry) {
  if (!entry.first_screenshot_id) return null;
  return `/screenshots/${entry.first_screenshot_id}?token=${state.token}`;
}

function entryAnalysis(entryId) {
  const v = recap.value?.entry_profiles?.[String(entryId)];
  if (!v) return null;
  if (typeof v === "string") return { profile: v };
  return v;
}

function matchEntryIds(match) {
  try { return JSON.parse(match.entry_ids || "[]"); } catch (_) { return []; }
}

// ── data loading ─────────────────────────────────────────────────────────────

async function loadCompetition() {
  const data = await apiRequest(`/competitions/${route.params.id}?include_all_runs=true`);
  competition.value = data.competition;
  entries.value = data.entries || [];
  runs.value = data.runs || [];
  matches.value = data.matches || [];
}

async function loadRecap() {
  recapLoading.value = true;
  try {
    recap.value = await apiRequest(`/competitions/${route.params.id}/recap`);
  } catch (_) {
    recap.value = null;
  } finally {
    recapLoading.value = false;
  }
}

async function generateRecap() {
  generateError.value = "";
  generating.value = true;
  try {
    recap.value = await apiRequest(`/competitions/${route.params.id}/recap/generate`, {
      method: "POST",
      body: JSON.stringify({ provider: generateProvider.value, model: generateModel.value }),
    });
  } catch (err) {
    generateError.value = err.message || "Generation failed";
  } finally {
    generating.value = false;
  }
}

async function copyLinkedin() {
  try {
    await navigator.clipboard.writeText(linkedinPost.value);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2500);
  } catch (_) {}
}

watch(generateProvider, () => {
  if (!generateModels.value.includes(generateModel.value)) {
    generateModel.value = generateModels.value[0] || "";
  }
});

onMounted(async () => {
  await loadCompetition();
  await loadRecap();
  if (!generateModels.value.includes(generateModel.value)) {
    generateModel.value = generateModels.value[0] || "";
  }
});
</script>

<template>
  <div class="page-shell space-y-6">

    <!-- ── Hero ─────────────────────────────────────────────────────────── -->
    <section class="olympics-hero">
      <div class="olympics-hero__grid">
        <div class="olympics-hero__copy">
          <p class="arena-eyebrow">Competition Recap</p>
          <h1>{{ competition?.name || "Competition" }}</h1>
          <p class="olympics-hero__body">{{ competition?.description || "No description provided." }}</p>
          <div class="olympics-hero__actions">
            <button class="ghost-button border-white/15 bg-white/10 text-white hover:bg-white/15"
              @click="router.push(`/competitions/${route.params.id}`)">
              Back to bracket
            </button>
            <StatusBadge v-if="competition" :status="competition.status" />
          </div>
        </div>

        <div class="olympics-hero__scoreboard">
          <article class="olympics-score-tile">
            <span>Apps</span>
            <strong>{{ entries.length }}</strong>
            <p>Competed</p>
          </article>
          <article class="olympics-score-tile">
            <span>Runs</span>
            <strong>{{ runs.length }}</strong>
            <p>Completed brackets</p>
          </article>
          <article class="olympics-score-tile">
            <span>Matches</span>
            <strong>{{ totalMatches }}</strong>
            <p>AI-judged</p>
          </article>
          <article class="olympics-score-tile">
            <span>Rounds</span>
            <strong>{{ totalRounds }}</strong>
            <p>Per bracket</p>
          </article>
        </div>
      </div>
    </section>

    <!-- ── Loading spinner ───────────────────────────────────────────────── -->
    <div v-if="recapLoading" class="flex justify-center py-16">
      <div class="recap-spinner" />
    </div>

    <template v-else>

      <!-- ── No recap yet ─────────────────────────────────────────────────── -->
      <template v-if="!recap && !generating">
        <SectionCard
          v-if="isAdmin"
          kicker="Generate recap"
          title="Turn the match record into a story"
          body="An AI reads every judge decision across all rounds and writes a profile for each app plus an overall tournament narrative — ready to paste into LinkedIn."
        >
          <div class="grid gap-4 sm:grid-cols-2">
            <div>
              <label class="field-label">Judge provider</label>
              <select v-model="generateProvider" class="field-input">
                <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>
            <div>
              <label class="field-label">Model</label>
              <select v-model="generateModel" class="field-input">
                <option v-for="m in generateModels" :key="m" :value="m">{{ m }}</option>
              </select>
            </div>
          </div>
          <div class="mt-5 flex flex-wrap items-center gap-4">
            <button class="primary-button px-6 py-3 text-base" :disabled="!generateModel" @click="generateRecap">
              Generate recap
            </button>
            <p class="text-sm text-slate-500">
              Runs {{ entries.length }} profile calls in parallel, then one narrative call. Takes ~30s.
            </p>
          </div>
          <p v-if="generateError" class="mt-4 text-sm font-medium text-rose-600">{{ generateError }}</p>
        </SectionCard>

        <EmptyState
          v-else
          title="Recap not yet available"
          body="An admin needs to generate the recap before it appears here."
        />
      </template>

      <!-- ── Generating in progress ─────────────────────────────────────── -->
      <SectionCard v-if="generating" kicker="Generating" title="Reading every match record...">
        <div class="flex items-center gap-4 py-4">
          <div class="recap-spinner" />
          <div>
            <p class="font-medium text-slate-800">Writing {{ entries.length }} app profiles in parallel</p>
            <p class="mt-1 text-sm text-slate-500">Then synthesising the tournament narrative. This takes about 30 seconds.</p>
          </div>
        </div>
      </SectionCard>

      <!-- ── Recap content ──────────────────────────────────────────────── -->
      <template v-if="recap">

        <!-- Overall narrative -->
        <section class="recap-narrative-panel">
          <div class="recap-narrative-panel__inner">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p class="section-kicker text-slate-400">Tournament narrative</p>
                <p class="mt-1 text-xs text-slate-500">
                  Generated {{ formatShortDate(recap.generated_at) }} via {{ recap.provider }} / {{ recap.model }}
                  <span v-if="recap.generation_count > 1"> · v{{ recap.generation_count }}</span>
                </p>
              </div>
              <div v-if="isAdmin && !generating" class="flex flex-wrap items-center gap-2">
                <select v-model="generateProvider" class="recap-regen-select">
                  <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
                </select>
                <select v-model="generateModel" class="recap-regen-select">
                  <option v-for="m in generateModels" :key="m" :value="m">{{ m }}</option>
                </select>
                <button
                  class="ghost-button border-white/15 bg-white/10 text-sm text-white hover:bg-white/15"
                  :disabled="!generateModel"
                  @click="generateRecap"
                >
                  Regenerate
                </button>
              </div>
            </div>
            <blockquote class="recap-narrative-panel__quote">
              {{ recap.overall_narrative }}
            </blockquote>
          </div>
        </section>

        <!-- App showcases: full page per entry -->
        <div class="recap-showcases">
          <article
            v-for="entry in sortedEntries"
            :key="entry.id"
            class="recap-showcase"
            :class="{ 'recap-showcase--champion': entry.id === championEntryId }"
          >
            <!-- Header bar -->
            <div class="recap-showcase__header">
              <div class="recap-showcase__header-left">
                <span v-if="entry.id === championEntryId" class="recap-showcase__crown-badge">Champion</span>
                <span class="recap-showcase__url">{{ compactUrl(entry.start_url || entry.session_id) }}</span>
              </div>
              <span class="recap-showcase__placement" :class="entryExitRound[entry.id]?.isChampion ? 'recap-badge--gold' : 'recap-badge--round'">
                {{ entryExitRound[entry.id]?.label || '—' }}
              </span>
            </div>

            <!-- Two-column body -->
            <div class="recap-showcase__body">

              <!-- Screenshot column -->
              <div class="recap-showcase__screenshot-col">
                <img
                  v-if="screenshotUrl(entry)"
                  :src="screenshotUrl(entry)"
                  class="recap-showcase__screenshot"
                  alt="App screenshot"
                  @error="(e) => e.target.style.display = 'none'"
                />
                <div v-else class="recap-showcase__no-shot">No screenshot</div>
                <div class="recap-showcase__meta">
                  <span>{{ entry.email }}</span>
                  <span>{{ entry.action_count || 0 }} AI actions taken</span>
                </div>
              </div>

              <!-- Analysis column -->
              <div class="recap-showcase__analysis">
                <!-- Goal -->
                <div class="recap-showcase__goal">
                  <p class="recap-section-label">Testing goal</p>
                  <p class="recap-showcase__goal-text">{{ entry.goal || "No goal recorded." }}</p>
                </div>

                <template v-if="entryAnalysis(entry.id)">
                  <div class="recap-showcase__section">
                    <p class="recap-section-label">What it does</p>
                    <p>{{ entryAnalysis(entry.id).what_it_does }}</p>
                  </div>

                  <div class="recap-showcase__section recap-showcase__section--amber">
                    <p class="recap-section-label">AI testing agent limitations</p>
                    <p>{{ entryAnalysis(entry.id).agent_limitations }}</p>
                  </div>

                  <div class="recap-showcase__section recap-showcase__section--green">
                    <p class="recap-section-label">Human verdict</p>
                    <p>{{ entryAnalysis(entry.id).human_verdict }}</p>
                  </div>

                  <div class="recap-showcase__section recap-showcase__section--blue">
                    <p class="recap-section-label">Competition performance</p>
                    <p>{{ entryAnalysis(entry.id).profile }}</p>
                  </div>
                </template>
                <div v-else class="recap-showcase__section">
                  <p class="text-sm text-slate-400 italic">No analysis generated yet. Regenerate the recap to produce full app profiles.</p>
                </div>
              </div>
            </div>
          </article>
        </div>

        <!-- Print button (screen only) -->
        <div class="recap-print-bar no-print">
          <button class="primary-button" @click="() => window.print()">Print / Save as PDF</button>
          <p class="text-sm text-slate-500">Each app gets its own page in the PDF.</p>
        </div>

        <!-- Round by round -->
        <SectionCard
          kicker="Round by round"
          :title="`${totalRounds} rounds · ${runs.length} runs`"
          body="Every head-to-head matchup and the AI judge's reasoning for each decision."
        >
          <div v-if="runGroups.length === 0">
            <EmptyState title="No match data" body="No completed matches to display." />
          </div>

          <div v-else class="space-y-8">
            <div v-for="runGroup in runGroups" :key="runGroup.runId">
              <p class="section-kicker mb-4">Run {{ runGroup.runIndex }}</p>
              <div class="space-y-6">
                <div v-for="round in runGroup.rounds" :key="round.number">
                  <p class="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Round {{ round.number }}</p>
                  <div class="space-y-3">
                    <article v-for="match in round.matches" :key="match.id" class="recap-match">
                      <div class="recap-match__contestants">
                        <div
                          v-for="entryId in matchEntryIds(match)"
                          :key="entryId"
                          class="recap-match__entry"
                          :class="{ 'recap-match__entry--winner': match.winner_entry_id === entryId }"
                        >
                          <span class="recap-match__entry-url">
                            {{ compactUrl(entryMap[entryId]?.start_url || entryMap[entryId]?.session_id || String(entryId)) }}
                          </span>
                          <span class="recap-match__entry-verdict">
                            {{ match.winner_entry_id === entryId ? 'Won' : (match.winner_entry_id ? 'Eliminated' : 'Pending') }}
                          </span>
                        </div>
                      </div>
                      <details v-if="match.judge_reasoning" class="recap-match__reasoning">
                        <summary>Judge reasoning</summary>
                        <p>{{ match.judge_reasoning }}</p>
                      </details>
                    </article>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </SectionCard>

        <!-- LinkedIn generator -->
        <SectionCard
          kicker="Share this"
          title="LinkedIn post"
          body="Pre-written from the narrative and stats. Edit before you copy."
        >
          <textarea
            class="recap-linkedin-textarea"
            :value="linkedinPost"
            rows="12"
            @input="(e) => linkedinPost = e.target.value"
          />
          <div class="mt-4 flex items-center gap-4">
            <button class="primary-button" @click="copyLinkedin">
              {{ copied ? 'Copied!' : 'Copy to clipboard' }}
            </button>
            <p class="text-sm text-slate-500">
              {{ entries.length }} apps · {{ totalRounds }} rounds · {{ totalMatches }} matches
            </p>
          </div>
        </SectionCard>

      </template>
    </template>
  </div>
</template>

<style scoped>
/* Spinner */
.recap-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #e2e8f0;
  border-top-color: #0ea5e9;
  border-radius: 50%;
  animation: recap-spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes recap-spin { to { transform: rotate(360deg); } }

/* Narrative panel */
.recap-narrative-panel {
  border-radius: 2rem;
  background:
    radial-gradient(circle at 15% 50%, rgba(56, 189, 248, 0.18), transparent 40%),
    linear-gradient(135deg, rgba(15, 23, 42, 0.97), rgba(30, 41, 59, 0.94));
  border: 1px solid rgba(125, 211, 252, 0.14);
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.2);
  padding: 2rem;
}

.recap-narrative-panel__inner {
  max-width: 860px;
}

.recap-narrative-panel__quote {
  margin-top: 1.5rem;
  font-size: 1.25rem;
  line-height: 1.8;
  color: rgba(241, 245, 249, 0.92);
  font-style: italic;
  border-left: 3px solid rgba(56, 189, 248, 0.5);
  padding-left: 1.25rem;
}

/* ── App showcase cards ──────────────────────────────────────────────────── */
.recap-badge--gold {
  background: rgba(245, 158, 11, 0.9);
  color: white;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: 999px;
}

.recap-badge--round {
  background: rgba(15, 23, 42, 0.72);
  color: rgba(241, 245, 249, 0.9);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: 999px;
}

.recap-showcases {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.recap-showcase {
  border-radius: 1.75rem;
  border: 1px solid rgba(203, 213, 225, 0.8);
  background: white;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.06);
}

.recap-showcase--champion {
  border-color: rgba(245, 158, 11, 0.5);
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.15), 0 8px 32px rgba(15, 23, 42, 0.08);
}

/* Header bar */
.recap-showcase__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  gap: 1rem;
  flex-wrap: wrap;
}

.recap-showcase__header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.recap-showcase__crown-badge {
  background: rgba(245, 158, 11, 0.15);
  color: #b45309;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(245, 158, 11, 0.3);
  white-space: nowrap;
  flex-shrink: 0;
}

.recap-showcase__url {
  font-weight: 700;
  font-size: 1rem;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recap-showcase__placement {
  flex-shrink: 0;
}

/* Two-column body */
.recap-showcase__body {
  display: grid;
  grid-template-columns: 360px 1fr;
  min-height: 480px;
}

@media (max-width: 900px) {
  .recap-showcase__body { grid-template-columns: 1fr; }
}

/* Screenshot column */
.recap-showcase__screenshot-col {
  display: flex;
  flex-direction: column;
  background: #f1f5f9;
  border-right: 1px solid #e2e8f0;
}

.recap-showcase__screenshot {
  width: 100%;
  flex: 1;
  object-fit: cover;
  object-position: top;
  display: block;
  min-height: 380px;
}

.recap-showcase__no-shot {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 0.8rem;
  min-height: 280px;
}

.recap-showcase__meta {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.75rem 1rem;
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
  font-size: 0.75rem;
  color: #64748b;
}

/* Analysis column */
.recap-showcase__analysis {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.recap-showcase__goal {
  padding-bottom: 1.25rem;
  border-bottom: 1px solid #f1f5f9;
}

.recap-showcase__goal-text {
  margin-top: 0.35rem;
  font-size: 0.875rem;
  color: #475569;
  line-height: 1.65;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.recap-section-label {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #94a3b8;
  margin-bottom: 0.35rem;
}

.recap-showcase__section {
  padding: 0.875rem 1rem;
  border-radius: 0.875rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  font-size: 0.875rem;
  color: #334155;
  line-height: 1.65;
}

.recap-showcase__section--amber {
  background: rgba(254, 243, 199, 0.6);
  border-color: rgba(245, 158, 11, 0.2);
}

.recap-showcase__section--amber .recap-section-label { color: #b45309; }

.recap-showcase__section--green {
  background: rgba(220, 252, 231, 0.6);
  border-color: rgba(34, 197, 94, 0.2);
}

.recap-showcase__section--green .recap-section-label { color: #15803d; }

.recap-showcase__section--blue {
  background: rgba(219, 234, 254, 0.6);
  border-color: rgba(59, 130, 246, 0.2);
}

.recap-showcase__section--blue .recap-section-label { color: #1d4ed8; }

/* Print button bar */
.recap-print-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem 0;
}

/* Round by round */
.recap-match {
  border-radius: 1.25rem;
  border: 1px solid rgba(203, 213, 225, 0.7);
  background: white;
  padding: 1rem 1.25rem;
}

.recap-match__contestants {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: stretch;
}

.recap-match__entry {
  flex: 1;
  min-width: 140px;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.6rem 0.75rem;
  border-radius: 0.875rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.recap-match__entry--winner {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.3);
}

.recap-match__entry-url {
  font-size: 0.82rem;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recap-match__entry--winner .recap-match__entry-url {
  color: #047857;
}

.recap-match__entry-verdict {
  font-size: 0.72rem;
  color: #94a3b8;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.recap-match__entry--winner .recap-match__entry-verdict {
  color: #10b981;
}

.recap-match__reasoning {
  margin-top: 0.75rem;
  font-size: 0.82rem;
  color: #64748b;
  line-height: 1.6;
}

.recap-match__reasoning summary {
  cursor: pointer;
  font-weight: 600;
  color: #475569;
  user-select: none;
  list-style: none;
}

.recap-match__reasoning summary::before {
  content: "+ ";
  color: #94a3b8;
}

.recap-match__reasoning[open] summary::before {
  content: "- ";
}

.recap-match__reasoning p {
  margin-top: 0.5rem;
  padding-left: 0.25rem;
}

/* Regenerate selects (inside dark narrative panel) */
.recap-regen-select {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(241, 245, 249, 0.9);
  border-radius: 0.5rem;
  padding: 0.35rem 0.6rem;
  font-size: 0.8rem;
  cursor: pointer;
}
.recap-regen-select option {
  background: #1e293b;
  color: #f1f5f9;
}

/* LinkedIn textarea */
.recap-linkedin-textarea {
  width: 100%;
  border-radius: 1rem;
  border: 1px solid #e2e8f0;
  padding: 1rem;
  font-size: 0.875rem;
  line-height: 1.7;
  color: #334155;
  background: #f8fafc;
  resize: vertical;
  font-family: inherit;
}

.recap-linkedin-textarea:focus {
  outline: none;
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

/* ── Print styles ──────────────────────────────────────────────────────────── */
@media print {
  /* Hide everything except showcases + narrative */
  .no-print,
  .olympics-hero__actions,
  .recap-spinner,
  .recap-narrative-panel .ghost-button,
  .recap-regen-select {
    display: none !important;
  }

  /* Remove page shell padding */
  .page-shell {
    padding: 0 !important;
  }

  /* Each showcase gets its own page */
  .recap-showcase {
    page-break-after: always;
    break-after: page;
    border-radius: 0;
    border: none;
    box-shadow: none;
    margin: 0;
  }

  .recap-showcase:last-child {
    page-break-after: auto;
    break-after: auto;
  }

  /* Expand screenshot to full height */
  .recap-showcase__screenshot {
    min-height: 460px;
  }

  /* Show full goal text */
  .recap-showcase__goal-text {
    -webkit-line-clamp: unset;
    overflow: visible;
  }

  /* Narrative panel on its own page */
  .recap-narrative-panel {
    page-break-after: always;
    break-after: page;
  }

  /* Round-by-round section: avoid breaking mid-match */
  .recap-match {
    page-break-inside: avoid;
    break-inside: avoid;
  }

  /* LinkedIn section: avoid printing */
  .recap-linkedin-textarea,
  .recap-print-bar {
    display: none !important;
  }
}
</style>
