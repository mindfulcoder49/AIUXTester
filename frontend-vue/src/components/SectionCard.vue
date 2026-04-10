<script setup>
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
});
</script>

<template>
  <section class="surface-card p-5 sm:p-6">
    <p v-if="kicker" class="section-kicker">{{ kicker }}</p>
    <div class="mt-2 flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <h2 class="font-display text-2xl font-bold text-slate-900">{{ title }}</h2>
        <p v-if="body" class="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{{ body }}</p>
      </div>
      <slot name="actions" />
    </div>
    <div class="mt-5">
      <slot />
    </div>
  </section>
</template>
