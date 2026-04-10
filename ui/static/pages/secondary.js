import { computed, onMounted, ref } from "../lib/vue-globals.js";
import { apiRequest, store } from "../lib/app-state.js";
import { pluralize } from "../lib/formatters.js";
import { back, go } from "../lib/navigation.js";
import { EmptyState, MetricRail, StatusPill } from "../components/primitives.js";

export const Docs = {
  components: { MetricRail },
  template: `
    <div class="page page--docs">
      <section class="page-hero">
        <div>
          <button class="button button--ghost button--small" @click="goBack">Back</button>
          <p class="section-kicker">Documentation Center</p>
          <h1>How the product works, from agent loop to evidence storage.</h1>
          <p class="page-hero__lead">
            AIUXTester combines exploratory browser execution, streaming observability, and structured postmortem analysis in one runtime.
          </p>
        </div>
        <MetricRail :metrics="docMetrics" />
      </section>

      <section class="card-grid card-grid--two">
        <article class="panel-surface" v-for="section in sections" :key="section.title">
          <div class="panel-heading panel-heading--compact">
            <div>
              <p class="section-kicker">{{ section.kicker }}</p>
              <h2>{{ section.title }}</h2>
            </div>
          </div>
          <p class="callout-copy">{{ section.body }}</p>
          <ul class="bullet-list">
            <li v-for="item in section.items" :key="item">{{ item }}</li>
          </ul>
        </article>
      </section>
    </div>
  `,
  setup() {
    const sections = [
      {
        kicker: "Platform Summary",
        title: "Core product loop",
        body: "One agent executes the session while a second analysis stage interprets what happened and why it matters.",
        items: [
          "Goal-driven browser execution using Playwright.",
          "Streaming screenshots, logs, intent, and reasoning over SSE.",
          "Structured postmortems backed by saved HTML and action history.",
        ],
      },
      {
        kicker: "Evidence Model",
        title: "What gets stored",
        body: "Every run is durable, searchable, and reviewable after the worker finishes.",
        items: [
          "Sessions, screenshots, HTML captures, actions, and memory.",
          "Run logs for debugging failures and provider behavior.",
          "Postmortem reports with recommendations and structural analysis.",
        ],
      },
      {
        kicker: "Operational Flow",
        title: "How it scales",
        body: "The system separates web/API, worker execution, and shared data services so runs can scale independently.",
        items: [
          "Redis/RQ decouples request handling from session execution.",
          "MariaDB or SQLite store shared run artifacts.",
          "Workers can scale with queue depth while the UI reconstructs from persisted data.",
        ],
      },
      {
        kicker: "Practical Guidance",
        title: "What to check first",
        body: "When a run looks wrong, check the evidence before guessing.",
        items: [
          "Inspect run logs before checking provider rate limits.",
          "Use screenshots and HTML captures to validate the failure mode.",
          "Treat postmortems as evidence-backed synthesis, not magic output.",
        ],
      },
    ];

    const docMetrics = computed(() => [
      { label: "Execution", value: "Playwright", detail: "Stealth browser control" },
      { label: "Streaming", value: "SSE", detail: "Live trace visibility" },
      { label: "Analysis", value: "Structured", detail: "Run and HTML postmortems" },
    ]);

    return { sections, docMetrics, goBack: () => back("/") };
  },
};

