function allowedConfigKeysForTier(tier) {
  if (tier === "free") {
    return ["mode", "max_steps", "stop_on_first_error"];
  }
  if (tier === "basic") {
    return [
      "mode",
      "max_steps",
      "stop_on_first_error",
      "max_history_actions",
      "loop_detection_enabled",
      "loop_detection_window",
    ];
  }
  return [
    "mode",
    "max_steps",
    "stop_on_first_error",
    "max_history_actions",
    "loop_detection_enabled",
    "loop_detection_window",
    "postmortem_depth",
    "custom_system_prompt_preamble",
  ];
}

function filterConfigForTier(config, tier) {
  const allowed = allowedConfigKeysForTier(tier);
  const out = {};
  allowed.forEach((k) => {
    if (k in config) out[k] = config[k];
  });
  return out;
}

const { createApp, reactive, computed, onMounted, onBeforeUnmount, ref } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

const store = reactive({
  token: localStorage.getItem("access_token") || "",
  user: null,
  models: {},
});

async function apiRequest(path, options = {}) {
  const headers = options.headers || {};
  if (store.token) headers["Authorization"] = `Bearer ${store.token}`;
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

async function loadUser() {
  if (!store.token) return;
  try {
    store.user = await apiRequest("/me");
    store.models = await apiRequest("/models");
  } catch (e) {
    store.token = "";
    localStorage.removeItem("access_token");
  }
}

const Home = {
  template: `
    <div class="home">
      <section class="panel glass hero">
        <div class="hero-shape hero-shape-a"></div>
        <div class="hero-shape hero-shape-b"></div>
        <p class="eyebrow">AIUXTester</p>
        <h1>Autonomous Website Testing For Real User Flows</h1>
        <p class="lead">
          Drive websites with agentic browser automation, stream every action, and generate structured postmortems across OpenAI, Gemini, and Claude.
        </p>
        <div class="hero-links">
          <a href="#/docs">Documentation</a>
          <a href="#/costs">Cost Model</a>
        </div>
        <button class="cta" @click="cta">{{ store.token ? "Open Dashboard" : "Get Started" }}</button>
      </section>

      <section class="panel">
        <h2>Quick Start</h2>
        <ol class="flat-list ordered">
          <li>Enter the website you want to explore.</li>
          <li>{{ store.token ? "You are logged in. Continue to dashboard." : "Log in to run agent sessions." }}</li>
          <li>Describe the task you want: <code>explore this website and try to accomplish it's primary use case</code>.</li>
        </ol>
      </section>
    </div>
  `,
  setup() {
    const cta = () => router.push(store.token ? "/app" : "/login");
    return { store, cta };
  },
};

const Docs = {
  template: `
    <div class="docs">
      <header>
        <button @click="back">Back</button>
        <h2>Documentation</h2>
      </header>
      <section class="panel">
        <h3>What The App Does</h3>
        <ul class="flat-list">
          <li>Runs browser sessions with Playwright in desktop or mobile mode.</li>
          <li>Uses LLM-selected actions and streams each step live.</li>
          <li>Saves action history, screenshots, logs, memory, and sanitized HTML.</li>
          <li>Generates postmortem analysis from run state and page HTML.</li>
        </ul>
      </section>
      <section class="panel">
        <h3>Quick Start Guide</h3>
        <ol class="flat-list ordered">
          <li>Enter the website you want to explore.</li>
          <li>Log in.</li>
          <li>In New Session, describe the task you want.</li>
          <li>Suggested task: <code>explore this website and try to accomplish it's primary use case</code>.</li>
          <li>Review stream, logs, and postmortem after completion.</li>
        </ol>
      </section>
    </div>
  `,
  setup() {
    const back = () => router.push("/");
    return { back };
  },
};

function formatPostmortemValue(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch (_) {
    return String(value);
  }
}

const Login = {
  template: `
    <div class="auth">
      <h1>AIUXTester</h1>
      <h2>Login</h2>
      <form @submit.prevent="submit">
        <input v-model="email" type="email" placeholder="Email" required />
        <input v-model="password" type="password" placeholder="Password" required />
        <button>Login</button>
      </form>
      <p><a href="#/register">Create an account</a></p>
    </div>
  `,
  setup() {
    const email = ref("");
    const password = ref("");
    const submit = async () => {
      const data = await apiRequest("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: email.value, password: password.value }),
      });
      store.token = data.access_token;
      localStorage.setItem("access_token", store.token);
      await loadUser();
      router.push("/app");
    };
    return { email, password, submit };
  },
};

