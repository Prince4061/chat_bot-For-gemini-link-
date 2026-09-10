import axios from 'axios';

// ---------------------------------------------------------------------------
// Identity headers
//  - X-Client-Id : anonymous per-browser id so each visitor only sees their own chats
//  - X-Admin-Token: admin key (kept in sessionStorage; cleared on 401)
// ---------------------------------------------------------------------------

const CLIENT_ID_KEY = 'vending_client_id';
const ADMIN_TOKEN_KEY = 'vending_admin_token';

function safeStorage(kind) {
  try {
    return kind === 'session' ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

export function getClientId() {
  const store = safeStorage('local');
  let id = store?.getItem(CLIENT_ID_KEY);
  if (!id) {
    const rand = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID().replace(/-/g, '')
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
    id = `web_${rand}`;
    store?.setItem(CLIENT_ID_KEY, id);
  }
  return id;
}

export function getAdminToken() {
  return safeStorage('session')?.getItem(ADMIN_TOKEN_KEY) || '';
}

export function setAdminToken(token) {
  const store = safeStorage('session');
  if (!token) store?.removeItem(ADMIN_TOKEN_KEY);
  else store?.setItem(ADMIN_TOKEN_KEY, token);
}

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 90000
});

api.interceptors.request.use((config) => {
  config.headers['X-Client-Id'] = getClientId();
  const token = getAdminToken();
  if (token) config.headers['X-Admin-Token'] = token;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err?.response?.status;
    const url = err?.config?.url || '';
    if (status === 401 && url.startsWith('/admin') && !url.startsWith('/admin/login')) {
      setAdminToken('');
      window.dispatchEvent(new CustomEvent('admin-unauthorized'));
    }
    // Surface the server's message so components can show it.
    const serverMsg = err?.response?.data?.error;
    if (serverMsg) err.message = serverMsg;
    return Promise.reject(err);
  }
);

export const chatApi = {
  sendMessage: async (sessionId, message, userTypeHint = 'customer') => {
    const res = await api.post('/chat', { session_id: sessionId, message, user_type_hint: userTypeHint });
    return res.data;
  },
  getSessions: async () => (await api.get('/chat/sessions')).data,
  getHistory: async (sessionId) => (await api.get(`/chat/history/${sessionId}`)).data,
  newSession: async (userType = 'customer') => (await api.post('/chat/sessions/new', { user_type: userType })).data,
  deleteSession: async (sessionId) => (await api.delete(`/chat/sessions/${sessionId}`)).data
};

