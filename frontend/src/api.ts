import type {
  AdminReview,
  ApiEnvelope,
  AuthTokens,
  CartLine,
  Category,
  InventoryTransaction,
  Order,
  Product,
  Refund,
  Review,
  Shop,
  UserProfile
} from './types';

const tokenKey = 'shopease_access_token';
const refreshKey = 'shopease_refresh_token';

export function getAccessToken() {
  return localStorage.getItem(tokenKey);
}

export function setTokens(tokens: AuthTokens) {
  localStorage.setItem(tokenKey, tokens.access);
  localStorage.setItem(refreshKey, tokens.refresh);
}

export function clearTokens() {
  localStorage.removeItem(tokenKey);
  localStorage.removeItem(refreshKey);
}

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
}

export async function tryRefreshToken(): Promise<boolean> {
  const token = localStorage.getItem(refreshKey);
  if (!token) return false;
  try {
    const res = await fetch('/api/users/token/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: token })
    });
    if (res.ok) {
      const json = await res.json();
      localStorage.setItem(tokenKey, json.access);
      return true;
    }
  } catch {}
  return false;
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...authHeaders(),
      ...(init.headers || {})
    }
  });
  const text = await response.text();
  let json: Record<string, unknown> = {};
  if (text) {
    try {
      json = JSON.parse(text);
    } catch {
      throw new Error(`Server returned invalid response (HTTP ${response.status})`);
    }
  }

  if (response.status === 401 && retry) {
    const hadRefreshToken = !!localStorage.getItem(refreshKey);
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return request<T>(path, init, false);
    }
    clearTokens();
    if (hadRefreshToken && !path.includes('/api/users/token')) {
      window.dispatchEvent(new CustomEvent('shopease:auth-expired'));
      throw new Error('Your session has expired. Please sign in again.');
    }
    // Login failure or anonymous request — use the server's error message
    const detail = json?.detail || json?.msg;
    throw new Error(typeof detail === 'string' ? detail : 'Invalid credentials');
  }

  if (!response.ok) {
    let message = json?.msg || json?.detail || '';
    // DRF validation errors: {"field":["error1","error2"]} — pick the first one
    if (!message && typeof json === 'object') {
      for (const [key, val] of Object.entries(json)) {
        if (Array.isArray(val) && val.length > 0) {
          message = `${key}: ${val[0]}`;
          break;
        }
      }
    }
    if (!message) message = `Request failed: ${response.status}`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }

  const envelope = json as ApiEnvelope<T>;
  if (typeof envelope.code === 'number' && envelope.code !== 0) {
    throw new Error(envelope.msg || 'Server returned an error');
  }
  if (envelope.data !== undefined) return envelope.data;
  if (envelope.results !== undefined) return envelope.results as T;
  return json as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<AuthTokens>('/api/users/token/', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    }),

  register: (payload: {
    username: string;
    display_name?: string;
    email: string;
    phone?: string;
    password: string;
    password2: string;
  }) =>
    request<{ username: string; email: string }>('/api/users/register/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  getProfile: () => request<UserProfile>('/api/users/info/'),

  updateProfile: (payload: Partial<UserProfile>) =>
    request<UserProfile>('/api/users/info/', {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),

  getCategories: () => request<Category[]>('/api/products/categories/'),

  createCategory: (payload: { name: string; slug: string; parent?: number | null }) =>
    request<Category>('/api/products/categories/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  updateCategory: (id: number, payload: { name: string; slug: string; parent?: number | null }) =>
    request<Category>(`/api/products/categories/${id}/`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),

  deleteCategory: (id: number) =>
    request<{ msg: string }>(`/api/products/categories/${id}/`, {
      method: 'DELETE'
    }),

  getProducts: async (params: Record<string, string | number | undefined> = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value));
    });
    const suffix = query.toString() ? `?${query.toString()}` : '';
    const response = await fetch(`/api/products/${suffix}`, { headers: { ...authHeaders() } });
    const json = await response.json();
    if (!response.ok) throw new Error(json?.msg || `Request failed: ${response.status}`);
    if (json.code !== 0) throw new Error(json.msg || 'Server returned an error');
    return { items: json.data as Product[], count: json.count as number };
  },

  getSellerProducts: (shopIds: number[]) =>
    request<Product[]>('/api/products/?shop=' + shopIds.join(',')),

  getProduct: (id: number) => request<Product>(`/api/products/${id}/`),

  getInventoryTransactions: (limit = 200) =>
    request<InventoryTransaction[]>(`/api/products/inventory-transactions/?limit=${limit}`),

  createProduct: (payload: {
    name: string;
    description?: string;
    price: number;
    stock: number;
    image?: string;
    category?: number | null;
    shop?: number | null;
    is_active: boolean;
  }) =>
    request<Product>('/api/products/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  getCart: () =>
    request<{ items: CartLine[]; total_count: number; total_price: string }>('/api/orders/cart/'),

  addCart: (productId: number, quantity: number) =>
    request<CartLine>('/api/orders/cart/add/', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, quantity })
    }),

  updateCart: (id: number, quantity: number) =>
    request<CartLine>(`/api/orders/cart/${id}/`, {
      method: 'PUT',
      body: JSON.stringify({ quantity })
    }),

  deleteCart: (id: number) =>
    request<{ msg: string }>(`/api/orders/cart/${id}/delete/`, {
      method: 'DELETE'
    }),

  clearCart: () =>
    request<{ msg: string }>('/api/orders/cart/clear/', {
      method: 'DELETE'
    }),

  createOrder: (payload: {
    address: string;
    receiver_name: string;
    receiver_phone: string;
    remark?: string;
    items: { product_id: number; quantity: number }[];
  }) =>
    request<Order>('/api/orders/create/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  directOrder: (payload: {
    product_id: number;
    quantity: number;
    address: string;
    receiver_name: string;
    receiver_phone: string;
    remark?: string;
  }) =>
    request<Order>('/api/orders/direct-create/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  getOrders: () => request<Order[]>('/api/orders/'),

  deleteOrder: (id: number) =>
    request<{ msg: string }>(`/api/orders/${id}/delete/`, {
      method: 'DELETE'
    }),

  createRefund: (orderId: number, reason: string) =>
    request<Refund>('/api/orders/refunds/create/', {
      method: 'POST',
      body: JSON.stringify({ order_id: orderId, reason })
    }),

  cancelRefund: (refundId: number) =>
    request<Refund>(`/api/orders/refunds/${refundId}/cancel/`, {
      method: 'PUT'
    }),

  followShop: (shopId: number) =>
    request<{ is_followed: boolean }>(`/api/products/shops/${shopId}/follow/`, {
      method: 'POST'
    }),

  getReviews: (productId: number) =>
    request<Review[]>(`/api/products/${productId}/reviews/`),

  createReview: (productId: number, payload: { rating: number; comment?: string; order_item_id?: number }) =>
    request<Review>(`/api/products/${productId}/reviews/create/`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  getShops: () => request<Shop[]>('/api/products/shops/'),

  createShop: (payload: { shop_name: string; description?: string }) =>
    request<Shop>('/api/products/shops/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  updateShop: (id: number, payload: { shop_name?: string; description?: string }) =>
    request<Shop>(`/api/products/shops/${id}/`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),

  updateProduct: (id: number, payload: Partial<Product>) =>
    request<Product>(`/api/products/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    }),

  deleteProduct: (id: number) =>
    request<{ msg: string }>(`/api/products/${id}/`, {
      method: 'DELETE'
    }),

  getInventories: () => request<InventoryTransaction[]>('/api/products/inventory/'),

  restockInventory: (productId: number, quantity: number) =>
    request<InventoryTransaction>(`/api/products/inventory/${productId}/restock/`, {
      method: 'POST',
      body: JSON.stringify({ quantity })
    }),

  updateOrderStatus: (orderId: number, status: string) =>
    request<Order>(`/api/orders/${orderId}/status/`, {
      method: 'PUT',
      body: JSON.stringify({ status })
    }),

  getRefunds: () => request<Refund[]>('/api/orders/refunds/'),

  processRefund: (refundId: number, payload: { status: string; admin_remark?: string }) =>
    request<Refund>(`/api/orders/refunds/${refundId}/process/`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),

  // Admin APIs
  adminStats: () => request<{
    total_users: number;
    total_sellers: number;
    total_shops: number;
    total_products: number;
    total_orders: number;
    total_revenue: number;
    total_categories: number;
    total_reviews: number;
    refund_rate: number;
    low_stock: number;
    top_products: { name: string; sold: number }[];
    monthly_revenue: { month: string; revenue: number }[];
  }>('/api/admin/stats/'),

  adminToggleUser: (username: string) =>
    request<{ username: string; status: string }>(`/api/admin/users/${username}/toggle/`, {
      method: 'PUT'
    }),

  adminApproveShop: (shopId: number, status_val: string) =>
    request<{ shop_id: number; status: string }>(`/api/admin/shops/${shopId}/approve/`, {
      method: 'PUT',
      body: JSON.stringify({ status: status_val })
    }),

  adminModerateProduct: (productId: number, status_val: string) =>
    request<{ msg: string }>(`/api/admin/products/${productId}/moderate/`, {
      method: 'PUT',
      body: JSON.stringify({ status: status_val })
    }),

  adminGetReviews: (statusFilter?: string) => {
    const params = statusFilter ? `?status=${statusFilter}` : '';
    return request<AdminReview[]>(`/api/admin/reviews/${params}`);
  },

  adminModerateReview: (reviewId: number, status_val: string) =>
    request<{ msg: string }>(`/api/admin/reviews/${reviewId}/moderate/`, {
      method: 'PUT',
      body: JSON.stringify({ status: status_val })
    }),

  adminSQLDemo: () => request<{
    title: string;
    description: string;
    sql: string;
    columns: string[];
    rows: (string | number)[][];
    error?: string;
  }[]>('/api/admin/sql-demo/'),

  adminAuditLogs: () => request<{
    id: number;
    user_name: string;
    action: string;
    table_name: string;
    record_id: string;
    description: string;
    old_value: string;
    new_value: string;
    detail: string;
    created_at: string;
  }[]>('/api/admin/audit-logs/'),

  writeAuditLog: (payload: {
    action: string;
    table: string;
    recordId: string;
    oldValue: string;
    newValue: string;
  }) =>
    request<{ msg: string }>('/api/admin/audit-logs/', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),

  // Database Explorer
  adminDbTables: () => request<{
    name: string; row_count: number; created_at: string; comment: string;
    columns: { name: string; type: string; nullable: boolean; key: string; default: string | null; extra: string }[];
  }[]>('/api/admin/db-tables/'),

  adminDbTable: (table: string, page = 1, size = 50) =>
    request<{ table: string; columns: string[]; rows: unknown[][]; total: number; page: number; size: number }>(
      `/api/admin/db-table/?table=${table}&page=${page}&size=${size}`
    ),

  adminChangeFeed: (since?: string, limit = 30) =>
    request<{ id: string; table: string; action: string; description: string; time: string }[]>(
      `/api/admin/change-feed/?limit=${limit}${since ? `&since=${encodeURIComponent(since)}` : ''}`
    ),

  adminOrders: (params?: { status?: string; search?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.search) query.set('search', params.search);
    const qs = query.toString();
    return request<{
      orders: {
        id: number; order_no: string; username: string;
        total_amount: number; status: string; status_text: string;
        receiver_name: string; receiver_phone: string; address: string;
        items: { product_name: string; price: number; quantity: number }[];
        created_at: string;
      }[];
      stats: { total: number; total_revenue: number; by_status: Record<string, number> };
    }>(`/api/admin/orders/${qs ? `?${qs}` : ''}`);
  }
};