const Register = {
  template: `
    <div class="auth">
      <h1>AIUXTester</h1>
      <h2>Register</h2>
      <form @submit.prevent="submit">
        <input v-model="email" type="email" placeholder="Email" required />
        <input v-model="password" type="password" placeholder="Password" required />
        <button>Create account</button>
      </form>
      <p><a href="#/login">Back to login</a></p>
    </div>
  `,
  setup() {
    const email = ref("");
    const password = ref("");
    const submit = async () => {
      const data = await apiRequest("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email: email.value, password: password.value }),
      });
      store.token = data.access_token;
      localStorage.setItem("access_token", store.token);
      await loadUser();
      router.push("/app");
    };
    return { email, password, submit };
  },
};

const Dashboard = {
  template: `
    <div class="dashboard">
      <header>
        <div>
          <h1>AIUXTester</h1>
          <p>Signed in as {{ store.user?.email }} ({{ store.user?.tier }})</p>
        </div>
        <div class="actions">
          <button @click="goHome">Home</button>
          <button @click="goDocs">Docs</button>
          <button @click="logout">Logout</button>
          <button @click="goCosts">Cost</button>
          <button v-if="store.user?.role === 'admin'" @click="goAdmin">Admin</button>
        </div>
      </header>

      <section class="panel">
        <h2>New Session</h2>
        <form @submit.prevent="createSession">
          <input v-model="goal" placeholder="Goal (e.g., create account)" required />
          <input v-model="start_url" placeholder="Start URL" required />

          <div class="row">
            <label>Mode</label>
            <select v-model="config.mode">
              <option value="desktop">Desktop</option>
              <option value="mobile">Mobile</option>
            </select>
          </div>

          <div class="row">
            <label>Provider</label>
            <select v-model="provider">
              <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>

          <div class="row">
            <label>Model</label>
            <select v-model="model">
              <option v-for="m in modelsForProvider" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>

          <div class="config">
            <h3>Config</h3>
            <div class="row">
              <label>Max Steps</label>
              <input type="number" v-model.number="config.max_steps" />
            </div>
            <div class="row">
              <label>Stop on First Error</label>
              <input type="checkbox" v-model="config.stop_on_first_error" />
            </div>

            <div v-if="tier !== 'free'" class="row">
              <label>History Actions</label>
              <input type="number" v-model.number="config.max_history_actions" />
            </div>
            <div v-if="tier !== 'free'" class="row">
              <label>Loop Detection</label>
              <input type="checkbox" v-model="config.loop_detection_enabled" />
            </div>
            <div v-if="tier !== 'free'" class="row">
              <label>Loop Window</label>
              <input type="number" v-model.number="config.loop_detection_window" />
            </div>

            <div v-if="tier === 'pro'" class="row">
              <label>Postmortem Depth</label>
              <select v-model="config.postmortem_depth">
                <option value="standard">Standard</option>
                <option value="deep">Deep</option>
              </select>
            </div>
            <div v-if="tier === 'pro'" class="row">
              <label>Custom Prompt Preamble</label>
              <textarea v-model="config.custom_system_prompt_preamble"></textarea>
            </div>
          </div>

          <button>Create & Start</button>
        </form>
      </section>

      <section class="panel">
        <h2>Your Sessions</h2>
        <div class="sessions">
          <div v-for="s in sessions" :key="s.id" class="session-card" @click="openSession(s.id)">
            <div>
              <strong>{{ s.goal }}</strong>
              <div>{{ s.start_url }}</div>
              <div>{{ s.provider }} / {{ s.model }}</div>
            </div>
            <div class="session-actions">
              <span class="status" :data-status="s.status">{{ s.status }}</span>
              <button type="button" class="rerun-btn" @click.stop="rerunFromSession(s)">Rerun</button>
            </div>
          </div>
        </div>
      </section>
    </div>
  `,
  setup() {
    const sessions = ref([]);
    const goal = ref("");
    const start_url = ref("");
    const provider = ref("openai");
    const model = ref("");
    const config = reactive({
      mode: "desktop",
      max_steps: 50,
      stop_on_first_error: false,
      max_history_actions: 5,
      loop_detection_enabled: true,
      loop_detection_window: 8,
      postmortem_depth: "standard",
      custom_system_prompt_preamble: "",
    });

    const tier = computed(() => store.user?.tier || "free");
    const providers = computed(() => Object.keys(store.models || {}));
    const modelsForProvider = computed(() => store.models?.[provider.value] || []);

    const loadSessions = async () => {
      sessions.value = await apiRequest("/sessions");
    };

    const createSession = async () => {
      const filteredConfig = filterConfigForTier(config, tier.value);
      const payload = {
        goal: goal.value,
        start_url: start_url.value,
        provider: provider.value,
        model: model.value || (modelsForProvider.value[0] || ""),
        config: filteredConfig,
      };
      const res = await apiRequest("/sessions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await loadSessions();
      router.push(`/sessions/${res.session_id}`);
    };

    const rerunFromSession = (s) => {
      goal.value = s.goal || "";
      start_url.value = s.start_url || "";
      provider.value = s.provider || provider.value;
      model.value = s.model || model.value;

      let savedConfig = {};
      if (s.config_json) {
        try {
          savedConfig = JSON.parse(s.config_json);
        } catch (_) {
          savedConfig = {};
        }
      }
      Object.assign(config, {
        ...config,
        ...savedConfig,
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    };

    const logout = () => {
      store.token = "";
      localStorage.removeItem("access_token");
      store.user = null;
      router.push("/");
    };

    const openSession = (id) => router.push(`/sessions/${id}`);
    const goAdmin = () => router.push("/admin");
    const goCosts = () => router.push("/costs");
    const goHome = () => router.push("/");
    const goDocs = () => router.push("/docs");

    onMounted(async () => {
      await loadSessions();
      if (!model.value && modelsForProvider.value.length) model.value = modelsForProvider.value[0];
    });

    return {
      store,
      sessions,
      goal,
      start_url,
      provider,
      model,
      config,
      tier,
      providers,
      modelsForProvider,
      createSession,
      rerunFromSession,
      logout,
      openSession,
      goAdmin,
      goCosts,
      goHome,
      goDocs,
    };
  },
};

const SessionDetail = {
  template: `
    <div class="session-detail">
      <header>
        <button @click="back">Back</button>
        <div>
          <h2>{{ session?.goal }}</h2>
          <p>{{ session?.start_url }} • {{ session?.provider }}/{{ session?.model }}</p>
          <p>Status: <strong>{{ session?.status }}</strong><span v-if="session?.end_reason"> • {{ session?.end_reason }}</span></p>
        </div>
        <div>
          <button @click="stop">Stop</button>
        </div>
      </header>

      <section class="panel">
        <h3>Live Stream</h3>
        <div class="stream">
          <div v-for="s in steps" :key="s.id || ('step-' + s.step + '-' + s.action)" class="step">
            <div class="step-meta">
              <span>#{{ s.step }}</span>
              <strong>{{ s.action }}</strong>
              <small>{{ s.url }}</small>
            </div>
            <div class="step-explain" v-if="s.intent || s.reasoning">
              <div v-if="s.intent"><strong>Intent:</strong> {{ s.intent }}</div>
              <div v-if="s.reasoning"><strong>Why:</strong> {{ s.reasoning }}</div>
            </div>
            <img :src="s.image" v-if="s.image" />
          </div>
        </div>
      </section>

      <section class="panel" v-if="postmortem">
        <h3>Postmortem</h3>
        <div class="postmortem-grid">
          <div class="postmortem-item">
            <h4>Run Analysis</h4>
            <div class="postmortem-text">{{ formatPostmortemValue(postmortem.run_analysis) }}</div>
          </div>
          <div class="postmortem-item">
            <h4>HTML Analysis</h4>
            <div class="postmortem-text">{{ formatPostmortemValue(postmortem.html_analysis) }}</div>
          </div>
          <div class="postmortem-item">
            <h4>Recommendations</h4>
            <div class="postmortem-text">{{ formatPostmortemValue(postmortem.recommendations) }}</div>
          </div>
        </div>
      </section>

      <section class="panel">
        <h3>Run Logs</h3>
        <div class="logs">
          <div v-for="(l, idx) in logs" :key="idx" class="log-row" :data-level="l.level">
            <span class="log-level">{{ l.level || "info" }}</span>
            <span class="log-step">step {{ l.step ?? "-" }}</span>
            <span class="log-message">{{ l.message }}</span>
            <small v-if="l.details">{{ l.details }}</small>
          </div>
        </div>
      </section>
    </div>
  `,
  setup() {
    const session = ref(null);
    const steps = ref([]);
    const postmortem = ref(null);
    const logs = ref([]);
    let eventSource = null;
    let refreshTimer = null;

    const loadSession = async (id) => {
      const data = await apiRequest(`/sessions/${id}`);
      session.value = data.session;
      const actionByStep = {};
      (data.actions || []).forEach((a) => {
        actionByStep[a.step_number] = a;
      });
      steps.value = data.screenshots.map((s) => ({
        id: s.id,
        step: s.step_number,
        action: s.action_taken,
        url: s.url,
        intent: actionByStep[s.step_number]?.intent || "",
        reasoning: actionByStep[s.step_number]?.reasoning || "",
        image: `/screenshots/${s.id}?token=${store.token}`,
      }));
      logs.value = (data.logs || []).map((l) => ({
        level: l.level,
        message: l.message,
        details: l.details,
        step: l.step_number,
      }));
      try {
        const report = await apiRequest(`/sessions/${id}/postmortem`);
        if (report) {
          postmortem.value = {
            run_analysis: report.run_analysis || "",
            html_analysis: report.html_analysis || "",
            recommendations: report.recommendations || "",
          };
        }
      } catch (_) {
        postmortem.value = null;
      }
    };

    const connectStream = (id) => {
      if (eventSource) eventSource.close();
      eventSource = new EventSource(`/sessions/${id}/stream?token=${store.token}`);
      eventSource.onmessage = (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === "step") {
          steps.value.push({
            id: msg.data.screenshot_id,
            step: msg.data.step,
            action: msg.data.action,
            url: msg.data.url,
            intent: msg.data.intent || "",
            reasoning: msg.data.reasoning || "",
            image: `/screenshots/${msg.data.screenshot_id}?token=${store.token}`,
          });
        }
        if (msg.type === "postmortem") {
          postmortem.value = msg.data;
        }
        if (msg.type === "status") {
          if (session.value) {
            session.value.status = msg.data.status;
            session.value.end_reason = msg.data.end_reason;
          }
          logs.value.push({
            level: "info",
            message: `Session status changed to ${msg.data.status}`,
            details: msg.data.end_reason || "",
            step: null,
          });
        }
        if (msg.type === "log") {
          logs.value.push({
            level: msg.data.level || "info",
            message: msg.data.message,
            details: msg.data.details || "",
            step: msg.data.step,
          });
        }
        if (msg.type === "error") {
          logs.value.push({
            level: "error",
            message: "Runtime error",
            details: msg.data.message || "",
            step: null,
          });
        }
      };
    };

    const startRefresh = (id) => {
      if (refreshTimer) clearInterval(refreshTimer);
      refreshTimer = setInterval(async () => {
        if (!session.value) return;
        if (["completed", "failed", "stopped", "loop_detected"].includes(session.value.status)) return;
        try {
          await loadSession(id);
        } catch (_) {}
      }, 3000);
    };

    const stop = async () => {
      await apiRequest(`/sessions/${session.value.id}/stop`, { method: "POST" });
    };

    const back = () => router.push("/app");

    onMounted(async () => {
      const id = router.currentRoute.value.params.id;
      await loadSession(id);
      connectStream(id);
      startRefresh(id);
    });

    onBeforeUnmount(() => {
      if (eventSource) eventSource.close();
      if (refreshTimer) clearInterval(refreshTimer);
    });

    return { session, steps, postmortem, logs, stop, back, formatPostmortemValue };
  },
};

const Admin = {
  template: `
    <div class="admin">
      <header>
        <button @click="back">Back</button>
        <h2>Admin</h2>
      </header>

      <section class="panel">
        <h3>Users</h3>
        <div class="users">
          <div v-for="u in users" :key="u.id" class="user-row">
            <div>{{ u.email }}</div>
            <select v-model="u.tier" @change="updateTier(u)">
              <option value="free">free</option>
              <option value="basic">basic</option>
              <option value="pro">pro</option>
            </select>
          </div>
        </div>
      </section>
    </div>
  `,
  setup() {
    const users = ref([]);
    const loadUsers = async () => {
      users.value = await apiRequest("/admin/users");
    };
    const updateTier = async (u) => {
      await apiRequest(`/admin/users/${u.id}/tier`, {
        method: "PATCH",
        body: JSON.stringify({ tier: u.tier }),
      });
    };
    const back = () => router.push("/app");

    onMounted(loadUsers);
    return { users, updateTier, back };
  },
};

const Costs = {
  template: `
    <div class="costs">
      <header>
        <button @click="back">Back</button>
        <h2>Cost Model</h2>
      </header>

      <section class="panel">
        <h3>Current Runtime Topology</h3>
        <ul class="flat-list">
          <li><code>aiuxtester</code>: web app machine + worker machine.</li>
          <li><code>aiuxtester-db</code>: 1 MariaDB machine with volume.</li>
          <li><code>aiuxtester-redis</code>: 1 Redis machine with volume.</li>
        </ul>
        <p class="muted">Current practical effect: core state services (DB/Redis) run continuously, and app+worker run continuously unless you manually scale down.</p>
      </section>

      <section class="panel">
        <h3>Estimator Inputs</h3>
        <div class="row"><label>Hours / month</label><input type="number" v-model.number="hoursPerMonth" /></div>
        <div class="row"><label>Web VM $/hour</label><input type="number" step="0.0001" v-model.number="price.web" /></div>
        <div class="row"><label>Worker VM $/hour</label><input type="number" step="0.0001" v-model.number="price.worker" /></div>
        <div class="row"><label>Redis VM $/hour</label><input type="number" step="0.0001" v-model.number="price.redis" /></div>
        <div class="row"><label>DB VM $/hour</label><input type="number" step="0.0001" v-model.number="price.db" /></div>
      </section>

      <section class="panel">
        <h3>Scenario Comparison</h3>
        <table class="cost-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Web</th>
              <th>Worker</th>
              <th>Redis</th>
              <th>DB</th>
              <th>Total / month</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Current (always-on)</td>
              <td>{{ money(alwaysOn.web) }}</td>
              <td>{{ money(alwaysOn.worker) }}</td>
              <td>{{ money(alwaysOn.redis) }}</td>
              <td>{{ money(alwaysOn.db) }}</td>
              <td><strong>{{ money(alwaysOn.total) }}</strong></td>
            </tr>
            <tr>
              <td>Scale web + worker only</td>
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
        <p class="muted">
          Assumptions used: web+worker active 25% in partial mode; full orchestration active 10% for all services.
          Update assumptions below to match your usage.
        </p>
        <div class="row"><label>Partial active ratio</label><input type="number" step="0.01" min="0" max="1" v-model.number="assumptions.partialActive" /></div>
        <div class="row"><label>Full-zero active ratio</label><input type="number" step="0.01" min="0" max="1" v-model.number="assumptions.fullActive" /></div>
      </section>

      <section class="panel">
        <h3>Scaling Notes</h3>
        <ul class="flat-list">
          <li>Worker scaling is straightforward: increase worker count when queue backlog grows.</li>
          <li>Web scaling is straightforward: increase app machine count for concurrent users.</li>
          <li>DB/Redis must stay shared and reachable by all workers to preserve correctness.</li>
          <li>Full scale-to-zero needs orchestration logic to wake DB/Redis/worker in sequence, then gate user actions until ready.</li>
        </ul>
      </section>
    </div>
  `,
  setup() {
    const hoursPerMonth = ref(730);
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

    const alwaysOn = computed(() => {
      const web = price.web * hoursPerMonth.value;
      const worker = price.worker * hoursPerMonth.value;
      const redis = price.redis * hoursPerMonth.value;
      const db = price.db * hoursPerMonth.value;
      return { web, worker, redis, db, total: web + worker + redis + db };
    });

    const partialZero = computed(() => {
      const web = price.web * hoursPerMonth.value * assumptions.partialActive;
      const worker = price.worker * hoursPerMonth.value * assumptions.partialActive;
      const redis = price.redis * hoursPerMonth.value;
      const db = price.db * hoursPerMonth.value;
      return { web, worker, redis, db, total: web + worker + redis + db };
    });

    const fullZero = computed(() => {
      const web = price.web * hoursPerMonth.value * assumptions.fullActive;
      const worker = price.worker * hoursPerMonth.value * assumptions.fullActive;
      const redis = price.redis * hoursPerMonth.value * assumptions.fullActive;
      const db = price.db * hoursPerMonth.value * assumptions.fullActive;
      return { web, worker, redis, db, total: web + worker + redis + db };
    });

    const money = (n) => `$${(Number(n) || 0).toFixed(2)}`;
    const back = () => router.push("/");

    return { hoursPerMonth, price, assumptions, alwaysOn, partialZero, fullZero, money, back };
  },
};

const routes = [
  { path: "/", component: Home },
  { path: "/docs", component: Docs },
  { path: "/costs", component: Costs },
  { path: "/login", component: Login },
  { path: "/register", component: Register },
  { path: "/app", component: Dashboard },
  { path: "/sessions/:id", component: SessionDetail },
  { path: "/admin", component: Admin },
];

const router = createRouter({ history: createWebHashHistory(), routes });

router.beforeEach(async (to) => {
  const publicPaths = new Set(["/", "/docs", "/costs", "/login", "/register"]);
  if (!store.user) await loadUser();
  if (!store.token && !publicPaths.has(to.path)) return "/login";
  if (to.path === "/admin" && store.user?.role !== "admin") return "/";
  return true;
});

const RootApp = {
  template: `<router-view />`,
};

const app = createApp(RootApp);
app.use(router);
app.mount("#app");
