import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  useRoute,
  watch,
} from "../lib/vue-globals.js";
import { apiRequest, store } from "../lib/app-state.js";
import {
  buildBracketLayout,
  buildPreviewRounds,
  getBracketConstants,
} from "../lib/bracket-layout.js";
import {
  compactUrl,
  formatShortDate,
  pluralize,
  prettyStatus,
} from "../lib/formatters.js";
import { back, go } from "../lib/navigation.js";
import { EmptyState, MetricRail, StatusPill } from "../components/primitives.js";

const BRACKET_CONSTANTS = getBracketConstants();

function parseMatches(matches) {
  return matches.map((match) => ({
    ...match,
    entry_ids_parsed: JSON.parse(match.entry_ids || "[]"),
  }));
}

export const CompetitionList = {
  components: { StatusPill, MetricRail, EmptyState },
  template: `
    <div class="page page--competitions">
      <section class="page-hero">
        <div>
          <p class="section-kicker">Competition Hub</p>
          <h1>Turn finished runs into an event instead of a spreadsheet.</h1>
          <p class="page-hero__lead">
            Open contests, close the field, then run bracket judging round by round with a presentation layer that feels like a real tournament.
          </p>
        </div>
        <div class="hero-actions">
          <button v-if="store.user?.role === 'admin'" class="button button--primary" @click="showCreate = !showCreate">
            {{ showCreate ? "Close creator" : "New competition" }}
          </button>
        </div>
      </section>

      <MetricRail :metrics="heroMetrics" />

      <section v-if="showCreate" class="panel-surface panel-surface--raised">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">Competition Setup</p>
            <h2>Create a new bracket</h2>
          </div>
        </div>
        <form class="form-layout" @submit.prevent="createCompetition">
          <div class="field-stack">
            <label class="field-label">Competition name</label>
            <input v-model="newName" placeholder="Vibecode Olympics - Spring Qualifier" required />
          </div>
          <div class="field-stack">
            <label class="field-label">Description</label>
            <textarea v-model="newDescription" rows="4" placeholder="What is being judged and how should entrants think about the format?"></textarea>
          </div>
          <div class="wizard-footer">
            <button class="button button--primary">Create competition</button>
            <button type="button" class="button button--ghost" @click="resetCreate">Cancel</button>
          </div>
          <p class="form-feedback form-feedback--error" v-if="createError">{{ createError }}</p>
        </form>
      </section>

      <section class="competition-groups">
        <article class="panel-surface" v-for="group in groupedCompetitions" :key="group.key">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">{{ group.kicker }}</p>
              <h2>{{ group.title }}</h2>
            </div>
            <span class="group-count">{{ pluralize(group.items.length, 'competition') }}</span>
          </div>

          <EmptyState
            v-if="group.items.length === 0"
            :title="'No ' + group.title.toLowerCase()"
            :body="group.empty"
          />

          <div v-else class="competition-card-grid">
            <article v-for="competition in group.items" :key="competition.id" class="competition-card competition-card--broadcast" @click="view(competition.id)">
              <div class="competition-card__header">
                <div>
                  <strong>{{ competition.name }}</strong>
                  <p>{{ competition.description || 'No description yet.' }}</p>
                </div>
                <StatusPill :status="competition.status" />
              </div>
              <div class="competition-card__meta">
                <span>{{ pluralize(competition.entry_count, 'entry') }}</span>
                <span>{{ formatShortDate(competition.updated_at || competition.created_at) }}</span>
              </div>
              <div class="competition-card__footer">
                <span>{{ stageCopy(competition.status) }}</span>
                <button type="button" class="button button--ghost button--small" @click.stop="view(competition.id)">Open bracket</button>
              </div>
            </article>
          </div>
        </article>
      </section>
    </div>
  `,
  setup() {
    const competitions = ref([]);
    const showCreate = ref(false);
    const newName = ref("");
    const newDescription = ref("");
    const createError = ref("");

    const load = async () => {
      competitions.value = await apiRequest("/competitions");
    };

    const heroMetrics = computed(() => [
      { label: "Open", value: String(competitions.value.filter((item) => item.status === "open").length), detail: "Accepting entries" },
      { label: "Running", value: String(competitions.value.filter((item) => item.status === "running").length), detail: "Judging live" },
      { label: "Complete", value: String(competitions.value.filter((item) => item.status === "complete").length), detail: "Ready to review" },
    ]);

    const groupedCompetitions = computed(() => [
      {
        key: "open",
        kicker: "Open Field",
        title: "Accepting entries",
        empty: "Open a new competition or wait for the next event to accept finished runs.",
        items: competitions.value.filter((item) => item.status === "open"),
      },
      {
        key: "running",
        kicker: "Active Brackets",
        title: "In progress",
        empty: "No competition is running at the moment.",
        items: competitions.value.filter((item) => item.status === "running" || item.status === "closed"),
      },
      {
        key: "complete",
        kicker: "Archive",
        title: "Completed",
        empty: "Completed competitions will appear here after judging finishes.",
        items: competitions.value.filter((item) => item.status === "complete"),
      },
    ]);

    const createCompetition = async () => {
      createError.value = "";
      try {
        await apiRequest("/competitions", {
          method: "POST",
          body: JSON.stringify({ name: newName.value, description: newDescription.value }),
        });
        resetCreate();
        await load();
      } catch (err) {
        createError.value = err.message || "Unable to create competition";
      }
    };

    const resetCreate = () => {
      showCreate.value = false;
      newName.value = "";
      newDescription.value = "";
      createError.value = "";
    };

    onMounted(load);

    return {
      store,
      competitions,
      showCreate,
      newName,
      newDescription,
      createError,
      heroMetrics,
      groupedCompetitions,
      createCompetition,
      resetCreate,
      view: (id) => go(`/competitions/${id}`),
      formatShortDate,
      pluralize,
      stageCopy: (status) => {
        if (status === "open") return "Entries are still coming in.";
        if (status === "closed") return "Field is locked and ready to judge.";
        if (status === "running") return "Judging is underway.";
        return "Champion decided and bracket archived.";
      },
    };
  },
};

