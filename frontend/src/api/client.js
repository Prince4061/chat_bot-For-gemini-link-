import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json'
  }
});

export const chatApi = {
  sendMessage: async (sessionId, message, userTypeHint = 'customer', customApiKey = '') => {
    const res = await api.post('/chat', {
      session_id: sessionId,
      message,
      user_type_hint: userTypeHint,
      custom_api_key: customApiKey || undefined
    });
    return res.data;
  },

  getSessions: async () => {
    const res = await api.get('/chat/sessions');
    return res.data;
  },

  getHistory: async (sessionId) => {
    const res = await api.get(`/chat/history/${sessionId}`);
    return res.data;
  },

  newSession: async (userType = 'customer') => {
    const res = await api.post('/chat/sessions/new', { user_type: userType });
    return res.data;
  },

  deleteSession: async (sessionId) => {
    const res = await api.delete(`/chat/sessions/${sessionId}`);
    return res.data;
  }
};

export const adminApi = {
  getMetrics: async () => {
    const res = await api.get('/admin/metrics');
    return res.data;
  },

  getProducts: async () => {
    const res = await api.get('/admin/products');
    return res.data;
  },

  createProduct: async (productData) => {
    const res = await api.post('/admin/products', productData);
    return res.data;
  },

  updateProduct: async (id, productData) => {
    const res = await api.put(`/admin/products/${id}`, productData);
    return res.data;
  },

  updateMargin: async (id, marginPercent) => {
    const res = await api.post(`/admin/products/${id}/margin`, {
      margin_percent: parseFloat(marginPercent)
    });
    return res.data;
  },

  deleteProduct: async (id) => {
    const res = await api.delete(`/admin/products/${id}`);
    return res.data;
  },

  getInventory: async (status = '', productId = '') => {
    const params = {};
    if (status) params.status = status;
    if (productId) params.product_id = productId;
    const res = await api.get('/admin/inventory', { params });
    return res.data;
  },

  bulkUploadInventory: async (productId, linksText) => {
    const res = await api.post('/admin/inventory/bulk-upload', {
      product_id: parseInt(productId),
      links_text: linksText
    });
    return res.data;
  },

  deleteInventoryItem: async (id) => {
    const res = await api.delete(`/admin/inventory/${id}`);
    return res.data;
  },

  getResellers: async () => {
    const res = await api.get('/admin/resellers');
    return res.data;
  },

  createReseller: async (resellerData) => {
    const res = await api.post('/admin/resellers', resellerData);
    return res.data;
  },

  updateReseller: async (id, resellerData) => {
    const res = await api.put(`/admin/resellers/${id}`, resellerData);
    return res.data;
  },

  adjustCredits: async (id, amount, reason = 'admin_topup', note = '') => {
    const res = await api.post(`/admin/resellers/${id}/credits`, {
      amount: parseInt(amount),
      reason,
      note
    });
    return res.data;
  },

  getResellerTransactions: async (id) => {
    const res = await api.get(`/admin/resellers/${id}/transactions`);
    return res.data;
  },

  getOrders: async () => {
    const res = await api.get('/admin/orders');
    return res.data;
  },

  approveOrder: async (orderId, paymentRef = 'ADMIN_APPROVED') => {
    const res = await api.post(`/admin/orders/${orderId}/approve`, { payment_ref: paymentRef });
    return res.data;
  },

  getSettings: async () => {
    const res = await api.get('/admin/settings');
    return res.data;
  },

  updateSettings: async (settingsData) => {
    const res = await api.post('/admin/settings', settingsData);
    return res.data;
  },

  simulateEvolutionWhatsApp: async (phone, message, name = 'WhatsApp User') => {
    const res = await api.post('/webhook/simulate', {
      phone,
      message,
      name
    });
    return res.data;
  }
};
