import { computed } from "../lib/vue-globals.js";
import { prettyStatus } from "../lib/formatters.js";

export const StatusPill = {
  props: {
    status: {
      type: String,
      default: "unknown",
    },
  },
  setup(props) {
    const label = computed(() => prettyStatus(props.status));
    return { label };
  },
  template: `
    <span class="status-pill" :data-status="status">
      <span class="status-pill__dot"></span>
      <span>{{ label }}</span>
    </span>
  `,
};

export const MetricRail = {
  props: {
    metrics: {
      type: Array,
      default: () => [],
    },
  },
  template: `
    <div class="metric-rail">
      <article v-for="metric in metrics" :key="metric.label" class="metric-card">
        <span class="metric-card__label">{{ metric.label }}</span>
        <strong class="metric-card__value">{{ metric.value }}</strong>
        <span v-if="metric.detail" class="metric-card__detail">{{ metric.detail }}</span>
      </article>
    </div>
  `,
};

export const EmptyState = {
  props: {
    title: {
      type: String,
      required: true,
    },
    body: {
      type: String,
      required: true,
    },
  },
  template: `
    <div class="empty-state">
      <strong>{{ title }}</strong>
      <p>{{ body }}</p>
    </div>
  `,
};
