<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  buildBracketLayout,
  buildPreviewRounds,
  groupMatchesIntoRounds,
  parseMatches,
} from "../lib/bracket.js";
import { compactUrl, prettyStatus } from "../lib/formatters.js";
import EmptyState from "./EmptyState.vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps({
  entries: {
    type: Array,
    default: () => [],
  },
  matches: {
    type: Array,
    default: () => [],
  },
  competitionStatus: {
    type: String,
    default: "",
  },
  liveMode: {
    type: Boolean,
    default: false,
  },
});

const entryMap = computed(() => {
  const map = {};
  props.entries.forEach((entry) => {
    map[entry.id] = entry;
  });
  return map;
});

const parsedMatches = computed(() => parseMatches(props.matches));
const actualRounds = computed(() => groupMatchesIntoRounds(parsedMatches.value));
const previewRounds = computed(() => buildPreviewRounds(props.entries.map((entry) => entry.id)));
const rounds = computed(() => (actualRounds.value.length ? actualRounds.value : previewRounds.value));
const layout = computed(() => buildBracketLayout(rounds.value));

const flattenedMatches = computed(() =>
  rounds.value.flatMap((round) =>
    round.matches.map((match) => ({
      ...match,
      roundNumber: round.roundNumber,
    })),
  ),
);

const matchMap = computed(() => {
  const map = {};
  flattenedMatches.value.forEach((match) => {
    map[String(match.id)] = match;
  });
  return map;
});

const championMatch = computed(() => actualRounds.value[actualRounds.value.length - 1]?.matches?.[0] || null);
const championEntry = computed(() => {
  const winnerId = championMatch.value?.winner_entry_id;
  return winnerId ? entryMap.value[winnerId] || null : null;
});

const selectedMatchId = ref(null);
const seenCompletedIds = new Set();
let seededCompletedMatches = false;

const activeMatch = computed(() => {
  if (!selectedMatchId.value) return null;
  return matchMap.value[selectedMatchId.value] || null;
});

const confettiPieces = Array.from({ length: 20 }, (_, index) => ({
  id: `confetti-${index + 1}`,
  left: `${4 + (index * 91) % 92}%`,
  delay: `${(index % 7) * 0.35}s`,
  duration: `${4.6 + (index % 5) * 0.55}s`,
  rotation: `${(index % 6) * 18}deg`,
}));

const liveMatchId = computed(() => {
  const runningMatch = flattenedMatches.value.find((match) => match.status === "running");
  return runningMatch ? String(runningMatch.id) : null;
});

const latestCompleteMatch = computed(() => {
  const completeMatches = flattenedMatches.value.filter((match) => match.status === "complete");
  if (!completeMatches.length) return null;
  return [...completeMatches].sort((a, b) => {
    if (a.roundNumber !== b.roundNumber) return a.roundNumber - b.roundNumber;
    return a.match_number - b.match_number;
  }).at(-1);
});

function entryLabel(entryId) {
  const entry = entryMap.value[entryId];
  if (!entry) {
    if (typeof entryId === "string" && entryId.startsWith("winner-r")) {
      const parts = entryId.match(/^winner-r(\d+)-m(\d+)$/);
      if (parts) return `Winner R${parts[1]} M${parts[2]}`;
    }
    return `Entry #${entryId}`;
  }
  return compactUrl(entry.start_url || entry.session_id);
}

function matchSummary(match) {
  if (match.status === "running") return "Judging live";
  if (match.status === "complete" && match.winner_entry_id) return `Winner: ${entryLabel(match.winner_entry_id)}`;
  return actualRounds.value.length ? "Awaiting verdict" : "Preview match";
}

function roundTitle(roundIndex) {
  const totalRounds = rounds.value.length;
  const fromEnd = totalRounds - roundIndex;
  if (totalRounds === 1) return "Grand Final";
  if (fromEnd === 1) return "Grand Final";
  if (fromEnd === 2) return "Semifinal";
  if (fromEnd === 3) return "Quarterfinal";
  return `Round ${roundIndex + 1}`;
}

