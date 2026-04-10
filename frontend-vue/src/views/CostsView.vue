<script setup>
import { computed, reactive } from "vue";
import PageHero from "../components/PageHero.vue";
import SectionCard from "../components/SectionCard.vue";

const price = reactive({
  web: 0.0080,
  worker: 0.0080,
  redis: 0.0040,
  db: 0.0060,
});

const assumptions = reactive({
  partialActive: 0.25,
  fullActive: 0.10,
});

const hours = reactive({ perMonth: 730 });

function money(value) {
  return `$${(Number(value) || 0).toFixed(2)}`;
}

const alwaysOn = computed(() => {
  const web = price.web * hours.perMonth;
  const worker = price.worker * hours.perMonth;
  const redis = price.redis * hours.perMonth;
  const db = price.db * hours.perMonth;
  return { web, worker, redis, db, total: web + worker + redis + db };
});

const partialZero = computed(() => {
  const web = price.web * hours.perMonth * assumptions.partialActive;
  const worker = price.worker * hours.perMonth * assumptions.partialActive;
  const redis = price.redis * hours.perMonth;
  const db = price.db * hours.perMonth;
  return { web, worker, redis, db, total: web + worker + redis + db };
});

const fullZero = computed(() => {
  const web = price.web * hours.perMonth * assumptions.fullActive;
  const worker = price.worker * hours.perMonth * assumptions.fullActive;
  const redis = price.redis * hours.perMonth * assumptions.fullActive;
  const db = price.db * hours.perMonth * assumptions.fullActive;
  return { web, worker, redis, db, total: web + worker + redis + db };
});

const metrics = computed(() => [
  { label: "Hours", value: String(hours.perMonth), detail: "Monthly estimate" },
  { label: "Always on", value: money(alwaysOn.value.total), detail: "Current baseline" },
  { label: "Full zero", value: money(fullZero.value.total), detail: "If every service sleeps" },
]);
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Cost model"
      title="Compare always-on infrastructure against partial and full scale-down assumptions."
      body="The estimator is intentionally simple: tune your service rates and active ratios, then compare the practical monthly envelope."
      :metrics="metrics"
    />

    <SectionCard
      kicker="Estimator inputs"
      title="Tune the assumptions"
      body="All inputs stay stacked in one form so the estimator remains easy to use on narrow screens."
    >
      <div class="grid gap-4 sm:grid-cols-2">
        <div>
          <label class="field-label">Hours per month</label>
          <input v-model.number="hours.perMonth" type="number" class="field-input" />
        </div>
        <div>
          <label class="field-label">Web VM $ / hour</label>
          <input v-model.number="price.web" type="number" step="0.0001" class="field-input" />
        </div>
        <div>
          <label class="field-label">Worker VM $ / hour</label>
          <input v-model.number="price.worker" type="number" step="0.0001" class="field-input" />
        </div>
        <div>
          <label class="field-label">Redis VM $ / hour</label>
          <input v-model.number="price.redis" type="number" step="0.0001" class="field-input" />
        </div>
        <div>
          <label class="field-label">DB VM $ / hour</label>
          <input v-model.number="price.db" type="number" step="0.0001" class="field-input" />
        </div>
        <div>
          <label class="field-label">Partial active ratio</label>
          <input v-model.number="assumptions.partialActive" type="number" step="0.01" min="0" max="1" class="field-input" />
        </div>
        <div>
          <label class="field-label">Full-zero active ratio</label>
          <input v-model.number="assumptions.fullActive" type="number" step="0.01" min="0" max="1" class="field-input" />
        </div>
      </div>
    </SectionCard>

    <SectionCard
      kicker="Scenario comparison"
      title="Monthly estimate"
      body="These totals use the same formulas as the original cost page, but the presentation stays vertical and touch-friendly."
    >
      <div class="overflow-hidden rounded-3xl border border-slate-200">
        <table class="min-w-full divide-y divide-slate-200 bg-white text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-[0.16em] text-slate-500">
            <tr>
              <th class="px-4 py-3">Scenario</th>
              <th class="px-4 py-3">Web</th>
              <th class="px-4 py-3">Worker</th>
              <th class="px-4 py-3">Redis</th>
              <th class="px-4 py-3">DB</th>
              <th class="px-4 py-3">Total</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 text-slate-700">
            <tr>
              <td class="px-4 py-3 font-medium">Always on</td>
              <td class="px-4 py-3">{{ money(alwaysOn.web) }}</td>
              <td class="px-4 py-3">{{ money(alwaysOn.worker) }}</td>
              <td class="px-4 py-3">{{ money(alwaysOn.redis) }}</td>
              <td class="px-4 py-3">{{ money(alwaysOn.db) }}</td>
              <td class="px-4 py-3 font-semibold">{{ money(alwaysOn.total) }}</td>
            </tr>
            <tr>
              <td class="px-4 py-3 font-medium">Scale web and worker only</td>
              <td class="px-4 py-3">{{ money(partialZero.web) }}</td>
              <td class="px-4 py-3">{{ money(partialZero.worker) }}</td>
              <td class="px-4 py-3">{{ money(partialZero.redis) }}</td>
              <td class="px-4 py-3">{{ money(partialZero.db) }}</td>
              <td class="px-4 py-3 font-semibold">{{ money(partialZero.total) }}</td>
            </tr>
            <tr>
              <td class="px-4 py-3 font-medium">Full zero orchestration</td>
              <td class="px-4 py-3">{{ money(fullZero.web) }}</td>
              <td class="px-4 py-3">{{ money(fullZero.worker) }}</td>
              <td class="px-4 py-3">{{ money(fullZero.redis) }}</td>
              <td class="px-4 py-3">{{ money(fullZero.db) }}</td>
              <td class="px-4 py-3 font-semibold">{{ money(fullZero.total) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </SectionCard>
  </div>
</template>
