import {
  AlertTriangle,
  BarChart3,
  Boxes,
  Building2,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Clock,
  Database,
  Filter,
  Home,
  LayoutDashboard,
  LogIn,
  LogOut,
  Package,
  PackagePlus,
  Pencil,
  RefreshCcw,
  Search,
  ShoppingCart,
  Store,
  Tags,
  User,
  X
} from 'lucide-react';
import { FormEvent, Fragment, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api, clearTokens, getAccessToken, setTokens, tryRefreshToken } from './api';
import { fallbackCategories, fallbackProducts } from './data';
import type { AdminReview, Category, InventoryChangeType, InventoryTransaction, LocalCartLine, Order, Product, Review, Shop, UserProfile } from './types';

const adminUrl = 'http://127.0.0.1:8000/admin/';
const cartKey = 'shopease_local_cart';
const followedKey = 'shopease_followed_shops';

function getFollowedShops(): number[] {
  try {
    return JSON.parse(localStorage.getItem(followedKey) || '[]');
  } catch {
    return [];
  }
}

function setFollowedShop(shopId: number, followed: boolean) {
  const list = getFollowedShops();
  const next = followed
    ? [...list, shopId].filter((v, i, a) => a.indexOf(v) === i)
    : list.filter((id) => id !== shopId);
  localStorage.setItem(followedKey, JSON.stringify(next));
}

type Route =
  | 'dashboard'
  | 'products'
  | 'inventory'
  | 'categories'
  | 'cart'
  | 'pending-orders'
  | 'checkout'
  | 'orders'
  | 'shops'
  | 'profile'
  | 'auth'
  | 'database'
  | 'seller-dashboard'
  | 'seller-store'
  | 'seller-products'
  | 'seller-orders'
  | 'seller-refunds'
  | 'admin-dashboard'
  | 'admin-users'
  | 'admin-stores'
  | 'admin-products'
  | 'admin-categories'
  | 'admin-reviews'
  | 'admin-orders'
  | 'admin-audit-logs'
  | 'admin-statistics'
  | 'order-detail'
  | 'shop-detail'
  | 'review';

type NoticeType = 'success' | 'error' | 'info';
type Notice = { type: NoticeType; message: string } | null;
type RoleMode = 'anonymous' | 'customer' | 'seller' | 'admin';
type LocalAccount = {
  username: string;
  password?: string;
  role: Exclude<RoleMode, 'anonymous'>;
  display_name: string;
  email: string;
  phone?: string;
  address?: string;
  company_name?: string;
  shopIds?: number[];
};
type CheckoutForm = {
  address: string;
  receiver_name: string;
  receiver_phone: string;
  remark: string;
};
type PendingOrderDraft = {
  id: number;
  createdAt: string;
  form: CheckoutForm;
  items: LocalCartLine[];
};
type AuditLog = {
  id: number;
  user: string;
  action: string;
  table: string;
  recordId: string;
  oldValue: string;
  newValue: string;
  createdAt: string;
};

function money(value: string | number | undefined) {
  const numberValue = Number(value || 0);
  return `$${numberValue.toFixed(2)}`;
}

function displayOrderNo(order: Pick<Order, 'order_no' | 'id'>) {
  const no = order.order_no || '';
  if (no.startsWith('LOCAL')) return `Demo Order ${no.replace('LOCAL', '')}`;
  if (no.startsWith('DEMO-ORDER-')) return no.replace('DEMO-ORDER-', 'Demo Order ');
  return `Order ${no || order.id}`;
}

function displayOrderCustomer(order: Order) {
  return order.username || order.receiver_name || 'Customer';
}

function statusLabel(status: string | undefined) {
  const labels: Record<string, string> = {
    paid: 'Paid',
    shipped: 'Shipped',
    completed: 'Completed',
    cancelled: 'Cancelled',
    refunded: 'Refunded',
    pending: 'Pending',
    approved: 'Approved',
    rejected: 'Rejected',
    reported: 'Reported',
    disabled: 'Disabled',
    off_shelf: 'Off shelf',
    hidden: 'Hidden',
    visible: 'Visible',
    已付款: 'Paid',
    已发货: 'Shipped',
    已完成: 'Completed',
    已取消: 'Cancelled',
    已退款: 'Refunded',
    待处理: 'Pending',
  };
  return labels[status || ''] || (status ? status.replace(/_/g, ' ') : '');
}

function formatAuditValue(value: string) {
  if (value === '{}') return 'Empty record';
  if (value === '-') return 'None';
  if (value === 'moderation') return 'Previous status';
  if (value === 'before checkout') return 'Stock before checkout';
  if (value === 'checkout stock') return 'Stock before checkout';
  return value;
}

function formatAuditRecord(log: AuditLog) {
  const recordId = log.recordId || '';
  if (log.table === 'orders' && recordId.startsWith('LOCAL')) {
    return `Demo Order ${recordId.replace('LOCAL', '')}`;
  }
  if (log.table === 'orders' && recordId.startsWith('DEMO-ORDER-')) {
    return recordId.replace('DEMO-ORDER-', 'Demo Order ');
  }
  return recordId;
}

const roleKey = 'shopease_role_mode';
const auditKey = 'shopease_audit_logs';
const pendingOrderKey = 'shopease_pending_orders';
const usersKey = 'shopease_local_users';
const currentUserKey = 'shopease_current_user';
const productsKey = 'shopease_products';
const ordersKey = 'shopease_orders';
const inventoryTransactionsKey = 'shopease_inventory_transactions';
const categoriesKey = 'shopease_categories';
const shopsKey = 'shopease_shops';

const seedAccounts: LocalAccount[] = [
  {
    username: 'customer01',
    password: 'customer123',
    role: 'customer',
    display_name: 'Demo Customer',
    email: 'customer01@shopease.local',
    phone: '13800138000',
    address: 'Demo customer address'
  },
  {
    username: 'seller_alice',
    password: 'seller123',
    role: 'seller',
    display_name: 'Alice Seller',
    email: 'alice@shopease.local',
    company_name: 'Alice Trading Co.',
    shopIds: [1]
  },
  {
    username: 'seller_charlie',
    password: 'seller123',
    role: 'seller',
    display_name: 'Charlie Seller',
    email: 'charlie@shopease.local',
    company_name: 'Charlie Home Ltd.',
    shopIds: [3]
  },
  {
    username: 'seller_diana',
    password: 'seller123',
    role: 'seller',
    display_name: 'Diana Seller',
    email: 'diana@shopease.local',
    company_name: 'Diana Books Ltd.',
    shopIds: [4]
  },
  {
    username: 'admin',
    password: 'admin123',
    role: 'admin',
    display_name: 'Platform Admin',
    email: 'admin@shopease.local'
  }
];

function readRoute(): { route: Route; productId?: number; id?: number; categoryId?: number } {
  const hash = window.location.hash.replace('#/', '') || 'dashboard';
  const [pathAndQuery] = hash.split('?');
  const [name, id] = pathAndQuery.split('/');
  const params = new URLSearchParams(hash.includes('?') ? hash.slice(hash.indexOf('?')) : '');
  const categoryId = params.get('category') ? Number(params.get('category')) : undefined;
  if (name === 'products' && id) return { route: 'products', productId: Number(id), categoryId };
  if (name === 'order-detail' && id) return { route: 'order-detail', id: Number(id) };
  if (name === 'shop-detail' && id) return { route: 'shop-detail', id: Number(id) };
  if (name === 'review' && id) return { route: 'review', id: Number(id) };
  const route = [
    'dashboard',
    'products',
    'inventory',
    'categories',
    'cart',
    'pending-orders',
    'checkout',
    'orders',
    'shops',
    'shop-detail',
    'profile',
    'auth',
    'database',
    'seller-dashboard',
    'seller-store',
    'seller-products',
    'seller-orders',
    'seller-refunds',
    'admin-dashboard',
    'admin-users',
    'admin-stores',
    'admin-products',
    'admin-categories',
    'admin-reviews',
    'admin-orders',
    'admin-audit-logs',
    'admin-statistics'
  ].includes(name)
    ? (name as Route)
    : 'dashboard';
  return { route, categoryId };
}

function loadLocalCart(): LocalCartLine[] {
  try {
    return JSON.parse(localStorage.getItem(cartKey) || '[]');
  } catch {
    return [];
  }
}

function saveLocalCart(cart: LocalCartLine[]) {
  localStorage.setItem(cartKey, JSON.stringify(cart));
}

function loadPendingOrders(): PendingOrderDraft[] {
  try {
    return JSON.parse(localStorage.getItem(pendingOrderKey) || '[]');
  } catch {
    return [];
  }
}

function loadAuditLogs(): AuditLog[] {
  try {
    return JSON.parse(localStorage.getItem(auditKey) || '[]');
  } catch {
    return [];
  }
}

function loadProducts(): Product[] {
  try {
    const stored = JSON.parse(localStorage.getItem(productsKey) || '[]') as Product[];
    return stored.map((product) => {
      const seed = fallbackProducts.find((item) => item.id === product.id);
      return {
        ...seed,
        ...product,
        sold_count: product.sold_count ?? seed?.sold_count ?? 0,
        review_count: product.review_count ?? seed?.review_count ?? 0,
        average_rating: product.average_rating ?? seed?.average_rating ?? 0,
        good_rate: product.good_rate ?? seed?.good_rate ?? 0
      };
    });
  } catch {
    return [];
  }
}

function loadOrders(): Order[] {
  try {
    return JSON.parse(localStorage.getItem(ordersKey) || '[]');
  } catch {
    return [];
  }
}

function loadCategories(): Category[] {
  try {
    return JSON.parse(localStorage.getItem(categoriesKey) || '[]');
  } catch {
    return [];
  }
}

function loadInventoryTransactions(): InventoryTransaction[] {
  try {
    return JSON.parse(localStorage.getItem(inventoryTransactionsKey) || '[]');
  } catch {
    return [];
  }
}

function loadShops(): Shop[] {
  try {
    return JSON.parse(localStorage.getItem(shopsKey) || '[]');
  } catch {
    return [];
  }
}

function saveShops(list: Shop[]) {
  localStorage.setItem(shopsKey, JSON.stringify(list));
}

function readRecord<T>(key: string, fallback: T): T {
  try {
    return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback));
  } catch {
    return fallback;
  }
}

function flattenCategories(categories: Category[], parent: number | null = null): Category[] {
  return categories.flatMap((category) => {
    const current = { ...category, parent, children: undefined };
    return [current, ...flattenCategories(category.children || [], category.id)];
  });
}

function buildCategoryTree(categories: Category[]): Category[] {
  const map = new Map<number, Category>();
  categories.forEach((category) => map.set(category.id, { ...category, children: [] }));
  const roots: Category[] = [];
  map.forEach((category) => {
    if (category.parent && map.has(category.parent)) {
      map.get(category.parent)!.children!.push(category);
    } else {
      roots.push(category);
    }
  });
  return roots;
}

function normalizeUsername(value: string | null | undefined) {
  return (value || '').trim().toLowerCase();
}

function resolveRoleForUsername(username: string): Exclude<RoleMode, 'anonymous'> {
  const normalized = normalizeUsername(username);
  if (normalized === 'admin' || /^a\d+/.test(normalized)) return 'admin';
  if (normalized.startsWith('seller_') || /^s\d+/.test(normalized)) return 'seller';
  return 'customer';
}

function loadUsers(): LocalAccount[] {
  try {
    const stored = JSON.parse(localStorage.getItem(usersKey) || '[]') as LocalAccount[];
    const merged = [...seedAccounts];
    stored.forEach((user) => {
      const corrected = { ...user, role: resolveRoleForUsername(user.username) };
      if (!merged.some((item) => normalizeUsername(item.username) === normalizeUsername(corrected.username))) merged.push(corrected);
    });
    const correctedMerged = merged.map((user) => ({ ...user, role: resolveRoleForUsername(user.username) }));
    localStorage.setItem(usersKey, JSON.stringify(correctedMerged));
    return correctedMerged;
  } catch {
    localStorage.setItem(usersKey, JSON.stringify(seedAccounts));
    return seedAccounts;
  }
}

function accountToProfile(account: LocalAccount): UserProfile {
  return {
    username: account.username,
    display_name: account.display_name,
    email: account.email,
    phone: account.phone,
    address: account.address
  };
}

function loadCurrentAccount(): LocalAccount | null {
  const stored = localStorage.getItem(currentUserKey);
  if (!stored) return null;
  let username = stored;
  try {
    const parsed = JSON.parse(stored) as LocalAccount;
    username = parsed.username || stored;
  } catch {}
  const normalized = normalizeUsername(username);
  const account = loadUsers().find((user) => normalizeUsername(user.username) === normalized) || null;
  if (account) localStorage.setItem(currentUserKey, account.username);
  return account;
}