export const adminApi = {
  // Returns true if the server requires an admin token. When false, the dashboard is open.
  isAuthRequired: async () => {
    try {
      const res = await api.get('/health');
      return Boolean(res.data?.admin_auth_required);
    } catch {
      return false;
    }
  },
  login: async (token) => {
    const res = await api.post('/admin/login', { token });
    if (res.data?.ok && token) setAdminToken(token);
    return res.data;
  },
  logout: () => setAdminToken(''),
  isLoggedIn: () => Boolean(getAdminToken()),

  getAgentStatus: async () => (await api.get('/admin/agent/status')).data,
  testLlm: async () => (await api.post('/admin/agent/test')).data,

  getMetrics: async () => (await api.get('/admin/metrics')).data,

  getProducts: async () => (await api.get('/admin/products')).data,
  createProduct: async (productData) => (await api.post('/admin/products', productData)).data,
  updateProduct: async (id, productData) => (await api.put(`/admin/products/${id}`, productData)).data,
  // Saves BOTH sliders: customer margin % and reseller margin % (each over base price).
  updateMargin: async (id, marginPercent, resellerMarginPercent) => {
    const body = { margin_percent: parseFloat(marginPercent) };
    if (resellerMarginPercent !== undefined && resellerMarginPercent !== null && resellerMarginPercent !== '') {
      body.reseller_margin_percent = parseFloat(resellerMarginPercent);
    }
    return (await api.post(`/admin/products/${id}/margin`, body)).data;
  },
  deleteProduct: async (id) => (await api.delete(`/admin/products/${id}`)).data,

  getInventory: async (status = '', productId = '') => {
    const params = {};
    if (status) params.status = status;
    if (productId) params.product_id = productId;
    return (await api.get('/admin/inventory', { params })).data;
  },
  bulkUploadInventory: async (productId, linksText) =>
    (await api.post('/admin/inventory/bulk-upload', { product_id: parseInt(productId), links_text: linksText })).data,
  deleteInventoryItem: async (id) => (await api.delete(`/admin/inventory/${id}`)).data,
  recheckInventory: async (productId = '') =>
    (await api.post('/admin/inventory/recheck', productId ? { product_id: parseInt(productId) } : {})).data,
  restoreInventoryItem: async (id) => (await api.post(`/admin/inventory/${id}/restore`)).data,

  getResellers: async () => (await api.get('/admin/resellers')).data,
  createReseller: async (resellerData) => (await api.post('/admin/resellers', resellerData)).data,
  updateReseller: async (id, resellerData) => (await api.put(`/admin/resellers/${id}`, resellerData)).data,
  unlockReseller: async (id) => (await api.post(`/admin/resellers/${id}/unlock`)).data,
  // Money wallet: + adds, − deducts (in the reseller's currency)
  adjustWallet: async (id, amount, reason = 'admin_topup', note = '') =>
    (await api.post(`/admin/resellers/${id}/wallet`, { amount: parseFloat(amount), reason, note })).data,
  getResellerTransactions: async (id) => (await api.get(`/admin/resellers/${id}/transactions`)).data,

  getOrders: async (status = '') => (await api.get('/admin/orders', { params: status ? { status } : {} })).data,
  approveOrder: async (orderId, paymentRef = 'ADMIN_APPROVED') =>
    (await api.post(`/admin/orders/${orderId}/approve`, { payment_ref: paymentRef })).data,
  cancelOrder: async (orderId) => (await api.post(`/admin/orders/${orderId}/cancel`)).data,

  getSettings: async () => (await api.get('/admin/settings')).data,
  updateSettings: async (settingsData) => (await api.post('/admin/settings', settingsData)).data,

  // Google Link Checker (logged-in headless browser that reads Google's "already used" page)
  googleCheckerStatus: async () => (await api.get('/admin/google-checker/status')).data,
  googleCheckerConnect: async (sessionJson) => (await api.post('/admin/google-checker/session', { session: sessionJson })).data,
  googleCheckerDisconnect: async () => (await api.delete('/admin/google-checker/session')).data,
  googleCheckerVerify: async () => (await api.post('/admin/google-checker/verify')).data,
  googleCheckerTest: async (url) => (await api.post('/admin/google-checker/test', { url })).data,
  // Fetched through the axios client so the X-Admin-Token header is sent; returns an object URL.
  googleCheckerScreenshot: async () => {
    const res = await api.get('/admin/google-checker/screenshot', { responseType: 'blob', params: { t: Date.now() } });
    return URL.createObjectURL(res.data);
  },

  // m00nshots supplier (auto-buy digital products on demand)
  moonshotsStatus: async () => (await api.get('/admin/moonshots/status')).data,
  moonshotsProducts: async (search = '') => (await api.get('/admin/moonshots/products', { params: search ? { search } : {} })).data,
  moonshotsProduct: async (supplierId, fresh = false) => (await api.get(`/admin/moonshots/products/${supplierId}`, { params: fresh ? { fresh: 1 } : {} })).data,
  moonshotsMapped: async (fresh = false) => (await api.get('/admin/moonshots/mapped', { params: fresh ? { fresh: 1 } : {} })).data,

  // Bot Tester (live chat with debug info)
  botTest: async (payload) => (await api.post('/admin/bot/test', payload)).data,
  botTestReset: async (sessionId) => (await api.post('/admin/bot/test/reset', { session_id: sessionId })).data,

  // AI training (Knowledge Base / FAQ)
  getKnowledge: async () => (await api.get('/admin/knowledge')).data,
  createKnowledge: async (entry) => (await api.post('/admin/knowledge', entry)).data,
  updateKnowledge: async (id, entry) => (await api.put(`/admin/knowledge/${id}`, entry)).data,
  deleteKnowledge: async (id) => (await api.delete(`/admin/knowledge/${id}`)).data,
  testKnowledge: async (question) => (await api.post('/admin/knowledge/test', { question })).data,

  simulateEvolutionWhatsApp: async (phone, message, name = 'WhatsApp User') =>
    (await api.post('/webhook/simulate', { phone, message, name })).data
};