export const CompetitionDetail = {
  components: { StatusPill, MetricRail, EmptyState },
  template: `
    <div class="page page--competition-detail">
      <section class="page-hero page-hero--competition">
        <div>
          <button class="button button--ghost button--small" @click="goBack">Back to competitions</button>
          <p class="section-kicker">Competition Bracket</p>
          <h1>{{ competition?.name || "Competition" }}</h1>
          <p class="page-hero__lead">{{ competition?.description || 'No description provided.' }}</p>
        </div>
        <div class="hero-actions">
          <StatusPill v-if="competition" :status="competition.status" />
          <div v-if="store.user?.role === 'admin' && competition" class="admin-control-cluster">
            <button v-if="competition.status === 'open'" class="button button--ghost" @click="closeEntries">Close entries</button>
            <template v-if="competition.status === 'closed'">
              <select v-model="judgeProvider">
                <option v-for="provider in providers" :key="provider" :value="provider">{{ provider }}</option>
              </select>
              <select v-model="judgeModel">
                <option v-for="modelOption in judgeModels" :key="modelOption" :value="modelOption">{{ modelOption }}</option>
              </select>
              <button class="button button--primary" @click="runCompetition" :disabled="running">Run bracket</button>
            </template>
          </div>
        </div>
      </section>

      <MetricRail :metrics="competitionMetrics" />
      <p class="form-feedback form-feedback--error" v-if="adminError">{{ adminError }}</p>

      <section v-if="championEntry" class="champion-banner panel-surface panel-surface--raised">
        <p class="section-kicker">Champion</p>
        <h2>{{ entryLabel(championEntry.id) }}</h2>
        <p>{{ championEntry.goal || championEntry.note || championEntry.start_url }}</p>
      </section>

      <div class="competition-detail-layout">
        <section class="panel-surface">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">Entrants</p>
              <h2>{{ pluralize(entries.length, 'entry') }}</h2>
            </div>
          </div>

          <EmptyState
            v-if="entries.length === 0"
            title="No entries yet"
            body="Finished runs submitted into this competition will appear here before judging starts."
          />

          <div v-else class="entry-card-grid">
            <article v-for="entry in entries" :key="entry.id" class="entry-card">
              <div class="entry-card__header">
                <div>
                  <a :href="'#/sessions/' + entry.session_id" @click.stop>{{ entryLabel(entry.id) }}</a>
                  <p>{{ entry.goal || 'No goal summary available.' }}</p>
                </div>
                <StatusPill :status="entry.session_status || 'unknown'" />
              </div>
              <div class="entry-card__meta">
                <span>{{ entry.email }}</span>
                <span>{{ pluralize(entry.action_count || 0, 'action') }}</span>
              </div>
              <p class="entry-card__note" v-if="entry.note">{{ entry.note }}</p>
            </article>
          </div>
        </section>

        <section class="panel-surface panel-surface--raised bracket-shell">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">Bracket Stage</p>
              <h2>{{ bracketTitle }}</h2>
            </div>
          </div>

          <EmptyState
            v-if="!layout.columns.length"
            title="Bracket not built yet"
            body="Once the field is closed and the competition runs, the tournament tree will appear here."
          />

          <div v-else class="bracket-scroll">
            <div class="bracket-stage" :style="{ width: layout.stageWidth + 'px', height: (layout.stageHeight + 44) + 'px' }">
              <div
                v-for="column in bracketColumns"
                :key="'title-' + column.index"
                class="bracket-round-label"
                :style="{ left: column.left + 'px' }"
              >
                Round {{ column.index + 1 }}
              </div>

              <svg class="bracket-svg" :viewBox="'0 0 ' + layout.stageWidth + ' ' + layout.stageHeight" preserveAspectRatio="none">
                <line
                  v-for="connector in layout.connectors"
                  :key="connector.key"
                  :x1="connector.x1"
                  :y1="connector.y1"
                  :x2="connector.x2"
                  :y2="connector.y2"
                />
              </svg>

              <article
                v-for="match in positionedMatches"
                :key="match.id"
                class="match-card match-card--tournament"
                :data-complete="match.status"
                :style="{
                  width: match.width + 'px',
                  height: match.height + 'px',
                  transform: 'translate(' + match.left + 'px,' + match.top + 'px)',
                }"
              >
                <div class="match-card__topline">
                  <span>Match {{ match.match_number }}</span>
                  <span>{{ prettyStatus(match.status || 'pending') }}</span>
                </div>
                <div class="match-entry-list">
                  <div
                    v-for="entryId in match.entry_ids_parsed"
                    :key="entryId"
                    class="match-entry"
                    :class="{ 'is-winner': match.winner_entry_id && entryId === match.winner_entry_id }"
                  >
                    <strong>{{ entryLabel(entryId) }}</strong>
                    <span>{{ winnerLabel(match, entryId) }}</span>
                  </div>
                </div>
                <details v-if="match.judge_reasoning" class="match-reasoning">
                  <summary>Judge reasoning</summary>
                  <p>{{ match.judge_reasoning }}</p>
                </details>
              </article>
            </div>
          </div>
        </section>
      </div>
    </div>
  `,
  setup() {
    const route = useRoute();
    const competition = ref(null);
    const entries = ref([]);
    const matches = ref([]);
    const judgeProvider = ref("openai");
    const judgeModel = ref("");
    const running = ref(false);
    const adminError = ref("");
    let pollTimer = null;

    const providers = computed(() => Object.keys(store.models || {}));
    const judgeModels = computed(() => store.models?.[judgeProvider.value] || []);

    const entryMap = computed(() => {
      const map = {};
      entries.value.forEach((entry) => {
        map[entry.id] = entry;
      });
      return map;
    });

    const parsedMatches = computed(() => parseMatches(matches.value));
    const rounds = computed(() => {
      if (!parsedMatches.value.length) return [];
      const byRound = {};
      parsedMatches.value.forEach((match) => {
        if (!byRound[match.round_number]) byRound[match.round_number] = [];
        byRound[match.round_number].push(match);
      });
      const maxRound = Math.max(...Object.keys(byRound).map(Number));
      return Array.from({ length: maxRound }, (_, index) => byRound[index + 1] || []);
    });

    const previewRounds = computed(() => buildPreviewRounds(entries.value.map((entry) => entry.id)));
    const displayRounds = computed(() => (rounds.value.length ? rounds.value : previewRounds.value));
    const layout = computed(() => buildBracketLayout(displayRounds.value));
    const bracketColumns = computed(() =>
      layout.value.columns.map((column, index) => ({
        index,
        left: index * (BRACKET_CONSTANTS.cardWidth + BRACKET_CONSTANTS.columnGap),
      }))
    );
    const positionedMatches = computed(() => layout.value.columns.flat());

    const displayMatchCount = computed(() => displayRounds.value.reduce((sum, round) => sum + round.length, 0));
    const completedMatches = computed(() => parsedMatches.value.filter((match) => match.status === "complete").length);
      const championEntry = computed(() => {
      const finalRound = rounds.value[rounds.value.length - 1] || [];
      const finalMatch = finalRound[0];
      if (!finalMatch?.winner_entry_id) return null;
      return entryMap.value[finalMatch.winner_entry_id] || null;
    });

    const competitionMetrics = computed(() => [
      { label: "Status", value: prettyStatus(competition.value?.status || "open"), detail: competition.value?.updated_at ? formatShortDate(competition.value.updated_at) : "Not started" },
      { label: "Entrants", value: String(entries.value.length), detail: pluralize(entries.value.length, "run") },
      {
        label: "Matches",
        value: rounds.value.length ? `${completedMatches.value}/${parsedMatches.value.length}` : `${displayMatchCount.value} preview`,
        detail: `${displayRounds.value.length} rounds`,
      },
    ]);

    const bracketTitle = computed(() => {
      if (competition.value?.status === "running") return "Bracket live";
      if (competition.value?.status === "complete") return "Bracket complete";
      if (!rounds.value.length && entries.value.length > 1) return "Bracket preview";
      if (competition.value?.status === "closed") return "Field locked";
      return "Awaiting entries";
    });

    const load = async () => {
      const data = await apiRequest(`/competitions/${route.params.id}`);
      competition.value = data.competition;
      entries.value = data.entries || [];
      matches.value = data.matches || [];
    };

    const closeEntries = async () => {
      adminError.value = "";
      try {
        await apiRequest(`/competitions/${competition.value.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: "closed" }),
        });
        await load();
      } catch (err) {
        adminError.value = err.message || "Unable to close entries";
      }
    };

    const runCompetition = async () => {
      adminError.value = "";
      running.value = true;
      try {
        await apiRequest(`/competitions/${competition.value.id}/run`, {
          method: "POST",
          body: JSON.stringify({ provider: judgeProvider.value, model: judgeModel.value }),
        });
        await load();
        startPoll();
      } catch (err) {
        adminError.value = err.message || "Unable to run competition";
        running.value = false;
      }
    };

    const startPoll = () => {
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(async () => {
        await load();
        if (competition.value?.status === "complete") {
          clearInterval(pollTimer);
          running.value = false;
        }
      }, 3000);
    };

    watch(judgeProvider, () => {
      if (!judgeModels.value.includes(judgeModel.value)) {
        judgeModel.value = judgeModels.value[0] || "";
      }
    });

    onMounted(async () => {
      await load();
      if (!judgeModels.value.includes(judgeModel.value)) {
        judgeModel.value = judgeModels.value[0] || "";
      }
      if (competition.value?.status === "running") {
        running.value = true;
        startPoll();
      }
    });

    onBeforeUnmount(() => {
      if (pollTimer) clearInterval(pollTimer);
    });

    return {
      store,
      competition,
      entries,
      running,
      adminError,
      judgeProvider,
      judgeModel,
      judgeModels,
      providers,
      layout,
      bracketColumns,
      positionedMatches,
      championEntry,
      competitionMetrics,
      bracketTitle,
      closeEntries,
      runCompetition,
      prettyStatus,
      pluralize,
      goBack: () => back("/competitions"),
      entryLabel: (entryId) => {
        const entry = entryMap.value[entryId];
        if (!entry) {
          if (typeof entryId === "string" && entryId.startsWith("winner-r")) {
            const parts = entryId.match(/^winner-r(\d+)-m(\d+)$/);
            if (parts) return `Winner R${parts[1]} M${parts[2]}`;
          }
          return `Entry #${entryId}`;
        }
        return compactUrl(entry.start_url || entry.session_id);
      },
      winnerLabel: (match, entryId) => {
        if (!match.winner_entry_id) return "Pending";
        return match.winner_entry_id === entryId ? "Winner" : "Eliminated";
      },
    };
  },
};
