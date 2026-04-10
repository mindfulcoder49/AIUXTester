<script setup>
import PageHero from "../components/PageHero.vue";
import SectionCard from "../components/SectionCard.vue";

const sections = [
  {
    kicker: "Platform summary",
    title: "Core runtime loop",
    body: "AIUXTester combines browser execution, live evidence capture, and structured postmortem analysis in a single loop.",
    items: [
      "Playwright drives the real browser session.",
      "The frontend replays screenshots, reasoning, and logs via SSE and persisted artifacts.",
      "Postmortem output is generated after the run using the stored evidence trail.",
    ],
  },
  {
    kicker: "Evidence model",
    title: "What gets persisted",
    body: "The backend stores enough information to reconstruct and audit each run after it completes.",
    items: [
      "Sessions, screenshots, HTML captures, actions, and memory.",
      "Run logs for prompt inspection and runtime debugging.",
      "Postmortem reports with run analysis, HTML analysis, and recommendations.",
    ],
  },
  {
    kicker: "Operational guidance",
    title: "How to debug a bad run",
    body: "Start with evidence, not assumptions.",
    items: [
      "Check the run logs to understand model or runtime failure modes.",
      "Validate screenshots and HTML captures before trusting the postmortem summary.",
      "Use session replays to distinguish UX confusion from agent failure.",
    ],
  },
];
</script>

<template>
  <div class="page-shell space-y-6">
    <PageHero
      kicker="Documentation center"
      title="The stack behind the testing workflow, replay surface, and postmortem outputs."
      body="This frontend keeps docs concise and readable while still surfacing the operational model behind the product."
    />

    <SectionCard
      v-for="section in sections"
      :key="section.title"
      :kicker="section.kicker"
      :title="section.title"
      :body="section.body"
    >
      <ul class="space-y-3 text-sm leading-6 text-slate-600">
        <li v-for="item in section.items" :key="item" class="rounded-2xl bg-slate-50 px-4 py-3">
          {{ item }}
        </li>
      </ul>
    </SectionCard>
  </div>
</template>
