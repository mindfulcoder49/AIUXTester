<script setup>
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
});
</script>

<template>
  <div class="metric-strip">
    <article v-for="item in items" :key="item.label" class="metric-tile">
      <p class="section-kicker">{{ item.label }}</p>
      <p class="mt-2 font-display text-3xl font-bold text-slate-900">{{ item.value }}</p>
      <p v-if="item.detail" class="mt-1 text-sm text-slate-500">{{ item.detail }}</p>
    </article>
  </div>
</template>
