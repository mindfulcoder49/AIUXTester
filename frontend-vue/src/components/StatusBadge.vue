<script setup>
import { computed } from "vue";
import { prettyStatus } from "../lib/formatters.js";

const props = defineProps({
  status: {
    type: String,
    default: "unknown",
  },
});

const statusClass = computed(() => `status-${props.status || "unknown"}`);
const label = computed(() => prettyStatus(props.status));
</script>

<template>
  <span class="status-badge" :class="statusClass">{{ label }}</span>
</template>