export const Costs = {
  components: { MetricRail },
  template: `
    <div class="page page--costs">
      <section class="page-hero">
        <div>
          <button class="button button--ghost button--small" @click="goBack">Back</button>
          <p class="section-kicker">Cost Model</p>
          <h1>Model the always-on footprint versus scale-to-zero orchestration.</h1>
          <p class="page-hero__lead">
            This estimator compares the current topology against partial and full scale-down scenarios so you can reason about infra tradeoffs.
          </p>
        </div>
        <MetricRail :metrics="costMetrics" />
      </section>

      <section class="dashboard-layout">
        <div class="panel-surface panel-surface--raised">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">Estimator Inputs</p>
              <h2>Adjust the assumptions</h2>
            </div>
          </div>
          <div class="field-grid field-grid--dual">
            <div class="field-stack"><label class="field-label">Hours / month</label><input type="number" v-model.number="hoursPerMonth" /></div>
            <div class="field-stack"><label class="field-label">Web VM $ / hour</label><input type="number" step="0.0001" v-model.number="price.web" /></div>
            <div class="field-stack"><label class="field-label">Worker VM $ / hour</label><input type="number" step="0.0001" v-model.number="price.worker" /></div>
            <div class="field-stack"><label class="field-label">Redis VM $ / hour</label><input type="number" step="0.0001" v-model.number="price.redis" /></div>
            <div class="field-stack"><label class="field-label">DB VM $ / hour</label><input type="number" step="0.0001" v-model.number="price.db" /></div>
            <div class="field-stack"><label class="field-label">Partial active ratio</label><input type="number" step="0.01" min="0" max="1" v-model.number="assumptions.partialActive" /></div>
            <div class="field-stack"><label class="field-label">Full active ratio</label><input type="number" step="0.01" min="0" max="1" v-model.number="assumptions.fullActive" /></div>
          </div>
        </div>

        <div class="stacked-panels">
          <section class="panel-surface">
            <div class="panel-heading">
              <div>
                <p class="section-kicker">Scenario Comparison</p>
                <h2>Monthly estimate</h2>
              </div>
            </div>
            <div class="table-card">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Scenario</th>
                    <th>Web</th>
                    <th>Worker</th>
                    <th>Redis</th>
                    <th>DB</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Current always-on</td>
                    <td>{{ money(alwaysOn.web) }}</td>
                    <td>{{ money(alwaysOn.worker) }}</td>
                    <td>{{ money(alwaysOn.redis) }}</td>
                    <td>{{ money(alwaysOn.db) }}</td>
                    <td><strong>{{ money(alwaysOn.total) }}</strong></td>
                  </tr>
                  <tr>
                    <td>Scale web and worker only</td>
                    <td>{{ money(partialZero.web) }}</td>
                    <td>{{ money(partialZero.worker) }}</td>
                    <td>{{ money(partialZero.redis) }}</td>
                    <td>{{ money(partialZero.db) }}</td>
                    <td><strong>{{ money(partialZero.total) }}</strong></td>
                  </tr>
                  <tr>
                    <td>Full zero orchestration</td>
                    <td>{{ money(fullZero.web) }}</td>
                    <td>{{ money(fullZero.worker) }}</td>
                    <td>{{ money(fullZero.redis) }}</td>
                    <td>{{ money(fullZero.db) }}</td>
                    <td><strong>{{ money(fullZero.total) }}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="panel-surface panel-surface--muted">
            <div class="panel-heading panel-heading--compact">
              <div>
                <p class="section-kicker">Scaling Notes</p>
                <h2>Operational guidance</h2>
              </div>
            </div>
            <ul class="bullet-list">
              <li>Worker scaling tracks queue depth best and is the least risky lever.</li>
              <li>Redis and the database must remain shared if you want correctness across app and worker machines.</li>
              <li>True scale-to-zero needs dependency wake-up sequencing and user-facing readiness states.</li>
            </ul>
          </section>
        </div>
      </section>
    </div>
  `,
  setup() {
    const hoursPerMonth = ref(730);
    const price = ref({
      web: 0.0080,
      worker: 0.0080,
      redis: 0.0040,
      db: 0.0060,
    });
    const assumptions = ref({
      partialActive: 0.25,
      fullActive: 0.10,
    });

    const alwaysOn = computed(() => {
      const web = price.value.web * hoursPerMonth.value;
      const worker = price.value.worker * hoursPerMonth.value;
      const redis = price.value.redis * hoursPerMonth.value;
      const db = price.value.db * hoursPerMonth.value;
      return { web, worker, redis, db, total: web + worker + redis + db };
    });

    const partialZero = computed(() => {
      const web = price.value.web * hoursPerMonth.value * assumptions.value.partialActive;
      const worker = price.value.worker * hoursPerMonth.value * assumptions.value.partialActive;
      const redis = price.value.redis * hoursPerMonth.value;
      const db = price.value.db * hoursPerMonth.value;
      return { web, worker, redis, db, total: web + worker + redis + db };
    });

    const fullZero = computed(() => {
      const web = price.value.web * hoursPerMonth.value * assumptions.value.fullActive;
      const worker = price.value.worker * hoursPerMonth.value * assumptions.value.fullActive;
      const redis = price.value.redis * hoursPerMonth.value * assumptions.value.fullActive;
      const db = price.value.db * hoursPerMonth.value * assumptions.value.fullActive;
      return { web, worker, redis, db, total: web + worker + redis + db };
    });

    const costMetrics = computed(() => [
      { label: "Hours", value: String(hoursPerMonth.value), detail: "Default month" },
      { label: "Always-on", value: money(alwaysOn.value.total), detail: "Current baseline" },
      { label: "Full zero", value: money(fullZero.value.total), detail: "All services scaled" },
    ]);

    const money = (value) => `$${(Number(value) || 0).toFixed(2)}`;

    return {
      hoursPerMonth,
      price: price.value,
      assumptions: assumptions.value,
      alwaysOn,
      partialZero,
      fullZero,
      costMetrics,
      money,
      goBack: () => back("/"),
    };
  },
};