function App() {
  const [router, setRouter] = useState(readRoute);
  const [products, setProducts] = useState<Product[]>(loadProducts);
  const [categories, setCategories] = useState<Category[]>(loadCategories);
  const [orders, setOrders] = useState<Order[]>(loadOrders);
  const [inventoryTransactions, setInventoryTransactions] = useState<InventoryTransaction[]>(loadInventoryTransactions);
  const [shops, setShops] = useState<Shop[]>(loadShops);
  const [currentAccount, setCurrentAccount] = useState<LocalAccount | null>(loadCurrentAccount);
  const [profile, setProfile] = useState<UserProfile | null>(() => {
    const account = loadCurrentAccount();
    return account ? accountToProfile(account) : null;
  });
  const [cart, setCart] = useState<LocalCartLine[]>(loadLocalCart);
  const [directItem, setDirectItem] = useState<{ product: Product; quantity: number } | null>(null);
  const [pendingOrders, setPendingOrders] = useState<PendingOrderDraft[]>(loadPendingOrders);
  const [roleMode, setRoleModeState] = useState<RoleMode>(() => {
    const account = loadCurrentAccount();
    const stored = localStorage.getItem(roleKey) as RoleMode;
    const resolved = account?.role || stored || 'anonymous';
    if ((resolved === 'admin' || resolved === 'seller') && !account) return 'anonymous';
    if (resolved === 'admin' && account?.role !== 'admin') return account?.role || 'anonymous';
    if (resolved === 'seller' && account?.role !== 'seller') return account?.role || 'anonymous';
    return resolved;
  });
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>(loadAuditLogs);
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(true);
  const [offlineMode, setOfflineMode] = useState(false);

  useEffect(() => {
    const onHashChange = () => setRouter(readRoute());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    const onAuthExpired = () => {
      setProfile(null);
      setCurrentAccount(null);
      setRoleModeState('anonymous');
      localStorage.removeItem(roleKey);
      if (window.location.hash !== '#/auth') {
        window.location.hash = '#/auth';
      }
    };
    window.addEventListener('shopease:auth-expired', onAuthExpired);
    return () => window.removeEventListener('shopease:auth-expired', onAuthExpired);
  }, []);

  useEffect(() => {
    bootstrap();
  }, []);

  useEffect(() => saveLocalCart(cart), [cart]);
  useEffect(() => {
    if (products.length > 0) localStorage.setItem(productsKey, JSON.stringify(products));
  }, [products]);
  useEffect(() => {
    if (categories.length > 0) localStorage.setItem(categoriesKey, JSON.stringify(categories));
  }, [categories]);
  useEffect(() => {
    localStorage.setItem(ordersKey, JSON.stringify(orders));
  }, [orders]);
  useEffect(() => {
    saveShops(shops);
  }, [shops]);
  const isAuthed = Boolean(getAccessToken() || currentAccount);
  const canPurchase = roleMode === 'customer';
  const cartCount = cart.reduce((sum, line) => sum + line.quantity, 0);
  const sellerShopIds = roleMode === 'seller' ? (currentAccount?.shopIds || []) : [];
  const users = loadUsers();
  const sellerProducts = roleMode === 'seller' ? products.filter((product) => product.shop && sellerShopIds.includes(product.shop)) : products;

  function isProductAvailable(product: Product) {
    const shop = shops.find(s => s.shop_id === product.shop);
    const category = categories.find(c => c.id === product.category);
    return product.is_active !== false
      && product.stock > 0
      && (shop ? shop.status === 'approved' : true)
      && (category ? category.is_active !== false : true);
  }

  async function bootstrap() {
    setLoading(true);
    const storedProducts = loadProducts();
    const storedCategories = loadCategories();
    if (storedProducts.length > 0) {
      setProducts(storedProducts);
    }
    if (storedCategories.length > 0) {
      setCategories(storedCategories);
    }
    try {
      const [productResult, categoryRows, shopRows] = await Promise.all([api.getProducts(), api.getCategories(), api.getShops()]);
      setProducts(productResult.items);
      setCategories(categoryRows);
      if (shopRows.length > 0) setShops(shopRows);
      setOfflineMode(false);
    } catch {
      if (storedProducts.length === 0) setProducts(fallbackProducts);
      if (storedCategories.length === 0) setCategories(fallbackCategories);
      setOfflineMode(true);
      showNotice('info', 'Backend is not reachable yet, so the UI is using demo data.');
    }

    if (getAccessToken() && !currentAccount) {
      const ok = await tryRefreshToken();
      if (ok) {
        await refreshUserData();
        await refreshInventoryTransactions();
      } else {
        clearTokens();
      }
    }
    setLoading(false);
  }

  async function refreshUserData() {
    try {
      const [profileData, orderRows] = await Promise.all([api.getProfile(), api.getOrders()]);
      setProfile(profileData);
      setOrders(orderRows);
    } catch {
      clearTokens();
      if (!currentAccount) {
        setProfile(null);
        setOrders(loadOrders());
      }
    }
  }

  async function refreshInventoryTransactions() {
    try {
      const rows = await api.getInventoryTransactions();
      setInventoryTransactions(rows);
    } catch {
      setInventoryTransactions(loadInventoryTransactions());
    }
  }

  function showNotice(type: NoticeType, message: string) {
    setNotice({ type, message });
    window.setTimeout(() => setNotice(null), 3600);
  }

  function addToCart(product: Product, quantity = 1) {
    if (!canPurchase) {
      showNotice('error', 'Visitors can only browse products. Please switch to Customer and login before purchasing.');
      window.location.hash = '#/auth';
      return;
    }
    if (!isProductAvailable(product)) {
      showNotice('error', product.stock <= 0 ? 'This product is out of stock.' : 'This product or its store is not available for customer purchase.');
      return;
    }
    setCart((current) => {
      const existing = current.find((line) => line.productId === product.id);
      const nextQuantity = (existing?.quantity || 0) + quantity;
      if (nextQuantity > product.stock) {
        showNotice('error', `Only ${product.stock} item(s) are available.`);
        return current;
      }
      if (existing) {
        return current.map((line) =>
          line.productId === product.id
            ? { ...line, quantity: line.quantity + quantity }
            : line
        );
      }
      return [...current, {
        productId: product.id,
        name: product.name,
        price: Number(product.price),
        image: product.image,
        quantity,
        stock: product.stock
      }];
    });

    if (isAuthed) {
      api.addCart(product.id, quantity).catch(() => undefined);
    }
    showNotice('success', `${product.name} added to cart.`);
  }

  function buyNow(product: Product) {
    if (!canPurchase) {
      showNotice('error', 'Visitors can only browse products. Please login as a customer before purchasing.');
      window.location.hash = '#/auth';
      return;
    }
    if (!isProductAvailable(product)) {
      showNotice('error', product.stock <= 0 ? 'This product is out of stock.' : 'This product or its store is not available for customer purchase.');
      return;
    }
    setDirectItem({ product, quantity: 1 });
    window.location.hash = '#/checkout';
  }

  function updateCart(productId: number, quantity: number) {
    const product = products.find((row) => row.id === productId);
    if (product && quantity > product.stock) {
      showNotice('error', `Only ${product.stock} item(s) are available.`);
      return;
    }
    setCart((current) =>
      current.flatMap((line) => {
        if (line.productId !== productId) return [line];
        if (quantity <= 0) return [];
        return [{ ...line, quantity }];
      })
    );
  }

  const catalogProducts = useMemo(() => products.filter(isProductAvailable), [products, shops, categories]);

  const shopGroups = useMemo(() => {
    const map = new Map<number | string, { id: number | null; name: string; products: Product[] }>();
    products.forEach((product) => {
      const key = product.shop || product.shop_name || 'unassigned';
      if (!map.has(key)) {
        map.set(key, { id: product.shop || null, name: product.shop_name || 'Unassigned Shop', products: [] });
      }
      map.get(key)!.products.push(product);
    });
    return Array.from(map.values());
  }, [products]);
  const catalogShopGroups = useMemo(() => {
    const map = new Map<number | string, { id: number | null; name: string; products: Product[] }>();
    catalogProducts.forEach((product) => {
      const key = product.shop || product.shop_name || 'unassigned';
      if (!map.has(key)) {
        map.set(key, { id: product.shop || null, name: product.shop_name || 'Unassigned Shop', products: [] });
      }
      map.get(key)!.products.push(product);
    });
    return Array.from(map.values());
  }, [catalogProducts]);
  const allShopGroups = useMemo(() => {
    const map = new Map<number, { id: number; name: string; productCount: number; sellerName: string; products: Product[] }>();
    shops.forEach((shop) => {
      map.set(shop.shop_id, { id: shop.shop_id, name: shop.shop_name, productCount: shop.product_count || 0, sellerName: shop.owner_username || '', products: [] });
    });
    products.forEach((product) => {
      if (product.shop) {
        const entry = map.get(product.shop);
        if (entry) entry.products.push(product);
      }
    });
    return Array.from(map.values());
  }, [shops, products]);
  const visibleSellerShops = (() => {
    const groups = roleMode === 'seller'
      ? shopGroups.filter((shop) => shop.id && sellerShopIds.includes(shop.id))
      : shopGroups;
    const existingIds = new Set(groups.map((g) => g.id));
    const orphanShops = shops
      .filter((s) => sellerShopIds.includes(s.shop_id) && !existingIds.has(s.shop_id))
      .map((s) => ({ id: s.shop_id, name: s.shop_name, products: [] as Product[] }));
    return [...groups, ...orphanShops];
  })();
  const sellerOrders = roleMode === 'seller'
    ? orders
        .map((order) => ({ ...order, items: (order.items || []).filter((item) => item.shop_id && sellerShopIds.includes(item.shop_id)) }))
        .filter((order) => order.items.length > 0)
    : orders;
  const sellerInventoryTransactions = roleMode === 'seller'
    ? inventoryTransactions.filter((transaction) => transaction.store_id && sellerShopIds.includes(transaction.store_id))
    : inventoryTransactions;
  const customerOrders = roleMode === 'customer' && currentAccount
    ? orders.filter((order) => !order.username || order.username === currentAccount.username)
    : orders;
  const dashboardOrders = roleMode === 'seller' ? sellerOrders : roleMode === 'customer' ? customerOrders : orders;

  const lowStock = products.filter((product) => product.stock <= 10);
  const sellerLowStock = sellerProducts.filter((product) => product.stock <= 10);
  const inventoryValue = products.reduce((sum, product) => sum + Number(product.price) * product.stock, 0);
  const topSellingProducts = [...products].sort((a, b) => (b.sold_count || 0) - (a.sold_count || 0)).slice(0, 5);
  const catalogTopSellingProducts = [...catalogProducts].sort((a, b) => (b.sold_count || 0) - (a.sold_count || 0)).slice(0, 5);
  const topRatedProducts = [...products]
    .filter((product) => product.review_count || product.average_rating)
    .sort((a, b) => (b.good_rate || 0) - (a.good_rate || 0) || (b.average_rating || 0) - (a.average_rating || 0))
    .slice(0, 5);
  const catalogTopRatedProducts = [...catalogProducts]
    .filter((product) => product.review_count || product.average_rating)
    .sort((a, b) => (b.good_rate || 0) - (a.good_rate || 0) || (b.average_rating || 0) - (a.average_rating || 0))
    .slice(0, 5);

  function setRoleMode(role: RoleMode) {
    if (currentAccount && role !== currentAccount.role) {
      showNotice('info', 'Role is controlled by the logged-in account. Logout to switch demo roles.');
      return;
    }
    if (role === 'admin' && !(currentAccount && currentAccount.role === 'admin')) {
      showNotice('info', 'Please log in with an admin account first.');
      window.location.hash = '#/auth';
      return;
    }
    if (role === 'seller' && !(currentAccount && currentAccount.role === 'seller')) {
      showNotice('info', 'Please log in with a seller account first.');
      window.location.hash = '#/auth';
      return;
    }
    localStorage.setItem(roleKey, role);
    setRoleModeState(role);
  }

  function appendAuditLog(action: string, table: string, recordId: string, oldValue: string, newValue: string) {
    const log: AuditLog = {
      id: Date.now() + Math.floor(Math.random() * 1000),
      user: profile?.username || roleMode,
      action,
      table,
      recordId,
      oldValue,
      newValue,
      createdAt: new Date().toISOString()
    };
    setAuditLogs((current) => {
      const next = [log, ...current].slice(0, 80);
      localStorage.setItem(auditKey, JSON.stringify(next));
      return next;
    });
    api.writeAuditLog({ action, table, recordId, oldValue, newValue }).catch(() => {});
  }

  function appendInventoryTransaction(
    product: Product,
    changeType: InventoryChangeType,
    quantityChange: number,
    relatedOrderId: number | null = null,
    relatedRefundId: number | null = null
  ) {
    const transaction: InventoryTransaction = {
      transaction_id: Date.now() + Math.floor(Math.random() * 1000),
      inventory_id: product.id,
      product_id: product.id,
      product_name: product.name,
      store_id: product.shop || null,
      store_name: product.shop_name || 'Unassigned Shop',
      change_type: changeType,
      quantity_change: quantityChange,
      related_order_id: relatedOrderId,
      related_refund_id: relatedRefundId,
      created_at: new Date().toISOString()
    };
    setInventoryTransactions((current) => [transaction, ...current].slice(0, 300));
  }

  function appendInventoryTransactionsForItems(
    items: { product_id: number; quantity: number }[],
    changeType: InventoryChangeType,
    relatedOrderId: number | null = null,
    relatedRefundId: number | null = null
  ) {
    items.forEach((item) => {
      const product = products.find((row) => row.id === item.product_id);
      if (product) appendInventoryTransaction(product, changeType, item.quantity, relatedOrderId, relatedRefundId);
    });
  }

  function updateStoreStatus(shopId: number | null, status: string) {
    if (!shopId) return;
    setShops((current) => current.map(s => s.shop_id === shopId ? { ...s, status } : s));
    api.adminApproveShop(shopId, status).catch(() => {});
  }

  function updateProductModeration(productId: number, status: string) {
    setProducts((current) => current.map(p => p.id === productId ? { ...p, is_active: status !== 'off_shelf' } : p));
    api.adminModerateProduct(productId, status).catch(() => {});
  }

  function updateReviewStatus(reviewId: number, status: string) {
    api.adminModerateReview(reviewId, status).catch(() => {});
  }

  function updateCategoryStatus(categoryId: number, status: string) {
    setCategories((current) => {
      const flat = flattenCategories(current);
      const target = flat.find(c => c.id === categoryId);
      if (target) {
        api.updateCategory(categoryId, { name: target.name, slug: target.slug, is_active: status === 'active' } as any).catch(() => {});
      }
      return buildCategoryTree(flat.map(c => c.id === categoryId ? { ...c, is_active: status === 'active' } : c));
    });
  }

  function updateUserStatus(username: string) {
    api.adminToggleUser(username).catch(() => {});
    if (currentAccount?.username === username) {
      clearTokens();
      localStorage.removeItem(currentUserKey);
      setCurrentAccount(null);
      setProfile(null);
      localStorage.setItem(roleKey, 'anonymous');
      setRoleModeState('anonymous');
      window.location.hash = '#/dashboard';
    }
  }

  function renameSellerStore(shopId: number | null, name: string) {
    if (!shopId || !name.trim()) return;
    const shop = shopGroups.find((row) => row.id === shopId);
    const oldName = shop?.name || String(shopId);
    setProducts((current) => current.map((product) => product.shop === shopId ? { ...product, shop_name: name.trim() } : product));
    appendAuditLog('UPDATE', 'stores.name', String(shopId), oldName, name.trim());
    api.updateShop(shopId, { shop_name: name.trim() }).catch(() => undefined);
    showNotice('success', 'Store information updated.');
  }

  function ensureLocalAccount(): LocalAccount {
    if (currentAccount) return currentAccount;
    // Create a local account from JWT profile so sellerShopIds works
    const account: LocalAccount = {
      username: profile?.username || 'unknown',
      display_name: profile?.display_name || profile?.username || 'Seller',
      email: profile?.email || '',
      phone: profile?.phone || '',
      role: 'seller',
      shopIds: []
    };
    const users = loadUsers();
    if (!users.some((u) => u.username === account.username)) {
      localStorage.setItem(usersKey, JSON.stringify([...users, account]));
    }
    localStorage.setItem(currentUserKey, JSON.stringify(account));
    setCurrentAccount(account);
    return account;
  }

  function addShopToAccount(shopId: number) {
    const account = ensureLocalAccount();
    const updatedAccount = {
      ...account,
      shopIds: [...(account.shopIds || []), shopId]
    };
    setCurrentAccount(updatedAccount);
    localStorage.setItem(currentUserKey, JSON.stringify(updatedAccount));
    // Also update the users list
    const users = loadUsers();
    const idx = users.findIndex((u) => u.username === updatedAccount.username);
    if (idx !== -1) {
      users[idx] = { ...users[idx], shopIds: updatedAccount.shopIds };
      localStorage.setItem(usersKey, JSON.stringify(users));
    }
  }

  async function createSellerStore(name: string, description: string) {
    try {
      const created = await api.createShop({ shop_name: name, description });
      showNotice('success', `Store "${created.shop_name}" created.`);
      appendAuditLog('INSERT', 'stores', String(created.shop_id), '{}', JSON.stringify({ shop_name: name }));
      addShopToAccount(created.shop_id);
      try {
        const freshShops = await api.getShops();
        setShops(freshShops);
      } catch {}
    } catch (error) {
      const fallbackId = Date.now();
      const dummy: Product = {
        id: fallbackId + 1000,
        name: 'Placeholder product',
        price: '0',
        stock: 0,
        shop: fallbackId,
        shop_name: name,
        is_active: true
      };
      setProducts((current) => [...current, dummy]);
      setShops((current) => [...current, { shop_id: fallbackId, user: 0, owner_username: currentAccount?.username || '', shop_name: name, rating: '0' }]);
      addShopToAccount(fallbackId);
      appendAuditLog('INSERT', 'stores', String(fallbackId), '{}', JSON.stringify({ shop_name: name, offline: true }));
      showNotice('success', `Store "${name}" created (offline mode).`);
    }
  }

  function refreshSellerData() {
    bootstrap();
    if (isAuthed) {
      refreshUserData();
      refreshInventoryTransactions();
    }
  }

  function updateCategory(categoryId: number, payload: { name: string; parent?: number | null }) {
    const slug = payload.name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    const flat = flattenCategories(categories).map((category) =>
      category.id === categoryId
        ? { ...category, name: payload.name, slug, parent: payload.parent ?? null }
        : category
    );
    setCategories(buildCategoryTree(flat));
    api.updateCategory(categoryId, { name: payload.name, slug, parent: payload.parent }).catch(() => {});
    showNotice('success', 'Category updated.');
  }

  function deleteCategory(categoryId: number) {
    const flat = flattenCategories(categories)
      .filter((category) => category.id !== categoryId)
      .map((category) => category.parent === categoryId ? { ...category, parent: null } : category);
    setCategories(buildCategoryTree(flat));
    api.deleteCategory(categoryId).catch(() => {});
    showNotice('success', 'Category deleted.');
  }

  function savePendingOrder(form: CheckoutForm, items: LocalCartLine[]) {
    if (items.length === 0) {
      showNotice('info', 'There are no items to save as a pending order.');
      return;
    }
    const draft: PendingOrderDraft = {
      id: Date.now(),
      createdAt: new Date().toISOString(),
      form,
      items
    };
    setPendingOrders((current) => {
      const next = [draft, ...current].slice(0, 20);
      localStorage.setItem(pendingOrderKey, JSON.stringify(next));
      return next;
    });
    appendAuditLog('INSERT', 'pending_orders', String(draft.id), '{}', JSON.stringify({ item_count: items.length }));
    showNotice('success', 'Pending order saved.');
    window.location.hash = '#/pending-orders';
  }

  function removePendingOrder(id: number) {
    setPendingOrders((current) => {
      const next = current.filter((draft) => draft.id !== id);
      localStorage.setItem(pendingOrderKey, JSON.stringify(next));
      return next;
    });
  }

  function createLocalOrder(
    payload: {
      address: string;
      receiver_name: string;
      receiver_phone: string;
      remark?: string;
      items: { product_id: number; quantity: number }[];
    },
    reason: string
  ) {
    const orderId = Date.now();
    const orderItems = payload.items.flatMap((item, index) => {
      const product = products.find((row) => row.id === item.product_id);
      if (!product) return [];
      return [
        {
          id: Date.now() + index,
          product: product.id,
          product_name: product.name,
          product_image: product.image,
          price: product.price,
          quantity: item.quantity,
          total_price: Number(product.price) * item.quantity,
          shop_name: product.shop_name || 'Demo Store',
          shop_id: product.shop || null
        }
      ];
    });
    const total = orderItems.reduce((sum, item) => sum + Number(item.total_price), 0);
    const order: Order = {
      id: orderId,
      order_no: `DEMO-ORDER-${orderId.toString().slice(-10)}`,
      total_amount: total,
      status: 'paid',
      status_text: 'Paid',
      address: payload.address,
      receiver_name: payload.receiver_name,
      receiver_phone: payload.receiver_phone,
      remark: payload.remark,
      items: orderItems,
      username: currentAccount?.username || 'customer01',
      created_at: new Date().toISOString()
    };

    setProducts((current) =>
      current.map((product) => {
        const item = payload.items.find((line) => line.product_id === product.id);
        if (!item) return product;
        return { ...product, stock: Math.max(0, product.stock - item.quantity), sold_count: (product.sold_count || 0) + item.quantity };
      })
    );
    appendAuditLog('INSERT', 'orders', order.order_no, '{}', reason);
    payload.items.forEach((item) => appendAuditLog('UPDATE', 'products.stock', String(item.product_id), 'checkout stock', `- ${item.quantity}`));
    appendInventoryTransactionsForItems(
      payload.items.map((item) => ({ ...item, quantity: -item.quantity })),
      'ORDER_DEDUCT',
      order.id,
      null
    );
    return order;
  }

  function localLogin(username: string, password: string) {
    const normalized = normalizeUsername(username);
    const account = loadUsers().find(
      (user) => (normalizeUsername(user.username) === normalized || normalizeUsername(user.email) === normalized) && user.password === password
    );
    if (!account) throw new Error('Invalid username/email or password');
    const correctedAccount = { ...account, role: resolveRoleForUsername(account.username) };
    localStorage.setItem(currentUserKey, correctedAccount.username);
    setCurrentAccount(correctedAccount);
    setProfile(accountToProfile(correctedAccount));
    localStorage.setItem(roleKey, correctedAccount.role);
    setRoleModeState(correctedAccount.role);
    appendAuditLog('LOGIN', 'users', correctedAccount.username, '-', correctedAccount.role);
    return correctedAccount;
  }

  function localRegister(payload: {
    username: string;
    display_name?: string;
    email: string;
    phone?: string;
    address?: string;
    company_name?: string;
    store_name?: string;
    role?: string;
    password: string;
    password2: string;
  }) {
    if (payload.password !== payload.password2) throw new Error('Passwords do not match');
    const users = loadUsers();
    if (users.some((user) => user.username === payload.username)) throw new Error('Username already exists');
    const role = payload.role === 'seller' ? 'seller' : 'customer';
    const newShopId = role === 'seller' ? Date.now() : undefined;
    const account: LocalAccount = {
      username: payload.username,
      password: payload.password,
      role,
      display_name: payload.display_name || payload.username,
      email: payload.email,
      phone: payload.phone,
      address: payload.address,
      company_name: payload.company_name,
      shopIds: newShopId ? [newShopId] : undefined
    };
    const nextUsers = [...users, account];
    localStorage.setItem(usersKey, JSON.stringify(nextUsers));
    if (role === 'seller' && newShopId) {
      appendAuditLog('INSERT', 'stores', String(newShopId), '{}', payload.store_name || `${payload.username}'s Store`);
    }
    appendAuditLog('INSERT', 'users', account.username, '{}', role);
    return account;
  }

  return (
    <div className="app">
      <Sidebar active={router.route} cartCount={cartCount} isAuthed={isAuthed} profile={profile} roleMode={roleMode} />
      <main className="main">
        <Topbar
          offlineMode={offlineMode}
          loading={loading}
          isAuthed={isAuthed}
          roleMode={roleMode}
          onRoleChange={setRoleMode}
          onRefresh={bootstrap}
          onLogout={() => {
            clearTokens();
            localStorage.removeItem(currentUserKey);
            setCurrentAccount(null);
            setProfile(null);
            localStorage.setItem(roleKey, 'anonymous');
            setRoleModeState('anonymous');
            window.location.hash = '#/dashboard';
            showNotice('success', 'Signed out.');
          }}
        />
        {notice && (
          <div className={`notice ${notice.type}`}>
            <span>{notice.message}</span>
            <button onClick={() => setNotice(null)} aria-label="Close notice">
              <X size={16} />
            </button>
          </div>
        )}

        {router.route === 'dashboard' && (
          <Dashboard
            roleMode={roleMode}
            products={roleMode === 'admin' ? products : roleMode === 'seller' ? sellerProducts : catalogProducts}
            categories={categories}
            orders={dashboardOrders}
            cartCount={cartCount}
            pendingOrders={pendingOrders}
            lowStock={roleMode === 'seller' ? sellerLowStock : roleMode === 'admin' ? lowStock : catalogProducts.filter((product) => product.stock <= 10)}
            inventoryValue={inventoryValue}
            shops={roleMode === 'admin' || roleMode === 'seller' ? visibleSellerShops : catalogShopGroups}
            auditLogs={auditLogs}
            profile={profile}
            topSellingProducts={roleMode === 'admin' || roleMode === 'seller' ? topSellingProducts : catalogTopSellingProducts}
            topRatedProducts={roleMode === 'admin' || roleMode === 'seller' ? topRatedProducts : catalogTopRatedProducts}
          />
        )}
        {router.route === 'products' && (
          <ProductsPage
            products={roleMode === 'admin' || roleMode === 'seller' ? products : catalogProducts}
            categories={categories}
            productId={router.productId}
            categoryId={router.categoryId}
            canPurchase={canPurchase}
            onAdd={addToCart}
            onBuy={buyNow}
          />
        )}
        {router.route === 'inventory' && (
          <InventoryPage
            products={products}
            categories={categories}
            lowStock={lowStock}
            onCreate={async (payload) => {
              const created = await api.createProduct(payload);
              setProducts((current) => [created, ...current]);
              appendAuditLog('INSERT', 'products', String(created.id), '{}', JSON.stringify({ name: created.name, stock: created.stock }));
              showNotice('success', 'Product created.');
            }}
            isAuthed={isAuthed}
          />
        )}
        {router.route === 'categories' && (
          <CategoriesPage
            categories={categories}
            isAuthed={isAuthed}
            onCreate={async (payload) => {
              const created = await api.createCategory(payload);
              setCategories((current) => [created, ...current]);
              appendAuditLog('INSERT', 'categories', String(created.id), '{}', JSON.stringify({ name: created.name }));
              showNotice('success', 'Category created.');
            }}
          />
        )}
        {router.route === 'cart' && <CartPage cart={cart} canPurchase={canPurchase} onUpdate={updateCart} onClear={() => setCart([])} />}
        {router.route === 'checkout' && (
          <CheckoutPage
            cart={cart}
            directItem={directItem}
            profile={profile}
            canPurchase={canPurchase}
            onCancel={(form) => {
              if (directItem) {
                setDirectItem(null);
                showNotice('info', 'Direct purchase cancelled.');
                window.location.hash = '#/products';
              } else {
                savePendingOrder(form, cart);
              }
            }}
            onSubmit={async (payload) => {
              let order: Order;
              const unavailable = payload.items
                .map((item) => {
                  const product = products.find((row) => row.id === item.product_id) || directItem?.product;
                  return product && product.stock < item.quantity ? product : null;
                })
                .find(Boolean);
              if (unavailable) {
                showNotice('error', `${unavailable.name} is out of stock or does not have enough inventory.`);
                return;
              }
              try {
                if (directItem) {
                  order = await api.directOrder({
                    product_id: directItem.product.id,
                    quantity: directItem.quantity,
                    address: payload.address,
                    receiver_name: payload.receiver_name,
                    receiver_phone: payload.receiver_phone,
                    remark: payload.remark
                  });
                } else {
                  order = await api.createOrder(payload);
                }
                order = { ...order, username: currentAccount?.username || order.username };
                setProducts((current) =>
                  current.map((product) => {
                    const item = payload.items.find((line) => line.product_id === product.id);
                    if (!item) return product;
                    return { ...product, stock: Math.max(0, product.stock - item.quantity), sold_count: (product.sold_count || 0) + item.quantity };
                  })
                );
                appendAuditLog('INSERT', 'orders', order.order_no, '{}', JSON.stringify({ total: order.total_amount }));
                payload.items.forEach((item) => appendAuditLog('UPDATE', 'products.stock', String(item.product_id), 'before checkout', `- ${item.quantity}`));
                appendInventoryTransactionsForItems(
                  payload.items.map((item) => ({ ...item, quantity: -item.quantity })),
                  'ORDER_DEDUCT',
                  order.id,
                  null
                );
              } catch (error) {
                const message = error instanceof Error ? error.message : 'Order creation failed';
                showNotice('error', message);
                return;
              }
              setOrders((current) => [order, ...current]);
              setCart([]);
              setDirectItem(null);
              showNotice('success', `${displayOrderNo(order)} created.`);
              window.location.hash = '#/orders';
            }}
          />
        )}
        {(router.route === 'orders' || router.route === 'pending-orders') && (
          <OrdersPage
            orders={roleMode === 'customer' ? customerOrders : orders}
            isAuthed={isAuthed}
            initialTab={router.route === 'pending-orders' ? 'pending' : 'completed'}
            onRefresh={refreshUserData}
            onRefund={async (orderId, reason) => {
              const targetOrder = orders.find((order) => order.id === orderId);
              let refundId: number | null = null;
              try {
                const refund = await api.createRefund(orderId, reason);
                refundId = refund.id;
                setOrders((current) =>
                  current.map((order) =>
                    order.id === orderId
                      ? { ...order, pending_refund_id: refund.id, pending_refund_status: 'pending' }
                      : order
                  )
                );
                showNotice('success', 'Refund request submitted. Waiting for review.');
              } catch (error) {
                showNotice('error', String(error));
              }
              appendAuditLog('INSERT', 'refund_requests', String(orderId), '{}', reason);
              if (targetOrder && refundId) {
                appendInventoryTransactionsForItems(
                  targetOrder.items.map((item) => ({ product_id: item.product, quantity: 0 })),
                  'REFUND_REQUESTED',
                  targetOrder.id,
                  refundId
                );
              }
              if (getAccessToken()) await refreshUserData();
            }}
            onCancelRefund={async (orderId, refundId) => {
              try {
                await api.cancelRefund(refundId);
                setOrders((current) =>
                  current.map((order) =>
                    order.id === orderId
                      ? { ...order, pending_refund_id: null, pending_refund_status: null }
                      : order
                  )
                );
                showNotice('success', 'Refund request cancelled.');
              } catch (error) {
                showNotice('error', String(error));
              }
            }}
            onDelete={async (orderId) => {
              try {
                await api.deleteOrder(orderId);
                setOrders((current) => current.filter((order) => order.id !== orderId));
                showNotice('success', 'Order deleted.');
              } catch (error) {
                showNotice('error', String(error));
              }
            }}
            onStatusChange={async (orderId, status) => {
              try {
                await api.updateOrderStatus(orderId, status);
                showNotice('success', status === 'completed' ? 'Receipt confirmed.' : `Order status updated to ${statusLabel(status)}.`);
              } catch (error) {
                showNotice('error', error instanceof Error ? error.message : 'Status update failed');
              }
              setOrders((current) => current.map((o) => o.id === orderId ? { ...o, status, status_text: statusLabel(status) } : o));
            }}
            pendingOrders={pendingOrders}
            onResume={(draft) => {
              setCart(draft.items);
              sessionStorage.setItem('shopease_active_pending_order', JSON.stringify(draft.form));
              window.location.hash = '#/checkout';
            }}
            onRemovePending={removePendingOrder}
          />
        )}
        {router.route === 'shops' && <ShopsPage shops={allShopGroups} isAuthed={isAuthed} onNotice={showNotice} />}
        {router.route === 'shop-detail' && (
          <ShopDetailPage
            shop={allShopGroups.find((shop) => shop.id === router.id)}
            isAuthed={isAuthed}
            roleMode={roleMode}
            transactions={roleMode === 'seller' ? sellerInventoryTransactions : inventoryTransactions}
            getStatus={(product: Product) => product.is_active === false ? 'off_shelf' : 'approved'}
            onNotice={showNotice}
            onUpdate={async (id, payload) => {
              try {
                await api.updateProduct(id, payload);
                showNotice('success', 'Product updated.');
              } catch (error) {
                showNotice('error', error instanceof Error ? error.message : 'Update failed');
              }
              setProducts((current) => current.map((p) => p.id === id ? { ...p, ...payload } : p));
            }}
            onDelete={async (id) => {
              try {
                await api.deleteProduct(id);
                showNotice('success', 'Product deleted.');
              } catch (error) {
                showNotice('error', error instanceof Error ? error.message : 'Delete failed, removed locally.');
              }
              setProducts((current) => current.filter((p) => p.id !== id));
            }}
          />
        )}
        {router.route === 'profile' && (
          <ProfilePage
            profile={profile}
            isAuthed={isAuthed}
            cartCount={cartCount}
            pendingOrders={pendingOrders}
            orders={roleMode === 'customer' ? customerOrders : orders}
            onSave={async (payload) => {
              let saved: UserProfile;
              try {
                saved = await api.updateProfile(payload);
              } catch {
                if (!currentAccount) throw new Error('No local user is logged in');
                const users = loadUsers().map((user) =>
                  user.username === currentAccount.username
                    ? {
                        ...user,
                        display_name: payload.display_name ?? user.display_name,
                        email: payload.email ?? user.email,
                        phone: payload.phone ?? user.phone,
                        address: payload.address ?? user.address
                      }
                    : user
                );
                localStorage.setItem(usersKey, JSON.stringify(users));
                const updated = users.find((user) => user.username === currentAccount.username)!;
                setCurrentAccount(updated);
                saved = accountToProfile(updated);
              }
              setProfile(saved);
              appendAuditLog('UPDATE', 'users', saved.username, 'profile form', JSON.stringify(payload));
              showNotice('success', 'Profile updated.');
            }}
          />
        )}
        {router.route === 'auth' && (
          <AuthPage
            onLogin={async (username, password) => {
              const normalizedUsername = normalizeUsername(username);
              const fallbackAccount = loadUsers().find(
                (user) => normalizeUsername(user.username) === normalizedUsername || normalizeUsername(user.email) === normalizedUsername
              );
              try {
                const tokens = await api.login(username, password);
                setTokens(tokens);
                const profileData = await api.getProfile().catch(() => null);
                if (profileData) setProfile(profileData);
                const orderRows = await api.getOrders().catch(() => loadOrders());
                setOrders(orderRows);
                await refreshInventoryTransactions();
                if (fallbackAccount) {
                  const correctedRole = resolveRoleForUsername(fallbackAccount.username);
                  const freshShops = correctedRole === 'seller' ? await api.getShops().catch(() => shops) : shops;
                  if (correctedRole === 'seller') setShops(freshShops);
                  const correctedAccount: LocalAccount = {
                    ...fallbackAccount,
                    role: correctedRole,
                    shopIds: correctedRole === 'seller'
                      ? freshShops
                          .filter((shop) => normalizeUsername(shop.owner_username || '') === normalizeUsername(fallbackAccount.username))
                          .map((shop) => shop.shop_id)
                      : fallbackAccount.shopIds
                  };
                  const updatedUsers = loadUsers().map((user) =>
                    normalizeUsername(user.username) === normalizeUsername(correctedAccount.username) ? correctedAccount : user
                  );
                  localStorage.setItem(usersKey, JSON.stringify(updatedUsers));
                  localStorage.setItem(currentUserKey, correctedAccount.username);
                  setCurrentAccount(correctedAccount);
                  setProfile(profileData || accountToProfile(correctedAccount));
                  setRoleModeState(correctedAccount.role);
                  localStorage.setItem(roleKey, correctedAccount.role);
                } else {
                  const role = resolveRoleForUsername(profileData?.username || normalizedUsername);
                  const freshShops = role === 'seller' ? await api.getShops().catch(() => shops) : shops;
                  if (role === 'seller') setShops(freshShops);
                  const shopIds = role === 'seller'
                    ? freshShops
                        .filter((shop) => normalizeUsername(shop.owner_username || '') === normalizedUsername)
                        .map((shop) => shop.shop_id)
                    : undefined;
                  const account: LocalAccount = {
                    username: profileData?.username || normalizedUsername,
                    display_name: profileData?.display_name || profileData?.username || normalizedUsername,
                    email: profileData?.email || '',
                    phone: profileData?.phone || undefined,
                    address: profileData?.address || undefined,
                    role,
                    shopIds
                  };
                  const users = loadUsers();
                  if (!users.some((u) => normalizeUsername(u.username) === normalizeUsername(account.username))) {
                    localStorage.setItem(usersKey, JSON.stringify([...users, account]));
                  }
                  localStorage.setItem(currentUserKey, account.username);
                  setCurrentAccount(account);
                  setRoleModeState(account.role);
                  localStorage.setItem(roleKey, account.role);
                  setProfile(profileData || accountToProfile(account));
                }
              } catch (error) {
                const message = error instanceof Error ? error.message : '';
                if (fallbackAccount?.password && fallbackAccount.password === password) {
                  localLogin(username, password);
                } else if (message.toLowerCase().includes('fetch') || message.toLowerCase().includes('network')) {
                  throw new Error('The backend is not running. Please double-click start.bat again and log in after the site opens.');
                } else {
                  throw new Error(message || 'Invalid username/email or password');
                }
              }
              // Load seller products if user has shops
              const account = loadCurrentAccount() || fallbackAccount;
              if (account?.shopIds?.length) {
                try {
                  const sellerProds = await api.getSellerProducts(account.shopIds);
                  setProducts((current) => {
                    const existing = new Map(current.map((p) => [p.id, p]));
                    sellerProds.forEach((p) => existing.set(p.id, p));
                    return Array.from(existing.values());
                  });
                } catch { /* use whatever was already loaded */ }
              }
              showNotice('success', 'Login successful.');
              window.location.hash = '#/dashboard';
            }}
            onRegister={async (payload) => {
              try {
                await api.register(payload);
              } catch (error) {
                const message = error instanceof Error ? error.message : '';
                if (message.toLowerCase().includes('fetch') || message.toLowerCase().includes('network')) {
                  localRegister(payload);
                  showNotice('info', 'Backend not reachable — account saved locally.');
                } else {
                  throw error;
                }
              }
              showNotice('success', 'Registration complete. Please log in with the new account.');
            }}
          />
        )}
        {router.route === 'database' && <DatabasePage />}
        {router.route.startsWith('seller-') && (
          <SellerGate isAuthed={isAuthed} roleMode={roleMode}>
            {router.route === 'seller-dashboard' && <SellerDashboard products={sellerProducts} orders={sellerOrders} lowStock={sellerLowStock} shops={visibleSellerShops} />}
            {router.route === 'seller-store' && <SellerStoresPage shops={visibleSellerShops} onSave={renameSellerStore} onCreate={createSellerStore} onRefresh={refreshSellerData} />}
            {router.route === 'seller-products' && (
              <SellerProductsPage
                products={sellerProducts}
                shops={visibleSellerShops}
                categories={categories}
                transactions={sellerInventoryTransactions}
                getStatus={(product: Product) => product.is_active === false ? 'off_shelf' : 'approved'}
                onUpdate={async (id, payload) => {
                  try {
                    await api.updateProduct(id, payload);
                    showNotice('success', 'Product updated.');
                    setProducts((current) => current.map((p) => p.id === id ? { ...p, ...payload } : p));
                  } catch (error) {
                    showNotice('error', error instanceof Error ? error.message : 'Update failed');
                  }
                }}
                onDelete={async (id) => {
                  try {
                    await api.deleteProduct(id);
                    showNotice('success', 'Product deleted.');
                  } catch (error) {
                    showNotice('error', error instanceof Error ? error.message : 'Delete failed, removed locally.');
                  }
                  setProducts((current) => current.filter((p) => p.id !== id));
                }}
                onRefresh={refreshSellerData}
              />
            )}
            {router.route === 'seller-orders' && (
              <SellerOrdersPage
                orders={sellerOrders}
                shops={visibleSellerShops}
                onStatusChange={async (orderId, status) => {
                  try {
                    await api.updateOrderStatus(orderId, status);
                    showNotice('success', status === 'shipped' ? 'Shipment confirmed.' : status === 'completed' ? 'Receipt confirmed.' : `Order status updated to ${statusLabel(status)}.`);
                    refreshInventoryTransactions();
                  } catch (error) {
                    showNotice('error', error instanceof Error ? error.message : 'Status update failed');
                  }
                  setOrders((current) => current.map((o) => o.id === orderId ? { ...o, status, status_text: status } : o));
                }}
              />
            )}
            {router.route === 'seller-refunds' && (
              <SellerRefundsPage
                orders={sellerOrders}
                onProcessRefund={async (refundId, status, remark) => {
                  try {
                    await api.processRefund(refundId, { status, admin_remark: remark });
                    showNotice('success', status === 'approved' ? 'Refund approved.' : 'Refund rejected.');
                    refreshInventoryTransactions();
                  } catch (error) {
                    showNotice('error', error instanceof Error ? error.message : 'Refund processing failed');
                  }
                  setOrders((current) =>
                    current.map((o) =>
                      o.pending_refund_id === refundId
                        ? { ...o, pending_refund_id: null, pending_refund_status: null, status: status === 'approved' ? 'refunded' : o.status }
                        : o
                    )
                  );
                }}
              />
            )}
          </SellerGate>
        )}
        <AdminGate isAuthed={isAuthed} roleMode={roleMode} active={router.route}>
          {router.route === 'admin-dashboard' && (
            <AdminDashboard products={products} orders={orders} shops={shopGroups} auditLogs={auditLogs} categories={categories} users={users} />
          )}
          {router.route === 'admin-users' && <AdminUsersPage users={users} onStatusChange={updateUserStatus} shops={shopGroups} orders={orders} />}
          {router.route === 'admin-stores' && (
            <AdminStoresPage shopGroups={shopGroups} shops={shops} onStatusChange={updateStoreStatus} />
          )}
          {router.route === 'admin-products' && (
            <AdminProductsPage products={products} categories={categories} onStatusChange={updateProductModeration} />
          )}
          {router.route === 'admin-categories' && (
            <AdminCategoriesPage
              categories={categories}
              products={products}
              onCreate={async (payload) => {
                try {
                  const created = await api.createCategory(payload);
                  setCategories((current) => buildCategoryTree([...flattenCategories(current), { ...created, children: [] }]));
                  showNotice('success', 'Category created.');
                } catch {
                  showNotice('error', 'Failed to create category.');
                }
              }}
              onUpdate={updateCategory}
              onStatusChange={updateCategoryStatus}
              onDelete={deleteCategory}
            />
          )}
          {router.route === 'admin-reviews' && (
            <AdminReviewsPage products={products} onStatusChange={updateReviewStatus} />
          )}
          {router.route === 'admin-orders' && <AdminOrdersPage />}
          {router.route === 'admin-audit-logs' && (
            <AdminAuditLogsPage />
          )}
          {router.route === 'admin-statistics' && (
            <AdminStatisticsPage products={products} orders={orders} categories={categories} lowStock={lowStock} shops={shopGroups} users={users} />
          )}
        </AdminGate>
        {router.route === 'order-detail' && <OrderDetailPage order={orders.find((order) => order.id === router.id)} />}
        {router.route === 'review' && <ReviewPage orders={orders} itemId={router.id} onNotice={showNotice} onRefresh={refreshUserData} />}
        <Footer />
      </main>
    </div>
  );
}

