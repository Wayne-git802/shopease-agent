export type ApiEnvelope<T> = {
  code?: number;
  msg?: string;
  data?: T;
  results?: T;
};

export type Category = {
  id: number;
  name: string;
  parent?: number | null;
  parent_name?: string | null;
  slug: string;
  is_active?: boolean;
  children?: Category[];
  created_at?: string;
};

export type Product = {
  id: number;
  name: string;
  description?: string | null;
  price: string | number;
  stock: number;
  image?: string | null;
  category?: number | null;
  category_name?: string | null;
  seller?: number;
  seller_name?: string;
  shop?: number | null;
  shop_name?: string | null;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
  sold_count?: number;
  review_count?: number;
  average_rating?: number;
  good_rate?: number;
};

export type CartLine = {
  id: number;
  product: number;
  product_name: string;
  product_price: string | number;
  product_image?: string | null;
  quantity: number;
  total_price: string | number;
  localOnly?: boolean;
};

export type LocalCartLine = {
  productId: number;
  name: string;
  price: number;
  image?: string | null;
  quantity: number;
  stock?: number;
};

export type OrderItem = {
  id: number;
  product: number;
  product_name: string;
  product_image?: string | null;
  price: string | number;
  quantity: number;
  total_price: string | number;
  shop_name?: string;
  shop_id?: number | null;
};

export type Order = {
  id: number;
  order_no: string;
  total_amount: string | number;
  status: string;
  status_text?: string;
  address: string;
  receiver_name: string;
  receiver_phone: string;
  remark?: string | null;
  items: OrderItem[];
  pending_refund_id?: number | null;
  pending_refund_status?: string | null;
  username?: string;
  created_at?: string;
  updated_at?: string;
};

export type InventoryChangeType =
  | 'RESTOCK'
  | 'ORDER_DEDUCT'
  | 'ADJUSTMENT'
  | 'REFUND_REQUESTED'
  | 'REFUND_APPROVED'
  | 'RETURN_RESTOCK';

export type InventoryTransaction = {
  transaction_id: number;
  inventory_id: number;
  product_id?: number;
  product_name?: string;
  store_id?: number | null;
  store_name?: string | null;
  change_type: InventoryChangeType;
  quantity_change: number;
  related_order_id?: number | null;
  related_refund_id?: number | null;
  created_at: string;
};

export type Refund = {
  id: number;
  refund_no: string;
  order: number;
  order_no: string;
  reason: string;
  total_amount: string | number;
  status: string;
  status_text?: string;
  admin_remark?: string | null;
  created_at?: string;
};

export type UserProfile = {
  username: string;
  display_name?: string | null;
  email: string;
  phone?: string | null;
  avatar?: string | null;
  address?: string | null;
  date_joined?: string;
};

export type Shop = {
  shop_id: number;
  user: number;
  owner_username: string;
  shop_name: string;
  description?: string | null;
  status?: string;
  rating: string | number;
  product_count?: number;
  created_at?: string;
};

export type Review = {
  review_id: number;
  product: number;
  user: number;
  username: string;
  order_item?: number | null;
  rating: number;
  comment?: string | null;
  status?: string;
  like_count: number;
  created_at?: string;
};

export type AdminReview = {
  review_id: number;
  product_id: number;
  product_name: string;
  username: string;
  rating: number;
  comment: string;
  status: string;
  like_count: number;
  created_at: string;
};

export type AuthTokens = {
  access: string;
  refresh: string;
};