export const Admin = {
  components: { StatusPill, EmptyState, MetricRail },
  template: `
    <div class="page page--admin">
      <section class="page-hero">
        <div>
          <button class="button button--ghost button--small" @click="goBack">Back</button>
          <p class="section-kicker">Admin Surface</p>
          <h1>Operational visibility for users, sessions, memory, logs, and queue health.</h1>
          <p class="page-hero__lead">
            Review live system state without dropping into the database or worker console.
          </p>
        </div>
        <div class="hero-actions">
          <button class="button button--primary" @click="goCompetitions">Competitions</button>
        </div>
        <MetricRail :metrics="adminMetrics" />
      </section>

      <section class="panel-surface panel-surface--raised">
        <div class="tab-bar">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="tab-button"
            :class="{ 'is-active': activeTab === tab.key }"
            @click="switchTab(tab.key)"
          >
            {{ tab.label }}
          </button>
        </div>

        <section v-if="activeTab === 'users'" class="admin-section">
          <div class="panel-heading"><div><p class="section-kicker">Users</p><h2>{{ users.length }} accounts</h2></div></div>
          <div class="admin-stack">
            <article v-for="user in users" :key="user.id" class="admin-row">
              <div>
                <strong>{{ user.email }}</strong>
                <p>{{ user.role }} | joined {{ (user.created_at || '').slice(0, 10) }}</p>
              </div>
              <select v-model="user.tier" @change="updateTier(user)">
                <option value="free">free</option>
                <option value="basic">basic</option>
                <option value="pro">pro</option>
              </select>
            </article>
          </div>
        </section>

        <section v-if="activeTab === 'sessions'" class="admin-section">
          <div class="panel-heading">
            <div><p class="section-kicker">Sessions</p><h2>Inspect run inventory</h2></div>
            <button class="button button--ghost" @click="loadSessions">Refresh</button>
          </div>
          <div class="filter-bar">
            <input v-model="sessionSearch" placeholder="Filter by email, URL, or goal" />
            <select v-model="sessionStatus" @change="loadSessions">
              <option value="">all statuses</option>
              <option value="running">running</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="stopped">stopped</option>
              <option value="loop_detected">loop_detected</option>
            </select>
            <select v-model="sessionLimit" @change="loadSessions">
              <option :value="25">25</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
              <option :value="250">250</option>
            </select>
          </div>
          <div class="table-card">
            <table class="data-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>URL</th>
                  <th>Goal</th>
                  <th>Status</th>
                  <th>Actions</th>
                  <th>Provider / Model</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="session in filteredSessions" :key="session.id" @click="openSession(session.id)" class="clickable-row">
                  <td>{{ session.email }}</td>
                  <td>{{ session.start_url }}</td>
                  <td>{{ session.goal }}</td>
                  <td><StatusPill :status="session.status" /></td>
                  <td>{{ session.action_count }}</td>
                  <td>{{ session.provider }} / {{ session.model }}</td>
                  <td>{{ (session.created_at || '').slice(0, 16).replace('T', ' ') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <EmptyState v-if="filteredSessions.length === 0" title="No sessions match" body="Change the search or filters to inspect a different slice of session history." />
        </section>

        <section v-if="activeTab === 'memory'" class="admin-section">
          <div class="panel-heading"><div><p class="section-kicker">Agent Memory</p><h2>Load memory for one session</h2></div></div>
          <div class="filter-bar">
            <input v-model="memorySessionId" placeholder="Session ID" @keyup.enter="loadMemory" />
            <button class="button button--ghost" @click="loadMemory">Load</button>
          </div>
          <div class="table-card" v-if="memory !== null && Object.keys(memory).length">
            <table class="data-table">
              <thead><tr><th>Key</th><th>Value</th></tr></thead>
              <tbody>
                <tr v-for="(value, key) in memory" :key="key">
                  <td>{{ key }}</td>
                  <td class="mono-cell">{{ value }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <EmptyState v-if="memory !== null && Object.keys(memory).length === 0" title="No memory saved" body="This session has not persisted any explicit memory keys." />
          <p class="form-feedback form-feedback--error" v-if="memoryError">{{ memoryError }}</p>
        </section>

        <section v-if="activeTab === 'logs'" class="admin-section">
          <div class="panel-heading"><div><p class="section-kicker">Run Logs</p><h2>Inspect a session log stream</h2></div></div>
          <div class="filter-bar">
            <input v-model="logsSessionId" placeholder="Session ID" @keyup.enter="loadLogs" />
            <select v-model="logsLevel">
              <option value="">all levels</option>
              <option value="error">error</option>
              <option value="warning">warning</option>
              <option value="info">info</option>
            </select>
            <button class="button button--ghost" @click="loadLogs">Load</button>
          </div>
          <div class="log-feed" v-if="filteredLogs.length">
            <article v-for="(log, index) in filteredLogs" :key="index" class="log-card" :data-level="log.level">
              <div class="log-card__header"><strong>{{ log.level || 'info' }}</strong><span>step {{ log.step_number ?? '-' }}</span></div>
              <p>{{ log.message }}</p>
              <p class="log-card__details" v-if="log.details">{{ log.details }}</p>
            </article>
          </div>
          <p class="form-feedback form-feedback--error" v-if="logsError">{{ logsError }}</p>
        </section>

        <section v-if="activeTab === 'queue'" class="admin-section">
          <div class="panel-heading">
            <div><p class="section-kicker">Queue Health</p><h2>Redis and worker status</h2></div>
            <button class="button button--ghost" @click="loadQueue">Refresh</button>
          </div>
          <div v-if="queue" class="metric-rail">
            <article class="metric-card"><span class="metric-card__label">Redis</span><strong class="metric-card__value">{{ queue.available ? 'yes' : 'no' }}</strong></article>
            <article class="metric-card" v-if="queue.available"><span class="metric-card__label">Queued</span><strong class="metric-card__value">{{ queue.queued }}</strong></article>
            <article class="metric-card" v-if="queue.available"><span class="metric-card__label">Active</span><strong class="metric-card__value">{{ queue.active }}</strong></article>
            <article class="metric-card" v-if="queue.available"><span class="metric-card__label">Failed</span><strong class="metric-card__value">{{ queue.failed }}</strong></article>
          </div>
          <p class="form-feedback form-feedback--error" v-if="queue?.error">{{ queue.error }}</p>
        </section>
      </section>
    </div>
  `,
  setup() {
    const tabs = [
      { key: "users", label: "Users" },
      { key: "sessions", label: "Sessions" },
      { key: "memory", label: "Memory" },
      { key: "logs", label: "Logs" },
      { key: "queue", label: "Queue" },
    ];
    const activeTab = ref("users");
    const users = ref([]);
    const sessions = ref([]);
    const sessionSearch = ref("");
    const sessionStatus = ref("");
    const sessionLimit = ref(50);
    const memory = ref(null);
    const memorySessionId = ref("");
    const memoryError = ref("");
    const logs = ref([]);
    const logsSessionId = ref("");
    const logsLevel = ref("");
    const logsError = ref("");
    const queue = ref(null);

    const adminMetrics = computed(() => [
      { label: "Role", value: store.user?.role || "admin", detail: store.user?.tier || "pro" },
      { label: "Users", value: String(users.value.length), detail: pluralize(users.value.length, "account") },
      { label: "Sessions", value: String(sessions.value.length), detail: "loaded slice" },
    ]);

    const loadUsers = async () => {
      users.value = await apiRequest("/admin/users");
    };
    const updateTier = async (user) => {
      await apiRequest(`/admin/users/${user.id}/tier`, {
        method: "PATCH",
        body: JSON.stringify({ tier: user.tier }),
      });
    };

    const loadSessions = async () => {
      const params = new URLSearchParams();
      if (sessionStatus.value) params.set("status", sessionStatus.value);
      params.set("limit", String(sessionLimit.value));
      sessions.value = await apiRequest(`/admin/sessions?${params.toString()}`);
    };
    const filteredSessions = computed(() => {
      const query = sessionSearch.value.toLowerCase();
      if (!query) return sessions.value;
      return sessions.value.filter((session) =>
        (session.email || "").toLowerCase().includes(query) ||
        (session.start_url || "").toLowerCase().includes(query) ||
        (session.goal || "").toLowerCase().includes(query)
      );
    });

    const loadMemory = async () => {
      memoryError.value = "";
      memory.value = null;
      if (!memorySessionId.value.trim()) return;
      try {
        memory.value = await apiRequest(`/admin/sessions/${memorySessionId.value.trim()}/memory`);
      } catch (err) {
        memoryError.value = err.message || "Unable to load memory";
      }
    };

    const loadLogs = async () => {
      logsError.value = "";
      logs.value = [];
      if (!logsSessionId.value.trim()) return;
      try {
        logs.value = await apiRequest(`/sessions/${logsSessionId.value.trim()}/logs`);
      } catch (err) {
        logsError.value = err.message || "Unable to load logs";
      }
    };
    const filteredLogs = computed(() => {
      if (!logsLevel.value) return logs.value;
      return logs.value.filter((entry) => (entry.level || "info") === logsLevel.value);
    });

    const loadQueue = async () => {
      queue.value = await apiRequest("/admin/queue");
    };

    const switchTab = (key) => {
      activeTab.value = key;
      if (key === "users" && !users.value.length) loadUsers();
      if (key === "sessions" && !sessions.value.length) loadSessions();
      if (key === "queue") loadQueue();
    };

    onMounted(async () => {
      await loadUsers();
      await loadSessions();
    });

    return {
      tabs,
      activeTab,
      users,
      sessions,
      sessionSearch,
      sessionStatus,
      sessionLimit,
      memory,
      memorySessionId,
      memoryError,
      logs,
      logsSessionId,
      logsLevel,
      logsError,
      queue,
      adminMetrics,
      filteredSessions,
      filteredLogs,
      switchTab,
      updateTier,
      loadSessions,
      loadMemory,
      loadLogs,
      loadQueue,
      openSession: (id) => go(`/sessions/${id}`),
      goBack: () => back("/app"),
      goCompetitions: () => go("/competitions"),
    };
  },
};