function Sidebar({
  active,
  cartCount,
  isAuthed,
  profile,
  roleMode
}: {
  active: Route;
  cartCount: number;
  isAuthed: boolean;
  profile: UserProfile | null;
  roleMode: RoleMode;
}) {
  const [navExpanded, setNavExpanded] = useState<Record<string, boolean>>({});
  const publicItems = [
    { route: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { route: 'products', label: 'Products', icon: Boxes },
    { route: 'shops', label: 'Shops', icon: Store }
  ] as const;
  const customerItems = [
    { route: 'cart', label: 'Cart', icon: ShoppingCart, badge: cartCount },
    { route: 'orders', label: 'Orders', icon: ClipboardList, children: [
      { route: 'orders', label: 'Completed Orders' },
      { route: 'pending-orders', label: 'Pending Orders' }
    ] as const },
    { route: 'profile', label: 'My ShopEase', icon: User }
  ] as const;
  const sellerItems = [
    { route: 'seller-dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { route: 'seller-orders', label: 'Orders', icon: ClipboardList },
    { route: 'seller-refunds', label: 'Refunds', icon: AlertTriangle },
    { route: 'seller-store', label: 'Store', icon: Store }
  ] as const;
  const adminItems = [
    { route: 'dashboard', label: 'Admin Dashboard', icon: LayoutDashboard },
    { route: 'admin-users', label: 'Users', icon: User },
    { route: 'admin-stores', label: 'Stores', icon: Store },
    { route: 'admin-categories', label: 'Category Management', icon: Tags },
    { route: 'admin-reviews', label: 'Review Moderation', icon: ClipboardList },
    { route: 'admin-orders', label: 'Admin Orders', icon: ClipboardList },
    { route: 'admin-audit-logs', label: 'Audit Logs', icon: Database },
    { route: 'admin-statistics', label: 'Statistics', icon: BarChart3 },
    { route: 'database', label: 'DB Design', icon: Database }
  ] as const;
  const items =
    roleMode === 'anonymous'
      ? publicItems
      : roleMode === 'customer'
        ? [...publicItems, ...customerItems]
        : roleMode === 'seller'
          ? sellerItems
          : adminItems;

  return (
    <aside className="sidebar">
      <a className="brand" href="#/dashboard">
        <span className="brandMark">SE</span>
        <span>
          <strong>ShopEase</strong>
          <small>Inventory System</small>
        </span>
      </a>
      <nav className="nav">
        {items.map((item) => {
          const Icon = item.icon;
          if ('children' in item && item.children) {
            const expanded = navExpanded[item.route];
            return (
              <div key={item.route}>
                <a
                  href={`#/${item.route}`}
                  className={active === item.route || active === 'pending-orders' ? 'active' : ''}
                  onClick={(e) => {
                    e.preventDefault();
                    setNavExpanded((prev) => ({ ...prev, [item.route]: !prev[item.route] }));
                  }}
                >
                  <Icon size={18} />
                  <span>{item.label}</span>
                  {expanded ? <ChevronUp size={14} style={{ marginLeft: 'auto' }} /> : <ChevronDown size={14} style={{ marginLeft: 'auto' }} />}
                  {'badge' in item && (item as { badge: number }).badge > 0 && <b>{(item as { badge: number }).badge}</b>}
                </a>
                {expanded && (
                  <div className="navSub">
                    {item.children.map((child) => (
                      <a key={child.route} href={`#/${child.route}`} className={active === child.route ? 'active' : ''}>
                        {child.label}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            );
          }
          return (
            <a key={item.route} href={`#/${item.route}`} className={active === item.route ? 'active' : ''}>
              <Icon size={18} />
              <span>{item.label}</span>
              {'badge' in item && item.badge > 0 && <b>{item.badge}</b>}
            </a>
          );
        })}
      </nav>
      <div className="roleBox">
        <small>Current role</small>
        <strong>{isAuthed ? profile?.display_name || profile?.username || roleMode : roleMode === 'anonymous' ? 'Visitor' : roleMode}</strong>
        <a href={isAuthed ? adminUrl : '#/auth'}>{isAuthed ? 'Admin console' : 'Login or register'}</a>
      </div>
    </aside>
  );
}

function Topbar({
  offlineMode,
  loading,
  isAuthed,
  roleMode,
  onRoleChange,
  onRefresh,
  onLogout
}: {
  offlineMode: boolean;
  loading: boolean;
  isAuthed: boolean;
  roleMode: RoleMode;
  onRoleChange: (role: RoleMode) => void;
  onRefresh: () => void;
  onLogout: () => void;
}) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">E-business inventory management</p>
        <h1>ShopEase Operations Workspace</h1>
      </div>
      <div className="topActions">
        {offlineMode && <span className="pill warning">Demo data</span>}
        <select className="roleSelect" value={roleMode} onChange={(event) => onRoleChange(event.target.value as RoleMode)}>
          <option value="anonymous">Visitor</option>
          <option value="customer">Customer</option>
          <option value="seller">Seller</option>
          <option value="admin">Admin</option>
        </select>
        <button className="iconButton" onClick={onRefresh} disabled={loading} title="Refresh data">
          <RefreshCcw size={18} />
        </button>
        {isAuthed ? (
          <button className="button quiet" onClick={onLogout}>
            <LogOut size={16} /> Logout
          </button>
        ) : (
          <a className="button primary" href="#/auth">
            <LogIn size={16} /> Login
          </a>
        )}
      </div>
    </header>
  );
}

function Dashboard({
  roleMode,
  products,
  categories,
  orders,
  cartCount,
  pendingOrders,
  lowStock,
  inventoryValue,
  shops,
  auditLogs,
  profile,
  topSellingProducts,
  topRatedProducts
}: {
  roleMode: RoleMode;
  products: Product[];
  categories: Category[];
  orders: Order[];
  cartCount: number;
  pendingOrders: PendingOrderDraft[];
  lowStock: Product[];
  inventoryValue: number;
  shops: { id: number | null; name: string; products: Product[] }[];
  auditLogs: AuditLog[];
  profile: UserProfile | null;
  topSellingProducts: Product[];
  topRatedProducts: Product[];
}) {
  const revenue = orders.reduce((sum, order) => sum + Number(order.total_amount), 0);
  if (roleMode === 'admin') {
    return (
      <section className="page">
        <div className="dashboardIntro">
          <div>
            <p className="eyebrow">Administrator workspace</p>
            <h2>Admin Dashboard</h2>
            <p>Monitor inventory, orders, sales, database coverage, and system logs.</p>
          </div>
          <a className="button primary" href="#/admin-audit-logs">View audit logs</a>
        </div>
        <div className="statsGrid">
          <Stat icon={Boxes} label="Active products" value={products.length} />
          <Stat icon={AlertTriangle} label="Low stock items" value={lowStock.length} tone={lowStock.length ? 'warn' : 'ok'} />
          <Stat icon={BarChart3} label="Inventory value" value={money(inventoryValue)} />
          <Stat icon={ClipboardList} label="Order count" value={orders.length} />
        </div>
        <div className="twoColumn">
          <section className="panel">
            <div className="panelHeader">
              <h2>Inventory Attention</h2>
              <a href="#/admin-products">Manage products</a>
            </div>
            <div className="tableWrap">
              <table className="compactTable">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Category</th>
                    <th>Stock</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {(lowStock.length ? lowStock : products.slice(0, 5)).map((product) => (
                    <tr key={product.id}>
                      <td>{product.name}</td>
                      <td>{product.category_name || 'Uncategorized'}</td>
                      <td><span className={product.stock <= 10 ? 'stock low' : 'stock'}>{product.stock}</span></td>
                      <td>{money(Number(product.price) * product.stock)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel">
            <div className="panelHeader">
              <h2>Database Coverage</h2>
              <a href="#/database">View ER summary</a>
            </div>
            <div className="coverage">
              {[
                ['Product', `${products.length} products loaded`],
                ['Category', `${categories.length} top-level categories`],
                ['Store', `${shops.length} shops`],
                ['Order', `Revenue tracked: ${money(revenue)}`],
                ['AuditLog', `${auditLogs.length} recent log rows`],
                ['Refund', 'Refund request restores stock']
              ].map(([name, desc]) => (
                <div key={name}>
                  <strong>{name}</strong>
                  <span>{desc}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
        <div className="twoColumn">
          <section className="panel">
            <div className="panelHeader">
              <h2>Best Sellers</h2>
              <a href="#/admin-statistics">Statistics</a>
            </div>
            <ProductRankList products={topSellingProducts} metric="sales" />
          </section>
          <section className="panel">
            <div className="panelHeader">
              <h2>Top Rated Products</h2>
              <a href="#/products">Product details</a>
            </div>
            <ProductRankList products={topRatedProducts} metric="rating" />
          </section>
        </div>
      </section>
    );
  }

  if (roleMode === 'seller') {
    return <SellerDashboard products={products} orders={orders} lowStock={lowStock} shops={shops} />;
  }

  if (roleMode === 'customer') {
    return (
      <section className="page">
        <div className="dashboardIntro">
          <div>
            <p className="eyebrow">Customer center</p>
            <h2>Welcome back{profile?.display_name ? `, ${profile.display_name}` : ''}</h2>
            <p>Track your cart, continue checkout, review recent orders, and keep shopping.</p>
          </div>
          <a className="button primary" href="#/products">Continue shopping</a>
        </div>

        <section className="panel">
          <div className="panelHeader">
            <h2>Recommended Products</h2>
            <a href="#/products">Browse all</a>
          </div>
          <div className="productGrid dashboardProductGrid">
            {topRatedProducts.slice(0, 8).map((product) => (
              <a className="productCard" href={`#/products/${product.id}`} key={product.id}>
                <img src={product.image || fallbackProducts[0].image || ''} alt={product.name} />
                <div className="productCardInfo">
                  <h4>{product.name}</h4>
                  <div className="productCardMeta">
                    <strong>{money(product.price)}</strong>
                    <span className="muted">{'★'.repeat(Math.round(product.average_rating || 4))}</span>
                  </div>
                </div>
              </a>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panelHeader">
            <h2>Categories</h2>
            <a href="#/products">All categories</a>
          </div>
          <div className="categoryGrid">
            {categories.filter((cat) => !cat.parent).map((cat, i) => {
              const colors = ['#eef2ff', '#fdf2f8', '#ecfdf5', '#fff7ed'];
              const iconColors = ['#4f46e5', '#db2777', '#059669', '#ea580c'];
              const childCount = cat.children?.length || 0;
              return (
                <a className="categoryCard" href={`#/products?category=${cat.id}`} key={cat.id} style={{ background: colors[i % colors.length] }}>
                  <div className="categoryIcon" style={{ background: iconColors[i % iconColors.length] }}>
                    <Tags size={20} color="white" />
                  </div>
                  <span>{cat.name}</span>
                  {childCount > 0 && <small style={{ color: '#64748b' }}>{childCount} subcategories</small>}
                </a>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <h2>Customer Shortcuts</h2>
          <div className="shortcutGrid">
            <a href="#/cart"><ShoppingCart size={18} />Cart</a>
            <a href="#/orders"><Clock size={18} />Pending orders</a>
            <a href="#/orders"><Package size={18} />Completed orders</a>
            <a href="#/profile"><User size={18} />Profile</a>
          </div>
        </section>
      </section>
    );
  }

  return (
    <section className="page">
      <div className="dashboardIntro">
        <div>
          <p className="eyebrow">Visitor homepage</p>
          <h2>Welcome to ShopEase</h2>
          <p>Browse products, view shops, and login or register to place orders.</p>
        </div>
        <div className="buttonRow">
          <a className="button primary" href="#/products">Browse products</a>
          <a className="button quiet" href="#/auth">Login / Register</a>
        </div>
      </div>
      <div className="twoColumn">
        <section className="panel">
          <div className="panelHeader">
            <h2>Featured Products</h2>
            <a href="#/products">View all</a>
          </div>
          <div className="compactProductList">
            {products.slice(0, 5).map((product) => (
              <a href={`#/products/${product.id}`} key={product.id}>
                <img src={product.image || fallbackProducts[0].image || ''} alt={product.name} />
                <span>{product.name}</span>
                <strong>{money(product.price)}</strong>
              </a>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panelHeader">
            <h2>Browse by Category</h2>
            <a href="#/products">Search products</a>
          </div>
          <div className="coverage">
            {categories.filter((c) => !c.parent).slice(0, 6).map((category) => (
              <a href={`#/products?category=${category.id}`} key={category.id} style={{ display: 'block' }}>
                <strong>{category.name}</strong>
                <span>{category.children?.length || 0} subcategories</span>
              </a>
            ))}
          </div>
        </section>
      </div>
      <div className="twoColumn">
        <section className="panel">
          <div className="panelHeader">
            <h2>Popular Products</h2>
            <a href="#/products">Browse products</a>
          </div>
          <ProductRankList products={topSellingProducts.slice(0, 4)} metric="sales" />
        </section>
        <section className="panel">
          <div className="panelHeader">
            <h2>Highly Rated</h2>
            <a href="#/products">View ratings</a>
          </div>
          <ProductRankList products={topRatedProducts.slice(0, 4)} metric="rating" />
        </section>
      </div>
      <section className="panel shopPreview">
        <div className="panelHeader">
          <h2>Shop List</h2>
          <a href="#/shops">View shops</a>
        </div>
        <div className="shopGrid">
          {shops.slice(0, 4).map((shop) => (
            <article
              className="shopCard shopCardClickable"
              key={shop.name}
              onClick={() => { if (shop.id) window.location.hash = `#/shop-detail/${shop.id}`; }}
            >
              <div className="shopIcon"><Store size={22} /></div>
              <h3>{shop.name}</h3>
              <p>{shop.products.length} products listed</p>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}

function Stat({ icon: Icon, label, value, tone }: { icon: typeof Boxes; label: string; value: string | number; tone?: string }) {
  return (
    <div className={`stat ${tone || ''}`}>
      <Icon size={22} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProductRankList({ products, metric }: { products: Product[]; metric: 'sales' | 'rating' }) {
  if (products.length === 0) return <div className="emptyState">No ranking data yet.</div>;
  return (
    <div className="compactProductList">
      {products.map((product) => (
        <a href={`#/products/${product.id}`} key={product.id}>
          <img src={product.image || fallbackProducts[0].image || ''} alt={product.name} />
          <span>{product.name}</span>
          <strong>{metric === 'sales' ? `${product.sold_count || 0} sold` : `${product.good_rate || 0}% good`}</strong>
        </a>
      ))}
    </div>
  );
}

function ProductsPage({
  products,
  categories,
  productId,
  categoryId,
  canPurchase,
  onAdd,
  onBuy
}: {
  products: Product[];
  categories: Category[];
  productId?: number;
  categoryId?: number;
  canPurchase: boolean;
  onAdd: (product: Product) => void;
  onBuy: (product: Product) => void;
}) {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState(categoryId ? String(categoryId) : '');
  const [sort, setSort] = useState('newest');

  useEffect(() => {
    if (categoryId) {
      setCategory(String(categoryId));
    }
  }, [categoryId]);

  // Server-side pagination & filtering
  const [page, setPage] = useState(1);
  const [serverProducts, setServerProducts] = useState<Product[]>(products);
  const [totalCount, setTotalCount] = useState(products.length);
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    api.getProducts({ search: debouncedSearch || undefined, category: category || undefined, page })
      .then(({ items, count }) => {
        if (!cancelled) {
          setServerProducts(items);
          setTotalCount(count);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [debouncedSearch, category, page]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, category]);

  const [reviews, setReviews] = useState<Review[]>([]);
  const [fetchedProduct, setFetchedProduct] = useState<Product | null>(null);

  const selected = productId
    ? (serverProducts.find((p) => p.id === productId) || products.find((p) => p.id === productId) || fetchedProduct)
    : null;

  useEffect(() => {
    if (productId && !serverProducts.find((p) => p.id === productId) && !products.find((p) => p.id === productId)) {
      api.getProduct(productId).then(setFetchedProduct).catch(() => {});
    } else if (productId) {
      setFetchedProduct(null);
    }
  }, [productId, serverProducts, products]);

  useEffect(() => {
    if (selected?.id) {
      api.getReviews(selected.id).then(setReviews).catch(() => setReviews([]));
    }
  }, [selected?.id]);

  const filtered = useMemo(() => {
    const result = serverProducts;
    if (sort === 'priceAsc') return [...result].sort((a, b) => Number(a.price) - Number(b.price));
    if (sort === 'priceDesc') return [...result].sort((a, b) => Number(b.price) - Number(a.price));
    if (sort === 'stockAsc') return [...result].sort((a, b) => a.stock - b.stock);
    return result;
  }, [serverProducts, sort]);

  const topLevelCats = useMemo(() => categories.filter(c => !c.parent), [categories]);

  const allCats = useMemo(() => {
    const flat: Category[] = [];
    const walk = (cats: Category[]) => {
      cats.forEach(c => { flat.push(c); if (c.children) walk(c.children); });
    };
    walk(categories);
    return flat;
  }, [categories]);

  const selectedCategoryName = category ? allCats.find(c => c.id === Number(category))?.name : '';
  const productCategoryLabel = (product: Product) => selectedCategoryName || product.category_name || 'Uncategorized';

  if (selected) {
    const selectedOutOfStock = selected.stock <= 0;
    return (
      <section className="page">
        <a className="backLink" href={category ? `#/products?category=${category}` : '#/products'}>Back to products</a>
        <div className="detailLayout">
          <img className="detailImage" src={selected.image || fallbackProducts[0].image || ''} alt={selected.name} />
          <div className="detailInfo">
            <span className="pill">{productCategoryLabel(selected)}</span>
            <h2>{selected.name}</h2>
            {selected.shop ? (
              <a
                href={`#/shop-detail/${selected.shop}`}
                className="productShopLink" style={{ marginBottom: 12 }}
              >
                <Building2 size={14} />
                {selected.shop_name || 'View shop'}
              </a>
            ) : (
              <span style={{ marginBottom: 12, fontSize: 14, color: '#94a3b8' }}>{selected.shop_name || 'Shop not assigned'}</span>
            )}
            <div className="detailMeta">
              <strong>{money(selected.price)}</strong>
              <span className={selected.stock <= 10 ? 'stock low' : 'stock'}>{selected.stock} in stock</span>
            </div>
            <div className="ratingPanel">
              <div>
                <strong>{selected.sold_count || 0}</strong>
                <span>Sold</span>
              </div>
              <div>
                <strong>{(selected.average_rating || 0).toFixed(1)}</strong>
                <span>Average rating</span>
              </div>
              <div>
                <strong>{selected.good_rate || 0}%</strong>
                <span>Good review rate</span>
              </div>
              <div>
                <strong>{selected.review_count || 0}</strong>
                <span>Reviews</span>
              </div>
            </div>
            <div className="buttonRow">
              <button className="button primary" disabled={selectedOutOfStock} onClick={() => onBuy(selected)}>
                {selectedOutOfStock ? 'Out of stock' : canPurchase ? 'Buy now' : 'Login to buy'}
              </button>
              <button className="button quiet" disabled={selectedOutOfStock} onClick={() => onAdd(selected)}>
                {selectedOutOfStock ? 'Unavailable' : canPurchase ? 'Add to cart' : 'Customer only'}
              </button>
            </div>
          </div>
        </div>
        {reviews.length > 0 ? (
          <div className="panel reviewsSection">
            <p className="eyebrow">User Reviews</p>
            <h3>{reviews.length} Reviews</h3>
            {reviews.map((review) => (
              <div className="reviewCard" key={review.review_id}>
                <div className="reviewHeader">
                  <strong>{review.username}</strong>
                  <span className="reviewStars">{'★'.repeat(review.rating)}{'☆'.repeat(5 - review.rating)}</span>
                  <span className="reviewDate">{review.created_at ? new Date(review.created_at).toLocaleDateString() : ''}</span>
                </div>
                {review.comment && <p>{review.comment}</p>}
              </div>
            ))}
          </div>
        ) : (
          <div className="panel emptyState">No reviews yet.</div>
        )}
      </section>
    );
  }

  const findParentInTree = (catId: number): Category | null => {
    for (const cat of categories) {
      if (cat.children?.some(c => c.id === catId)) return cat;
    }
    return null;
  };

  const selectedParentId = category ? Number(category) : null;
  const selectedCat = selectedParentId ? allCats.find(c => c.id === selectedParentId) : null;
  const parentId = selectedCat?.parent as number | undefined;
  const treeParent = selectedParentId ? findParentInTree(selectedParentId) : null;
  const isParentSelected = selectedCat ? (!parentId && !treeParent) : false;
  const activeParent = isParentSelected
    ? selectedCat
    : (allCats.find(c => c.id === parentId) || treeParent || null);

  const selectCategory = (catId: string) => {
    setCategory(catId);
    window.location.hash = catId ? `#/products?category=${catId}` : '#/products';
  };

  return (
    <section className="page">
      <div className="toolbar">
        <div className="searchBox">
          <Search size={18} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search products, shops, categories" />
        </div>
        <div className="toolbarBottom">
          <span className="resultCount">{totalCount} products</span>
          <div className="sortWrap">
            <Filter size={14} />
            <select className="sortSelect" value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="newest">Default</option>
              <option value="priceAsc">Price low to high</option>
              <option value="priceDesc">Price high to low</option>
              <option value="stockAsc">Low stock first</option>
            </select>
          </div>
        </div>
      </div>
      <div className="twoColumn sidebarGrid">
        <aside className="panel" style={{ padding: 12 }}>
          <h3 style={{ marginBottom: 12, fontSize: 14 }}>Categories</h3>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            <li style={{ marginBottom: 4 }}>
              <button
                className={category === '' ? 'categoryChip active' : 'categoryChip'}
                onClick={() => selectCategory('')}
                style={{ width: '100%', textAlign: 'left', justifyContent: 'flex-start' }}
              >
                All
              </button>
            </li>
            {topLevelCats.map(parent => {
              const isActive = activeParent?.id === parent.id || category === String(parent.id);
              return (
                <li key={parent.id} style={{ marginBottom: 4 }}>
                  <button
                    className={isActive ? 'categoryChip active' : 'categoryChip'}
                    onClick={() => selectCategory(String(parent.id))}
                    style={{
                      width: '100%', textAlign: 'left', justifyContent: 'flex-start',
                      fontWeight: 700, fontSize: 14
                    }}
                  >
                    {parent.name}
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>
        <div>
          <div className="productGrid">
            {filtered.map((product) => {
              const outOfStock = product.stock <= 0;
              return (
                <article
                  className={outOfStock ? 'productCard outOfStock' : 'productCard'}
                  key={product.id}
                  onClick={() => { window.location.hash = `#/products/${product.id}`; }}
                >
                  <img src={product.image || fallbackProducts[0].image || ''} alt={product.name} />
                  <div>
                    <span>{productCategoryLabel(product)}</span>
                    <h3>{product.name}</h3>
                    <p>{product.shop_name || product.seller_name || 'ShopEase seller'}</p>
                    {product.review_count ? (
                      <span style={{ fontSize: 12, color: '#f59e0b' }}>{'★'.repeat(Math.round(product.average_rating || 0))} {product.review_count} review{product.review_count !== 1 ? 's' : ''}</span>
                    ) : null}
                  </div>
                  <div className="cardFooter">
                    <strong>{money(product.price)}</strong>
                    <span className={product.stock <= 10 ? 'stock low' : 'stock'}>{outOfStock ? 'Out' : product.stock}</span>
                  </div>
                  <div className="buttonRow">
                    <button className="button primary" disabled={outOfStock} onClick={(e) => { e.stopPropagation(); onAdd(product); }}>
                      {outOfStock ? 'Out of stock' : canPurchase ? 'Add to cart' : 'Login'}
                    </button>
                    <button className="button accent" disabled={outOfStock} onClick={(e) => { e.stopPropagation(); onBuy(product); }}>
                      {outOfStock ? 'Unavailable' : canPurchase ? 'Buy' : 'View only'}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
          {totalCount > 20 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 20, alignItems: 'center' }}>
              <button
                className="button quiet"
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <span style={{ fontSize: 14, color: '#64748b' }}>
                Page {page} of {Math.ceil(totalCount / 20)}
              </span>
              <button
                className="button quiet"
                disabled={page >= Math.ceil(totalCount / 20)}
                onClick={() => setPage(p => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function InventoryPage({
  products,
  categories,
  lowStock,
  onCreate,
  isAuthed
}: {
  products: Product[];
  categories: Category[];
  lowStock: Product[];
  onCreate: (payload: {
    name: string;
    description?: string;
    price: number;
    stock: number;
    image?: string;
    category?: number | null;
    shop?: number | null;
    is_active: boolean;
  }) => Promise<void>;
  isAuthed: boolean;
}) {
  const [form, setForm] = useState({ name: '', price: '19.99', stock: '25', category: '', image: '', description: '' });
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await onCreate({
        name: form.name,
        price: Number(form.price),
        stock: Number(form.stock),
        image: form.image || undefined,
        description: form.description,
        category: form.category ? Number(form.category) : null,
        is_active: true
      });
      setForm({ name: '', price: '19.99', stock: '25', category: '', image: '', description: '' });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="page">
      <div className="splitHeader">
        <div>
          <h2>Inventory Management</h2>
          <p>Manage product stock, low-stock review, and seller product creation.</p>
        </div>
        <span className="pill warning">{lowStock.length} low stock</span>
      </div>
      <div className="twoColumn wideLeft">
        <section className="panel">
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Shop</th>
                  <th>Category</th>
                  <th>Stock</th>
                  <th>Unit price</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product) => (
                  <tr key={product.id}>
                    <td>{product.name}</td>
                    <td>{product.shop_name || '-'}</td>
                    <td>{product.category_name || '-'}</td>
                    <td>
                      <span className={product.stock <= 10 ? 'stock low' : 'stock'}>{product.stock}</span>
                    </td>
                    <td>{money(product.price)}</td>
                    <td>{money(Number(product.price) * product.stock)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <div className="panelHeader">
            <h2>Publish Product</h2>
            <PackagePlus size={20} />
          </div>
          {!isAuthed && <p className="muted">Login is required because the backend sets the product seller from the JWT user.</p>}
          <form className="stackForm" onSubmit={submit}>
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Product name" />
            <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description" />
            <div className="formGrid">
              <input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} type="number" step="0.01" min="0" />
              <input value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} type="number" min="0" />
            </div>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="">No category</option>
              {categories.map((parent) =>
                parent.children?.length ? (
                  <optgroup label={`── ${parent.name} ──`} key={parent.id}>
                    {parent.children.map((child) => (
                      <option value={child.id} key={child.id}>{child.name}</option>
                    ))}
                  </optgroup>
                ) : null
              )}
            </select>
            <div className="stackForm">
              <input value={form.image} onChange={(e) => setForm({ ...form, image: e.target.value })} placeholder="Image URL (e.g. https://images.unsplash.com/photo-...)" />
              {form.image && <img src={form.image} alt="Preview" style={{ maxWidth: 200, maxHeight: 200, borderRadius: 8, marginTop: 4 }} onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />}
            </div>
            <button className="button primary" disabled={!isAuthed || saving}>
              {saving ? 'Saving...' : 'Create product'}
            </button>
          </form>
        </section>
      </div>
    </section>
  );
}

function CategoriesPage({
  categories,
  isAuthed,
  onCreate
}: {
  categories: Category[];
  isAuthed: boolean;
  onCreate: (payload: { name: string; slug: string; parent?: number | null }) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [parent, setParent] = useState('');
  const slug = name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

  return (
    <section className="page">
      <div className="twoColumn">
        <section className="panel">
          <div className="panelHeader">
            <h2>Category Tree</h2>
            <Tags size={20} />
          </div>
          <div className="categoryTree">
            {categories.map((category) => (
              <div key={category.id} className="categoryNode">
                <strong>{category.name}</strong>
                <small>{category.slug}</small>
                {category.children?.map((child) => (
                  <span key={child.id}>{child.name}</span>
                ))}
              </div>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>Create Category</h2>
          <form
            className="stackForm"
            onSubmit={async (event) => {
              event.preventDefault();
              await onCreate({ name, slug, parent: parent ? Number(parent) : null });
              setName('');
              setParent('');
            }}
          >
            <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Category name" />
            <input value={slug} readOnly aria-label="Generated slug" />
            <select value={parent} onChange={(e) => setParent(e.target.value)}>
              <option value="">Top-level category</option>
              {categories.map((category) => (
                <option value={category.id} key={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
            <button className="button primary" disabled={!isAuthed || !slug}>
              Create category
            </button>
          </form>
        </section>
      </div>
    </section>
  );
}

function CartPage({
  cart,
  canPurchase,
  onUpdate,
  onClear
}: {
  cart: LocalCartLine[];
  canPurchase: boolean;
  onUpdate: (productId: number, quantity: number) => void;
  onClear: () => void;
}) {
  const total = cart.reduce((sum, line) => sum + line.price * line.quantity, 0);
  if (!canPurchase) {
    return (
      <section className="page">
        <div className="panel emptyState">
          Visitors can browse products only. Please login or switch to Customer to use the cart.
          <a className="button primary" href="#/auth">Login</a>
        </div>
      </section>
    );
  }
  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <h2>Shopping Cart</h2>
          <button className="button quiet" onClick={onClear}>
            Clear
          </button>
        </div>
        {cart.length === 0 ? (
          <div className="emptyState">Your cart is empty.</div>
        ) : (
          cart.map((line) => (
            <div className="cartLine" key={line.productId}>
              <img src={line.image || fallbackProducts[0].image || ''} alt={line.name} />
              <div>
                <strong>{line.name}</strong>
                <span>{money(line.price)}</span>
              </div>
              <div className="stepper">
                <button onClick={() => onUpdate(line.productId, line.quantity - 1)}>-</button>
                <input value={line.quantity} readOnly />
                <button onClick={() => onUpdate(line.productId, line.quantity + 1)}>+</button>
              </div>
              <strong>{money(line.price * line.quantity)}</strong>
            </div>
          ))
        )}
        <div className="cartTotal">
          <span>Total</span>
          <strong>{money(total)}</strong>
          {canPurchase ? (
            <a className="button primary" href="#/checkout">
              Checkout
            </a>
          ) : (
            <a className="button primary" href="#/auth">
              Login as customer
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

function PendingOrdersPage({
  drafts,
  onResume,
  onRemove
}: {
  drafts: PendingOrderDraft[];
  onResume: (draft: PendingOrderDraft) => void;
  onRemove: (id: number) => void;
}) {
  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <h2>Pending Orders</h2>
          <span className="pill">{drafts.length} saved</span>
        </div>
        {drafts.length === 0 ? (
          <div className="emptyState">No pending checkout drafts yet.</div>
        ) : (
          drafts.map((draft) => {
            const total = draft.items.reduce((sum, line) => sum + line.price * line.quantity, 0);
            return (
              <article className="orderCard" key={draft.id}>
                <div className="orderTop">
                  <div>
                    <strong>Pending #{draft.id}</strong>
                    <span>{new Date(draft.createdAt).toLocaleString()}</span>
                  </div>
                  <span className="status">Draft</span>
                </div>
                {draft.items.map((line) => (
                  <div className="orderItem" key={line.productId}>
                    <span>{line.name}</span>
                    <span>x {line.quantity}</span>
                    <strong>{money(line.price * line.quantity)}</strong>
                  </div>
                ))}
                <div className="orderBottom">
                  <span>{draft.form.receiver_name || 'No receiver yet'} / {draft.form.address || 'No address yet'}</span>
                  <strong>{money(total)}</strong>
                  <button className="button primary" onClick={() => onResume(draft)}>Resume checkout</button>
                  <button className="button quiet" onClick={() => onRemove(draft.id)}>Remove</button>
                </div>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}

function CheckoutPage({
  cart,
  directItem,
  profile,
  canPurchase,
  onCancel,
  onSubmit
}: {
  cart: LocalCartLine[];
  directItem?: { product: Product; quantity: number } | null;
  profile: UserProfile | null;
  canPurchase: boolean;
  onCancel: (form: CheckoutForm) => void;
  onSubmit: (payload: {
    address: string;
    receiver_name: string;
    receiver_phone: string;
    remark?: string;
    items: { product_id: number; quantity: number }[];
  }) => Promise<void>;
}) {
  const [form, setForm] = useState<CheckoutForm>(() => {
    try {
      const draft = JSON.parse(sessionStorage.getItem('shopease_active_pending_order') || 'null') as CheckoutForm | null;
      sessionStorage.removeItem('shopease_active_pending_order');
      if (draft) return draft;
    } catch {
      // Ignore invalid draft state.
    }
    return {
      address: profile?.address || '',
      receiver_name: profile?.display_name || profile?.username || '',
      receiver_phone: profile?.phone || '',
      remark: ''
    };
  });
  const [saving, setSaving] = useState(false);

  const isDirect = !!directItem;
  const summaryItems: LocalCartLine[] = isDirect
    ? [{ productId: directItem!.product.id, name: directItem!.product.name, price: Number(directItem!.product.price), image: directItem!.product.image, quantity: directItem!.quantity }]
    : cart;
  const total = summaryItems.reduce((sum, line) => sum + line.price * line.quantity, 0);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await onSubmit({
        ...form,
        items: summaryItems.map((line) => ({ product_id: line.productId, quantity: line.quantity }))
      });
    } finally {
      setSaving(false);
    }
  };

  if (!canPurchase) {
    return (
      <section className="page">
        <div className="panel emptyState">
          Visitors can browse products only. Please login or switch to Customer before checkout.
          <a className="button primary" href="#/auth">Login</a>
        </div>
      </section>
    );
  }

  return (
    <section className="page">
      <div className="twoColumn">
        <section className="panel">
          <h2>Checkout</h2>
          <form
            className="stackForm"
            onSubmit={handleSubmit}
          >
            <input required value={form.receiver_name} onChange={(e) => setForm({ ...form, receiver_name: e.target.value })} placeholder="Receiver name" />
            <input required value={form.receiver_phone} onChange={(e) => setForm({ ...form, receiver_phone: e.target.value })} placeholder="Phone number" />
            <input required value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="Shipping address" />
            <textarea value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} placeholder="Order remark" />
            <div className="buttonRow checkoutActions">
              <button className="button primary" disabled={summaryItems.length === 0 || saving}>
                {saving ? 'Creating order...' : 'Place order'}
              </button>
              <button type="button" className="button quiet" disabled={saving || summaryItems.length === 0} onClick={() => onCancel(form)}>
                Cancel and save pending
              </button>
            </div>
          </form>
        </section>
        <section className="panel">
          <h2>Order Summary</h2>
          {summaryItems.map((line) => (
            <div className="summaryLine" key={line.productId}>
              <span>{line.name} x {line.quantity}</span>
              <strong>{money(line.price * line.quantity)}</strong>
            </div>
          ))}
          <div className="summaryTotal">
            <span>Total</span>
            <strong>{money(total)}</strong>
          </div>
        </section>
      </div>
    </section>
  );
}

function OrdersPage({
  orders,
  isAuthed,
  initialTab,
  onRefresh,
  onRefund,
  onCancelRefund,
  onDelete,
  onStatusChange,
  pendingOrders,
  onResume,
  onRemovePending
}: {
  orders: Order[];
  isAuthed: boolean;
  initialTab?: 'completed' | 'pending';
  onRefresh: () => void;
  onRefund: (orderId: number, reason: string) => Promise<void>;
  onCancelRefund: (orderId: number, refundId: number) => Promise<void>;
  onDelete: (orderId: number) => Promise<void>;
  onStatusChange: (orderId: number, status: string) => Promise<void>;
  pendingOrders: PendingOrderDraft[];
  onResume: (draft: PendingOrderDraft) => void;
  onRemovePending: (id: number) => void;
}) {
  const tab = initialTab || 'completed';
  const [working, setWorking] = useState<number | null>(null);
  return (
    <section className="page">
      {tab === 'completed' && (
        <div className="panel">
          <div className="panelHeader">
            <h2>Completed Orders</h2>
            <button className="button quiet" onClick={onRefresh}>Refresh</button>
          </div>
          {!isAuthed && <p className="muted">Login to load your server-side order history.</p>}
          {orders.length === 0 ? (
            <div className="emptyState">No completed orders yet.</div>
          ) : (
            orders.map((order) => (
              <article className="orderCard" key={order.id}>
                <div className="orderTop">
                  <div className="orderPrimary">
                    <strong>{displayOrderCustomer(order)}</strong>
                    <span>{order.items?.length || 0} item{(order.items?.length || 0) === 1 ? '' : 's'} · {money(order.total_amount)}</span>
                  </div>
                  <span className={`status ${order.pending_refund_id ? 'pending' : order.status}`}>
                    {order.pending_refund_id ? 'Refund pending' : statusLabel(order.status_text || order.status)}
                  </span>
                </div>
                {order.remark && <p className="orderRemark">Remark: {order.remark}</p>}
                {(order.items || []).map((item) => (
                  <div className="orderItem" key={item.id}>
                    <img
                      className="orderItemImage"
                      src={item.product_image || ''}
                      alt={item.product_name}
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                      }}
                    />
                    <span className="orderItemName">{item.product_name}</span>
                    <span>x {item.quantity}</span>
                    <strong>{money(item.total_price)}</strong>
                  </div>
                ))}
                <div className="orderBottom">
                  <details className="orderInlineDetails">
                    <summary>Details</summary>
                    <div>
                      <span>{displayOrderNo(order)}</span>
                      <span>{order.created_at ? new Date(order.created_at).toLocaleString() : ''}</span>
                      <span>{order.receiver_name} / {order.receiver_phone}</span>
                      <span>{order.address}</span>
                    </div>
                  </details>
                  <a className="button quiet" href={`#/order-detail/${order.id}`}>
                    Open
                  </a>
                  <button
                    className="button quiet"
                    disabled={working === order.id || order.status === 'refunded' || order.status === 'cancelled'}
                    onClick={async () => {
                      if (order.pending_refund_id) {
                        setWorking(order.id);
                        try {
                          await onCancelRefund(order.id, order.pending_refund_id);
                        } finally {
                          setWorking(null);
                        }
                        return;
                      }
                      const reason = window.prompt('Refund reason');
                      if (!reason) return;
                      setWorking(order.id);
                      try {
                        await onRefund(order.id, reason);
                      } finally {
                        setWorking(null);
                      }
                    }}
                  >
                    {order.pending_refund_id ? 'Cancel refund' : 'Refund'}
                  </button>
                  {order.status === 'shipped' && (
                    <button
                      className="button primary small"
                      disabled={working === order.id}
                      onClick={async () => {
                        if (!window.confirm('Confirm that the order has been received?')) return;
                        setWorking(order.id);
                        try {
                          await onStatusChange(order.id, 'completed');
                        } finally {
                          setWorking(null);
                        }
                      }}
                    >
                      Confirm receipt
                    </button>
                  )}
                  {order.items?.[0] && (
                    <a className="button quiet" href={`#/review/${order.items[0].id}`}>
                      Review
                    </a>
                  )}
                  <button
                    className="button quiet"
                    disabled={working === order.id}
                    onClick={async () => {
                      if (!window.confirm('Delete this order from your view?')) return;
                      setWorking(order.id);
                      try {
                        await onDelete(order.id);
                      } finally {
                        setWorking(null);
                      }
                    }}
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
      )}

      {tab === 'pending' && (
        <div className="panel">
          <div className="panelHeader">
            <h2>Pending Orders</h2>
            <span className="pill">{pendingOrders.length} saved</span>
          </div>
          {pendingOrders.length === 0 ? (
            <div className="emptyState">No pending checkout drafts yet.</div>
          ) : (
            pendingOrders.map((draft) => {
              const total = draft.items.reduce((sum, line) => sum + line.price * line.quantity, 0);
              return (
                <article className="orderCard" key={draft.id}>
                  <div className="orderTop">
                    <div>
                      <strong>Pending #{draft.id}</strong>
                      <span>{new Date(draft.createdAt).toLocaleString()}</span>
                    </div>
                    <span className="status">Draft</span>
                  </div>
                  {draft.items.map((line) => (
                    <div className="orderItem" key={line.productId}>
                      <img
                        className="orderItemImage"
                        src={line.image || ''}
                        alt={line.name}
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = 'none';
                        }}
                      />
                      <span>{line.name}</span>
                      <span>x {line.quantity}</span>
                      <strong>{money(line.price * line.quantity)}</strong>
                    </div>
                  ))}
                  <div className="orderBottom">
                    <span>{draft.form.receiver_name || 'No receiver yet'} / {draft.form.address || 'No address yet'}</span>
                    <strong>{money(total)}</strong>
                    <button className="button primary" onClick={() => onResume(draft)}>Resume checkout</button>
                    <button className="button quiet" onClick={() => onRemovePending(draft.id)}>Remove</button>
                  </div>
                </article>
              );
            })
          )}
        </div>
      )}
    </section>
  );
}

function getShopSellerName(shop: { sellerName?: string; products?: Product[] }) {
  if (shop.sellerName) return shop.sellerName;
  return shop.products?.find((product) => product.seller_name)?.seller_name || 'seller account';
}

function ShopsPage({
  shops
}: {
  shops: { id: number | null; name: string; productCount: number; products: Product[] }[];
  isAuthed: boolean;
  onNotice: (type: NoticeType, message: string) => void;
}) {
  const [showFollowed, setShowFollowed] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 15;
  const followedIds = getFollowedShops();
  const filtered = showFollowed
    ? shops.filter((shop) => shop.id && followedIds.includes(shop.id))
    : shops;
  const totalPages = Math.ceil(filtered.length / pageSize);
  const displayed = filtered.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => { setPage(1); }, [showFollowed]);

  return (
    <section className="page">
      <div className="toolbar">
        <h2>Shops</h2>
        <span className="resultCount">{filtered.length} shops</span>
        <button
          className={showFollowed ? 'button primary' : 'button quiet'}
          onClick={() => setShowFollowed(!showFollowed)}
        >
          My Followed {followedIds.length > 0 && `(${followedIds.length})`}
        </button>
      </div>
      {displayed.length === 0 && showFollowed ? (
        <div className="panel emptyState">No followed shops yet. Visit a shop and click Follow.</div>
      ) : (
        <>
          <div className="shopGrid">
            {displayed.map((shop) => (
              <div
                className="shopCard shopCardClickable"
                key={shop.name}
                onClick={() => {
                  if (shop.id) window.location.hash = `#/shop-detail/${shop.id}`;
                }}
              >
                <div className="shopIcon">
                  <Building2 size={24} />
                </div>
                <h3>{shop.name}</h3>
                <p>Seller: {getShopSellerName(shop)}</p>
                <p>{shop.productCount} products listed</p>
                <div className="miniProducts">
                  {(shop.products || []).slice(0, 3).map((product) => (
                    <span key={product.id}>{product.name}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 20, alignItems: 'center' }}>
              <button
                className="button quiet"
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <span style={{ fontSize: 14, color: '#64748b' }}>
                Page {page} of {totalPages}
              </span>
              <button
                className="button quiet"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function ShopDetailPage({ shop, isAuthed, roleMode, transactions, getStatus, onNotice, onUpdate, onDelete }: {
  shop?: { id: number | null; name: string; products: Product[] };
  isAuthed: boolean;
  roleMode: RoleMode;
  transactions: InventoryTransaction[];
  getStatus: (product: Product) => string;
  onNotice: (type: NoticeType, message: string) => void;
  onUpdate: (id: number, payload: Partial<Product>) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [followed, setFollowed] = useState(() => shop?.id ? getFollowedShops().includes(shop.id) : false);
  const [sort, setSort] = useState('recommended');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<{ name: string; price: string; description: string; stock: number; image: string }>({ name: '', price: '', description: '', stock: 0, image: '' });
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [stockEdits, setStockEdits] = useState<Record<number, number>>({});
  const [saving, setSaving] = useState(false);
  const [fetchedProducts, setFetchedProducts] = useState<Product[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);

  useEffect(() => {
    if (!shop?.id) return;
    setLoadingProducts(true);
    api.getProducts({ shop: shop.id, page_size: 500 })
      .then((res) => setFetchedProducts(res.items))
      .catch(() => setFetchedProducts([]))
      .finally(() => setLoadingProducts(false));
  }, [shop?.id]);

  const displayProducts = fetchedProducts.length > 0 ? fetchedProducts : shop?.products || [];

  const isManager = roleMode === 'admin' || roleMode === 'seller';

  if (!shop) {
    return <section className="page"><div className="panel emptyState">Shop not found.</div></section>;
  }

  const sorted = useMemo(() => {
    const list = [...displayProducts];
    switch (sort) {
      case 'price-desc': return list.sort((a, b) => Number(b.price) - Number(a.price));
      case 'price-asc': return list.sort((a, b) => Number(a.price) - Number(b.price));
      case 'sales-desc': return list.sort((a, b) => (b.sold_count || 0) - (a.sold_count || 0));
      case 'sales-asc': return list.sort((a, b) => (a.sold_count || 0) - (b.sold_count || 0));
      default: return list;
    }
  }, [displayProducts, sort]);

  return (
    <section className="page">
      <div className="shopBanner">
        <div className="shopBannerMain">
          <div className="shopBannerIcon">
            <Building2 size={32} />
          </div>
          <div>
            <p className="eyebrow">Shop</p>
            <h2>{shop.name}</h2>
            <span className="shopBannerSeller">{getShopSellerName(shop)} / {displayProducts.length} products</span>
          </div>
        </div>
        <div className="shopBannerActions">
          {shop.id && !isManager && (
            <button
              className={followed ? 'button followedButton' : 'button followButton'}
              onClick={async () => {
                if (!isAuthed) {
                  onNotice('error', 'Login is required to follow a shop.');
                  window.location.hash = '#/auth';
                  return;
                }
                try {
                  const result = await api.followShop(shop.id!);
                  setFollowed(result.is_followed);
                  setFollowedShop(shop.id!, result.is_followed);
                  onNotice('success', result.is_followed ? 'Followed shop' : 'Unfollowed shop');
                } catch (error) {
                  onNotice('error', error instanceof Error ? error.message : 'Operation failed');
                }
              }}
            >
              {followed ? 'Followed' : 'Follow shop'}
            </button>
          )}
          {isManager && (
            <a className="button primary" href="#/inventory">+ Add Product</a>
          )}
        </div>
      </div>

      {isManager && editingId && (
        <div className="panel" style={{ marginBottom: 16, background: '#f8fafc' }}>
          <h3>Edit Product #{editingId}</h3>
          <div className="stackForm">
            <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="Product name" />
            <input value={editForm.price} onChange={(e) => setEditForm({ ...editForm, price: e.target.value })} placeholder="Price" type="number" min="0" step="0.01" />
            <textarea value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} placeholder="Description" />
            <input value={editForm.stock} onChange={(e) => setEditForm({ ...editForm, stock: Number(e.target.value) })} placeholder="Stock" type="number" min="0" />
            <input value={editForm.image} onChange={(e) => setEditForm({ ...editForm, image: e.target.value })} placeholder="Image URL (optional)" />
            <div className="buttonRow">
              <button className="button primary" disabled={!editForm.name.trim() || saving} onClick={async () => {
                setSaving(true);
                try { await onUpdate(editingId, { name: editForm.name.trim(), price: editForm.price, description: editForm.description.trim(), stock: editForm.stock, image: editForm.image.trim() || undefined }); setEditingId(null); }
                finally { setSaving(false); }
              }}>{saving ? 'Saving...' : 'Save'}</button>
              <button className="button quiet" onClick={() => setEditingId(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {isManager ? (
        <div className="panel">
          <div className="toolbar">
            <a href="#/shops" className="button quiet">&larr; Back to shops</a>
            <div className="toolbarRight">
              <select className="sortSelect" value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="recommended">Recommended</option>
                <option value="price-desc">Price: High to Low</option>
                <option value="price-asc">Price: Low to High</option>
                <option value="sales-desc">Sales: High to Low</option>
                <option value="sales-asc">Sales: Low to High</option>
              </select>
            </div>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Price</th>
                  <th>Stock</th>
                  <th>Sold</th>
                  <th>Active</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((product) => {
                  const isExpanded = expandedId === product.id;
                  const productTxs = transactions.filter((t) => t.product_id === product.id).slice(0, 10);
                  const currentStock = stockEdits[product.id] ?? product.stock;
                  return (
                    <Fragment key={product.id}>
                      <tr>
                        <td>
                          <a href={`#/products/${product.id}`} style={{ color: '#1e293b', textDecoration: 'none', fontWeight: 600 }}>{product.name}</a>
                          {product.category_name && <small className="muted" style={{ display: 'block' }}>{product.category_name}</small>}
                        </td>
                        <td>{money(product.price)}</td>
                        <td>
                          <span className={currentStock <= 10 ? 'stock low' : 'stock'} style={{ marginRight: 4 }}>{currentStock}</span>
                          <button className="button quiet small" onClick={async () => { const s = currentStock + 1; setStockEdits({ ...stockEdits, [product.id]: s }); await onUpdate(product.id, { stock: s }); }}>+</button>
                          <button className="button quiet small" disabled={currentStock <= 0} onClick={async () => { const s = Math.max(0, currentStock - 1); setStockEdits({ ...stockEdits, [product.id]: s }); await onUpdate(product.id, { stock: s }); }}>-</button>
                        </td>
                        <td>{product.sold_count || 0}</td>
                        <td>
                          <button
                            className={`button small ${product.is_active !== false ? 'primary' : 'quiet'}`}
                            onClick={async () => { try { await onUpdate(product.id, { is_active: product.is_active === false }); } catch {} }}
                          >
                            {product.is_active !== false ? 'On shelf' : 'Off shelf'}
                          </button>
                        </td>
                        <td>
                          <div className="buttonRow tableActions">
                            <button className="button quiet small" onClick={() => setExpandedId(isExpanded ? null : product.id)}>{isExpanded ? 'Hide log' : 'Log'}</button>
                            <button className="button quiet small" onClick={() => {
                              setEditingId(product.id);
                              setEditForm({ name: product.name, price: String(product.price), description: product.description || '', stock: currentStock, image: product.image || '' });
                            }}>Edit</button>
                            <button className="button danger small" onClick={async () => {
                              if (!window.confirm(`Delete "${product.name}"?`)) return;
                              await onDelete(product.id);
                            }}>Delete</button>
                          </div>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={6} style={{ background: '#f8fafc', padding: 12 }}>
                            <strong>Inventory transactions</strong>
                            {productTxs.length === 0 ? <p className="muted">No transactions yet.</p> : (
                              <table className="compactTable">
                                <thead><tr><th>Time</th><th>Change</th><th>Qty</th><th>Note</th></tr></thead>
                                <tbody>
                                  {productTxs.map((tx) => (
                                    <tr key={tx.transaction_id}>
                                      <td>{tx.created_at ? new Date(tx.created_at).toLocaleString() : '-'}</td>
                                      <td><span className={`pill ${tx.change_type?.includes('REFUND') ? 'warning' : ''}`}>{tx.change_type || '-'}</span></td>
                                      <td>{tx.quantity_change ?? '-'}</td>
                                      <td>{tx.related_order_id ? `Order #${tx.related_order_id}` : tx.related_refund_id ? `Refund #${tx.related_refund_id}` : '-'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <>
          <div className="toolbar">
            <a href="#/shops" className="button">&larr; Back to shops</a>
            <div className="toolbarRight">
              <select className="sortSelect" value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="recommended">Recommended</option>
                <option value="price-desc">Price: High to Low</option>
                <option value="price-asc">Price: Low to High</option>
                <option value="sales-desc">Sales: High to Low</option>
                <option value="sales-asc">Sales: Low to High</option>
              </select>
            </div>
          </div>
          {sorted.length === 0 ? (
            <div className="panel emptyState">This shop has no products yet.</div>
          ) : (
            <div className="productGrid">
              {sorted.map((product) => (
                <a className="productCard" href={`#/products/${product.id}`} key={product.id}>
                  <img src={product.image || fallbackProducts[0].image || ''} alt={product.name} />
                  <h3>{product.name}</h3>
                  <p>{product.description || 'No description'}</p>
                  <div className="cardFooter">
                    <strong>{money(product.price)}</strong>
                    <span className={product.stock > 0 ? 'stock' : 'stock low'}>
                      {product.stock > 0 ? `${product.stock} in stock` : 'Out of stock'}
                    </span>
                  </div>
                </a>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function ProfilePage({
  profile,
  isAuthed,
  onSave,
  cartCount,
  pendingOrders,
  orders
}: {
  profile: UserProfile | null;
  isAuthed: boolean;
  onSave: (payload: Partial<UserProfile>) => Promise<void>;
  cartCount: number;
  pendingOrders: PendingOrderDraft[];
  orders: Order[];
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    display_name: profile?.display_name || '',
    email: profile?.email || '',
    phone: profile?.phone || '',
    address: profile?.address || '',
    avatar: profile?.avatar || ''
  });

  useEffect(() => {
    setForm({
      display_name: profile?.display_name || '',
      email: profile?.email || '',
      phone: profile?.phone || '',
      address: profile?.address || '',
      avatar: profile?.avatar || ''
    });
  }, [profile]);

  if (!isAuthed) {
    return (
      <section className="page">
        <div className="panel emptyState">
          Login to view and update your profile.
          <a className="button primary" href="#/auth">Login</a>
        </div>
      </section>
    );
  }

  return (
    <section className="page">
      <div className="profileBanner">
        <div className="profileBannerMain">
          {profile?.avatar ? (
            <img
              className="profileAvatar"
              src={profile.avatar}
              alt=""
            />
          ) : (
            <div className="profileAvatarFallback">
              <User size={32} />
            </div>
          )}
          <div>
            <p className="eyebrow">My ShopEase</p>
            <h2>Hi, {profile?.display_name || profile?.username || 'Customer'}</h2>
            <span className="profileRole">@{profile?.username}</span>
          </div>
        </div>
        <button className="button" onClick={() => setEditing(true)}>
          <Pencil size={16} />
          Edit
        </button>
      </div>

      <div className="statsGrid">
        <Stat icon={ShoppingCart} label="Cart quantity" value={cartCount} />
        <Stat icon={ClipboardList} label="Pending orders" value={pendingOrders.length} />
        <Stat icon={ClipboardList} label="Recent orders" value={orders.length} />
        <Stat icon={User} label="Profile" value={profile?.username || 'Customer'} />
      </div>

      <section className="panel" style={{ marginTop: 18 }}>
        <div className="panelHeader">
          <h2>Recent Orders</h2>
          <a href="#/orders">My orders</a>
        </div>
        <OrderMiniList orders={orders.slice(0, 4)} />
      </section>

      {editing && (
        <div className="modalOverlay" onClick={() => setEditing(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modalHeader">
              <h2>Edit Profile</h2>
              <button className="iconButton" onClick={() => setEditing(false)}>
                <X size={18} />
              </button>
            </div>
            <form
              className="stackForm"
              onSubmit={async (event) => {
                event.preventDefault();
                await onSave(form);
                setEditing(false);
              }}
            >
              <label className="fieldLabel">Avatar URL</label>
              <input
                value={form.avatar}
                onChange={(e) => setForm({ ...form, avatar: e.target.value })}
                placeholder="https://..."
              />
              <div className="formGrid">
                <div>
                  <label className="fieldLabel">Display name</label>
                  <input
                    value={form.display_name}
                    onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                    placeholder="Display name"
                  />
                </div>
                <div>
                  <label className="fieldLabel">Phone</label>
                  <input
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    placeholder="Phone"
                  />
                </div>
              </div>
              <label className="fieldLabel">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="Email"
              />
              <label className="fieldLabel">Shipping address</label>
              <textarea
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder="Shipping address"
              />
              <div className="modalActions">
                <button type="button" className="button" onClick={() => setEditing(false)}>
                  Cancel
                </button>
                <button type="submit" className="button primary">
                  Save profile
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

function AuthPage({
  onLogin,
  onRegister
}: {
  onLogin: (username: string, password: string) => Promise<void>;
  onRegister: (payload: {
    username: string;
    display_name?: string;
    email: string;
    phone?: string;
    address?: string;
    company_name?: string;
    store_name?: string;
    role?: string;
    password: string;
    password2: string;
  }) => Promise<void>;
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [form, setForm] = useState({
    username: '',
    display_name: '',
    email: '',
    phone: '',
    address: '',
    company_name: '',
    store_name: '',
    role: 'customer',
    password: '',
    password2: ''
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  return (
    <section className="page authPage">
      <div className="panel narrow">
        <div className="segmented">
          <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Login</button>
          <button className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>Register</button>
        </div>
        <form
          className="stackForm"
          onSubmit={async (event) => {
            event.preventDefault();
            setFormError('');
            setSaving(true);
            try {
              if (mode === 'login') await onLogin(form.username, form.password);
              else await onRegister(form);
            } catch (error) {
              setFormError(error instanceof Error ? error.message : 'Authentication failed. Please check your input.');
            } finally {
              setSaving(false);
            }
          }}
        >
          <input required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="Username" />
          {mode === 'register' && (
            <>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="customer">Customer</option>
                <option value="seller">Seller</option>
              </select>
              <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} placeholder="Display name" />
              <input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email" />
              <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Phone" />
              {form.role === 'customer' ? (
                <input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="Customer address" />
              ) : (
                <>
                  <input value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} placeholder="Company name" />
                  <input value={form.store_name} onChange={(e) => setForm({ ...form, store_name: e.target.value })} placeholder="Store name" />
                </>
              )}
            </>
          )}
          <input required type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Password (uppercase + lowercase + digit)" />
          {mode === 'register' && (
            <input required type="password" value={form.password2} onChange={(e) => setForm({ ...form, password2: e.target.value })} placeholder="Confirm password" />
          )}
          {formError && <p className="formError">{formError}</p>}
          <button className="button primary" disabled={saving}>
            {saving ? 'Working...' : mode === 'login' ? 'Login' : 'Create account'}
          </button>
        </form>
        <p className="muted">Role-specific fields are shown for the demo schema. The current backend creates a base user; Seller/Customer profile tables can be wired when those endpoints are added.</p>
      </div>
    </section>
  );
}

function SellerGate({ isAuthed, roleMode, children }: { isAuthed: boolean; roleMode: RoleMode; children: ReactNode }) {
  if (isAuthed && roleMode === 'seller') return <>{children}</>;
  return (
    <section className="page" style={{ position: 'relative', overflow: 'hidden' }}>
      <div style={{ filter: 'blur(6px)', pointerEvents: 'none', opacity: 0.25 }}>
        <div className="statsGrid" style={{ marginBottom: 16 }}>
          <div className="statCard"><strong>—</strong><span>Stores</span></div>
          <div className="statCard"><strong>—</strong><span>Products</span></div>
          <div className="statCard"><strong>—</strong><span>Orders</span></div>
          <div className="statCard"><strong>—</strong><span>Low stock</span></div>
        </div>
        <div className="panel"><div className="panelHeader"><h2>Quick actions</h2></div><div className="shortcutGrid"><span>Products & inventory</span><span>Orders</span><span>Refunds</span><span>Store settings</span></div></div>
      </div>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="panel" style={{ textAlign: 'center', maxWidth: 400, boxShadow: '0 4px 24px rgba(0,0,0,0.12)' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🔒</div>
          <h2 style={{ marginBottom: 8 }}>Login required</h2>
          <p style={{ color: '#64748b', marginBottom: 16 }}>Log in with a seller account to manage your stores and orders.</p>
          <a className="button primary" href="#/auth" style={{ display: 'inline-block' }}>Login</a>
        </div>
      </div>
    </section>
  );
}

function AdminGate({ isAuthed, roleMode, active, children }: { isAuthed: boolean; roleMode: RoleMode; active: Route; children: ReactNode }) {
  if (isAuthed && roleMode === 'admin') return <>{children}</>;
  if (!active.startsWith('admin-') && active !== 'database') return <>{children}</>;
  return (
    <section className="page" style={{ position: 'relative', overflow: 'hidden' }}>
      <div style={{ filter: 'blur(6px)', pointerEvents: 'none', opacity: 0.25 }}>
        <div className="statsGrid" style={{ marginBottom: 16 }}>
          <div className="statCard"><strong>—</strong><span>Users</span></div>
          <div className="statCard"><strong>—</strong><span>Stores</span></div>
          <div className="statCard"><strong>—</strong><span>Products</span></div>
          <div className="statCard"><strong>—</strong><span>Orders</span></div>
        </div>
        <div className="panel"><div className="panelHeader"><h2>Admin tools</h2></div><div className="shortcutGrid"><span>User management</span><span>Store moderation</span><span>Review moderation</span><span>Audit logs</span></div></div>
      </div>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="panel" style={{ textAlign: 'center', maxWidth: 400, boxShadow: '0 4px 24px rgba(0,0,0,0.12)' }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🔒</div>
          <h2 style={{ marginBottom: 8 }}>Admin login required</h2>
          <p style={{ color: '#64748b', marginBottom: 16 }}>Admin permission is required to access this page.</p>
          <a className="button primary" href="#/auth" style={{ display: 'inline-block' }}>Login</a>
        </div>
      </div>
    </section>
  );
}

function SellerDashboard({
  products,
  orders,
  lowStock,
  shops
}: {
  products: Product[];
  orders: Order[];
  lowStock: Product[];
  shops: { id: number | null; name: string; products: Product[] }[];
}) {
  const revenue = orders.reduce((sum, order) => sum + Number(order.total_amount), 0);
  const productCount = products.length;
  const pendingRefundCount = orders.filter((o) => o.pending_refund_id).length;

  return (
    <section className="page">
      <div className="statsGrid">
        <Stat icon={Store} label="Stores" value={shops.length} />
        <Stat icon={Boxes} label="Products" value={productCount} />
        <Stat icon={ClipboardList} label="Orders" value={orders.length} />
        <Stat icon={AlertTriangle} label="Low stock" value={lowStock.length} tone={lowStock.length ? 'warn' : 'ok'} />
      </div>

      <section className="panel">
        <div className="panelHeader"><h2>Quick actions</h2></div>
        <div className="shortcutGrid">
          <a href="#/seller-products">Products & inventory</a>
          <a href="#/seller-orders">Orders ({orders.length})</a>
          <a href="#/seller-refunds">Refunds ({pendingRefundCount})</a>
          <a href="#/seller-store">Store settings</a>
        </div>
        <div style={{ marginTop: 16 }}>
          <div className="summaryTotal">
            <span>Total revenue</span>
            <strong>{money(revenue)}</strong>
          </div>
        </div>
        {lowStock.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <strong>Low stock alert</strong>
            {lowStock.slice(0, 5).map((p) => (
              <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                <span>{p.name}</span>
                <span className="stock low">{p.stock}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panelHeader"><h2>Shops</h2><a href="#/seller-store">Manage</a></div>
        <div className="shopGrid">
          {shops.map((shop) => {
            const shopProducts = products.filter((p) => p.shop === shop.id);
            const shopOrders = orders.filter((o) => o.items.some((i) => i.shop_id === shop.id));
            const shopRevenue = shopOrders.reduce((sum, o) => sum + Number(o.total_amount), 0);
            const status = 'approved';
            return (
              <article
                className="shopCard shopCardClickable"
                key={shop.name}
                onClick={() => { if (shop.id) window.location.hash = `#/shop-detail/${shop.id}`; }}
              >
                <div className="shopIcon"><Store size={22} /></div>
                <h3>{shop.name}</h3>
                <StatusPill status={status} />
                <div className="coverage">
                  <div><strong>{shopProducts.length}</strong><span>Products</span></div>
                  <div><strong>{shopOrders.length}</strong><span>Orders</span></div>
                  <div><strong>{money(shopRevenue)}</strong><span>Revenue</span></div>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </section>
  );
}

function SellerStoresPage({
  shops,
  onSave,
  onCreate,
  onRefresh
}: {
  shops: { id: number | null; name: string; products: Product[] }[];
  onSave: (shopId: number | null, name: string) => void;
  onCreate: (name: string, description: string) => Promise<void>;
  onRefresh: () => void;
}) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [storeName, setStoreName] = useState('');
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [saving, setSaving] = useState(false);

  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <h2>Seller Store Management</h2>
          <div className="buttonRow">
            <button className="button quiet" onClick={onRefresh}>Refresh</button>
            <button className="button primary" onClick={() => setCreating(true)}>New store</button>
          </div>
        </div>

        {creating && (
          <div className="panel" style={{ marginBottom: 16, background: '#f8fafc' }}>
            <h3>Create new store</h3>
            <div className="stackForm">
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Store name" />
              <textarea value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Store description (optional)" />
              <div className="buttonRow">
                <button className="button primary" disabled={!newName.trim() || saving} onClick={async () => {
                  setSaving(true);
                  try { await onCreate(newName.trim(), newDesc.trim()); setCreating(false); setNewName(''); setNewDesc(''); }
                  finally { setSaving(false); }
                }}>{saving ? 'Creating...' : 'Create'}</button>
                <button className="button quiet" onClick={() => { setCreating(false); setNewName(''); setNewDesc(''); }}>Cancel</button>
              </div>
            </div>
          </div>
        )}

        <div className="shopGrid">
          {shops.map((shop) => (
            <article
              className="shopCard shopCardClickable"
              key={shop.name}
              onClick={() => {
                if (editingId !== shop.id && shop.id) window.location.hash = `#/shop-detail/${shop.id}`;
              }}
            >
              <div className="shopIcon"><Store size={22} /></div>
              {editingId === shop.id ? (
                <input value={storeName} onChange={(event) => setStoreName(event.target.value)} aria-label="Store name" onClick={(e) => e.stopPropagation()} />
              ) : (
                <h3>{shop.name}</h3>
              )}
              <p>Seller: {getShopSellerName(shop)}</p>
              <p>Status: <StatusPill status="approved" /></p>
              <p>Products: {shop.products.length}</p>
              {editingId === shop.id ? (
                <div className="buttonRow" onClick={(e) => e.stopPropagation()}>
                  <button className="button primary" onClick={() => { onSave(shop.id, storeName); setEditingId(null); }}>Save</button>
                  <button className="button quiet" onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              ) : (
                <button className="button quiet" onClick={(e) => { e.stopPropagation(); setEditingId(shop.id); setStoreName(shop.name); }}>Edit store</button>
              )}
            </article>
          ))}
          {shops.length === 0 && <div className="emptyState">No stores yet. Create your first store above.</div>}
        </div>
      </div>
    </section>
  );
}

function SellerProductsPage({
  products,
  shops,
  categories,
  transactions,
  getStatus,
  onUpdate,
  onDelete,
  onRefresh
}: {
  products: Product[];
  shops: { id: number | null; name: string; products: Product[] }[];
  categories: Category[];
  transactions: InventoryTransaction[];
  getStatus: (product: Product) => string;
  onUpdate: (id: number, payload: Partial<Product>) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onRefresh: () => void;
}) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<{ name: string; price: string; description: string; stock: number; image: string }>({ name: '', price: '', description: '', stock: 0, image: '' });
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [stockEdits, setStockEdits] = useState<Record<number, number>>({});
  const [saving, setSaving] = useState(false);
  const [selectedShop, setSelectedShop] = useState<string>('all');

  const shopNames = shops.map((s) => s.name).filter(Boolean);
  const filteredProducts = selectedShop === 'all'
    ? products
    : products.filter((p) => p.shop_name === selectedShop);

  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <h2>Products & Inventory</h2>
          <div className="buttonRow">
            {shopNames.length > 0 && (
              <select value={selectedShop} onChange={(e) => setSelectedShop(e.target.value)}>
                <option value="all">All shops ({products.length})</option>
                {shopNames.map((name) => {
                  const count = products.filter((p) => p.shop_name === name).length;
                  return <option key={name} value={name}>{name} ({count})</option>;
                })}
              </select>
            )}
            <button className="button quiet" onClick={onRefresh}>Refresh</button>
            <a className="button primary" href="#/inventory">Add product</a>
          </div>
        </div>

        {editingId && (
          <div className="panel" style={{ marginBottom: 16, background: '#f8fafc' }}>
            <h3>Edit Product #{editingId}</h3>
            <div className="stackForm">
              <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="Product name" />
              <input value={editForm.price} onChange={(e) => setEditForm({ ...editForm, price: e.target.value })} placeholder="Price" type="number" min="0" step="0.01" />
              <textarea value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} placeholder="Description" />
              <input value={editForm.stock} onChange={(e) => setEditForm({ ...editForm, stock: Number(e.target.value) })} placeholder="Stock" type="number" min="0" />
              <input value={editForm.image} onChange={(e) => setEditForm({ ...editForm, image: e.target.value })} placeholder="Image URL (optional)" />
              <div className="buttonRow">
                <button className="button primary" disabled={!editForm.name.trim() || saving} onClick={async () => {
                  setSaving(true);
                  try { await onUpdate(editingId, { name: editForm.name.trim(), price: editForm.price, description: editForm.description.trim(), stock: editForm.stock, image: editForm.image.trim() || undefined }); setEditingId(null); }
                  finally { setSaving(false); }
                }}>{saving ? 'Saving...' : 'Save'}</button>
                <button className="button quiet" onClick={() => setEditingId(null)}>Cancel</button>
              </div>
            </div>
          </div>
        )}

        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Store</th>
                <th>Price</th>
                <th>Stock</th>
                <th>Sold</th>
                <th>Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredProducts.map((product) => {
                const isExpanded = expandedId === product.id;
                const productTxs = transactions.filter((t) => t.product_id === product.id).slice(0, 10);
                const currentStock = stockEdits[product.id] ?? product.stock;
                return (
                  <Fragment key={product.id}>
                    <tr>
                      <td>
                        <a href={`#/products/${product.id}`} style={{ color: '#1e293b', textDecoration: 'none' }}>{product.name}</a>
                        {product.category_name && <small className="muted" style={{ display: 'block' }}>{product.category_name}</small>}
                      </td>
                      <td>{product.shop_name || '-'}</td>
                      <td>{money(product.price)}</td>
                      <td>
                        <span className={currentStock <= 10 ? 'stock low' : 'stock'} style={{ marginRight: 4 }}>{currentStock}</span>
                        <button className="button quiet small" onClick={async () => { const s = currentStock + 1; setStockEdits({ ...stockEdits, [product.id]: s }); await onUpdate(product.id, { stock: s }); }}>+</button>
                        <button className="button quiet small" disabled={currentStock <= 0} onClick={async () => { const s = Math.max(0, currentStock - 1); setStockEdits({ ...stockEdits, [product.id]: s }); await onUpdate(product.id, { stock: s }); }}>-</button>
                      </td>
                      <td>{product.sold_count || 0}</td>
                      <td>
                        <button
                          className={`button small ${product.is_active !== false ? 'primary' : 'quiet'}`}
                          onClick={async () => { try { await onUpdate(product.id, { is_active: product.is_active === false }); } catch { /* fallback handled by parent */ } }}
                        >
                          {product.is_active !== false ? 'On shelf' : 'Off shelf'}
                        </button>
                      </td>
                      <td>
                        <div className="buttonRow tableActions">
                          <button className="button quiet small" onClick={() => setExpandedId(isExpanded ? null : product.id)}>{isExpanded ? 'Hide log' : 'Log'}</button>
                          <button className="button quiet small" onClick={() => {
                            setEditingId(product.id);
                            setEditForm({ name: product.name, price: String(product.price), description: product.description || '', stock: currentStock, image: product.image || '' });
                          }}>Edit</button>
                          <button className="button danger small" onClick={async () => {
                            if (!window.confirm(`Delete "${product.name}"?`)) return;
                            await onDelete(product.id);
                          }}>Delete</button>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={7} style={{ background: '#f8fafc', padding: 12 }}>
                          <strong>Inventory log for {product.name}</strong>
                          {productTxs.length === 0 ? (
                            <p className="muted">No transactions yet.</p>
                          ) : (
                            <table style={{ marginTop: 8, fontSize: 13 }}>
                              <thead>
                                <tr><th>Date</th><th>Change type</th><th>Qty change</th><th>Related order</th></tr>
                              </thead>
                              <tbody>
                                {productTxs.map((tx) => (
                                  <tr key={tx.transaction_id}>
                                    <td>{new Date(tx.created_at).toLocaleString()}</td>
                                    <td><code>{tx.change_type}</code></td>
                                    <td className={tx.quantity_change < 0 ? 'negativeNumber' : 'positiveNumber'}>{tx.quantity_change > 0 ? '+' : ''}{tx.quantity_change}</td>
                                    <td>{tx.related_order_id ? `#${tx.related_order_id}` : '-'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function SellerOrdersPage({ orders, shops, onStatusChange }: { orders: Order[]; shops: { id: number | null; name: string; products: Product[] }[]; onStatusChange: (orderId: number, status: string) => Promise<void> }) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [changingId, setChangingId] = useState<number | null>(null);
  const [selectedShop, setSelectedShop] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const shopNames = shops.map((s) => s.name).filter(Boolean);
  const statusLabels: Record<string, string> = { paid: 'Paid', shipped: 'Shipped', completed: 'Completed', cancelled: 'Cancelled', refunded: 'Refunded' };
  const filteredOrders = (selectedShop === 'all' ? orders : orders.filter((o) => o.items.some((i) => i.shop_name === selectedShop)))
    .filter((o) => statusFilter === 'all' || o.status === statusFilter);

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    const base = selectedShop === 'all' ? orders : orders.filter((o) => o.items.some((i) => i.shop_name === selectedShop));
    base.forEach((o) => { counts[o.status] = (counts[o.status] || 0) + 1; });
    return counts;
  }, [orders, selectedShop]);

  const shopCounts = useMemo(() => {
    const counts: Record<string, number> = { all: orders.length };
    shopNames.forEach((name) => { counts[name] = orders.filter((o) => o.items.some((i) => i.shop_name === name)).length; });
    return counts;
  }, [orders, shopNames]);

  if (orders.length === 0) return (
    <section className="page"><div className="panel emptyState">No orders yet for your store.</div></section>
  );

  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <h2>Orders</h2>
          <span className="resultCount">{filteredOrders.length} orders</span>
        </div>
        <div className="categoryRow">
          {shopNames.length > 0 && (
            <>
              <button
                className={selectedShop === 'all' ? 'categoryChip active' : 'categoryChip'}
                onClick={() => setSelectedShop('all')}
              >
                All shops ({shopCounts.all})
              </button>
              {shopNames.map((name) => (
                <button
                  key={name}
                  className={selectedShop === name ? 'categoryChip active' : 'categoryChip'}
                  onClick={() => setSelectedShop(name)}
                >
                  {name} ({shopCounts[name] || 0})
                </button>
              ))}
            </>
          )}
        </div>
        <div className="categoryRow" style={{ paddingTop: 0 }}>
          <button
            className={statusFilter === 'all' ? 'categoryChip active' : 'categoryChip'}
            onClick={() => setStatusFilter('all')}
          >
            All ({orders.filter((o) => selectedShop === 'all' || o.items.some((i) => i.shop_name === selectedShop)).length})
          </button>
          {Object.entries(statusCounts).map(([key, count]) => (
            <button
              key={key}
              className={statusFilter === key ? 'categoryChip active' : 'categoryChip'}
              onClick={() => setStatusFilter(key)}
            >
              {statusLabels[key] || key} ({count})
            </button>
          ))}
        </div>
        {filteredOrders.length === 0 ? (
          <div className="emptyState">No orders match the current filter.</div>
        ) : (
          <div className="miniOrderList">
            {filteredOrders.map((order) => {
              const canShip = order.status === 'paid';
              const isExpanded = expandedId === order.id;
              return (
                <div className="miniOrderRow" key={order.id} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }} onClick={() => setExpandedId(isExpanded ? null : order.id)}>
                    <div className="miniOrderImages">
                      {(order.items || []).slice(0, 3).map((item) => (
                        <img key={item.id} src={item.product_image || ''} alt={item.product_name} onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                      ))}
                    </div>
                    <div className="miniOrderInfo" style={{ flex: 1 }}>
                      <strong>{displayOrderNo(order)}</strong>
                      <span>{displayOrderCustomer(order)} · {order.items?.[0]?.shop_name || '-'}</span>
                    </div>
                    <StatusPill status={order.status} />
                    {canShip && (
                      <button className="button primary small" disabled={changingId === order.id} onClick={async (e) => {
                        e.stopPropagation();
                        if (!window.confirm('Confirm shipment? Inventory status will be updated.')) return;
                        setChangingId(order.id);
                        try { await onStatusChange(order.id, 'shipped'); } finally { setChangingId(null); }
                      }}>{changingId === order.id ? '...' : 'Confirm shipment'}</button>
                    )}
                    <span style={{ fontSize: 12, color: '#94a3b8' }}>{isExpanded ? '▲' : '▼'}</span>
                  </div>
                  {isExpanded && (
                    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #e2e8f0' }}>
                      <div style={{ marginBottom: 8 }}>
                        {(order.items || []).map((item) => (
                          <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                            <span>{item.product_name} x {item.quantity}</span>
                            <strong>{money(item.total_price)}</strong>
                          </div>
                        ))}
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        <span>Receiver: {order.receiver_name} / {order.receiver_phone}</span><br />
                        <span>Address: {order.address}</span>
                        {order.remark && <><br /><span>Remark: {order.remark}</span></>}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong>Total: {money(order.total_amount)}</strong>
                        <div className="buttonRow">
                          {order.pending_refund_id && <a className="button quiet" href="#/seller-refunds">View refund</a>}
                          {canShip && (
                            <button className="button primary" disabled={changingId === order.id} onClick={async () => {
                              if (!window.confirm('Confirm shipment? Inventory status will be updated.')) return;
                              setChangingId(order.id);
                              try { await onStatusChange(order.id, 'shipped'); } finally { setChangingId(null); }
                            }}>{changingId === order.id ? '...' : 'Confirm shipment'}</button>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

function SellerRefundsPage({ orders, onProcessRefund }: { orders: Order[]; onProcessRefund: (refundId: number, status: string, remark?: string) => Promise<void> }) {
  const refundOrders = orders.filter((o) => o.pending_refund_id);
  const [processingId, setProcessingId] = useState<number | null>(null);

  if (refundOrders.length === 0) return (
    <section className="page">
      <div className="panel emptyState">No pending refund requests.</div>
    </section>
  );

  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <h2>Refund Requests</h2>
          <span className="pill warning">{refundOrders.length} pending</span>
        </div>
        <div className="miniOrderList">
          {refundOrders.map((order) => (
            <div className="miniOrderRow" key={order.id} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div className="miniOrderInfo" style={{ flex: 1 }}>
                  <strong>{displayOrderNo(order)}</strong>
                  <span>{displayOrderCustomer(order)}</span>
                </div>
                <span className="pill warning">Refund pending</span>
              </div>
              <div style={{ marginTop: 8 }}>
                {(order.items || []).map((item) => (
                  <div key={item.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                    <span>{item.product_name} x {item.quantity}</span>
                    <span>{money(item.total_price)}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, paddingTop: 8, borderTop: '1px solid #e2e8f0' }}>
                  <strong>Total: {money(order.total_amount)}</strong>
                  <div className="buttonRow">
                    <button className="button primary" disabled={processingId === order.pending_refund_id} onClick={async () => {
                      if (!order.pending_refund_id) return;
                      setProcessingId(order.pending_refund_id);
                      try { await onProcessRefund(order.pending_refund_id, 'approved', 'Seller approved refund'); } finally { setProcessingId(null); }
                    }}>Approve</button>
                    <button className="button danger" disabled={processingId === order.pending_refund_id} onClick={async () => {
                      if (!order.pending_refund_id) return;
                      setProcessingId(order.pending_refund_id);
                      try { await onProcessRefund(order.pending_refund_id, 'rejected', 'Seller rejected refund'); } finally { setProcessingId(null); }
                    }}>Reject</button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}


function AdminDashboard({
  products,
  orders,
  shops,
  auditLogs,
  categories,
  users
}: {
  products: Product[];
  orders: Order[];
  shops: { id: number | null; name: string; products: Product[] }[];
  auditLogs: AuditLog[];
  categories: Category[];
  users: LocalAccount[];
}) {
  const revenue = orders.reduce((sum, order) => sum + Number(order.total_amount), 0);
  const sellerCount = users.filter((user) => user.role === 'seller').length;
  const [dbStats, setDbStats] = useState<{
    total_users: number; total_sellers: number; total_shops: number;
    total_products: number; total_orders: number; total_revenue: number;
    total_reviews: number; refund_rate: number; low_stock: number;
    top_products: { name: string; sold: number }[];
    monthly_revenue: { month: string; revenue: number }[];
  } | null>(null);

  useEffect(() => {
    api.adminStats().then(setDbStats).catch(() => {});
  }, []);

  return (
    <section className="page">
      <div className="statsGrid">
        <Stat icon={User} label="Users (local)" value={users.length} />
        <Stat icon={User} label="Sellers" value={sellerCount} />
        <Stat icon={Store} label="Stores" value={shops.length} />
        <Stat icon={Boxes} label="Products" value={products.length} />
      </div>
      {dbStats && (
        <div className="statsGrid" style={{ marginTop: 12 }}>
          <Stat icon={Database} label="DB Users" value={dbStats.total_users} />
          <Stat icon={Database} label="DB Sellers" value={dbStats.total_sellers} />
          <Stat icon={Database} label="DB Products" value={dbStats.total_products} />
          <Stat icon={Database} label="DB Orders" value={dbStats.total_orders} />
          <Stat icon={Database} label="DB Revenue" value={money(dbStats.total_revenue)} />
        </div>
      )}
      <div className="twoColumn">
        <section className="panel">
          <h2>Platform Summary</h2>
          <div className="coverage">
            <div><strong>Total revenue</strong><span>{money(revenue)}</span></div>
            <div><strong>Categories</strong><span>{categories.length} top-level groups</span></div>
            <div><strong>Database stats</strong><span>{dbStats ? `${dbStats.total_orders} orders, ${dbStats.low_stock} low-stock products` : 'Loading...'}</span></div>
          </div>
          <div className="shortcutGrid adminShortcutGrid">
            <a href="#/admin-stores">Store approval</a>
            <a href="#/admin-products">Product review</a>
            <a href="#/admin-categories">Category management</a>
            <a href="#/admin-reviews">Review moderation</a>
            <a href="#/admin-statistics">Platform statistics</a>
          </div>
        </section>
        <section className="panel">
          <div className="panelHeader">
            <h2>Audit Logs</h2>
            <a href="#/admin-audit-logs">View all</a>
          </div>
          <p className="muted" style={{ padding: '12px 0' }}>All operations are logged to the database audit_logs table. Click "View all" to inspect.</p>
        </section>
      </div>
      {dbStats && dbStats.top_products.length > 0 && (
        <section className="panel" style={{ marginTop: 16 }}>
          <h2>Top Selling Products (from DB)</h2>
          <div className="tableWrap">
            <table>
              <thead><tr><th>Product</th><th>Units Sold</th></tr></thead>
              <tbody>
                {dbStats.top_products.map((p, i) => (
                  <tr key={i}><td>{p.name}</td><td>{p.sold}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  );
}

function AdminUsersPage({
  users,
  onStatusChange,
  shops,
  orders
}: {
  users: LocalAccount[];
  onStatusChange: (username: string) => void;
  shops: { id: number | null; name: string; products: Product[] }[];
  orders: Order[];
}) {
  const [query, setQuery] = useState('');
  const [disabledUsers, setDisabledUsers] = useState<Record<string, boolean>>({});
  const [selectedUsername, setSelectedUsername] = useState(users[0]?.username || '');
  const filtered = users.filter((user) =>
    [user.username, user.email, user.role, user.display_name, user.company_name]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(query.toLowerCase())
  );
  const selected = users.find((user) => user.username === selectedUsername) || filtered[0] || users[0];
  const userOrders = selected ? orders.filter((order) => order.username === selected.username || order.receiver_name === selected.display_name) : [];
  const userShops = selected?.role === 'seller' ? shops.filter((shop) => shop.id && selected.shopIds?.includes(shop.id)) : [];
  return (
    <section className="page">
      <div className="twoColumn wideLeft">
        <div className="panel">
          <div className="panelHeader">
            <h2>Admin User Management</h2>
            <div className="searchBox"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search username, email, role" /></div>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Details</th>
                  <th>Operations</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((user) => {
                  const isDisabled = disabledUsers[user.username] || false;
                  const status = isDisabled ? 'disabled' : 'active';
                  return (
                    <tr key={user.username}>
                      <td>{user.username}</td>
                      <td>{user.email}</td>
                      <td>{user.role}</td>
                      <td><StatusPill status={status} /></td>
                      <td>
                        <button className="button quiet small" onClick={() => setSelectedUsername(user.username)}>
                          View details
                        </button>
                      </td>
                      <td>
                        <button
                          className={isDisabled ? 'button quiet small' : 'button danger small'}
                          onClick={() => {
                            setDisabledUsers(prev => ({ ...prev, [user.username]: !isDisabled }));
                            onStatusChange(user.username);
                          }}
                        >
                          {isDisabled ? 'Enable user' : 'Disable user'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <aside className="panel">
          <h2>User Details</h2>
          {selected ? (
            <div className="coverage">
              <div><strong>Username</strong><span>{selected.username}</span></div>
              <div><strong>Display name</strong><span>{selected.display_name}</span></div>
              <div><strong>Email</strong><span>{selected.email}</span></div>
              <div><strong>Role</strong><span>{selected.role}</span></div>
              <div><strong>Status</strong><span>{disabledUsers[selected.username] ? 'disabled' : 'active'}</span></div>
              <div><strong>Phone</strong><span>{selected.phone || '-'}</span></div>
              <div><strong>Address</strong><span>{selected.address || '-'}</span></div>
              {selected.role === 'seller' && <div><strong>Company</strong><span>{selected.company_name || '-'}</span></div>}
              {selected.role === 'seller' && <div><strong>Stores</strong><span>{userShops.map((shop) => shop.name).join(', ') || '-'}</span></div>}
              {selected.role === 'customer' && <div><strong>Orders</strong><span>{userOrders.length} order(s)</span></div>}
            </div>
          ) : (
            <div className="emptyState">Select a user to inspect profile and business details.</div>
          )}
        </aside>
      </div>
    </section>
  );
}

function AdminStoresPage({
  shopGroups,
  shops,
  onStatusChange
}: {
  shopGroups: { id: number | null; name: string; products: Product[] }[];
  shops: Shop[];
  onStatusChange: (shopId: number | null, status: string) => void;
}) {
  const getStatus = (shopId: number | null): string => {
    if (!shopId) return 'disabled';
    const shop = shops.find(s => s.shop_id === shopId);
    return shop?.status || 'approved';
  };
  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <div>
            <h2>Store / Seller Approval</h2>
            <p className="muted">Approve seller store applications, disable violating stores, and restore disabled stores.</p>
          </div>
          <span className="pill">{shopGroups.length} stores</span>
        </div>
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Store</th>
                <th>Seller</th>
                <th>Status</th>
                <th>Products</th>
                <th>Sales status</th>
                <th>Operations</th>
              </tr>
            </thead>
            <tbody>
              {shopGroups.map((shop) => {
                const status = getStatus(shop.id);
                const revenue = shop.products.reduce((sum, product) => sum + Number(product.price) * (product.sold_count || 0), 0);
                return (
                  <tr key={shop.name}>
                    <td>{shop.name}</td>
                    <td>{getShopSellerName(shop)}</td>
                    <td><StatusPill status={status} /></td>
                    <td>{shop.products.length}</td>
                    <td>{money(revenue)} sales</td>
                    <td>
                      <div className="buttonRow tableActions">
                        <button className="button quiet small" onClick={() => onStatusChange(shop.id, 'approved')}>Approve</button>
                        <button className="button danger small" onClick={() => onStatusChange(shop.id, 'disabled')}>Disable</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function AdminProductsPage({
  products,
  categories,
  onStatusChange
}: {
  products: Product[];
  categories: Category[];
  onStatusChange: (productId: number, status: string) => void;
}) {
  const [filter, setFilter] = useState('');
  const getStatus = (product: Product): string => {
    return product.is_active === false ? 'off_shelf' : 'approved';
  };
  const filtered = products.filter((product) => !filter || getStatus(product) === filter);
  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <div>
            <h2>Product Review and Off-shelf Control</h2>
            <p className="muted">Review new products, remove violating items, and flag reported products for later inspection.</p>
          </div>
          <div className="buttonRow">
            <span className="pill">{categories.length} categories</span>
            <select value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="">All statuses</option>
              <option value="approved">approved</option>
              <option value="off_shelf">off_shelf</option>
            </select>
          </div>
        </div>
        <ProductAdminTable products={filtered} getStatus={getStatus} onStatusChange={onStatusChange} />
      </div>
    </section>
  );
}

function AdminCategoriesPage({
  categories,
  products,
  onCreate,
  onUpdate,
  onStatusChange,
  onDelete
}: {
  categories: Category[];
  products: Product[];
  onCreate: (payload: { name: string; slug: string; parent?: number | null }) => Promise<void>;
  onUpdate: (categoryId: number, payload: { name: string; parent?: number | null }) => void;
  onStatusChange: (categoryId: number, status: string) => void;
  onDelete: (categoryId: number) => void;
}) {
  const topLevel = categories.filter(c => !c.parent);
  const flat = flattenCategories(categories);
  const [name, setName] = useState('');
  const [parent, setParent] = useState('');
  const [editing, setEditing] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editParent, setEditParent] = useState('');
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const slug = name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  const productCount = (categoryId: number) => products.filter(p => p.category === categoryId).length;

  const toggleCollapse = (id: number) => {
    setCollapsed(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const renderRow = (cat: Category, depth: number) => {
    const isActive = cat.is_active !== false;
    const status = isActive ? 'active' : 'disabled';
    const isEditing = editing === cat.id;
    const children = cat.children || [];
    const hasChildren = children.length > 0;
    const isCollapsed = collapsed.has(cat.id);
    const parentName = flat.find(r => r.id === cat.parent)?.name;

    return (
      <Fragment key={cat.id}>
        <tr style={depth > 0 ? { background: '#f8f9fa' } : { borderTop: '2px solid #e9ecef' }}>
          <td style={{ paddingLeft: 16 + depth * 24 }}>
            {depth > 0 && <span style={{ color: '#adb5bd', marginRight: 6, fontSize: 12 }}>└─</span>}
            {depth === 0 && hasChildren && (
              <span
                onClick={() => toggleCollapse(cat.id)}
                style={{ cursor: 'pointer', marginRight: 6, fontSize: 12, userSelect: 'none' }}
              >
                {isCollapsed ? <ChevronDown size={14} style={{ display: 'inline', verticalAlign: -2 }} /> : <ChevronUp size={14} style={{ display: 'inline', verticalAlign: -2 }} />}
              </span>
            )}
            {depth === 0 && !hasChildren && <span style={{ marginRight: 20, display: 'inline-block' }} />}
            {isEditing ? (
              <input value={editName} onChange={e => setEditName(e.target.value)} style={{ width: 150 }} />
            ) : (
              <span style={depth === 0 ? { fontWeight: 700, fontSize: 15 } : { fontSize: 14 }}>
                {cat.name}
                {depth === 0 && hasChildren && (
                  <span style={{ fontWeight: 400, color: '#6c757d', fontSize: 12, marginLeft: 8 }}>
                    ({children.length} sub)
                  </span>
                )}
              </span>
            )}
          </td>
          <td style={depth > 0 ? { color: '#6c757d', fontSize: 13 } : { fontSize: 14 }}>
            {isEditing ? (
              <select value={editParent} onChange={e => setEditParent(e.target.value)}>
                <option value="">Top-level</option>
                {topLevel.filter(r => r.id !== cat.id).map(r => (
                  <option value={r.id} key={r.id}>{r.name}</option>
                ))}
              </select>
            ) : depth > 0 ? parentName : <span style={{ color: '#adb5bd' }}>—</span>}
          </td>
          <td><StatusPill status={status} /></td>
          <td>
            {depth === 0
              ? countWithChildren(products, cat)
              : productCount(cat.id)}
          </td>
          <td>
            <div className="buttonRow tableActions">
              {isEditing ? (
                <>
                  <button className="button primary small" onClick={() => {
                    onUpdate(cat.id, { name: editName, parent: editParent ? Number(editParent) : null });
                    setEditing(null);
                  }}>Save</button>
                  <button className="button quiet small" onClick={() => setEditing(null)}>Cancel</button>
                </>
              ) : (
                <button className="button quiet small" onClick={() => {
                  setEditing(cat.id);
                  setEditName(cat.name);
                  setEditParent(cat.parent ? String(cat.parent) : '');
                }}>Edit</button>
              )}
              <button className="button quiet small" onClick={() => onStatusChange(cat.id, status === 'active' ? 'disabled' : 'active')}>
                {status === 'active' ? 'Disable' : 'Enable'}
              </button>
              <button className="button danger small" onClick={() => onDelete(cat.id)}>Delete</button>
            </div>
          </td>
        </tr>
        {depth === 0 && hasChildren && !isCollapsed && children.map(child => renderRow(child, depth + 1))}
      </Fragment>
    );
  };

  return (
    <section className="page">
      <div className="twoColumn wideLeft">
        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2>Category Management</h2>
              <p className="muted">Two-level hierarchy: top-level categories and their subcategories. Top-level product count includes subcategory products.</p>
            </div>
            <span className="pill">{flat.length} total ({topLevel.length} top-level)</span>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Parent</th>
                  <th>Status</th>
                  <th>Products</th>
                  <th>Operations</th>
                </tr>
              </thead>
              <tbody>
                {topLevel.map(cat => renderRow(cat, 0))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <h2>Create Category</h2>
          <form
            className="stackForm"
            onSubmit={async e => {
              e.preventDefault();
              await onCreate({ name, slug, parent: parent ? Number(parent) : null });
              setName('');
              setParent('');
            }}
          >
            <input required value={name} onChange={e => setName(e.target.value)} placeholder="Category name" />
            <input value={slug} readOnly aria-label="Generated slug" />
            <select value={parent} onChange={e => setParent(e.target.value)}>
              <option value="">Top-level category</option>
              {topLevel.map(cat => (
                <option value={cat.id} key={cat.id}>{cat.name}</option>
              ))}
            </select>
            <button className="button primary" disabled={!slug}>Create category</button>
          </form>
          <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
            Select "Top-level" to create a primary category. Select an existing top-level category to create a subcategory. Third-level is not allowed.
          </p>
        </section>
      </div>
    </section>
  );
}

function countWithChildren(products: Product[], category: Category): number {
  const childIds = (category.children || []).map(c => c.id);
  return products.filter(p => p.category === category.id || childIds.includes(p.category!)).length;
}

function AdminReviewsPage({
  products,
  onStatusChange
}: {
  products: Product[];
  onStatusChange: (reviewId: number, status: string) => void;
}) {
  const [reviews, setReviews] = useState<AdminReview[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('hidden');

  const fetchReviews = () => {
    setLoading(true);
    api.adminGetReviews(statusFilter || undefined)
      .then(setReviews)
      .catch(() => setReviews([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchReviews(); }, [statusFilter]);

  const handleAction = (reviewId: number, newStatus: string) => {
    onStatusChange(reviewId, newStatus);
    setReviews((prev) => prev.filter((r) => r.review_id !== reviewId));
  };

  const statusBadge = (status: string) => {
    const map: Record<string, { label: string; className: string }> = {
      hidden: { label: 'Hidden', className: 'pill' },
      visible: { label: 'Visible', className: 'pill success' },
      deleted: { label: 'Deleted', className: 'pill warning' },
      reported: { label: 'Reported', className: 'pill error' },
    };
    const item = map[status] || { label: status, className: 'pill' };
    return <span className={item.className}>{item.label}</span>;
  };

  const lowRatedProducts = products.filter((product) => (product.average_rating || 5) < 4 || (product.good_rate || 100) < 80);

  return (
    <section className="page">
      <div className="twoColumn wideLeft">
        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2>Review Moderation</h2>
              <p className="muted">Reviews submitted by users require admin approval before becoming visible.</p>
            </div>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="hidden">Pending</option>
              <option value="visible">Approved</option>
              <option value="deleted">Deleted</option>
              <option value="reported">Reported</option>
              <option value="">All</option>
            </select>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Product</th>
                  <th>User</th>
                  <th>Rating</th>
                  <th>Comment</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7} className="emptyState">Loading reviews...</td></tr>
                ) : reviews.length === 0 ? (
                  <tr><td colSpan={7} className="emptyState">No reviews matching this filter.</td></tr>
                ) : reviews.map((r) => (
                  <tr key={r.review_id}>
                    <td>{r.review_id}</td>
                    <td>{r.product_name}</td>
                    <td>{r.username}</td>
                    <td>{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</td>
                    <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.comment}</td>
                    <td>{statusBadge(r.status)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {r.status === 'hidden' && (
                          <button className="button small primary" onClick={() => handleAction(r.review_id, 'visible')}>Approve</button>
                        )}
                        {r.status !== 'deleted' && (
                          <button className="button small quiet" onClick={() => handleAction(r.review_id, 'deleted')}>Delete</button>
                        )}
                        {r.status === 'visible' && (
                          <button className="button small quiet" onClick={() => handleAction(r.review_id, 'hidden')}>Hide</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <h2>Low Rating Products</h2>
          <div className="coverage">
            {lowRatedProducts.length === 0 ? <div><strong>All clear</strong><span>No low-rated products to display.</span></div> : lowRatedProducts.map((product) => (
              <div key={product.id}>
                <strong>{product.name}</strong>
                <span>{(product.average_rating || 0).toFixed(1)} avg / {product.good_rate || 0}% good</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function AdminOrdersPage() {
  const [data, setData] = useState<{
    orders: {
      id: number; order_no: string; username: string;
      total_amount: number; status: string; status_text: string;
      receiver_name: string; receiver_phone: string; address: string;
      items: { product_name: string; price: number; quantity: number }[];
      created_at: string;
    }[];
    stats: { total: number; total_revenue: number; by_status: Record<string, number> };
  } | null>(null);
  const [filter, setFilter] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const fetchOrders = () => {
    setLoading(true);
    api.adminOrders({ status: filter || undefined, search: search || undefined })
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchOrders(); }, [filter]);

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    fetchOrders();
  };

  const statusOptions = [
    { value: '', label: 'All' },
    { value: 'paid', label: 'Paid' },
    { value: 'shipped', label: 'Shipped' },
    { value: 'completed', label: 'Completed' },
    { value: 'cancelled', label: 'Cancelled' },
    { value: 'refunded', label: 'Refunded' },
  ];

  return (
    <section className="page">
      {data && (
        <div className="statsGrid">
          <Stat icon={ClipboardList} label="Total Orders" value={data.stats.total} />
          <Stat icon={BarChart3} label="Total Revenue" value={money(data.stats.total_revenue)} />
          <Stat icon={Package} label="Paid" value={data.stats.by_status.paid || 0} tone="info" />
          <Stat icon={RefreshCcw} label="Shipped" value={data.stats.by_status.shipped || 0} tone="info" />
          <Stat icon={ClipboardList} label="Completed" value={data.stats.by_status.completed || 0} tone="ok" />
          <Stat icon={AlertTriangle} label="Refunded" value={data.stats.by_status.refunded || 0} tone={data.stats.by_status.refunded ? 'warn' : 'ok'} />
        </div>
      )}
      <div className="panel">
        <div className="panelHeader">
          <div>
            <h2>All Platform Orders</h2>
            <p className="muted">Manage orders across all users. Change status, review items, and monitor order flow.</p>
          </div>
          <div className="buttonRow">
            <form onSubmit={handleSearch} className="searchBox" style={{ margin: 0 }}>
              <Search size={16} />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search order no..." />
            </form>
            <select value={filter} onChange={e => setFilter(e.target.value)}>
              {statusOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button className="button quiet" onClick={fetchOrders} disabled={loading}>
              <RefreshCcw size={14} /> {loading ? '...' : 'Refresh'}
            </button>
          </div>
        </div>
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Order No</th>
                <th>User</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Receiver</th>
                <th>Items</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {!data ? (
                <tr><td colSpan={7} className="emptyState">Loading...</td></tr>
              ) : data.orders.length === 0 ? (
                <tr><td colSpan={7} className="emptyState">No orders found.</td></tr>
              ) : data.orders.map(order => (
                <Fragment key={order.id}>
                  <tr>
                    <td><code>{order.order_no}</code></td>
                    <td>{order.username}</td>
                    <td>{money(order.total_amount)}</td>
                    <td><StatusPill status={order.status} /></td>
                    <td>{order.receiver_name}</td>
                    <td>
                      <button className="button quiet small" onClick={() => setExpanded(expanded === order.id ? null : order.id)}>
                        {order.items.length} item(s) {expanded === order.id ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      </button>
                    </td>
                    <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                      {new Date(order.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                  {expanded === order.id && (
                    <tr>
                      <td colSpan={7} style={{ background: '#f8f9fa' }}>
                        <div className="coverage" style={{ padding: 8 }}>
                          <div><strong>Phone</strong><span>{order.receiver_phone}</span></div>
                          <div><strong>Address</strong><span>{order.address}</span></div>
                          {order.items.map((item, i) => (
                            <div key={i}><strong>{item.product_name}</strong><span>{money(item.price)} x {item.quantity} = {money(item.price * item.quantity)}</span></div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

const TABLE_COLORS: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  inventory:  { bg: '#fff8f0', border: '#f0ad4e', text: '#b85c00', icon: '📦' },
  orders:     { bg: '#f0f7ff', border: '#5b9bd5', text: '#1a56a0', icon: '📋' },
  users:      { bg: '#f5f0ff', border: '#8b5cf6', text: '#5b21b6', icon: '👤' },
  shops:      { bg: '#fff0f7', border: '#e85d9a', text: '#9b1d5a', icon: '🏪' },
  products:   { bg: '#f0fff4', border: '#48bb78', text: '#22543d', icon: '📦' },
  reviews:    { bg: '#fffbeb', border: '#f59e0b', text: '#92400e', icon: '⭐' },
  refunds:    { bg: '#fef2f2', border: '#ef4444', text: '#991b1b', icon: '↩️' },
  carts:      { bg: '#f0fdfa', border: '#14b8a6', text: '#115e59', icon: '🛒' },
};

function AdminAuditLogsPage() {
  const [logs, setLogs] = useState<{
    id: number; user_name: string; action: string;
    table_name: string; record_id: string;
    description: string; old_value: string; new_value: string;
    detail: string; created_at: string;
  }[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('');

  const fetchLogs = () => {
    setLoading(true);
    api.adminAuditLogs()
      .then(setLogs)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchLogs(); }, []);

  const filtered = filter ? logs.filter(l => l.table_name === filter) : logs;
  const tableTypes = [...new Set(logs.map(l => l.table_name))];

  return (
    <section className="page">
      <div className="panel">
        <div className="panelHeader">
          <div>
            <h2>Audit Logs</h2>
            <p className="muted">Every key data mutation is recorded here — orders, inventory, refunds, moderation, and more.</p>
          </div>
          <button className="button quiet" onClick={fetchLogs} disabled={loading}>
            <RefreshCcw size={14} /> {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        {/* Filter chips */}
        <div style={{ padding: '8px 16px', display: 'flex', gap: 6, flexWrap: 'wrap', borderBottom: '1px solid #eee' }}>
          <button
            onClick={() => setFilter('')}
            style={{
              padding: '4px 12px', borderRadius: 14, fontSize: 12, fontWeight: 600,
              border: '1px solid #ccc', cursor: 'pointer',
              background: filter === '' ? '#333' : '#fff',
              color: filter === '' ? '#fff' : '#555',
            }}
          >
            All
          </button>
          {tableTypes.map(t => {
            const c = TABLE_COLORS[t] || { bg: '#f5f5f5', border: '#999', text: '#555', icon: '📝' };
            return (
              <button
                key={t}
                onClick={() => setFilter(filter === t ? '' : t)}
                style={{
                  padding: '4px 12px', borderRadius: 14, fontSize: 12, fontWeight: 600,
                  border: `1px solid ${c.border}`, cursor: 'pointer',
                  background: filter === t ? c.border : '#fff',
                  color: filter === t ? '#fff' : c.text,
                }}
              >
                {c.icon} {t}
              </button>
            );
          })}
        </div>

        {/* Card feed */}
        <div style={{ padding: '12px 16px', maxHeight: 560, overflow: 'auto' }}>
          {filtered.length === 0 ? (
            <p className="muted" style={{ textAlign: 'center', padding: 48 }}>
              {logs.length === 0
                ? 'No audit logs yet. Perform some operations and refresh.'
                : 'No matching logs for this filter.'}
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {filtered.map(log => {
                const c = TABLE_COLORS[log.table_name] || { bg: '#f9fafb', border: '#9ca3af', text: '#374151', icon: '📝' };
                return (
                  <div key={log.id} style={{
                    padding: '12px 14px', background: c.bg, borderRadius: 8,
                    borderLeft: `4px solid ${c.border}`, fontSize: 13, lineHeight: 1.55,
                  }}>
                    {/* Top row: table badge + action + time */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{
                          fontSize: 11, fontWeight: 700, color: c.text,
                          background: '#fff', padding: '2px 10px', borderRadius: 4,
                          border: `1px solid ${c.border}60`
                        }}>
                          {c.icon} {log.table_name}
                        </span>
                        <span style={{ fontWeight: 700, color: '#1a1a2e', fontSize: 13.5 }}>
                          {log.action}
                        </span>
                      </div>
                      <span style={{ fontSize: 11, color: '#888', whiteSpace: 'nowrap' }}>
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                    </div>

                    {/* Description */}
                    <div style={{ color: '#333', fontSize: 13, marginBottom: 6 }}>
                      {log.description || <span className="muted">—</span>}
                    </div>

                    {/* Old → New value comparison */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 11, color: '#888', fontWeight: 500 }}>
                        {log.user_name || 'system'}
                      </span>
                      {log.old_value && log.new_value ? (
                        <>
                          <span style={{
                            fontSize: 10, background: '#fee2e2', color: '#991b1b',
                            padding: '2px 8px', borderRadius: 4, fontFamily: 'monospace',
                            maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {log.old_value}
                          </span>
                          <span style={{ fontSize: 11, color: '#999' }}>→</span>
                          <span style={{
                            fontSize: 10, background: '#dcfce7', color: '#166534',
                            padding: '2px 8px', borderRadius: 4, fontFamily: 'monospace',
                            maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {log.new_value}
                          </span>
                        </>
                      ) : (
                        <span style={{ fontSize: 11, color: '#999' }}>#{log.record_id}</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div style={{ padding: '8px 16px', borderTop: '1px solid #eee', fontSize: 11, color: '#999' }}>
          Showing {filtered.length} of {logs.length} records
        </div>
      </div>
    </section>
  );
}

function AdminStatisticsPage({
  products,
  orders,
  categories,
  lowStock,
  shops,
  users
}: {
  products: Product[];
  orders: Order[];
  categories: Category[];
  lowStock: Product[];
  shops: { id: number | null; name: string; products: Product[] }[];
  users: LocalAccount[];
}) {
  const revenue = orders.reduce((sum, order) => sum + Number(order.total_amount), 0);
  const refundRate = orders.length ? Math.round((orders.filter((order) => order.status === 'refunded').length / orders.length) * 100) : 0;
  const topProducts = [...products].sort((a, b) => (b.sold_count || 0) - (a.sold_count || 0)).slice(0, 5);
  const lowestRated = [...products].sort((a, b) => (a.average_rating || 5) - (b.average_rating || 5)).slice(0, 5);
  const categorySales = flattenCategories(categories).map((category) => ({
    category,
    sales: products.filter((product) => product.category === category.id).reduce((sum, product) => sum + (product.sold_count || 0), 0),
    count: products.filter((product) => product.category === category.id).length
  }));
  return (
    <section className="page">
      <div className="statsGrid">
        <Stat icon={User} label="Total users" value={users.length} />
        <Stat icon={User} label="Total sellers" value={users.filter((user) => user.role === 'seller').length} />
        <Stat icon={Store} label="Total stores" value={shops.length} />
        <Stat icon={Boxes} label="Total products" value={products.length} />
        <Stat icon={ClipboardList} label="Total orders" value={orders.length} />
        <Stat icon={BarChart3} label="Total sales" value={money(revenue)} />
        <Stat icon={AlertTriangle} label="Refund rate" value={`${refundRate}%`} tone={refundRate ? 'warn' : 'ok'} />
        <Stat icon={ClipboardList} label="Reviews" value={products.reduce((s, p) => s + (p.review_count || 0), 0)} />
      </div>
      <div className="statsGrid compactStats">
        <Stat icon={ClipboardList} label="Order count" value={orders.length} />
        <Stat icon={AlertTriangle} label="Low stock" value={lowStock.length} tone={lowStock.length ? 'warn' : 'ok'} />
        <Stat icon={Tags} label="Categories" value={categories.length} />
      </div>
      <div className="twoColumn">
        <section className="panel">
          <h2>High-sales Products</h2>
          <ProductAdminTable products={topProducts} />
        </section>
        <section className="panel">
          <h2>Lowest-rated Products</h2>
          <div className="coverage">
            {lowestRated.map((product) => (
              <div key={product.id}><strong>{product.name}</strong><span>{(product.average_rating || 0).toFixed(1)} avg / {product.good_rate || 0}% good</span></div>
            ))}
          </div>
        </section>
      </div>
      <section className="panel shopPreview">
        <h2>Category Sales</h2>
        <div className="tableWrap">
          <table>
            <thead><tr><th>Category</th><th>Product count</th><th>Sales quantity</th><th>Subcategory count</th></tr></thead>
            <tbody>
              {categorySales.map(({ category, sales, count }) => (
                <tr key={category.id}>
                  <td>{category.name}</td>
                  <td>{count}</td>
                  <td>{sales}</td>
                  <td>{category.children?.length || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function OrderDetailPage({ order }: { order?: Order }) {
  if (!order) {
    return <section className="page"><div className="panel emptyState">Order not found.</div></section>;
  }
  return (
    <div className="modalOverlay" onClick={() => window.history.back()}>
      <div className="modal orderDetailModal" onClick={(e) => e.stopPropagation()}>
        <div className="modalHeader">
          <div>
            <h2>Order Detail</h2>
            <p className="muted">{displayOrderNo(order)}</p>
          </div>
          <div className="modalHeaderRight">
            <span className={`status ${order.status}`}>{statusLabel(order.status_text || order.status)}</span>
            <button className="iconButton" onClick={() => window.history.back()}>
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="orderDetailItems">
          {(order.items || []).map((item) => (
            <div className="orderDetailItem" key={item.id}>
              <img
                className="orderDetailImage"
                src={item.product_image || ''}
                alt={item.product_name}
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none';
                }}
              />
              <div className="orderDetailItemInfo">
                <strong>{item.product_name}</strong>
                <span>Quantity: {item.quantity}</span>
                <span>Subtotal: {money(item.total_price)}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="orderDetailMeta">
          <div className="orderDetailField">
            <span>Total amount</span>
            <strong>{money(order.total_amount)}</strong>
          </div>
          <div className="orderDetailField">
            <span>Receiver</span>
            <strong>{order.receiver_name} / {order.receiver_phone}</strong>
          </div>
          <div className="orderDetailField">
            <span>Address</span>
            <strong>{order.address}</strong>
          </div>
          <div className="orderDetailField">
            <span>Payment</span>
            <strong>Simulated Payment / Paid</strong>
          </div>
          {order.remark && (
            <div className="orderDetailField">
              <span>Remark</span>
              <strong>{order.remark}</strong>
            </div>
          )}
          {order.created_at && (
            <div className="orderDetailField">
              <span>Created</span>
              <strong>{new Date(order.created_at).toLocaleString()}</strong>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ReviewPage({
  orders,
  itemId,
  onNotice,
  onRefresh
}: {
  orders: Order[];
  itemId?: number;
  onNotice: (type: NoticeType, message: string) => void;
  onRefresh: () => void;
}) {
  const item = orders.flatMap((order) => order.items || []).find((row) => row.id === itemId);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  return (
    <section className="page">
      <div className="toolbar">
        <a href="#/orders" className="button">← Back to orders</a>
      </div>
      <div className="panel narrow">
        <h2>Create Review</h2>
        <p className="muted">{item ? item.product_name : 'Select an order item from My Orders.'}</p>
        <form
          className="stackForm"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!item || !rating || !comment.trim()) return;
            setSubmitting(true);
            try {
              await api.createReview(item.product, {
                rating,
                comment,
                order_item_id: item.id
              });
              onNotice('success', 'Review submitted.');
              onRefresh();
              window.location.hash = '#/orders';
            } catch (error) {
              onNotice('error', String(error));
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <div className="starPicker">
            {[1, 2, 3, 4, 5].map((star) => (
              <span
                key={star}
                className="starEmoji"
                onClick={() => setRating(star)}
                role="button"
                style={{ cursor: 'pointer', fontSize: '28px', userSelect: 'none' }}
              >
                {star <= rating ? '⭐' : '☆'}
              </span>
            ))}
          </div>
          {rating > 0 && <p className="muted">{rating} star{rating === 1 ? '' : 's'}</p>}
          <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Comment" />
          <button className="button primary" disabled={!item || !rating || !comment.trim() || submitting}>Submit review</button>
        </form>
      </div>
    </section>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone = ['pending', 'reported', 'disabled', 'off_shelf', 'hidden'].includes(status) ? 'warning' : '';
  return <span className={`pill ${tone}`}>{statusLabel(status)}</span>;
}

function ProductAdminTable({
  products,
  getStatus,
  onStatusChange
}: {
  products: Product[];
  getStatus?: (product: Product) => string;
  onStatusChange?: (productId: number, status: string) => void;
}) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>Store</th>
            <th>Category</th>
            <th>Price</th>
            <th>Inventory</th>
            <th>Sales</th>
            <th>Rating</th>
            <th>Status</th>
            {onStatusChange && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {products.map((product) => {
            const status = getStatus ? getStatus(product) : product.is_active === false ? 'off_shelf' : 'approved';
            return (
              <tr key={product.id}>
                <td>{product.name}</td>
                <td>{product.shop_name || '-'}</td>
                <td>{product.category_name || '-'}</td>
                <td>{money(product.price)}</td>
                <td><span className={product.stock <= 10 ? 'stock low' : 'stock'}>{product.stock}</span></td>
                <td>{product.sold_count || 0}</td>
                <td>{(product.average_rating || 0).toFixed(1)} / {product.good_rate || 0}%</td>
                <td><StatusPill status={status} /></td>
                {onStatusChange && (
                  <td>
                    <div className="buttonRow tableActions">
                      <button className="button quiet small" onClick={() => onStatusChange(product.id, 'approved')}>Approve</button>
                      <button className="button danger small" onClick={() => onStatusChange(product.id, 'off_shelf')}>Off shelf</button>
                    </div>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function OrderMiniList({ orders }: { orders: Order[] }) {
  if (orders.length === 0) return <div className="emptyState">No orders loaded yet.</div>;
  return (
    <div className="miniOrderList">
      {orders.map((order) => (
        <div className="miniOrderRow" key={order.id}>
          <div className="miniOrderImages">
            {(order.items || []).slice(0, 3).map((item) => (
              <img
                key={item.id}
                src={item.product_image || ''}
                alt={item.product_name}
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none';
                }}
              />
            ))}
          </div>
          <div className="miniOrderInfo">
            <strong><a href={`#/order-detail/${order.id}`}>{displayOrderCustomer(order)}</a></strong>
            <span>{displayOrderNo(order)} / {money(order.total_amount)} / {statusLabel(order.status_text || order.status)}</span>
            {order.remark && <span>Remark: {order.remark}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function AuditLogList({
  logs,
  selectedIds,
  allSelected,
  onToggle,
  onToggleAll,
  onDelete
}: {
  logs: AuditLog[];
  selectedIds?: number[];
  allSelected?: boolean;
  onToggle?: (id: number) => void;
  onToggleAll?: () => void;
  onDelete?: (id: number) => void;
}) {
  if (logs.length === 0) return <div className="emptyState">No audit logs yet. Checkout, refund, review, or inventory save will create demo logs.</div>;
  const selectable = Boolean(onToggle && onDelete);
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            {selectable && (
              <th>
                <input type="checkbox" checked={Boolean(allSelected)} onChange={onToggleAll} aria-label="Select all audit logs" />
              </th>
            )}
            <th>Log ID</th>
            <th>User</th>
            <th>Operation</th>
            <th>Table</th>
            <th>Record</th>
            <th>Before change</th>
            <th>After change</th>
            <th>Created at</th>
            {selectable && <th>Operations</th>}
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id}>
              {selectable && (
                <td>
                  <input type="checkbox" checked={selectedIds?.includes(log.id) || false} onChange={() => onToggle?.(log.id)} aria-label={`Select log ${log.id}`} />
                </td>
              )}
              <td>{log.id}</td>
              <td>{log.user}</td>
              <td>{log.action}</td>
              <td>{log.table}</td>
              <td>{formatAuditRecord(log)}</td>
              <td>{formatAuditValue(log.oldValue)}</td>
              <td>{formatAuditValue(log.newValue)}</td>
              <td>{new Date(log.createdAt).toLocaleString()}</td>
              {selectable && (
                <td>
                  <button className="button quiet small" onClick={() => onDelete?.(log.id)}>
                    Delete
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ManagementTable({ title, headers, rows }: { title: string; headers: string[]; rows: string[][] }) {
  return (
    <div className="panel">
      <div className="panelHeader">
        <h2>{title}</h2>
        <div className="searchBox"><Search size={16} /><input placeholder="Search or filter" /></div>
      </div>
      <div className="tableWrap">
        <table>
          <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Footer() {
  return (
    <footer className="siteFooter">
      <p>© 2026 ShopEase Inventory System. All rights reserved.</p>
      <p>COMP3013 Database Management System Project | Group 18</p>
    </footer>
  );
}

const TABLE_SCHEMAS = [
  {
    name: 'users', desc: 'User accounts (extends Django AbstractUser)', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Primary key'],
      ['username', 'VARCHAR(30)', 'UNIQUE, NOT NULL', 'Login account (lowercase, alphanumeric only)'],
      ['password', 'VARCHAR(128)', 'NOT NULL', 'Hashed password (Django PBKDF2)'],
      ['display_name', 'VARCHAR(50)', 'NULL', 'Public display name (any characters)'],
      ['email', 'VARCHAR(254)', 'NOT NULL', 'Email address'],
      ['phone', 'VARCHAR(11)', 'NULL', 'Phone number'],
      ['avatar', 'VARCHAR(200)', 'NULL', 'Avatar image URL'],
      ['address', 'VARCHAR(255)', 'NULL', 'Default shipping address'],
      ['is_active', 'TINYINT(1)', 'NOT NULL, DEFAULT 1', 'Account enabled (admin toggle)'],
      ['is_staff', 'TINYINT(1)', 'NOT NULL, DEFAULT 0', 'Django admin access'],
      ['is_superuser', 'TINYINT(1)', 'NOT NULL, DEFAULT 0', 'Superuser flag'],
      ['first_name', 'VARCHAR(150)', 'NOT NULL', 'Django built-in (unused)'],
      ['last_name', 'VARCHAR(150)', 'NOT NULL', 'Django built-in (unused)'],
      ['last_login', 'DATETIME(6)', 'NULL', 'Last login timestamp'],
      ['date_joined', 'DATETIME(6)', 'NOT NULL', 'Registration timestamp'],
    ]
  },
  {
    name: 'shops', desc: 'Online stores owned by sellers', fields: [
      ['shop_id', 'INT', 'PK, AUTO_INCREMENT', 'Shop unique identifier'],
      ['user_id', 'BIGINT', 'FK → users.id, NOT NULL', 'Shop owner (1 user owns N shops)'],
      ['shop_name', 'VARCHAR(100)', 'NOT NULL', 'Store name'],
      ['description', 'LONGTEXT', 'NULL', 'Store description'],
      ['status', 'VARCHAR(20)', 'NOT NULL, DEFAULT approved', 'Status: pending / approved / rejected / disabled'],
      ['rating', 'DECIMAL(3,2)', 'NOT NULL, DEFAULT 5.00', 'Average store rating (0.00–5.00)'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Creation timestamp'],
    ]
  },
  {
    name: 'categories', desc: 'Product categories (self-referential, 2-level)', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Primary key'],
      ['name', 'VARCHAR(100)', 'NOT NULL', 'Category display name'],
      ['parent_id', 'BIGINT', 'FK → categories.id, NULL', 'Parent category (NULL = top-level)'],
      ['slug', 'VARCHAR(100)', 'UNIQUE, NOT NULL', 'URL-friendly identifier'],
      ['is_active', 'TINYINT(1)', 'NOT NULL, DEFAULT 1', 'Whether category is enabled'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Creation timestamp'],
    ]
  },
  {
    name: 'products', desc: 'Product listings', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Primary key'],
      ['name', 'VARCHAR(200)', 'NOT NULL', 'Product name'],
      ['description', 'LONGTEXT', 'NULL', 'Product description'],
      ['price', 'DECIMAL(12,2)', 'NOT NULL', 'Unit price (12 digits, 2 decimal places)'],
      ['image', 'VARCHAR(200)', 'NULL', 'Product image URL'],
      ['category_id', 'BIGINT', 'FK → categories.id, SET NULL', 'Product category'],
      ['seller_id', 'BIGINT', 'FK → users.id, NOT NULL', 'Seller (product owner)'],
      ['shop_id', 'INT', 'FK → shops.shop_id, SET NULL', 'Associated shop'],
      ['is_active', 'TINYINT(1)', 'NOT NULL, DEFAULT 1', 'Listed (1) / Delisted (0)'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Creation timestamp'],
      ['updated_at', 'DATETIME(6)', 'NOT NULL', 'Last update timestamp'],
      ['', '', 'INDEX idx_product_price (price)', 'Price-based filtering/sorting'],
      ['', '', 'INDEX idx_product_cat_active (category_id, is_active)', 'Category browse with active filter'],
    ]
  },
  {
    name: 'inventory', desc: 'Stock levels (1:1 with Product, single source of truth)', fields: [
      ['inventory_id', 'INT', 'PK, AUTO_INCREMENT', 'Inventory record ID'],
      ['product_id', 'BIGINT', 'UNIQUE, FK → products.id (CASCADE)', 'Associated product (1:1)'],
      ['quantity', 'INT UNSIGNED', 'NOT NULL, DEFAULT 0', 'Current stock quantity'],
      ['updated_at', 'DATETIME(6)', 'NOT NULL', 'Last modification timestamp'],
    ]
  },
  {
    name: 'inventory_transactions', desc: 'Immutable stock change ledger', fields: [
      ['transaction_id', 'INT', 'PK, AUTO_INCREMENT', 'Transaction unique ID'],
      ['inventory_id', 'INT', 'FK → inventory.inventory_id (CASCADE)', 'Target inventory record'],
      ['change_type', 'VARCHAR(32)', 'NOT NULL', 'RESTOCK / ORDER_DEDUCT / ADJUSTMENT / REFUND_REQUESTED / REFUND_APPROVED / RETURN_RESTOCK'],
      ['quantity_change', 'INT', 'NOT NULL', 'Positive = stock in, Negative = stock out'],
      ['related_order_id', 'BIGINT', 'FK → orders.id, SET NULL', 'Related order (if applicable)'],
      ['related_refund_id', 'BIGINT', 'FK → refunds.id, SET NULL', 'Related refund (if applicable)'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Transaction timestamp'],
      ['', '', 'INDEX idx_inv_txn_type_time (change_type, created_at)', 'Filtering by type + time'],
    ]
  },
  {
    name: 'carts', desc: 'Shopping cart (Cart + CartItem merged)', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Cart item ID'],
      ['user_id', 'BIGINT', 'FK → users.id (CASCADE)', 'Cart owner'],
      ['product_id', 'BIGINT', 'FK → products.id (CASCADE)', 'Product in cart'],
      ['quantity', 'INT UNSIGNED', 'NOT NULL, DEFAULT 1', 'Quantity'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Added timestamp'],
      ['updated_at', 'DATETIME(6)', 'NOT NULL', 'Last modified timestamp'],
      ['', '', 'UNIQUE(user_id, product_id)', 'One entry per user per product'],
    ]
  },
  {
    name: 'orders', desc: 'Purchase orders with state machine', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Internal primary key'],
      ['order_no', 'VARCHAR(32)', 'UNIQUE, NOT NULL', 'Human-readable order number (timestamp + UUID)'],
      ['user_id', 'BIGINT', 'FK → users.id (CASCADE)', 'Buyer'],
      ['total_amount', 'DECIMAL(10,2)', 'NOT NULL', 'Order total (sum of item prices)'],
      ['status', 'VARCHAR(20)', 'NOT NULL, DEFAULT paid', 'paid → shipped → completed; paid → cancelled; (any) → refunded'],
      ['address', 'VARCHAR(255)', 'NOT NULL', 'Shipping address (single field)'],
      ['receiver_name', 'VARCHAR(100)', 'NOT NULL', 'Recipient name'],
      ['receiver_phone', 'VARCHAR(11)', 'NOT NULL', 'Recipient phone'],
      ['remark', 'LONGTEXT', 'NULL', 'Order notes'],
      ['buyer_deleted', 'TINYINT(1)', 'NOT NULL, DEFAULT 0', 'Soft delete flag for buyer'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Order creation timestamp'],
      ['updated_at', 'DATETIME(6)', 'NOT NULL', 'Last update timestamp'],
      ['', '', 'INDEX idx_order_status (status)', 'Status filtering'],
      ['', '', 'INDEX idx_order_created (created_at)', 'Date sorting'],
      ['', '', 'INDEX idx_order_user_status (user_id, status)', 'User order list with status'],
    ]
  },
  {
    name: 'order_items', desc: 'Line items within an order', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Line item ID'],
      ['order_id', 'BIGINT', 'FK → orders.id (CASCADE)', 'Parent order'],
      ['product_id', 'BIGINT', 'FK → products.id (CASCADE)', 'Purchased product'],
      ['price', 'DECIMAL(10,2)', 'NOT NULL', 'Unit price at time of purchase (snapshot)'],
      ['quantity', 'INT UNSIGNED', 'NOT NULL, DEFAULT 1', 'Quantity purchased'],
    ]
  },
  {
    name: 'refunds', desc: 'Refund requests', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Internal primary key'],
      ['refund_no', 'VARCHAR(32)', 'UNIQUE, NOT NULL', 'Refund number (REF + timestamp + UUID)'],
      ['order_id', 'BIGINT', 'FK → orders.id (CASCADE)', 'Associated order'],
      ['user_id', 'BIGINT', 'FK → users.id (CASCADE)', 'Applicant (buyer)'],
      ['reason', 'LONGTEXT', 'NOT NULL', 'Refund reason'],
      ['total_amount', 'DECIMAL(10,2)', 'NOT NULL', 'Total refund amount'],
      ['status', 'VARCHAR(20)', 'NOT NULL, DEFAULT pending', 'pending / approved / rejected / refunded'],
      ['admin_remark', 'LONGTEXT', 'NULL', 'Admin/seller remark when processing'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Application timestamp'],
      ['updated_at', 'DATETIME(6)', 'NOT NULL', 'Last update timestamp'],
      ['', '', 'INDEX idx_refund_status (status)', 'Status filtering'],
      ['', '', 'INDEX idx_refund_created (created_at)', 'Date sorting'],
    ]
  },
  {
    name: 'refund_items', desc: 'Line items within a refund', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Refund item ID'],
      ['refund_id', 'BIGINT', 'FK → refunds.id (CASCADE)', 'Parent refund'],
      ['order_item_id', 'BIGINT', 'FK → order_items.id (CASCADE)', 'Order item being refunded'],
      ['quantity', 'INT UNSIGNED', 'NOT NULL, DEFAULT 1', 'Quantity being refunded'],
      ['refund_amount', 'DECIMAL(10,2)', 'NOT NULL', 'Amount refunded for this item'],
    ]
  },
  {
    name: 'reviews', desc: 'Product reviews (moderated: hidden by default)', fields: [
      ['review_id', 'INT', 'PK, AUTO_INCREMENT', 'Review unique ID'],
      ['product_id', 'BIGINT', 'FK → products.id (CASCADE)', 'Reviewed product'],
      ['user_id', 'BIGINT', 'FK → users.id (CASCADE)', 'Reviewer'],
      ['order_item_id', 'BIGINT', 'FK → order_items.id, SET NULL', 'Associated order item (verified purchase)'],
      ['rating', 'SMALLINT UNSIGNED', 'NOT NULL, CHECK 1-5', 'Rating score'],
      ['comment', 'LONGTEXT', 'NULL', 'Review text'],
      ['status', 'VARCHAR(20)', 'NOT NULL, DEFAULT hidden', 'hidden(待审核) / visible(通过) / deleted(不通过) / reported(被举报)'],
      ['like_count', 'INT UNSIGNED', 'NOT NULL, DEFAULT 0', 'Like count'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Review timestamp'],
      ['', '', 'INDEX idx_review_status (status)', 'Moderation filtering'],
      ['', '', 'INDEX idx_review_created (created_at)', 'Date sorting'],
    ]
  },
  {
    name: 'shop_follows', desc: 'User-shop follow relationship (N:M)', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Follow record ID'],
      ['user_id', 'BIGINT', 'FK → users.id (CASCADE)', 'Follower'],
      ['shop_id', 'INT', 'FK → shops.shop_id (CASCADE)', 'Shop being followed'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Follow timestamp'],
      ['', '', 'UNIQUE(user_id, shop_id)', 'One follow per user per shop'],
    ]
  },
  {
    name: 'audit_logs', desc: 'Immutable audit trail for all critical operations', fields: [
      ['id', 'BIGINT', 'PK, AUTO_INCREMENT', 'Log entry ID'],
      ['user_id', 'BIGINT', 'FK → users.id, SET NULL', 'User who triggered the action'],
      ['action', 'VARCHAR(50)', 'NOT NULL', 'Action type (e.g. Order Created, Refund Approved, Product Moderated)'],
      ['table_name', 'VARCHAR(50)', 'NOT NULL', 'Affected table name'],
      ['record_id', 'VARCHAR(50)', 'NOT NULL', 'Affected record identifier'],
      ['description', 'LONGTEXT', 'NOT NULL', 'Human-readable description of the change'],
      ['old_value', 'LONGTEXT', 'NOT NULL, DEFAULT ""', 'Value before change (JSON or text)'],
      ['new_value', 'LONGTEXT', 'NOT NULL, DEFAULT ""', 'Value after change (JSON or text)'],
      ['detail', 'LONGTEXT', 'NOT NULL, DEFAULT ""', 'Additional detail as JSON (legacy compat)'],
      ['created_at', 'DATETIME(6)', 'NOT NULL', 'Timestamp of action'],
      ['', '', 'INDEX idx_alog_table_time (table_name, created_at)', 'Audit log by table + time'],
      ['', '', 'INDEX idx_alog_time (created_at)', 'Time-based queries'],
    ]
  },
];

const ER_DIAGRAM = `
┌──────────────┐   1:N    ┌──────────────┐
│    users     │──────────▶│    shops     │
│  (User)      │           │ (OnlineStore)│
└──┬──┬──┬──┬──┘           └──────┬───────┘
   │  │  │  │ 1:N                  │ 1:N
   │  │  │  │                      ▼
   │  │  │  │             ┌──────────────┐    1:1    ┌──────────────┐   1:N    ┌──────────────────┐
   │  │  │  │             │   products   │──────────▶│  inventory   │─────────▶│inventory_transact│
   │  │  │  │             │  (Product)   │           │ (Inventory)  │          │ (stock ledger)   │
   │  │  │  │             └──┬──┬──┬─────┘           └──────────────┘          └──────────────────┘
   │  │  │  │                │  │  │
   │  │  │  │ N:1            │  │  └──────────────┐
   │  │  │  │    ┌───────────┘  │ N:1              │
   │  │  │  │    │              ▼                   │
   │  │  │  │    │    ┌──────────────┐              │
   │  │  │  │    │    │  categories  │              │
   │  │  │  │    │    │ (Category)   │              │
   │  │  │  │    │    │ self-ref:    │              │
   │  │  │  │    │    │ parent_id FK │              │
   │  │  │  │    │    └──────────────┘              │
   │  │  │  │    │                                 │
   │  │  │  │    │ 1:N                             │ 1:N
   │  │  │  │    ▼                                 ▼
   │  │  │  │ ┌──────────────┐ 1:N  ┌──────────────┐   1:N   ┌──────────────┐
   │  │  │  │ │   reviews    │◀─────│ order_items  │◀───────│    orders    │
   │  │  │  │ │  (Review)    │      │ (OrderItem)  │        │(PurchaseRec) │
   │  │  │  │ └──────────────┘      └──────────────┘        └──────┬───────┘
   │  │  │  │                                                     │ 1:N
   │  │  │  │                                                     ▼
   │  │  │  │                                              ┌──────────────┐  1:N   ┌──────────────┐
   │  │  │  │                                              │   refunds    │◀───────│ refund_items │
   │  │  │  │                                              │(RefundRequest│        │ (RefundItem) │
   │  │  │  │                                              └──────────────┘        └──────────────┘
   │  │  │  │
   │  │  │  │ 1:N    ┌──────────────┐
   │  │  │  └───────▶│    carts     │
   │  │  │           │(Cart+CartItem)│
   │  │  │           └──────────────┘
   │  │  │
   │  │  │ N:M    ┌──────────────┐
   │  │  └───────▶│ shop_follows │
   │  │           │ (ShopFollow) │
   │  │           └──────────────┘
   │  │
   │  │ 1:N    ┌──────────────┐
   │  └───────▶│  audit_logs  │
   │           │ (AuditLog)   │
   │           └──────────────┘
   │
   │ (inventory_transactions also has)
   │ (FK → orders + FK → refunds)
   ▼
 (SET NULL on user delete for audit_logs)
`;

function DatabasePage() {
  const [activeTab, setActiveTab] = useState<'er' | 'schema' | 'sql' | 'browser'>('schema');
  const [sqlDemos, setSqlDemos] = useState<{
    title: string; description: string; sql: string;
    columns: string[]; rows: (string | number)[][]; error?: string;
  }[]>([]);
  const [loading, setLoading] = useState(false);
  const [schemaSearch, setSchemaSearch] = useState('');

  // Data Browser state
  const [dbTables, setDbTables] = useState<{ name: string; row_count: number; columns: { name: string; type: string; nullable: boolean; key: string }[] }[]>([]);
  const [selectedTable, setSelectedTable] = useState('');
  const [tableData, setTableData] = useState<{ columns: string[]; rows: unknown[][]; total: number; page: number; size: number } | null>(null);
  const [browserPage, setBrowserPage] = useState(1);
  const [browserLoading, setBrowserLoading] = useState(false);
  const [changeFeed, setChangeFeed] = useState<{ id: string; table: string; action: string; description: string; time: string }[]>([]);
  const [feedSince, setFeedSince] = useState('');

  useEffect(() => {
    setLoading(true);
    api.adminSQLDemo()
      .then(setSqlDemos)
      .catch(() => setSqlDemos([]))
      .finally(() => setLoading(false));
  }, []);

  // Load table list when browser tab is active
  useEffect(() => {
    if (activeTab !== 'browser') return;
    api.adminDbTables().then(setDbTables).catch(() => {});
  }, [activeTab]);

  // Load table data
  useEffect(() => {
    if (!selectedTable || activeTab !== 'browser') return;
    setBrowserLoading(true);
    api.adminDbTable(selectedTable, browserPage, 50)
      .then(setTableData)
      .catch(() => setTableData(null))
      .finally(() => setBrowserLoading(false));
  }, [selectedTable, browserPage, activeTab]);

  // Auto-refresh change feed
  useEffect(() => {
    if (activeTab !== 'browser') return;
    const loadFeed = () => {
      api.adminChangeFeed(feedSince || undefined, 30).then(feed => {
        setChangeFeed(prev => {
          const seen = new Set(prev.map(f => f.id));
          const merged = [...feed.filter(f => !seen.has(f.id)), ...prev];
          return merged.slice(0, 50);
        });
        if (feed.length > 0 && !feedSince) {
          setFeedSince(feed[0].time);
        }
      }).catch(() => {});
    };
    loadFeed();
    const timer = setInterval(loadFeed, 5000);
    return () => clearInterval(timer);
  }, [activeTab, feedSince]);

  const filteredSchemas = TABLE_SCHEMAS.filter(t =>
    !schemaSearch ||
    t.name.includes(schemaSearch.toLowerCase()) ||
    t.desc.includes(schemaSearch)
  );

  return (
    <section className="page">
      <div className="panel">
        <div className="splitHeader">
          <div>
            <h2>Database Design & SQL Demonstration</h2>
            <p>COMP3013 DBMS Project — 16 tables, full schema, ER diagram, and live SQL queries</p>
          </div>
          <span className="pill">{TABLE_SCHEMAS.length} tables</span>
        </div>

        <div className="tabRow" style={{ marginBottom: 16 }}>
          <button className={`tab ${activeTab === 'schema' ? 'active' : ''}`} onClick={() => setActiveTab('schema')}>Table Schema</button>
          <button className={`tab ${activeTab === 'er' ? 'active' : ''}`} onClick={() => setActiveTab('er')}>ER Diagram</button>
          <button className={`tab ${activeTab === 'sql' ? 'active' : ''}`} onClick={() => setActiveTab('sql')}>SQL Queries ({sqlDemos.length})</button>
          <button className={`tab ${activeTab === 'browser' ? 'active' : ''}`} onClick={() => setActiveTab('browser')}>Data Browser</button>
        </div>

        {activeTab === 'schema' && (
          <div>
            <div className="searchBox" style={{ marginBottom: 12 }}>
              <Search size={16} />
              <input value={schemaSearch} onChange={e => setSchemaSearch(e.target.value)} placeholder="Search table name or description" />
            </div>
            {filteredSchemas.map(table => (
              <details key={table.name} style={{ marginBottom: 8 }}>
                <summary style={{ fontWeight: 700, fontSize: 15, cursor: 'pointer' }}>
                  {table.name} — <span style={{ fontWeight: 400, color: '#666' }}>{table.desc}</span>
                </summary>
                <div className="tableWrap" style={{ marginTop: 8 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Column</th>
                        <th>Type</th>
                        <th>Constraint</th>
                        <th>Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {table.fields.map((f, i) => (
                        <tr key={i}>
                          <td style={{ fontWeight: 600 }}>{f[0] || <em style={{ color: '#999' }}>—</em>}</td>
                          <td><code>{f[1]}</code></td>
                          <td style={{ color: '#d63384' }}>{f[2]}</td>
                          <td style={{ color: '#666' }}>{f[3]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            ))}
          </div>
        )}

        {activeTab === 'er' && (
          <div>
            <p className="muted" style={{ marginBottom: 12 }}>
              Relations: users 1:1 shops, shops 1:N products, users 1:N orders, orders 1:N order_items, order_items N:1 products, products 1:1 inventory, inventory 1:N inventory_transactions, orders 1:N refunds, refunds 1:N refund_items, products 1:N reviews, categories self-referencing tree, users N:M shops via shop_follows. audit_logs is the unified change feed recording all key data mutations across the system.
            </p>
            <pre style={{
              background: '#1e1e2e', color: '#cdd6f4', padding: 16, borderRadius: 8,
              fontSize: 13, lineHeight: 1.4, overflow: 'auto', maxHeight: 500,
              fontFamily: '"Cascadia Code", "Fira Code", monospace'
            }}>
              {ER_DIAGRAM}
            </pre>
          </div>
        )}

        {activeTab === 'sql' && (
          <div>
            {loading && <div className="emptyState">Loading SQL demos from database...</div>}
            {sqlDemos.map((demo, idx) => (
              <details key={idx} style={{ marginBottom: 12, border: '1px solid #e5e5e5', borderRadius: 8, overflow: 'hidden' }}>
                <summary style={{ padding: '12px 16px', fontWeight: 700, fontSize: 15, cursor: 'pointer', background: '#f8f9fa' }}>
                  {demo.title}
                </summary>
                <div style={{ padding: 16 }}>
                  <p className="muted" style={{ marginBottom: 12 }}>{demo.description}</p>
                  <pre style={{
                    background: '#1e1e2e', color: '#a6e3a1', padding: 14, borderRadius: 6,
                    fontSize: 12.5, lineHeight: 1.5, overflow: 'auto', maxHeight: 240,
                    fontFamily: '"Cascadia Code", "Fira Code", monospace', whiteSpace: 'pre-wrap'
                  }}>
                    {demo.sql}
                  </pre>
                  {demo.error ? (
                    <div style={{ color: '#e74c3c', marginTop: 8 }}>Error: {demo.error}</div>
                  ) : (
                    <div className="tableWrap" style={{ marginTop: 12 }}>
                      <table>
                        <thead>
                          <tr>{demo.columns.map((col, i) => <th key={i}>{col}</th>)}</tr>
                        </thead>
                        <tbody>
                          {demo.rows.length === 0 ? (
                            <tr><td colSpan={demo.columns.length} style={{ textAlign: 'center', color: '#999' }}>No data (database may be empty)</td></tr>
                          ) : demo.rows.map((row, ri) => (
                            <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{String(cell)}</td>)}</tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}

        {activeTab === 'browser' && (
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {/* Main area: table selector + data grid */}
            <div style={{ flex: 1, minWidth: 360 }}>
              {/* Table selector */}
              <div className="splitHeader" style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <Database size={20} />
                  <select
                    value={selectedTable}
                    onChange={e => { setSelectedTable(e.target.value); setBrowserPage(1); }}
                    style={{
                      padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd',
                      fontSize: 14, fontWeight: 600, background: '#fff', minWidth: 200
                    }}
                  >
                    <option value="">Select a table...</option>
                    {dbTables.map(t => (
                      <option key={t.name} value={t.name}>{t.name} ({t.row_count} rows)</option>
                    ))}
                  </select>
                </div>
                {tableData && (
                  <span style={{ fontSize: 13, color: '#666' }}>
                    {tableData.total.toLocaleString()} row{tableData.total !== 1 ? 's' : ''}
                  </span>
                )}
              </div>

              {/* Data grid */}
              {!selectedTable ? (
                <div className="emptyState">
                  <Database size={40} style={{ color: '#ccc', marginBottom: 12 }} />
                  <div>Select a table above to browse its data</div>
                </div>
              ) : browserLoading ? (
                <div className="emptyState">Loading...</div>
              ) : tableData ? (
                <div>
                  <div className="tableWrap" style={{ maxHeight: '60vh', overflow: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          {tableData.columns.map(col => (
                            <th key={col} style={{ position: 'sticky', top: 0, background: '#f8f9fa', zIndex: 1 }}>
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {tableData.rows.length === 0 ? (
                          <tr><td colSpan={tableData.columns.length} style={{ textAlign: 'center', color: '#999' }}>No rows</td></tr>
                        ) : tableData.rows.map((row, ri) => (
                          <tr key={ri}>
                            {row.map((cell, ci) => (
                              <td key={ci} style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {cell === null ? <em style={{ color: '#bbb' }}>NULL</em> : String(cell)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination */}
                  {tableData.total > tableData.size && (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, marginTop: 12 }}>
                      <button
                        className="btn secondary"
                        disabled={browserPage <= 1}
                        onClick={() => setBrowserPage(p => p - 1)}
                        style={{ padding: '6px 14px' }}
                      >
                        Prev
                      </button>
                      <span style={{ fontSize: 13, color: '#666' }}>
                        Page {browserPage} / {Math.ceil(tableData.total / tableData.size)}
                      </span>
                      <button
                        className="btn secondary"
                        disabled={browserPage >= Math.ceil(tableData.total / tableData.size)}
                        onClick={() => setBrowserPage(p => p + 1)}
                        style={{ padding: '6px 14px' }}
                      >
                        Next
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="emptyState" style={{ color: '#e74c3c' }}>Failed to load table data</div>
              )}
            </div>

            {/* Change feed panel */}
            <div style={{
              width: 360, background: '#fafbfc', borderRadius: 8, padding: 0,
              border: '1px solid #e5e5e5', maxHeight: '70vh', display: 'flex', flexDirection: 'column'
            }}>
              {/* Header */}
              <div style={{
                padding: '12px 14px', borderBottom: '1px solid #e5e5e5',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                background: '#fff', borderRadius: '8px 8px 0 0'
              }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: 8, margin: 0, fontSize: 14 }}>
                  <Clock size={15} />
                  数据库变更通知
                </h4>
                <span style={{ fontSize: 11, color: '#999', display: 'flex', alignItems: 'center', gap: 4 }}>
                  每 5s 刷新 <RefreshCcw size={11} />
                </span>
              </div>

              {/* Feed list */}
              <div style={{ overflow: 'auto', padding: '8px 10px', flex: 1 }}>
                {changeFeed.length === 0 ? (
                  <p className="muted" style={{ fontSize: 13, textAlign: 'center', padding: 32 }}>
                    暂无变更，进行一笔交易试试
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {changeFeed.map(entry => {
                      const colors: Record<string, { bg: string; border: string; text: string; icon: string }> = {
                        inventory:  { bg: '#fff8f0', border: '#f0ad4e', text: '#b85c00', icon: '📦' },
                        orders:     { bg: '#f0f7ff', border: '#5b9bd5', text: '#1a56a0', icon: '📋' },
                        users:      { bg: '#f5f0ff', border: '#8b5cf6', text: '#5b21b6', icon: '👤' },
                        shops:      { bg: '#fff0f7', border: '#e85d9a', text: '#9b1d5a', icon: '🏪' },
                        products:   { bg: '#f0fff4', border: '#48bb78', text: '#22543d', icon: '📦' },
                        reviews:    { bg: '#fffbeb', border: '#f59e0b', text: '#92400e', icon: '⭐' },
                      };
                      const c = colors[entry.table] || { bg: '#f0faf0', border: '#5cb85c', text: '#2d6a2d', icon: '📝' };
                      return (
                        <div key={entry.id} style={{
                          padding: '10px 12px', background: c.bg, borderRadius: 6,
                          borderLeft: `3px solid ${c.border}`, fontSize: 12.5, lineHeight: 1.5,
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                            <span style={{
                              fontSize: 10, fontWeight: 700, color: c.text,
                              background: '#fff', padding: '2px 8px', borderRadius: 4,
                              border: `1px solid ${c.border}40`
                            }}>
                              {c.icon} {entry.table}
                            </span>
                            <span style={{ fontSize: 10, color: '#999' }}>
                              {new Date(entry.time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                          </div>
                          <div style={{ fontWeight: 600, color: '#333', marginBottom: 2 }}>
                            {entry.action}
                          </div>
                          <div style={{ color: '#666', fontSize: 11.5 }}>
                            {entry.description}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default App;
