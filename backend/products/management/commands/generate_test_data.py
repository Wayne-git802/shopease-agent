"""
生成测试数据的管理命令
用法: python manage.py generate_test_data
"""
import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from products.models import Category, Product, Shop, Inventory

User = get_user_model()


class Command(BaseCommand):
    help = '生成测试数据：多店铺、用户、商品（8个店铺+65个商品）'

    def handle(self, *args, **options):
        self.stdout.write('开始生成测试数据...\n')

        # 创建分类
        categories = self.create_categories()
        self.stdout.write(self.style.SUCCESS(f'[OK] 创建了 {len(categories)} 个分类'))

        # 创建用户和店铺
        users = self.create_users()
        self.stdout.write(self.style.SUCCESS(f'[OK] 创建了 {len(users)} 个用户'))

        # 创建商品
        products = self.create_products(users, categories)
        self.stdout.write(self.style.SUCCESS(f'[OK] 创建了 {len(products)} 个商品'))

        self.stdout.write(self.style.SUCCESS('\n所有测试数据生成成功！'))

    def create_categories(self):
        """创建商品分类"""
        # 格式：(名称, slug, 父分类名称或None)
        category_data = [
            # 电子产品
            ('电子产品', 'electronics', None),
            ('手机通讯', 'phones', '电子产品'),
            ('电脑整机', 'computers', '电子产品'),
            ('平板影音', 'tablets', '电子产品'),
            ('智能设备', 'smart-devices', '电子产品'),
            ('数码配件', 'accessories', '电子产品'),
            
            # 服装鞋包
            ('服装鞋包', 'fashion', None),
            ('潮流男装', 'mens-wear', '服装鞋包'),
            ('时尚女装', 'womens-wear', '服装鞋包'),
            ('潮流鞋靴', 'shoes', '服装鞋包'),
            ('精品箱包', 'bags', '服装鞋包'),
            ('内衣配饰', 'underwear', '服装鞋包'),
            
            # 家居生活
            ('家居生活', 'home', None),
            ('大家电', 'large-appliances', '家居生活'),
            ('小家电', 'small-appliances', '家居生活'),
            ('居家日用', 'daily-use', '家居生活'),
            ('家纺床品', 'bedding', '家居生活'),
            ('家居装饰', 'decor', '家居生活'),
            
            # 食品生鲜
            ('食品生鲜', 'food', None),
            ('新鲜水果', 'fruits', '食品生鲜'),
            ('海鲜肉类', 'meat', '食品生鲜'),
            ('有机蔬菜', 'vegetables', '食品生鲜'),
            ('休闲零食', 'snacks', '食品生鲜'),
            ('粮油调味', 'oils', '食品生鲜'),
            ('营养保健', 'health', '食品生鲜'),
            
            # 美妆护肤
            ('美妆护肤', 'beauty', None),
            ('面部护肤', 'face-care', '美妆护肤'),
            ('彩妆香氛', 'makeup', '美妆护肤'),
            ('个人护理', 'personal-care', '美妆护肤'),
            ('男士护肤', 'mens-grooming', '美妆护肤'),
            
            # 运动户外
            ('运动户外', 'sports', None),
            ('运动鞋服', 'sportswear', '运动户外'),
            ('健身器材', 'fitness', '运动户外'),
            ('户外装备', 'outdoor', '运动户外'),
            ('骑行装备', 'cycling', '运动户外'),
            
            # 母婴玩具
            ('母婴玩具', 'baby', None),
            ('奶粉辅食', 'baby-food', '母婴玩具'),
            ('尿裤湿巾', 'diapers', '母婴玩具'),
            ('玩具益智', 'toys', '母婴玩具'),
            ('童装童鞋', 'kids-clothing', '母婴玩具'),
            
            # 图书文具
            ('图书文具', 'books', None),
            ('人文社科', 'humanities', '图书文具'),
            ('儿童读物', 'children-books', '图书文具'),
            ('教辅教材', 'textbooks', '图书文具'),
            ('文具办公', 'stationery', '图书文具'),
        ]

        categories = {}
        # 先创建顶级分类
        for name, slug, parent_name in category_data:
            if parent_name is None:
                cat, created = Category.objects.get_or_create(
                    slug=slug,
                    defaults={'name': name}
                )
                categories[name] = cat
                if created:
                    self.stdout.write(f'  + {name}')

        # 再创建子分类
        for name, slug, parent_name in category_data:
            if parent_name is not None:
                parent_cat = categories.get(parent_name)
                if parent_cat:
                    cat, created = Category.objects.get_or_create(
                        slug=slug,
                        defaults={'name': name, 'parent': parent_cat}
                    )
                    categories[name] = cat
                    if created:
                        self.stdout.write(f'    └ {name}')

        return list(categories.values())

    def create_users(self):
        """创建测试用户（包括店铺老板专用账号）"""
        # 保留 alice 和 bob
        User.objects.exclude(username__in=['alice', 'bob']).delete()

        users = list(User.objects.all())

        # 店铺老板数据：(username, display_name)
        shop_owners_data = [
            ('shop_digital',    '数码科技馆-小张'),
            ('shop_fashion',    '时尚潮流屋-Lisa'),
            ('shop_home',       '居家生活馆-老王'),
            ('shop_food',       '鲜味直达-陈掌柜'),
            ('shop_beauty',     '美妆小铺-Angel'),
            ('shop_sports',     '运动达人店-阿强'),
            ('shop_baby',       '宝贝乐园-宝妈小刘'),
            ('shop_books',      '书香阁-李老师'),
        ]

        cities = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '南京', '西安', '重庆']
        streets = ['中山路', '人民路', '建设路', '解放路', '长江路', '黄河路', '平安路', '幸福路']

        # 创建店铺老板账号
        for username, display_name in shop_owners_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'display_name': display_name,
                    'email': f'{username}@shop.com',
                    'phone': f'138{random.randint(10000000, 99999999)}',
                    'address': random.choice(cities) + ' ' + random.choice(streets) + f' {random.randint(1, 999)}号',
                }
            )
            if created:
                user.set_password('password123')
                user.save()
            if user not in users:
                users.append(user)

        # 创建普通测试用户
        first_names = ['赵', '钱', '孙', '李', '周', '吴', '郑', '王', '冯', '陈']
        last_names = ['明', '华', '芳', '伟', '娜', '强', '磊', '洋', '静', '杰']

        for i in range(20):
            username = f'user{i+1:03d}'
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'display_name': random.choice(first_names) + random.choice(last_names),
                    'email': f'{username}@example.com',
                    'phone': f'139{random.randint(10000000, 99999999)}',
                    'address': random.choice(cities) + ' ' + random.choice(streets) + f' {random.randint(1, 999)}号',
                }
            )
            if created:
                user.set_password('password123')
                user.save()
            if user not in users:
                users.append(user)

        self.stdout.write(f'  共创建 {len(users)} 个用户（含8位店铺老板）')
        return users

    def create_products(self, users, categories):
        """创建测试商品（多店铺版：商品按分类分配到不同店铺）"""
        Product.objects.all().delete()
        Shop.objects.all().delete()

        # 获取分类字典
        cat_dict = {c.name: c for c in categories}

        # ===== 创建8个店铺，每个对应一个顶级分类 =====
        # 格式：(username用户名, 店铺名, 店铺简介, 评分, 负责的分类名称列表)
        shop_configs = [
            ('shop_digital', '数码科技馆',
             '专注3C数码，正品行货，官方授权。主营手机、电脑、平板、智能设备及数码配件。',
             Decimal('4.85'),
             ['手机通讯', '电脑整机', '平板影音', '智能设备', '数码配件']),

            ('shop_fashion', '时尚潮流屋',
             '潮流前线，品质穿搭。精选男女装、鞋靴、箱包，引领时尚风向标。',
             Decimal('4.75'),
             ['潮流男装', '时尚女装', '潮流鞋靴', '精品箱包', '内衣配饰']),

            ('shop_home', '居家生活馆',
             '懂生活更懂你。大家电、小家电、家居日用一站购齐，让生活更美好。',
             Decimal('4.90'),
             ['大家电', '小家电', '居家日用', '家纺床品', '家居装饰']),

            ('shop_food', '鲜味直达',
             '产地直发，新鲜到家。全球优选生鲜食材、休闲零食、营养保健品。',
             Decimal('4.80'),
             ['新鲜水果', '海鲜肉类', '有机蔬菜', '休闲零食', '粮油调味', '营养保健']),

            ('shop_beauty', '美妆小铺',
             '美丽从这里开始。汇聚国际大牌护肤彩妆，专业美妆顾问在线服务。',
             Decimal('4.70'),
             ['面部护肤', '彩妆香氛', '个人护理', '男士护肤']),

            ('shop_sports', '运动达人店',
             '专业运动装备，激发你的潜能。跑步、健身、户外、骑行全覆盖。',
             Decimal('4.82'),
             ['运动鞋服', '健身器材', '户外装备', '骑行装备']),

            ('shop_baby', '宝贝乐园',
             '用心呵护每一个宝贝。母婴用品、益智玩具、童装童鞋，安全放心。',
             Decimal('4.88'),
             ['奶粉辅食', '尿裤湿巾', '玩具益智', '童装童鞋']),

            ('shop_books', '书香阁',
             '阅读点亮人生。正版图书、文具办公、儿童读物，知识改变命运。',
             Decimal('4.92'),
             ['人文社科', '儿童读物', '教辅教材', '文具办公']),
        ]

        # 构建店铺映射：分类名 -> Shop实例
        shop_map = {}   # 分类名 -> Shop对象
        user_map = {u.username: u for u in users}
        shops_created = []

        for username, shop_name, description, rating, cat_names in shop_configs:
            owner = user_map.get(username)
            if not owner:
                self.stdout.write(self.style.WARNING(f'  ⚠ 用户 {username} 不存在，跳过店铺 {shop_name}'))
                continue

            shop = Shop.objects.create(
                user=owner,
                shop_name=shop_name,
                description=description,
                rating=rating
            )
            shops_created.append(shop)

            for cat_name in cat_names:
                if cat_name in cat_dict:
                    shop_map[cat_name] = shop

            self.stdout.write(f'  [店铺] {shop_name} (店主: {owner.display_name}) - 负责: {", ".join(cat_names[:3])}...')

        self.stdout.write(f'\n[OK] 创建了 {len(shops_created)} 个店铺\n')

        # 商品详细数据：名称、描述、价格、库存、图片URL、商品详情
        product_data = [
            # ===== 手机通讯 =====
            {
                'name': 'iPhone 16 Pro Max 256GB',
                'description': '苹果旗舰手机，A18 Pro芯片，钛金属边框，支持5G',
                'detail': '''【核心配置】
• 芯片：A18 Pro仿生芯片，6核CPU+6核GPU
• 屏幕：6.9英寸OLED超视网膜XDR显示屏，2796×1290像素分辨率
• 存储：256GB/512GB/1TB可选
• 摄像头：4800万像素主摄+1200万超广角+1200万5倍长焦

【外观设计】
• 钛金属边框，更轻更坚固
• 沙漠色钛金属新配色
• 超瓷晶面板，更耐摔

【续航能力】
• 视频播放最长可达33小时
• 支持MagSafe无线充电
• 支持Qi2标准无线充电

【包装清单】
手机×1、Type-C充电线×1、取卡针×1、说明书×1''',
                'price': Decimal('9999.00'),
                'stock': 50,
                'category': cat_dict.get('手机通讯'),
                'image': 'https://images.unsplash.com/photo-1592750475338-74b7b21085ab?w=400&h=400&fit=crop'
            },
            {
                'name': 'iPhone 16 128GB',
                'description': '苹果新一代智能手机，A18芯片，性价比之选',
                'detail': '''【核心配置】
• 芯片：A18仿生芯片，6核CPU+5核GPU
• 屏幕：6.1英寸OLED超视网膜XDR显示屏
• 存储：128GB/256GB/512GB可选
• 摄像头：4800万主摄+1200万超广角

【产品特点】
• 支持Apple Intelligence智能助手
• 全新相机控制按钮
• 操作按钮快速切换功能

【颜色选择】
黑色、白色、粉色、深青色、群青色''',
                'price': Decimal('5999.00'),
                'stock': 80,
                'category': cat_dict.get('手机通讯'),
                'image': 'https://images.unsplash.com/photo-1510557880182-3d4d3cba35a5?w=400&h=400&fit=crop'
            },
            {
                'name': '华为 Mate 70 Pro+',
                'description': '华为旗舰手机，麒麟9100处理器，XMAGE影像',
                'detail': '''【核心配置】
• 处理器：麒麟9100旗舰芯片
• 屏幕：6.8英寸OLED曲面屏，1-120Hz自适应刷新
• 电池：5500mAh大容量电池
• 快充：100W有线+80W无线快充

【影像系统】
• 5000万像素主摄（可变光圈）
• 4800万超聚光微距长焦
• 4000万超广角摄像头
• XMAGE华为影像品牌加持

【特色功能】
• 卫星通话功能
• 隔空手势操作
• AI信息保护''',
                'price': Decimal('7999.00'),
                'stock': 60,
                'category': cat_dict.get('手机通讯'),
                'image': 'https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop'
            },
            {
                'name': '小米 15 Ultra',
                'description': '小米旗舰手机，骁龙8 Gen4，徕卡光学镜头',
                'detail': '''【核心配置】
• 处理器：骁龙8 Gen4旗舰芯片
• 屏幕：6.73英寸2K AMOLED曲面屏
• 电池：6000mAh超大容量
• 快充：120W有线+50W无线快充

【影像系统】
• 1英寸超大底主摄
• 5000万徕卡浮动长焦
• 5000万徕卡超广角
• 支持8K视频录制

【存储版本】
• 12GB+256GB
• 16GB+512GB
• 16GB+1TB''',
                'price': Decimal('6499.00'),
                'stock': 70,
                'category': cat_dict.get('手机通讯'),
                'image': 'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400&h=400&fit=crop'
            },
            {
                'name': '三星 Galaxy S25 Ultra',
                'description': '三星Galaxy旗舰，骁龙8 Gen4，2亿像素摄像头',
                'detail': '''【核心配置】
• 处理器：骁龙8 Gen4 for Galaxy专属版
• 屏幕：6.8英寸Dynamic AMOLED 2X曲面屏
• 电池：5000mAh
• 防水：IP68级防水防尘

【影像系统】
• 2亿像素主摄
• 5000万5倍长焦
• 1200万超广角
• 支持100倍Space Zoom

【S Pen触控笔】
• 内置S Pen触控笔
• 手写转文字
• 悬浮操作''',
                'price': Decimal('9699.00'),
                'stock': 45,
                'category': cat_dict.get('手机通讯'),
                'image': 'https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=400&h=400&fit=crop'
            },
            {
                'name': 'OPPO Find X8 Pro',
                'description': 'OPPO旗舰手机，天玑9400，哈苏影像',
                'detail': '''【核心配置】
• 处理器：天玑9400旗舰芯片
• 屏幕：6.78英寸AMOLED曲面屏
• 电池：5910mAh冰川电池
• 快充：80W超级闪充

【影像系统】
• 5000万哈苏主摄
• 5000万哈苏长焦（3倍光学变焦）
• 5000万超广角
• 哈苏自然色彩优化''',
                'price': Decimal('4999.00'),
                'stock': 65,
                'category': cat_dict.get('手机通讯'),
                'image': 'https://images.unsplash.com/photo-1598327105666-5b89351aff97?w=400&h=400&fit=crop'
            },

            # ===== 电脑整机 =====
            {
                'name': 'MacBook Pro 16英寸 M4 Max',
                'description': '苹果专业笔记本，M4 Max芯片，专业级性能',
                'detail': '''【核心配置】
• 芯片：Apple M4 Max（14核CPU+32核GPU）
• 内存：36GB统一内存
• 存储：1TB SSD
• 屏幕：16.2英寸Liquid Retina XDR显示屏

【专业性能】
• 支持最高8TB SSD存储
• 雷雳5接口（120Gb/s）
• SDXC卡槽
• HDMI 2.1接口

【续航能力】
• 最长可达24小时电池续航
• 140W USB-C电源适配器

【适合人群】
视频剪辑师、3D设计师、音乐制作人、软件开发者''',
                'price': Decimal('26999.00'),
                'stock': 15,
                'category': cat_dict.get('电脑整机'),
                'image': 'https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&h=400&fit=crop'
            },
            {
                'name': 'MacBook Air 15英寸 M3',
                'description': '苹果轻薄笔记本，M3芯片，超长续航',
                'detail': '''【核心配置】
• 芯片：Apple M3（8核CPU+10核GPU）
• 内存：8GB/16GB/24GB可选
• 存储：256GB/512GB/1TB/2TB SSD
• 屏幕：15.3英寸Liquid Retina显示屏

【产品特点】
• 机身厚度仅1.15厘米
• 重量仅1.51千克
• 无风扇静音设计
• 触控ID指纹解锁

【接口】
两个雷雳/USB 4端口
MagSafe 3充电接口''',
                'price': Decimal('10499.00'),
                'stock': 40,
                'category': cat_dict.get('电脑整机'),
                'image': 'https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?w=400&h=400&fit=crop'
            },
            {
                'name': '联想拯救者 Y9000P 2024',
                'description': '联想游戏笔记本，i9-14900HX，RTX4060',
                'detail': '''【核心配置】
• 处理器：Intel i9-14900HX（24核心32线程）
• 显卡：NVIDIA RTX 4060 8GB
• 内存：32GB DDR5
• 存储：1TB PCIe 4.0 SSD

【屏幕素质】
• 16英寸2.5K分辨率
• 240Hz高刷新率
• 100% sRGB色域
• 500nit高亮度

【散热系统】
霜刃Pro散热系统5.0
全区进出风设计
一键超频模式''',
                'price': Decimal('11999.00'),
                'stock': 30,
                'category': cat_dict.get('电脑整机'),
                'image': 'https://images.unsplash.com/photo-1603302576837-37561b2e2302?w=400&h=400&fit=crop'
            },
            {
                'name': 'ThinkPad X1 Carbon AI 2024',
                'description': '联想商务旗舰笔记本，酷睿Ultra7，轻薄便携',
                'detail': '''【核心配置】
• 处理器：Intel 酷睿Ultra7 155H
• 内存：32GB LPDDR5X
• 存储：1TB PCIe Gen4 SSD
• 屏幕：14英寸2.8K OLED触控屏

【商务特性】
• 机身重量仅1.12千克
• ThinkShield安全防护
• 物理摄像头开关
• 指纹识别+人脸识别

【接口丰富】
• 2×雷雳4
• 2×USB-A 3.2
• HDMI 2.1
• SIM卡槽''',
                'price': Decimal('14999.00'),
                'stock': 25,
                'category': cat_dict.get('电脑整机'),
                'image': 'https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=400&h=400&fit=crop'
            },
            {
                'name': '戴尔 XPS 15 9530',
                'description': '戴尔高端轻薄本，i7-13700H，4K触控屏',
                'detail': '''【核心配置】
• 处理器：Intel i7-13700H
• 显卡：NVIDIA RTX 4060
• 内存：32GB DDR5
• 存储：1TB SSD
• 屏幕：15.6英寸3.5K OLED触控屏

【极致视觉】
• 100% DCI-P3色域
• 400尼特亮度
• 触控操作支持
• InfinityEdge超窄边框''',
                'price': Decimal('15999.00'),
                'stock': 20,
                'category': cat_dict.get('电脑整机'),
                'image': 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop'
            },

            # ===== 平板影音 =====
            {
                'name': 'iPad Pro 13英寸 M4',
                'description': '苹果旗舰平板，M4芯片，超薄设计',
                'detail': '''【核心配置】
• 芯片：Apple M4
• 屏幕：13英寸Ultra Retina XDR显示屏
• 存储：256GB/512GB/1TB/2TB
• 厚度：仅5.1毫米

【专业创作】
• Apple Pencil Pro悬停功能
• 120Hz ProMotion自适应刷新
• Liquid Retina XDR显示技术
• nano-texture 纳米纹理玻璃（1TB/2TB可选）

【配件支持】
• 妙控键盘
• Apple Pencil Pro
• Apple Pencil USB-C''',
                'price': Decimal('11499.00'),
                'stock': 35,
                'category': cat_dict.get('平板影音'),
                'image': 'https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=400&h=400&fit=crop'
            },
            {
                'name': 'iPad Air 11英寸 M2',
                'description': '苹果轻薄平板，M2芯片，高性价比',
                'detail': '''【核心配置】
• 芯片：Apple M2
• 屏幕：11英寸Liquid Retina显示屏
• 存储：128GB/256GB/512GB/1TB
• 厚度：6.1毫米

【产品特点】
• 支持Apple Pencil Pro
• 支持Apple Pencil悬停
• 1200万摄像头
• 横向立体声扬声器

【颜色选择】
蓝色、紫色、星光色、深空灰色''',
                'price': Decimal('4799.00'),
                'stock': 60,
                'category': cat_dict.get('平板影音'),
                'image': 'https://images.unsplash.com/photo-1561154464-82e9adf32764?w=400&h=400&fit=crop'
            },
            {
                'name': '华为 MatePad Pro 13.2',
                'description': '华为旗舰平板，麒麟9000S，144Hz屏幕',
                'detail': '''【核心配置】
• 处理器：麒麟9000S
• 屏幕：13.2英寸柔性OLED
• 分辨率：2.8K
• 刷新率：144Hz

【星闪技术】
• 华为M-Pencil 第三代
• 万级压感
• 超低时延
• 星闪无线连接

【专业办公】
• PC级WPS Office
• PC级CAJViewer
• 超级中转站''',
                'price': Decimal('4999.00'),
                'stock': 45,
                'category': cat_dict.get('平板影音'),
                'image': 'https://images.unsplash.com/photo-1455234267280-1e757e20f7d9?w=400&h=400&fit=crop'
            },

            # ===== 智能设备 =====
            {
                'name': 'Apple Watch Series 10 46mm',
                'description': '苹果智能手表，S10芯片，更大屏幕',
                'detail': '''【核心配置】
• 芯片：S10 SiP芯片
• 屏幕：46mm OLED全天候显示屏
• 防水：50米防水
• 续航：约18小时

【健康监测】
• 血氧检测
• 心电图ECG
• 睡眠追踪
• 经期追踪

【运动功能】
• 运动模式100+
• 体能训练App
• 活动圆环
• 竞速路线''',
                'price': Decimal('3499.00'),
                'stock': 50,
                'category': cat_dict.get('智能设备'),
                'image': 'https://images.unsplash.com/photo-1434493789847-2f02dc6ca35d?w=400&h=400&fit=crop'
            },
            {
                'name': '华为 Watch GT 5 Pro 46mm',
                'description': '华为高端智能手表，麒麟芯片，健康管理',
                'detail': '''【核心配置】
• 屏幕：1.43英寸AMOLED
• 续航：最长14天
• 防水：5ATM+IP69K
• 材质：钛金属表壳

【健康管理】
• TruSense健康检测
• 心率、血氧、体温
• 睡眠呼吸暂停筛查
• 情绪健康监测

【运动模式】
• 100+运动模式
• 跑步路线
• 越野跑
• 骑行''',
                'price': Decimal('2488.00'),
                'stock': 55,
                'category': cat_dict.get('智能设备'),
                'image': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400&h=400&fit=crop'
            },
            {
                'name': 'AirPods Pro 2',
                'description': '苹果降噪耳机，H2芯片，自适应音频',
                'detail': '''【核心配置】
• 芯片：Apple H2
• 降噪：主动降噪2倍效果
• 空间音频：个性化空间音频
• 续航：6小时（耳机）+30小时（充电盒）

【功能特点】
• 自适应音频
• 对话感知
• 个性化音量
• 皮革保护套兼容

【操作方式】
• 按压控制
• 滑动调节音量
• "嘿 Siri"语音唤醒''',
                'price': Decimal('1899.00'),
                'stock': 120,
                'category': cat_dict.get('智能设备'),
                'image': 'https://images.unsplash.com/photo-1606220588913-b3aacb4d2f46?w=400&h=400&fit=crop'
            },
            {
                'name': '索尼 WH-1000XM5',
                'description': '索尼旗舰降噪耳机，30小时续航，极致降噪',
                'detail': '''【核心配置】
• 降噪：HD降噪处理器QN1
• 驱动单元：30mm
• 续航：30小时（降噪开）
• 充电：USB-C，3小时充满

【音质表现】
• Hi-Res认证
• DSEE Extreme音质增强
• LDAC蓝牙传输
• 360临场音效

【智能功能】
• 自适应声音控制
• 佩戴感应
• 快速提醒模式
• 多设备连接''',
                'price': Decimal('2699.00'),
                'stock': 80,
                'category': cat_dict.get('智能设备'),
                'image': 'https://images.unsplash.com/photo-1618366712010-f4ae9c647dcb?w=400&h=400&fit=crop'
            },
            {
                'name': '小米手环 9 Pro',
                'description': '小米智能手环，NFC门禁，21天续航',
                'detail': '''【核心配置】
• 屏幕：1.74英寸AMOLED
• 续航：典型使用21天
• 防水：5ATM
• 重量：仅22.5克

【健康监测】
• 心率监测
• 血氧检测
• 睡眠监测
• 压力监测

【便捷功能】
• NFC门禁卡
• NFC公交卡
• 支付宝/微信支付
• 小爱同学语音助手''',
                'price': Decimal('399.00'),
                'stock': 200,
                'category': cat_dict.get('智能设备'),
                'image': 'https://images.unsplash.com/photo-1575311373937-040b8e1fd5b6?w=400&h=400&fit=crop'
            },

            # ===== 潮流男装 =====
            {
                'name': '男士纯棉商务休闲polo衫',
                'description': '精选新疆长绒棉，珠地网眼面料，舒适透气',
                'detail': '''【面料材质】
• 面料：100%新疆长绒棉
• 克重：220g/㎡珠地网眼
• 工艺：液氨整理抗皱

【尺码选择】
S/M/L/XL/XXL/XXXL

【颜色可选】
白色、黑色、深蓝色、浅灰色、酒红色、藏青色

【洗涤说明】
• 可机洗，水温不超过40℃
• 不可漂白
• 悬挂晾干
• 中温熨烫''',
                'price': Decimal('169.00'),
                'stock': 150,
                'category': cat_dict.get('潮流男装'),
                'image': 'https://images.unsplash.com/photo-1625910513413-5fc4e5e40687?w=400&h=400&fit=crop'
            },
            {
                'name': '男士修身直筒牛仔裤',
                'description': '水洗工艺面料，柔软舒适，经典版型',
                'detail': '''【面料材质】
• 主面料：98%棉+2%氨纶
• 面料工艺：水洗做旧
• 厚度：常规

【版型特点】
• 修身直筒版型
• 中腰设计
• 经典五袋款

【尺码选择】
28/29/30/31/32/33/34/36

【颜色可选】
深蓝、水洗蓝、黑色''',
                'price': Decimal('229.00'),
                'stock': 120,
                'category': cat_dict.get('潮流男装'),
                'image': 'https://images.unsplash.com/photo-1542272604-787c3835535d?w=400&h=400&fit=crop'
            },
            {
                'name': '男士春秋休闲夹克',
                'description': '时尚工装风，多口袋设计，百搭款式',
                'detail': '''【面料材质】
• 外层：100%纯棉
• 内里：聚酯纤维
• 填充：空气棉

【设计特点】
• 立领设计
• 多口袋工装风格
• 袖口可调节
• 下摆可调节

【尺码选择】
M/L/XL/XXL

【颜色可选】
军绿色、深灰色、卡其色、黑色''',
                'price': Decimal('359.00'),
                'stock': 80,
                'category': cat_dict.get('潮流男装'),
                'image': 'https://images.unsplash.com/photo-1551028719-00167b16eac5?w=400&h=400&fit=crop'
            },
            {
                'name': '男士纯棉圆领短袖T恤',
                'description': '基础款纯棉T恤，宽松版型，多色可选',
                'detail': '''【面料材质】
• 面料：100%纯棉
• 克重：200g
• 工艺：蚀毛处理

【产品特点】
• 宽松版型
• 罗纹领口
• 双车线工艺

【尺码选择】
S/M/L/XL/XXL

【颜色可选】
白色、黑色、灰色、深蓝、绿色、橙色、紫色（共15色）''',
                'price': Decimal('89.00'),
                'stock': 300,
                'category': cat_dict.get('潮流男装'),
                'image': 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop'
            },

            # ===== 时尚女装 =====
            {
                'name': '女士法式碎花连衣裙',
                'description': '2024新款碎花裙，雪纺面料，轻盈飘逸',
                'detail': '''【面料材质】
• 主面料：100%聚酯纤维
• 内衬：雪纺
• 厚度：轻薄

【设计特点】
• V领设计
• 腰部系带
• 百褶裙摆
• 七分袖

【尺码选择】
S/M/L/XL

【颜色可选】
白色底小碎花、粉色碎花、蓝色碎花

【洗涤方式】
建议手洗，水温不超过30℃''',
                'price': Decimal('259.00'),
                'stock': 100,
                'category': cat_dict.get('时尚女装'),
                'image': 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=400&h=400&fit=crop'
            },
            {
                'name': '女士高腰直筒牛仔裤',
                'description': '显瘦高腰设计，弹力面料，百搭单品',
                'detail': '''【面料材质】
• 主面料：71%棉+26%聚酯纤维+3%氨纶
• 厚度：常规

【版型特点】
• 高腰设计
• 直筒裤型
• 前片抓皱
• 后口袋提臀

【尺码选择】
25/26/27/28/29/30/31

【颜色可选】
深蓝、水洗蓝、黑色、白色''',
                'price': Decimal('199.00'),
                'stock': 130,
                'category': cat_dict.get('时尚女装'),
                'image': 'https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=400&h=400&fit=crop'
            },
            {
                'name': '女士慵懒风针织开衫',
                'description': '秋季新款，宽松慵懒风，百搭外穿',
                'detail': '''【面料材质】
• 面料：36%羊毛+64%腈纶
• 纱线：粗棒针
• 厚度：加厚

【设计特点】
• 落肩袖设计
• 慵懒宽松版型
• 螺纹袖口和下摆
• 金属扣装饰

【尺码选择】
均码（适合S-XL）

【颜色可选】
米白色、燕麦色、驼色、灰色、黑色''',
                'price': Decimal('299.00'),
                'stock': 85,
                'category': cat_dict.get('时尚女装'),
                'image': 'https://images.unsplash.com/photo-1434389677669-e08b4cac3105?w=400&h=400&fit=crop'
            },
            {
                'name': '女士修身小西装',
                'description': '职业通勤必备，简约修身，优雅干练',
                'detail': '''【面料材质】
• 面料：95%聚酯纤维+5%氨纶
• 内里：100%聚酯纤维
• 厚度：适中

【设计特点】
• 平驳领设计
• 单排扣
• 后背开叉
• 修身版型

【尺码选择】
S/M/L/XL

【颜色可选】
黑色、深灰色、卡其色''',
                'price': Decimal('399.00'),
                'stock': 70,
                'category': cat_dict.get('时尚女装'),
                'image': 'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=400&h=400&fit=crop'
            },

            # ===== 潮流鞋靴 =====
            {
                'name': 'Nike Air Jordan 1 Low',
                'description': '经典AJ1低帮版，OG配色，复古运动风',
                'detail': '''【鞋款信息】
• 系列：Air Jordan 1 Low
• 配色：Chicago红白黑
• 年份：2024复刻

【材质配置】
• 鞋面：优质皮革
• 中底：Air Max气垫
• 外底：橡胶

【尺码选择】
US 6/6.5/7/7.5/8/8.5/9/9.5/10/10.5/11/12

【产品特点】
• 经典芝加哥配色
• 低帮设计更百搭
• 舒适缓震脚感''',
                'price': Decimal('1399.00'),
                'stock': 60,
                'category': cat_dict.get('潮流鞋靴'),
                'image': 'https://images.unsplash.com/photo-1552346154-21d32810aba3?w=400&h=400&fit=crop'
            },
            {
                'name': 'Adidas Ultraboost 24',
                'description': '阿迪达斯旗舰跑鞋，Boost中底，能量回馈',
                'detail': '''【核心技术】
• 中底：Full-length Boost
• 鞋面：PRIMEKNIT 2.0
• 外底：Continental马牌橡胶

【性能特点】
• 能量回馈超过80%
• 轻量化设计
• 透气网面
• 包裹性强

【尺码选择】
35/36/37/38/39/40/41/42/43/44

【适用场景】
跑步训练、日常通勤、健身房''',
                'price': Decimal('1299.00'),
                'stock': 75,
                'category': cat_dict.get('潮流鞋靴'),
                'image': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop'
            },
            {
                'name': '男士商务正装皮鞋',
                'description': '头层牛皮，简约三接头，舒适内里',
                'detail': '''【材质工艺】
• 鞋面：头层牛皮
• 内里：头层猪皮
• 鞋底：橡胶底
• 工艺：布莱克工艺

【设计特点】
• 经典三接头设计
• 圆头楦型
• 低跟设计
• 商务正装风格

【尺码选择】
38/39/40/41/42/43/44

【颜色可选】
黑色、棕色''',
                'price': Decimal('459.00'),
                'stock': 55,
                'category': cat_dict.get('潮流鞋靴'),
                'image': 'https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=400&h=400&fit=crop'
            },
            {
                'name': '女士优雅细跟单鞋',
                'description': '尖头细跟，优雅通勤，百搭时尚',
                'detail': '''【材质工艺】
• 鞋面：PU材质
• 内里：PU
• 鞋底：橡胶底
• 跟高：7cm

【设计特点】
• 尖头设计
• 细跟
• 浅口款式
• 一脚蹬穿法

【尺码选择】
34/35/36/37/38/39

【颜色可选】
黑色、白色、裸色、酒红色''',
                'price': Decimal('299.00'),
                'stock': 90,
                'category': cat_dict.get('潮流鞋靴'),
                'image': 'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=400&h=400&fit=crop'
            },
            {
                'name': 'New Balance 2002R',
                'description': '复古百搭老爹鞋，透气网面，舒适脚感',
                'detail': '''【核心技术】
• 中底：ABZORB缓震
• 鞋面：猪八革+网布
• 外底：N-ERGY缓震橡胶

【设计特点】
• 复古老爹鞋风格
• 厚底设计
• 透气网面
• 多元配色

【尺码选择】
36/37/38/39/40/41/42/43/44

【搭配建议】
牛仔裤、运动裤、连衣裙均可''',
                'price': Decimal('899.00'),
                'stock': 65,
                'category': cat_dict.get('潮流鞋靴'),
                'image': 'https://images.unsplash.com/photo-1551107696-a4b0c5a0d9a2?w=400&h=400&fit=crop'
            },

            # ===== 精品箱包 =====
            {
                'name': '女士时尚手提单肩包',
                'description': '简约纯色，大容量，职场通勤',
                'detail': '''【材质工艺】
• 面料：PU皮革
• 里料：涤纶
• 五金：优质合金

【规格尺寸】
• 高度：28cm
• 宽度：36cm
• 厚度：12cm
• 肩带长度：可调节

【颜色可选】
黑色、米白色、咖啡色、砖红色

【适用场景】
上班通勤、商务会议、日常出行''',
                'price': Decimal('329.00'),
                'stock': 80,
                'category': cat_dict.get('精品箱包'),
                'image': 'https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=400&h=400&fit=crop'
            },
            {
                'name': '男士商务公文包',
                'description': '头层牛皮，大容量，多功能分层',
                'detail': '''【材质工艺】
• 面料：头层牛皮
• 里料：尼龙
• 五金：铜制

【规格尺寸】
• 高度：30cm
• 宽度：42cm
• 厚度：10cm

【功能分区】
• 电脑隔层（可放15寸笔记本）
• 文件层
• 拉链暗袋
• 前置口袋

【颜色可选】
黑色、棕色''',
                'price': Decimal('599.00'),
                'stock': 45,
                'category': cat_dict.get('精品箱包'),
                'image': 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop'
            },
            {
                'name': '双肩背笔记本电脑包',
                'description': '防泼水面料，人体工学肩带，多功能收纳',
                'detail': '''【材质工艺】
• 面料：防泼水涤纶
• 里料：抗菌里布
• 肩带：人体工学设计

【规格尺寸】
• 高度：45cm
• 宽度：32cm
• 厚度：15cm
• 容量：约25L

【功能分区】
• 电脑隔层（可放16寸）
• 主袋
• 前置口袋
• 侧袋

【颜色可选】
黑色、深灰色、海军蓝''',
                'price': Decimal('189.00'),
                'stock': 100,
                'category': cat_dict.get('精品箱包'),
                'image': 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400&h=400&fit=crop'
            },

            # ===== 大家电 =====
            {
                'name': '美的变频空调 1.5匹',
                'description': '智能WiFi控制，新一级能效，冷暖两用',
                'detail': '''【基本参数】
• 匹数：1.5匹
• 能效等级：新一级能效
• 变频/定频：变频
• 冷暖类型：冷暖

【功能特点】
• 智能WiFi控制
• 自清洁功能
• 静音运行
• 独立除湿

【适用面积】
15-23平方米

【售后服务】
• 整机包修6年
• 上门安装
• 免费移机一次''',
                'price': Decimal('2599.00'),
                'stock': 40,
                'category': cat_dict.get('大家电'),
                'image': 'https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=400&h=400&fit=crop'
            },
            {
                'name': '海尔对开门冰箱 602L',
                'description': '大容量对开门，变频节能，智能控温',
                'detail': '''【基本参数】
• 总容积：602升
• 能效等级：一级能效
• 变频/定频：变频
• 颜色：银河灰

【功能分区】
• 冷藏室：382升
• 冷冻室：220升
• 变温室：支持

【技术特点】
• 风冷无霜
• 干湿分储
• 智能控温
• LED触控屏

【尺寸】
深738mm × 宽911mm × 高1775mm''',
                'price': Decimal('4999.00'),
                'stock': 25,
                'category': cat_dict.get('大家电'),
                'image': 'https://images.unsplash.com/photo-1571175443880-49e1d25b2bc5?w=400&h=400&fit=crop'
            },
            {
                'name': '小米75寸4K智能电视',
                'description': '全面屏设计，MEMC运动补偿，小爱同学',
                'detail': '''【基本参数】
• 屏幕尺寸：75英寸
• 分辨率：3840×2160（4K）
• 刷新率：120Hz
• 操作系统：MIUI TV

【画质表现】
• MEMC运动补偿
• HDR10+认证
• 杜比视界
• DCI-P3 94%广色域

【智能功能】
• 小爱同学语音控制
• 远场语音
• APP远程控制
• 海量影视资源

【接口】
HDMI 2.1 × 2、USB 2.0 × 2、网口、光纤''',
                'price': Decimal('3999.00'),
                'stock': 30,
                'category': cat_dict.get('大家电'),
                'image': 'https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=400&h=400&fit=crop'
            },
            {
                'name': '小天鹅滚筒洗衣机 10kg',
                'description': '大容量洗烘一体，银离子除菌，智能投放',
                'detail': '''【基本参数】
• 洗涤容量：10kg
• 烘干容量：7kg
• 能效等级：一级能效
• 脱水转速：1200转/分

【功能特点】
• 洗烘一体
• 银离子除菌
• 智能投放洗涤剂
• 高温筒自洁

【洗涤程序】
棉麻、羽绒、羊毛、快洗15′、超微净泡等多种程序

【尺寸】
深600mm × 宽595mm × 高850mm''',
                'price': Decimal('3999.00'),
                'stock': 28,
                'category': cat_dict.get('大家电'),
                'image': 'https://images.unsplash.com/photo-1626806787461-102c1bfaaea1?w=400&h=400&fit=crop'
            },

            # ===== 小家电 =====
            {
                'name': '戴森吹风机 HD15',
                'description': '高速吹风机，智能温控，减少热损伤',
                'detail': '''【核心技术】
• 马达：戴森V9数码马达
• 转速：110,000转/分
• 风速：41升/秒
• 智能温控：40次/秒监测

【功能特点】
• 快速干发
• 减少热损伤
• 呵护头皮
• 减少毛躁

【配件包含】
• 柔和风嘴
• 顺滑风嘴
• 造型风嘴
• 扩散风嘴

【颜色可选】
紫红色、藏青铜色、银白色''',
                'price': Decimal('2999.00'),
                'stock': 45,
                'category': cat_dict.get('小家电'),
                'image': 'https://images.unsplash.com/photo-1522338140262-f46f5913618a?w=400&h=400&fit=crop'
            },
            {
                'name': '小米空气净化器4 Pro',
                'description': '除甲醛除菌，智能联动，睡眠模式',
                'detail': '''【净化能力】
• CADR：500m³/h（颗粒物）
• CCM：P4级
• 适用面积：35-60㎡

【净化技术】
• H13级HEPA滤网
• 高效活性炭
• 抗菌涂层
• UV杀菌

【智能功能】
• 米家APP控制
• 小爱同学语音控制
• 智能联动
• 滤芯更换提醒

【噪音水平】
• 睡眠模式：33dB
• 最高档：64dB''',
                'price': Decimal('1299.00'),
                'stock': 60,
                'category': cat_dict.get('小家电'),
                'image': 'https://images.unsplash.com/photo-1585664811087-47f65abbad64?w=400&h=400&fit=crop'
            },
            {
                'name': '九阳破壁机Y1',
                'description': '多功能破壁料理机，免手洗低噪音',
                'detail': '''【基本参数】
• 功率：1200W
• 容量：1.75L
• 转速：43000转/分
• 噪音：低于75dB

【功能特点】
• 免手洗
• 热烘除菌
• 10分钟快浆
• 12小时预约

【菜单功能】
• 豆浆
• 果汁
• 米糊
• 辅食
• 绞肉
• 磨粉

【配件】
搅拌杯 × 1、研磨杯 × 1、清洁刷 × 1''',
                'price': Decimal('699.00'),
                'stock': 55,
                'category': cat_dict.get('小家电'),
                'image': 'https://images.unsplash.com/photo-1570222094114-d054a4e6e9ad?w=400&h=400&fit=crop'
            },
            {
                'name': '苏泊尔电饭煲 4L',
                'description': 'IH电磁加热，智能多功能，微压技术',
                'detail': '''【基本参数】
• 容量：4L（可煮2-8人饭）
• 功率：1200W
• 内胆：球釜内胆
• 控制方式：微电脑

【加热方式】
• IH电磁加热
• 顶部加热
• 微压蒸汽阀

【烹饪功能】
• 柴火饭
• 快速饭
• 粥/汤
• 蒸煮
• 酸奶
• 蛋糕

【特色功能】
• 24小时预约
• APP智能食谱
• 可拆洗上盖''',
                'price': Decimal('399.00'),
                'stock': 70,
                'category': cat_dict.get('小家电'),
                'image': 'https://images.unsplash.com/photo-1517080817486-cb44a53e68f1?w=400&h=400&fit=crop'
            },

            # ===== 新鲜水果 =====
            {
                'name': '智利进口车厘子 JJ级 2斤',
                'description': '空运直达，新鲜保障，单果直径28-30mm',
                'detail': '''【产品规格】
• 等级：JJ级（单果直径28-30mm）
• 净重：2斤（约500g）
• 产地：智利
• 包装：礼盒装

【品质保证】
• 空运直达
• 冷链运输
• 新鲜采摘
• 人工挑选

【食用建议】
• 清洗后即可食用
• 0-4℃冷藏保存
• 建议7天内食用完毕

【温馨提示】
水果为生鲜产品，收货后请尽快检查，如有损坏请在24小时内联系客服''',
                'price': Decimal('168.00'),
                'stock': 100,
                'category': cat_dict.get('新鲜水果'),
                'image': 'https://images.unsplash.com/photo-1528821128474-27f963b062bf?w=400&h=400&fit=crop'
            },
            {
                'name': '云南高原蓝莓 125g*4盒',
                'description': '当季新鲜，脆甜多汁，花青素丰富',
                'detail': '''【产品规格】
• 规格：125g × 4盒（共500g）
• 产地：云南
• 品种：优瑞卡
• 等级：特级

【品质特点】
• 当日采摘
• 人工挑选
• 脆甜可口
• 花青素丰富

【营养价值】
• 富含花青素
• 维生素C丰富
• 护眼明目
• 抗氧化

【保存方式】
• 0-4℃冷藏保存
• 建议3-5天内食用''',
                'price': Decimal('89.00'),
                'stock': 150,
                'category': cat_dict.get('新鲜水果'),
                'image': 'https://images.unsplash.com/photo-1498557850523-fd3d118b962e?w=400&h=400&fit=crop'
            },
            {
                'name': '泰国金枕榴莲 3-4斤',
                'description': '进口榴莲，肉厚核小，浓郁香甜',
                'detail': '''【产品规格】
• 品种：金枕榴莲
• 产地：泰国
• 重量：3-4斤（整个带壳）
• 规格：2-3房肉

【品质特点】
• 肉厚核小
• 浓郁香甜
• 奶香味足
• 口感绵密

【选购说明】
• 按重量计价
• 支持开盲盒验货
• 熟透即食

【保存方法】
• 切开：用保鲜膜包好冷藏，3天内食用
• 未开：阴凉通风处保存，熟软后冷藏''',
                'price': Decimal('199.00'),
                'stock': 50,
                'category': cat_dict.get('新鲜水果'),
                'image': 'https://images.unsplash.com/photo-1553531384-cc64ac80f931?w=400&h=400&fit=crop'
            },
            {
                'name': '四川春见耙耙柑 5斤',
                'description': '当季新鲜，爆汁甜蜜，无籽易剥',
                'detail': '''【产品规格】
• 产地：四川
• 品种：春见（耙耙柑）
• 规格：5斤（约12-15个）
• 口感：甘甜多汁

【产品特点】
• 自然成熟
• 无籽
• 皮薄易剥
• 爆汁

【营养价值】
• 维生素C
• 膳食纤维
• 果酸

【保存方式】
• 常温保存7天
• 冷藏保存15天''',
                'price': Decimal('49.00'),
                'stock': 200,
                'category': cat_dict.get('新鲜水果'),
                'image': 'https://images.unsplash.com/photo-15827e1d0e0c9?w=400&h=400&fit=crop'
            },

            # ===== 休闲零食 =====
            {
                'name': '三只松鼠坚果礼盒 1528g',
                'description': '每日坚果混合装，营养健康，送礼佳品',
                'detail': '''【产品规格】
• 净含量：1528g
• 内含：夏威夷果、碧根果、腰果、开心果等8种坚果
• 包装：礼盒装

【产品组成】
• 夏威夷果 200g
• 碧根果 200g
• 腰果 200g
• 开心果 200g
• 榛子 200g
• 核桃仁 200g
• 巴旦木 200g
• 松子 128g

【产品特点】
• 科学配比
• 独立小包装
• 锁鲜工艺

【适用场景】
年节送礼、员工福利、居家零食''',
                'price': Decimal('139.00'),
                'stock': 180,
                'category': cat_dict.get('休闲零食'),
                'image': 'https://images.unsplash.com/photo-1606923829579-0cb981a83e2e?w=400&h=400&fit=crop'
            },
            {
                'name': '德芙巧克力礼盒 312g',
                'description': '丝滑牛奶巧克力，多种口味，精致礼盒',
                'detail': '''【产品规格】
• 净含量：312g
• 口味：牛奶、榛仁、德芙纵享
• 包装：精美礼盒

【产品组成】
• 德芙丝滑牛奶巧克力 252g
• 德芙榛仁巧克力 60g

【产品特点】
• 进口可可
• 丝滑口感
• 入口即化

【保存方式】
阴凉干燥处保存，避免阳光直射''',
                'price': Decimal('89.00'),
                'stock': 120,
                'category': cat_dict.get('休闲零食'),
                'image': 'https://images.unsplash.com/photo-1549007994-cb92caebd54b?w=400&h=400&fit=crop'
            },
            {
                'name': '百草味猪肉脯 500g',
                'description': '靖江特产，传统工艺，肉香浓郁',
                'detail': '''【产品规格】
• 净含量：500g
• 产地：江苏靖江
• 口味：原味、香辣、蜜汁

【产品特点】
• 精选猪后腿肉
• 传统工艺制作
• 薄而不碎
• 肉香浓郁

【食用方式】
开袋即食，亦可微波加热

【保存方式】
常温保存，避免潮湿''',
                'price': Decimal('59.00'),
                'stock': 150,
                'category': cat_dict.get('休闲零食'),
                'image': 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=400&h=400&fit=crop'
            },

            # ===== 面部护肤 =====
            {
                'name': '兰蔻小黑瓶精华 50ml',
                'description': '肌底液修护，加速肌肤代谢，肌肤焕亮',
                'detail': '''【产品功效】
• 修护肌肤屏障
• 加速肌肤代谢
• 细滑毛孔
• 焕亮肤色

【核心成分】
• 双重酵母精粹
• 益生元成分
• 五大益生元及益生菌萃取物

【使用方法】
早晚洁面后，取适量精华液于掌心，轻拍面部至吸收

【适用肤质】
各种肤质适用，尤其适合敏感肌

【注意事项】
• 本品为化妆品，勿涂抹于伤口处
• 使用前请做过敏测试''',
                'price': Decimal('899.00'),
                'stock': 60,
                'category': cat_dict.get('面部护肤'),
                'image': 'https://images.unsplash.com/photo-1620916566398-39f1143ab7be?w=400&h=400&fit=crop'
            },
            {
                'name': '雅诗兰黛小棕瓶眼霜 15ml',
                'description': '熬夜眼霜，淡化黑眼圈，细纹隐形',
                'detail': '''【产品功效】
• 淡化黑眼圈
• 减少细纹
• 紧致眼周
• 深层修护

【核心科技】
• 时钟节律科技
• 酵母提取物
• 透明质酸

【使用方法】
• 早晚各一次
• 取绿豆大小
• 无名指轻点眼周
• 由内眼角向外眼角涂抹

【适用人群】
• 熬夜党
• 上班族
• 眼部有细纹人群''',
                'price': Decimal('599.00'),
                'stock': 80,
                'category': cat_dict.get('面部护肤'),
                'image': 'https://images.unsplash.com/photo-1611930022073-b7a4ba5fcccd?w=400&h=400&fit=crop'
            },
            {
                'name': 'SK-II神仙水 230ml',
                'description': '护肤精华露，平衡水油，肌肤透亮',
                'detail': '''【产品功效】
• 平衡肌肤水油
• 改善肌肤屏障
• 肌肤焕亮
• 收缩毛孔

【核心成分】
• 90%以上PITERA™
• 50多种氨基酸
• 维生素群
• 有机酸

【使用方法】
• 早晚各一次
• 洁面后轻拍
• 或用化妆棉湿敷

【适用肤质】
多种肤质适用，尤其适合油皮、混油皮''',
                'price': Decimal('1540.00'),
                'stock': 40,
                'category': cat_dict.get('面部护肤'),
                'image': 'https://images.unsplash.com/photo-1570194065650-d99fb4b8ccb0?w=400&h=400&fit=crop'
            },
            {
                'name': '欧莱雅复颜抗皱套装',
                'description': '日霜+晚霜组合，紧致抗皱，保湿修护',
                'detail': '''【产品规格】
• 日霜 50ml
• 晚霜 50ml
• 眼霜 15ml

【产品功效】
• 减少细纹
• 紧致肌肤
• 深层保湿
• 修护肌肤

【核心成分】
• 视黄醇Pro
• 基层提拉素
• 积雪草凝萃

【适用人群】
• 25岁以上
• 需要抗初老
• 细纹松弛肌肤''',
                'price': Decimal('399.00'),
                'stock': 90,
                'category': cat_dict.get('面部护肤'),
                'image': 'https://images.unsplash.com/photo-1556228720-195a672e8a03?w=400&h=400&fit=crop'
            },

            # ===== 运动鞋服 =====
            {
                'name': 'Nike Air Zoom Pegasus 41',
                'description': '耐克跑步鞋，React泡棉，舒适缓震',
                'detail': '''【核心技术】
• 中底：React泡棉
• 气垫：Air Zoom可视气垫
• 鞋面：网眼布+Flywire

【性能特点】
• 出色缓震
• 轻盈透气
• 稳定支撑
• 耐磨抓地

【适用场景】
日常慢跑、长距离训练、马拉松

【尺码选择】
US 6-13（男女同款）

【颜色可选】
黑、白、蓝、红等多色''',
                'price': Decimal('899.00'),
                'stock': 70,
                'category': cat_dict.get('运动鞋服'),
                'image': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop'
            },
            {
                'name': '阿迪达斯三叶草运动裤',
                'description': '经典三条纹，棉质面料，舒适运动',
                'detail': '''【面料材质】
• 主面料：100%棉
• 罗纹：棉+氨纶

【设计特点】
• 经典三条纹设计
• 锥形版型
• 抽绳松紧腰
• 侧边口袋

【尺码选择】
XS/S/M/L/XL/XXL

【颜色可选】
黑色、深灰色、藏蓝色

【适用场景】
运动健身、休闲日常、居家穿着''',
                'price': Decimal('299.00'),
                'stock': 100,
                'category': cat_dict.get('运动鞋服'),
                'image': 'https://images.unsplash.com/photo-1506629082955-511b1aa562c8?w=400&h=400&fit=crop'
            },
            {
                'name': 'Under Armour运动T恤',
                'description': '速干面料，排汗透气，高性能运动服',
                'detail': '''【面料科技】
• 面料：100%聚酯纤维
• 技术：UA Microthread
• 功能：速干排汗

【产品特点】
• 轻盈舒适
• 抗菌防臭
• 四向弹力
• 减少摩擦

【尺码选择】
S/M/L/XL/XXL

【颜色可选】
黑色、白色、蓝色、红色、灰色

【适用场景】
健身训练、运动跑步、户外运动''',
                'price': Decimal('199.00'),
                'stock': 120,
                'category': cat_dict.get('运动鞋服'),
                'image': 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&h=400&fit=crop'
            },

            # ===== 玩具益智 =====
            {
                'name': '乐高星球大战千年隼号 75257',
                'description': '星球大战主题，1365片颗粒，收藏价值高',
                'detail': '''【产品信息】
• 编号：75257
• 颗粒数：1365片
• 人仔数：8个
• 成品尺寸：33×22×10cm

【包含人仔】
• 汉·索罗
• 丘巴卡
• 莱娅公主
• C-3PO等共8个

【产品特点】
• 星球大战授权
• 细节丰富
• 可开合货舱
• 旋转炮塔

【难度等级】
适合10岁以上儿童及成人

【拼装时间】
约4-6小时''',
                'price': Decimal('999.00'),
                'stock': 45,
                'category': cat_dict.get('玩具益智'),
                'image': 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=400&h=400&fit=crop'
            },
            {
                'name': '变形金刚经典继承者级 擎天柱',
                'description': '经典角色，可变形，人形/卡车形态',
                'detail': '''【产品信息】
• 系列：经典继承者级
• 角色：擎天柱（Optimus Prime）
• 比例：继承者级

【变形设计】
• 人形高度：约15cm
• 变形步骤：适中难度
• 特色：武器可收纳

【产品特点】
• 高度还原动画形象
• 关节可动
• 附带武器装备
• 收藏展示两相宜

【适用年龄】
8岁以上''',
                'price': Decimal('399.00'),
                'stock': 60,
                'category': cat_dict.get('玩具益智'),
                'image': 'https://images.unsplash.com/photo-1558618047-3c8c76ca7d13?w=400&h=400&fit=crop'
            },
            {
                'name': '儿童磁力片积木 100件套',
                'description': '早教益智，磁力吸附，创意拼搭',
                'detail': '''【产品规格】
• 件数：100件
• 材质：ABS塑料+磁铁
• 包装：礼盒装

【包含内容】
• 三角形 × 20
• 正方形 × 60
• 五边形 × 10
• 六边形 × 10
• 磁性车轮 × 4套

【产品特点】
• 磁力吸附易拼接
• 颜色鲜艳
• 锻炼动手能力
• 培养空间想象力

【适用年龄】
3岁以上''',
                'price': Decimal('129.00'),
                'stock': 100,
                'category': cat_dict.get('玩具益智'),
                'image': 'https://images.unsplash.com/photo-1587654780291-39c9404d746b?w=400&h=400&fit=crop'
            },

            # ===== 人文社科 =====
            {
                'name': '人类简史三部曲套装',
                'description': '尤瓦尔·赫拉利作品，知识出版社，完整套装',
                'detail': '''【套装内容】
• 《人类简史》- 从动物到上帝
• 《未来简史》- 从智人到智神
• 《今日简史》- 人性与未来

【作者介绍】
尤瓦尔·赫拉利（Yuval Noah Harari）
• 以色列历史学家
• 牛津大学博士
• 耶路撒冷希伯来大学教授

【内容简介】
• 从认知革命到科技革命
• 探讨人类过去、现在与未来
• 跨学科视角解读历史

【出版社】知识出版社
【总页数】约1200页''',
                'price': Decimal('198.00'),
                'stock': 50,
                'category': cat_dict.get('人文社科'),
                'image': 'https://images.unsplash.com/photo-1512820790803-83ca734da794?w=400&h=400&fit=crop'
            },
            {
                'name': '活着（余华）',
                'description': '经典文学小说，感动无数读者，修订版',
                'detail': '''【书籍信息】
• 书名：《活着》
• 作者：余华
• 出版社：作家出版社
• 页数：191页

【内容简介】
• 讲述了农民福贵悲惨的一生
• 历经战乱、饥荒、亲人离世
• 展现了生命的韧性
• 中国当代文学经典

【获奖记录】
• 意大利格林扎纳·卡佛文学奖
• 中华优秀出版物奖

【推荐理由】
• 豆瓣9.4高分
• 销量突破2000万册
• 被译成50多种语言''',
                'price': Decimal('35.00'),
                'stock': 200,
                'category': cat_dict.get('人文社科'),
                'image': 'https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=400&h=400&fit=crop'
            },

            # ===== 营养保健 =====
            {
                'name': '汤臣倍健蛋白粉 450g',
                'description': '动植物双蛋白，增强免疫力，补充营养',
                'detail': '''【产品规格】
• 净含量：450g（约30小袋）
• 口味：原味
• 规格：罐装

【营养成分】
• 动植物双蛋白配方
• 大豆蛋白+乳清蛋白
• 蛋白质含量：80%

【功效作用】
• 增强免疫力
• 补充优质蛋白
• 改善亚健康
• 术后恢复

【适宜人群】
• 体质虚弱者
• 老年人
• 术后恢复
• 素食者

【食用方法】
• 每日1-2次
• 每次1袋
• 温水冲泡''',
                'price': Decimal('198.00'),
                'stock': 80,
                'category': cat_dict.get('营养保健'),
                'image': 'https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=400&h=400&fit=crop'
            },
            {
                'name': '燕窝 即食冰糖燕窝 70g*6瓶',
                'description': '印尼燕窝，精选燕窝丝，滋补养颜',
                'detail': '''【产品规格】
• 规格：70g × 6瓶
• 产地：印度尼西亚
• 固形物含量：≥30%

【品质保证】
• 精选白燕窝
• 人工挑毛
• 古法炖煮
• 0添加防腐剂

【功效作用】
• 滋阴润肺
• 养颜美容
• 增强免疫力
• 促进细胞分裂

【食用方法】
开盖即食，早晚各一瓶效果更佳

【保存方式】
常温保存18个月''',
                'price': Decimal('599.00'),
                'stock': 40,
                'category': cat_dict.get('营养保健'),
                'image': 'https://images.unsplash.com/photo-1583225214464-9296029427aa?w=400&h=400&fit=crop'
            },
            {
                'name': '长白山人参 50g',
                'description': '吉林长白山人参，鲜参烘干，礼盒装',
                'detail': '''【产品规格】
• 重量：50g（约2-3支）
• 产地：吉林长白山
• 年份：5年生
• 等级：优等

【品质特点】
• 林下参
• 自然生长
• 人工精选
• 传统工艺烘干

【功效作用】
• 大补元气
• 复脉固脱
• 补脾益肺
• 生津养血

【食用方法】
• 泡水：3-5片/人参段
• 炖汤：整支炖鸡/炖肉
• 泡酒

【保存方式】
冷藏保存''',
                'price': Decimal('399.00'),
                'stock': 35,
                'category': cat_dict.get('营养保健'),
                'image': 'https://images.unsplash.com/photo-1587854692152-cbe660dbde88?w=400&h=400&fit=crop'
            },
        ]

        products = []
        for i, product_info in enumerate(product_data):
            category = product_info.get('category')
            cat_name = category.name if category else '未分类'

            # 根据商品分类分配到对应的店铺
            shop = shop_map.get(cat_name)
            if not shop:
                # 如果没有匹配的店铺，使用第一个店铺
                shop = shops_created[0]

            seller = shop.user

            product = Product.objects.create(
                name=product_info['name'],
                description=product_info['description'],
                price=product_info['price'],
                category=category,
                seller=seller,
                shop=shop,
                image=product_info.get('image', f'https://picsum.photos/seed/{i+100}/400/400'),
                is_active=True
            )

            Inventory.objects.create(
                product=product,
                quantity=product_info['stock'],
            )
            
            products.append(product)
            self.stdout.write(f'  + {product.name} [{cat_name}] -> [{shop.shop_name}]')

        return products