function openMatch(match) {
  selectedMatchId.value = String(match.id);
}

function closeMatch() {
  selectedMatchId.value = null;
}

function onKeydown(event) {
  if (event.key === "Escape" && selectedMatchId.value) {
    closeMatch();
  }
}

function entrantTone(match, entryId) {
  if (match.status === "running") return "arena-entrant is-live";
  if (match.winner_entry_id && entryId === match.winner_entry_id) return "arena-entrant is-winner";
  if (match.winner_entry_id) return "arena-entrant is-eliminated";
  return "arena-entrant";
}

watch(
  flattenedMatches,
  (matches) => {
    const completed = matches.filter((match) => match.status === "complete");
    if (!seededCompletedMatches) {
      completed.forEach((match) => seenCompletedIds.add(String(match.id)));
      seededCompletedMatches = true;
      return;
    }

    const freshCompletion = completed
      .filter((match) => !seenCompletedIds.has(String(match.id)))
      .sort((a, b) => {
        if (a.roundNumber !== b.roundNumber) return a.roundNumber - b.roundNumber;
        return a.match_number - b.match_number;
      })
      .at(-1);
    completed.forEach((match) => seenCompletedIds.add(String(match.id)));

    if (freshCompletion && props.liveMode) {
      selectedMatchId.value = String(freshCompletion.id);
    }
  },
  { deep: true, immediate: true },
);

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <EmptyState
    v-if="!rounds.length"
    title="Bracket not available yet"
    body="Once entries arrive or judging begins, the round structure will appear here."
  />

  <div v-else class="arena-shell">
    <div class="arena-shell__header">
      <div>
        <p class="arena-eyebrow">VibeCode Olympics Broadcast</p>
        <h3 class="arena-shell__title">Live elimination bracket</h3>
        <p class="arena-shell__body">
          The stage shifts into a tournament broadcast mode: connected rounds, live verdict pulses, and modal judge explanations built for demo screens.
        </p>
      </div>

      <div class="arena-shell__summary">
        <div class="arena-mini-card">
          <span>Bracket</span>
          <strong>{{ actualRounds.length ? "Live data" : "Preview" }}</strong>
        </div>
        <div class="arena-mini-card">
          <span>Latest verdict</span>
          <strong>{{ latestCompleteMatch ? `R${latestCompleteMatch.roundNumber} M${latestCompleteMatch.match_number}` : "Pending" }}</strong>
        </div>
        <div class="arena-mini-card">
          <span>Current match</span>
          <strong>{{ liveMatchId ? "Judging now" : championEntry ? "Champion locked" : "Waiting" }}</strong>
        </div>
      </div>
    </div>

    <div class="arena-marquee">
      <span>VIBECODE OLYMPICS</span>
      <span>LIVE BRACKET FEED</span>
      <span>JUDGE CAM</span>
      <span>VIBECODE OLYMPICS</span>
      <span>LIVE BRACKET FEED</span>
      <span>JUDGE CAM</span>
    </div>

    <div class="arena-stage">
      <div v-if="championEntry" class="arena-confetti" aria-hidden="true">
        <span
          v-for="piece in confettiPieces"
          :key="piece.id"
          class="arena-confetti__piece"
          :style="{
            left: piece.left,
            animationDelay: piece.delay,
            animationDuration: piece.duration,
            '--piece-rotation': piece.rotation,
          }"
        />
      </div>

      <div class="hidden lg:block">
        <div class="arena-scroll">
          <div
            class="arena-bracket"
            :style="{ width: `${layout.width}px`, height: `${layout.height}px` }"
          >
            <svg class="arena-bracket__connections" :viewBox="`0 0 ${layout.width} ${layout.height}`" preserveAspectRatio="none">
              <defs>
                <linearGradient id="arena-line" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="#38bdf8" />
                  <stop offset="50%" stop-color="#c084fc" />
                  <stop offset="100%" stop-color="#f97316" />
                </linearGradient>
              </defs>
              <path
                v-for="edge in layout.edges"
                :key="edge.id"
                class="arena-bracket__path"
                :class="{ 'is-champion': edge.championEdge }"
                :d="`M ${edge.sourceX} ${edge.sourceY} H ${edge.midpointX} V ${edge.targetY} H ${edge.targetX}`"
              />
            </svg>

            <div
              v-for="header in layout.roundHeaders"
              :key="header.id"
              class="arena-round-header"
              :style="{ left: `${header.x}px`, width: `${header.width}px` }"
            >
              <p class="arena-round-header__eyebrow">Round {{ header.roundNumber }}</p>
              <h4>{{ roundTitle(header.roundNumber - 1) }}</h4>
            </div>

            <button
              v-for="node in layout.nodes"
              :key="node.id"
              type="button"
              class="arena-match-card"
              :class="{
                'is-running': node.match.status === 'running',
                'is-complete': node.match.status === 'complete',
                'is-selected': selectedMatchId === String(node.match.id),
              }"
              :style="{
                left: `${node.x}px`,
                top: `${node.y}px`,
                width: `${node.width}px`,
                height: `${node.height}px`,
              }"
              @click="openMatch(node.match)"
            >
              <div class="arena-match-card__chrome">
                <div>
                  <p class="arena-match-card__eyebrow">Match {{ node.match.match_number }}</p>
                  <h4>Round {{ node.match.round_number }}</h4>
                </div>
                <StatusBadge :status="node.match.status || 'pending'" />
              </div>

              <div class="arena-match-card__entrants">
                <div
                  v-for="entryId in node.match.entry_ids_parsed"
                  :key="entryId"
                  :class="entrantTone(node.match, entryId)"
                >
                  <span class="truncate">{{ entryLabel(entryId) }}</span>
                  <strong>{{ node.match.winner_entry_id === entryId ? "ADV" : node.match.winner_entry_id ? "OUT" : node.match.status === "running" ? "LIVE" : "TBD" }}</strong>
                </div>
              </div>

              <div class="arena-match-card__footer">
                <p>{{ matchSummary(node.match) }}</p>
                <span>{{ node.match.judge_reasoning ? "Open verdict" : node.match.status === "running" ? "Open live view" : "Open matchup" }}</span>
              </div>
            </button>

            <div
              v-if="layout.championNode"
              class="arena-champion-card"
              :class="{ 'is-complete': !!championEntry }"
              :style="{
                left: `${layout.championNode.x}px`,
                top: `${layout.championNode.y}px`,
                width: `${layout.championNode.width}px`,
                height: `${layout.championNode.height}px`,
              }"
            >
              <div class="arena-trophy">
                <div class="arena-trophy__shine" />
                <svg viewBox="0 0 160 160" aria-hidden="true">
                  <defs>
                    <linearGradient id="arena-trophy-fill" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stop-color="#fde68a" />
                      <stop offset="40%" stop-color="#f59e0b" />
                      <stop offset="100%" stop-color="#f97316" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M52 24h56v22c0 17-10 32-26 39v13h22v16H56V98h22V85C62 78 52 63 52 46V24Zm-24 10h16v12c0 12 9 22 21 24v15C42 82 28 65 28 46V34Zm88 0h16v12c0 19-14 36-37 39V70c12-2 21-12 21-24V34Zm-47 88h22v12H69v-12Zm-12 14h46v12H57v-12Z"
                    fill="url(#arena-trophy-fill)"
                  />
                </svg>
              </div>
              <p class="arena-champion-card__eyebrow">Champion podium</p>
              <h4>{{ championEntry ? entryLabel(championEntry.id) : "Awaiting champion" }}</h4>
              <p>
                {{
                  championEntry
                    ? (championEntry.goal || championEntry.note || championEntry.start_url)
                    : "The final winner locks here with confetti and the trophy spotlight."
                }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div class="space-y-4 lg:hidden">
        <section v-for="round in rounds" :key="round.roundNumber" class="arena-mobile-round">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="arena-eyebrow">Round {{ round.roundNumber }}</p>
              <h4>{{ roundTitle(round.roundNumber - 1) }}</h4>
            </div>
            <p class="text-sm text-slate-300">{{ round.matches.length }} {{ round.matches.length === 1 ? "match" : "matches" }}</p>
          </div>

          <div class="mt-4 space-y-3">
            <button
              v-for="match in round.matches"
              :key="match.id"
              type="button"
              class="arena-mobile-match"
              :class="{
                'is-running': match.status === 'running',
                'is-complete': match.status === 'complete',
              }"
              @click="openMatch(match)"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="arena-match-card__eyebrow">Match {{ match.match_number }}</p>
                  <h5>{{ matchSummary(match) }}</h5>
                </div>
                <StatusBadge :status="match.status || 'pending'" />
              </div>
              <div class="mt-3 space-y-2">
                <div
                  v-for="entryId in match.entry_ids_parsed"
                  :key="entryId"
                  :class="entrantTone(match, entryId)"
                >
                  <span class="truncate">{{ entryLabel(entryId) }}</span>
                  <strong>{{ match.winner_entry_id === entryId ? "ADV" : match.winner_entry_id ? "OUT" : "TBD" }}</strong>
                </div>
              </div>
            </button>
          </div>
        </section>
      </div>
    </div>

    <teleport to="body">
      <transition name="arena-modal-fade">
        <div v-if="activeMatch" class="arena-modal-backdrop" @click.self="closeMatch">
          <section class="arena-modal">
            <div class="arena-modal__header">
              <div>
                <p class="arena-eyebrow">Round {{ activeMatch.roundNumber }} | Match {{ activeMatch.match_number }}</p>
                <h3>{{ matchSummary(activeMatch) }}</h3>
              </div>
              <div class="flex items-center gap-3">
                <StatusBadge :status="activeMatch.status || 'pending'" />
                <button type="button" class="arena-modal__close" @click="closeMatch">Close</button>
              </div>
            </div>

            <div class="arena-modal__body">
              <div class="arena-modal__panel">
                <p class="arena-eyebrow">Entrants</p>
                <div class="mt-4 space-y-3">
                  <div
                    v-for="entryId in activeMatch.entry_ids_parsed"
                    :key="entryId"
                    :class="entrantTone(activeMatch, entryId)"
                  >
                    <span class="truncate">{{ entryLabel(entryId) }}</span>
                    <strong>
                      {{
                        activeMatch.winner_entry_id === entryId
                          ? "Winner"
                          : activeMatch.winner_entry_id
                            ? "Eliminated"
                            : activeMatch.status === "running"
                              ? "Live"
                              : "Pending"
                      }}
                    </strong>
                  </div>
                </div>
              </div>

              <div class="arena-modal__panel">
                <p class="arena-eyebrow">Judge explanation</p>
                <div class="arena-modal__reasoning">
                  <template v-if="activeMatch.judge_reasoning">
                    <p class="arena-modal__winner">
                      Winner locked:
                      <strong>{{ entryLabel(activeMatch.winner_entry_id) }}</strong>
                    </p>
                    <p class="whitespace-pre-wrap leading-7 text-slate-200">{{ activeMatch.judge_reasoning }}</p>
                  </template>
                  <template v-else-if="activeMatch.status === 'running'">
                    <p class="leading-7 text-slate-200">
                      The judge is evaluating this matchup right now. Keep the modal open on the event screen to catch the verdict as soon as polling updates the bracket.
                    </p>
                  </template>
                  <template v-else>
                    <p class="leading-7 text-slate-200">
                      This matchup has not produced a verdict yet. Once the judge completes the decision, the reasoning will appear here and the bracket card will light up.
                    </p>
                  </template>
                </div>
              </div>
            </div>
          </section>
        </div>
      </transition>
    </teleport>
  </div>
</template>
