<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import EmptyState from "../components/EmptyState.vue";
import PageHero from "../components/PageHero.vue";
import SectionCard from "../components/SectionCard.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { apiRequest, state } from "../lib/store.js";
import { formatShortDate, pluralize } from "../lib/formatters.js";

const router = useRouter();
const competitions = ref([]);
const showCreate = ref(false);
const newName = ref("");
const newDescription = ref("");
const createError = ref("");

const heroMetrics = computed(() => [
  { label: "Open", value: String(competitions.value.filter((item) => item.status === "open").length), detail: "Accepting entries" },
  { label: "Running", value: String(competitions.value.filter((item) => item.status === "running").length), detail: "Judging now" },
  { label: "Complete", value: String(competitions.value.filter((item) => item.status === "complete").length), detail: "Archived" },
]);

const groups = computed(() => [
  {
    key: "open",
    title: "Accepting entries",
    body: "Open competitions are still collecting finished sessions.",
    items: competitions.value.filter((item) => item.status === "open"),
  },
  {
    key: "active",
    title: "Active brackets",
    body: "Closed and running competitions that are ready for judging or already underway.",
    items: competitions.value.filter((item) => item.status === "closed" || item.status === "running"),
  },
  {
    key: "complete",
    title: "Completed competitions",
    body: "Completed tournaments stay here for replay and comparison.",
    items: competitions.value.filter((item) => item.status === "complete"),
  },
]);

async function loadCompetitions() {
  competitions.value = await apiRequest("/competitions");
}

async function createCompetition() {
  createError.value = "";
  try {
    await apiRequest("/competitions", {
      method: "POST",
      body: JSON.stringify({ name: newName.value, description: newDescription.value }),
    });
    showCreate.value = false;
    newName.value = "";
    newDescription.value = "";
    await loadCompetitions();
  } catch (err) {
    createError.value = err.message || "Unable to create competition";
  }
}

onMounted(loadCompetitions);
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Competition hub"
      title="One vertical competition flow, from event setup to finished bracket."
      body="The second frontend removes multi-column page layouts and keeps competition management readable while preserving the same backend behavior."
      :metrics="heroMetrics"
    >
      <template #actions>
        <div v-if="state.user?.role === 'admin'" class="mb-5 flex flex-wrap gap-3">
          <button class="primary-button" @click="showCreate = !showCreate">
            {{ showCreate ? "Close creator" : "New competition" }}
          </button>
        </div>
      </template>
    </PageHero>

    <SectionCard
      v-if="showCreate"
      kicker="Competition setup"
      title="Create a new bracket"
      body="The creation flow is intentionally simple and stays inline with the rest of the page."
    >
      <form class="space-y-5" @submit.prevent="createCompetition">
        <div>
          <label class="field-label">Competition name</label>
          <input v-model="newName" class="field-input" placeholder="Vibecode Olympics - Spring qualifier" required />
        </div>
        <div>
          <label class="field-label">Description</label>
          <textarea v-model="newDescription" class="field-input min-h-32" rows="4" placeholder="What is being judged and how should entrants think about the format?" />
        </div>
        <div class="flex flex-wrap gap-3">
          <button class="primary-button">Create competition</button>
          <button type="button" class="ghost-button" @click="showCreate = false">Cancel</button>
        </div>
        <p v-if="createError" class="text-sm font-medium text-rose-600">{{ createError }}</p>
      </form>
    </SectionCard>

    <SectionCard
      v-for="group in groups"
      :key="group.key"
      :kicker="group.key === 'open' ? 'Open field' : group.key === 'active' ? 'Bracket stage' : 'Archive'"
      :title="group.title"
      :body="group.body"
    >
      <EmptyState
        v-if="group.items.length === 0"
        :title="`No ${group.title.toLowerCase()}`"
        body="This section will populate automatically as competitions are created, closed, run, and completed."
      />

      <div v-else class="space-y-4">
        <article
          v-for="competition in group.items"
          :key="competition.id"
          class="surface-muted cursor-pointer p-4 transition hover:border-brand-200 hover:bg-white"
          @click="router.push(`/competitions/${competition.id}`)"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <h3 class="font-display text-2xl font-semibold text-slate-900">{{ competition.name }}</h3>
              <p class="mt-2 text-sm leading-6 text-slate-600">{{ competition.description || "No description yet." }}</p>
              <p class="mt-3 text-sm text-slate-500">
                {{ pluralize(competition.entry_count, "entry") }} | {{ pluralize(competition.run_count || 0, "run") }} | {{ formatShortDate(competition.updated_at || competition.created_at) }}
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <StatusBadge :status="competition.status" />
              <button class="ghost-button" @click.stop="router.push(`/competitions/${competition.id}`)">Open</button>
            </div>
          </div>
        </article>
      </div>
    </SectionCard>
  </div>
</template>
