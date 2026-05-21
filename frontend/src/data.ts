import type { Category, Product } from './types';

export const fallbackCategories: Category[] = [
  { id: 1, name: 'Electronics', slug: 'electronics', children: [{ id: 11, name: 'Audio', slug: 'audio' }, { id: 12, name: 'Wearables', slug: 'wearables' }] },
  { id: 2, name: 'Clothing', slug: 'clothing', children: [{ id: 21, name: 'Mens Wear', slug: 'mens-wear' }, { id: 22, name: 'Accessories', slug: 'accessories' }] },
  { id: 3, name: 'Home & Garden', slug: 'home-garden', children: [{ id: 31, name: 'Kitchen', slug: 'kitchen' }, { id: 32, name: 'Storage', slug: 'storage' }] },
  { id: 4, name: 'Books', slug: 'books', children: [{ id: 41, name: 'Programming', slug: 'programming' }, { id: 42, name: 'Science', slug: 'science' }] }
];

export const fallbackProducts: Product[] = [
  {
    id: 101,
    name: 'Wireless Bluetooth Headphones',
    description: 'High quality audio device with stable stock tracking.',
    price: '79.99',
    stock: 50,
    image: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&h=500&fit=crop',
    category: 11,
    category_name: 'Audio',
    seller_name: 'alice',
    shop: 1,
    shop_name: "Alice's Electronics",
    is_active: true,
    sold_count: 312,
    review_count: 86,
    average_rating: 4.7,
    good_rate: 92
  },
  {
    id: 102,
    name: 'Smart Watch Pro',
    description: 'Wearable device with health tracking and inventory alerts.',
    price: '299.99',
    stock: 8,
    image: 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&h=500&fit=crop',
    category: 12,
    category_name: 'Wearables',
    seller_name: 'alice',
    shop: 1,
    shop_name: "Alice's Electronics",
    is_active: true,
    sold_count: 228,
    review_count: 64,
    average_rating: 4.8,
    good_rate: 95
  },
  {
    id: 103,
    name: 'Coffee Maker Deluxe',
    description: 'Kitchen appliance item with supplier-facing stock visibility.',
    price: '149.99',
    stock: 20,
    image: 'https://images.unsplash.com/photo-1541167760496-1628856ab772?w=600&h=500&fit=crop',
    category: 31,
    category_name: 'Kitchen',
    seller_name: 'charlie',
    shop: 3,
    shop_name: "Charlie's Home & Living",
    is_active: true,
    sold_count: 144,
    review_count: 41,
    average_rating: 4.5,
    good_rate: 88
  },
  {
    id: 104,
    name: 'Python Mastery Guide',
    description: 'Programming book sample item for the product catalog.',
    price: '49.99',
    stock: 35,
    image: 'https://images.unsplash.com/photo-1515879218367-8466d910aaa4?w=600&h=500&fit=crop',
    category: 41,
    category_name: 'Programming',
    seller_name: 'diana',
    shop: 4,
    shop_name: "Diana's Book Nook",
    is_active: true,
    sold_count: 198,
    review_count: 52,
    average_rating: 4.9,
    good_rate: 96
  }
];
