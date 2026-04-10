<script setup>
import MetricStrip from "./MetricStrip.vue";

defineProps({
  kicker: {
    type: String,
    default: "",
  },
  title: {
    type: String,
    required: true,
  },
  body: {
    type: String,
    default: "",
  },
  metrics: {
    type: Array,
    default: () => [],
  },
});
</script>

<template>
  <section class="hero-panel">
    <slot name="actions" />
    <p v-if="kicker" class="section-kicker">{{ kicker }}</p>
    <h1 class="mt-3 max-w-4xl font-display text-4xl font-bold leading-tight sm:text-5xl">{{ title }}</h1>
    <p v-if="body" class="mt-4 max-w-3xl text-base leading-7 text-slate-200">{{ body }}</p>
    <MetricStrip v-if="metrics.length" :items="metrics" class="mt-6" />
  </section>
</template>
