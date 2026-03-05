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
      router.push("/");
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
      router.push("/");
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
          <button @click="logout">Logout</button>
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
      router.push("/login");
    };

    const openSession = (id) => router.push(`/sessions/${id}`);
    const goAdmin = () => router.push("/admin");

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

    const back = () => router.push("/");

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
    const back = () => router.push("/");

    onMounted(loadUsers);
    return { users, updateTier, back };
  },
};

const routes = [
  { path: "/login", component: Login },
  { path: "/register", component: Register },
  { path: "/", component: Dashboard },
  { path: "/sessions/:id", component: SessionDetail },
  { path: "/admin", component: Admin },
];

const router = createRouter({ history: createWebHashHistory(), routes });

router.beforeEach(async (to) => {
  if (!store.user) await loadUser();
  if (!store.token && to.path !== "/login" && to.path !== "/register") return "/login";
  if (to.path === "/admin" && store.user?.role !== "admin") return "/";
  return true;
});

const RootApp = {
  template: `<router-view />`,
};

const app = createApp(RootApp);
app.use(router);
app.mount("#app");
