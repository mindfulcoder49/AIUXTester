<script setup>
defineProps({
  title: {
    type: String,
    required: true,
  },
  body: {
    type: String,
    required: true,
  },
});
</script>

<template>
  <div class="surface-muted p-5">
    <h3 class="font-display text-xl font-semibold text-slate-900">{{ title }}</h3>
    <p class="mt-2 text-sm leading-6 text-slate-600">{{ body }}</p>
  </div>
</template>
