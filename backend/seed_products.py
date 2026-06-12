"""Seed script: insert 200 hand-crafted Chinese electronics products.
6 categories (~33 each): phones, headphones, monitors, keyboards, powerbanks, watches.
Each with brand, rating, sales_rank, specs(use_case/pros/cons/review_sentiment/review_count),
and Inventory records.
"""
import django, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
django.setup()

from products.models import Product, Category, Shop, Inventory
from django.contrib.auth import get_user_model

User = get_user_model()
seller = User.objects.get(id=1)
shop = Shop.objects.filter(status='approved').first()
if not shop:
    shop = Shop.objects.create(
        user=seller, shop_name="Admin's Electronics Store",
        status='approved', rating=4.80
    )
    print(f"Created shop: {shop.shop_name}")

# ── Ensure categories exist ──
tv_audio = Category.objects.get(name='Tv, Audio & Cameras', parent__isnull=True)
accessories = Category.objects.get(name='Accessories', parent__isnull=True)

cat_defs = [
    ("智能手机", accessories, "cn-智能手机"),
    ("耳机", tv_audio, "cn-耳机"),
    ("显示器", tv_audio, "cn-显示器"),
    ("键盘", accessories, "cn-键盘"),
    ("充电宝", accessories, "cn-充电宝"),
    ("智能手表", accessories, "cn-智能手表"),
]

categories = {}
for name, parent, slug in cat_defs:
    cat, created = Category.objects.get_or_create(
        name=name, parent=parent,
        defaults={"slug": slug, "is_active": True},
    )
    categories[name] = cat
    print(f"Category: {name} (id={cat.id}, created={created})")

# ── 200 Products ──
# Each tuple: (category_name, name, brand, price, rating, sales_rank, weight, specs_dict)
# specs_dict keys: 屏幕/芯片/容量/etc..., use_case, pros, cons, review_sentiment, review_count
# Additional: bt, nc, battery for relevant categories

products_data = []

# ════════════════════════════════════════
# 智能手机 (Phones) — 33 products
# ════════════════════════════════════════
phones = [
    ("华为 Mate 70 Pro+", "华为", 8999, 4.8, 1, 225, "6.82英寸 OLED, 麒麟9100, 16GB+1TB, 100W有线+80W无线", "商务旗舰,影像天花板", "卫星通信,鸿蒙生态,徕卡四摄", "价格较高,重量偏重", "positive", 3124),
    ("华为 Mate 70 Pro", "华为", 6999, 4.7, 2, 215, "6.82英寸 OLED, 麒麟9100, 12GB+512GB, 100W有线+80W无线", "高端商务,影像创作", "XMAGE影像,卫星通信,续航好", "无3.5mm耳机孔,稍贵", "positive", 2891),
    ("华为 Mate 70", "华为", 5499, 4.6, 5, 208, "6.7英寸 OLED, 麒麟9010, 12GB+256GB, 66W有线+50W无线", "日常旗舰,均衡体验", "手感好,影像出色,系统流畅", "充电速度不如Pro版", "positive", 2109),
    ("小米 15 Ultra", "小米", 6999, 4.7, 3, 226, "6.73英寸 2K OLED, 骁龙8 Gen4, 16GB+512GB, 90W有线+80W无线", "影像旗舰,徕卡联名", "一英寸大底,徕卡色彩,双向卫星", "机身较厚重", "positive", 2678),
    ("小米 15 Pro", "小米", 4999, 4.6, 4, 213, "6.73英寸 2K OLED, 骁龙8 Gen4, 12GB+256GB, 120W有线+50W无线", "全能旗舰,性能影像双修", "120W秒充,徕卡长焦,屏幕顶级", "续航中规中矩", "positive", 3421),
    ("小米 15", "小米", 3999, 4.5, 8, 191, "6.36英寸 1.5K OLED, 骁龙8 Gen4, 12GB+256GB, 90W有线+50W无线", "小屏旗舰,手感党首选", "单手操作舒适,徕卡三摄,小屏续航好", "小屏看视频略小", "positive", 1987),
    ("Redmi K80 Pro", "红米", 2999, 4.5, 10, 212, "6.67英寸 2K OLED, 骁龙8 Gen4, 12GB+256GB, 120W有线", "性能旗舰,游戏玩家", "120W秒充,2K直屏,性价比极高", "塑料中框,影像一般", "positive", 4521),
    ("Redmi K80", "红米", 2299, 4.4, 15, 206, "6.67英寸 2K OLED, 骁龙8 Gen3, 12GB+256GB, 90W有线", "中端性能机,日常使用", "2K屏下放,续航好,价格亲民", "拍照一般,无无线充", "positive", 3876),
    ("Redmi Note 14 Pro+", "红米", 1899, 4.3, 20, 198, "6.67英寸 1.5K OLED, 骁龙7+ Gen3, 8GB+256GB, 67W有线", "中端性价比,学生首选", "大电池,快充,屏幕好", "塑料机身,无长焦", "positive", 5234),
    ("Redmi Note 14 Pro", "红米", 1499, 4.2, 28, 195, "6.67英寸 1.5K OLED, 天玑8300, 8GB+128GB, 45W有线", "千元机皇,入门首选", "价格极低,屏幕出色,续航长", "游戏性能一般", "positive", 6432),
    ("OPPO Find X8 Pro", "OPPO", 5999, 4.6, 6, 215, "6.82英寸 2K OLED, 天玑9400, 16GB+512GB, 100W有线+50W无线", "影像旗舰,哈苏人像", "哈苏色彩,双潜望长焦,手感好", "价格略高,系统广告多", "positive", 1892),
    ("OPPO Find X8", "OPPO", 3999, 4.5, 9, 196, "6.59英寸 1.5K OLED, 天玑9400, 12GB+256GB, 80W有线", "全能次旗舰", "轻薄手感,哈苏人像,性能强劲", "无无线充电", "positive", 2356),
    ("OPPO Reno 13 Pro", "OPPO", 3299, 4.4, 18, 189, "6.7英寸 OLED, 天玑8300, 12GB+256GB, 80W有线", "拍照手机,女性用户", "自拍好,颜值高,轻薄", "性能一般,性价比不如K系列", "positive", 1789),
    ("OPPO A5 Pro", "OPPO", 1499, 4.2, 35, 185, "6.7英寸 OLED, 骁龙6 Gen1, 8GB+128GB, 45W有线", "入门机,老年用户", "大屏大电池,耐用抗摔", "性能弱,拍照一般", "neutral", 3210),
    ("vivo X200 Pro", "vivo", 5999, 4.7, 7, 223, "6.78英寸 2K OLED, 天玑9400, 16GB+512GB, 100W有线+50W无线", "影像旗舰,蔡司联名", "蔡司APO长焦,自研V4芯片,人像之王", "稍重,ColorOS需适应", "positive", 2134),
    ("vivo X200", "vivo", 3999, 4.5, 11, 202, "6.67英寸 1.5K OLED, 天玑9300+, 12GB+256GB, 90W有线", "均衡旗舰", "蔡司长焦,性能强,续航好", "无无线充,边框塑料感", "positive", 1876),
    ("vivo S20 Pro", "vivo", 2999, 4.4, 22, 186, "6.67英寸 OLED, 天玑8300, 12GB+256GB, 80W有线", "自拍神器,年轻用户", "前置柔光灯,人像美颜,轻薄", "性能中端,没长焦", "positive", 2543),
    ("iQOO 13", "iQOO", 3999, 4.5, 12, 210, "6.78英寸 2K OLED, 骁龙8 Gen4, 12GB+256GB, 120W有线", "游戏旗舰,电竞玩家", "120W闪充,2K电竞屏,散热强", "影像一般,无无线充", "positive", 3124),
    ("iQOO Neo 10", "iQOO", 2299, 4.4, 19, 203, "6.78英寸 1.5K OLED, 骁龙8 Gen3, 12GB+256GB, 120W有线", "中端电竞,游戏党", "120W快充,性能强,散热好", "塑料中框,拍照弱", "positive", 4321),
    ("荣耀 Magic7 Pro", "荣耀", 5699, 4.6, 13, 218, "6.8英寸 2K OLED, 骁龙8 Gen4, 12GB+256GB, 100W有线+80W无线", "全能旗舰,生态用户", "护眼屏,青海湖电池,卫星通信", "系统需适应,品牌溢价", "positive", 1654),
    ("荣耀 Magic7", "荣耀", 4499, 4.5, 17, 205, "6.78英寸 1.5K OLED, 骁龙8 Gen4, 12GB+256GB, 100W有线+50W无线", "次旗舰,护眼党", "绿洲护眼屏,续航强,信号好", "影像不如竞品Pro", "positive", 1987),
    ("荣耀 300 Pro", "荣耀", 2699, 4.3, 26, 195, "6.7英寸 OLED, 骁龙8s Gen3, 12GB+256GB, 100W有线+66W无线", "中端全能,女性用户", "颜值高,拍照好,同档罕见无线充", "性价比不如红米", "positive", 2310),
    ("荣耀 200 Pro", "荣耀", 2499, 4.3, 29, 199, "6.7英寸 OLED, 骁龙8s Gen3, 12GB+256GB, 100W有线+66W无线", "中端影像机", "雅顾人像,青海湖电池,屏幕好", "性能不如K系列", "positive", 2891),
    ("三星 Galaxy S25 Ultra", "三星", 9999, 4.6, 14, 232, "6.9英寸 2K OLED, 骁龙8 Gen4, 12GB+512GB, 45W有线", "安卓机皇,商务人士", "S Pen,顶级屏幕,One UI", "充电慢,价格高", "neutral", 1456),
    ("真我 GT7 Pro", "真我", 3299, 4.4, 21, 218, "6.78英寸 1.5K OLED, 骁龙8 Gen4, 12GB+256GB, 120W有线", "性价比旗舰", "120W闪充,大电池,屏幕好", "品牌认知度低,系统优化一般", "positive", 1987),
    ("真我 GT Neo 6", "真我", 1799, 4.3, 32, 193, "6.78英寸 1.5K OLED, 骁龙8s Gen3, 8GB+256GB, 120W有线", "中端性能,学生党", "120W秒充,性能强,价格低", "拍照一般,塑料机身", "positive", 3456),
    ("一加 13", "一加", 4799, 4.6, 16, 220, "6.82英寸 2K OLED, 骁龙8 Gen4, 12GB+256GB, 100W有线+50W无线", "性能旗舰,极客用户", "哈苏影像,24GB大内存,三段式", "ColorOS融合争议", "positive", 2134),
    ("一加 Ace 5 Pro", "一加", 2799, 4.4, 24, 208, "6.78英寸 1.5K OLED, 骁龙8 Gen4, 12GB+256GB, 100W有线", "中高端性能机", "骁龙旗舰芯下放,100W快充", "无无线充,长焦一般", "positive", 2876),
    ("魅族 21 Pro", "魅族", 4999, 4.4, 31, 214, "6.79英寸 2K OLED, 骁龙8 Gen3, 12GB+256GB, 80W有线+50W无线", "颜值党,魅友信仰", "白色面板,极窄边框,Flyme纯净", "发布晚,价格偏高", "neutral", 987),
    ("努比亚 Z70 Ultra", "努比亚", 4999, 4.3, 33, 228, "6.8英寸 OLED屏下, 骁龙8 Gen4, 12GB+256GB, 80W有线", "真全面屏,科技爱好者", "屏下摄像头真全面屏,35mm主摄", "系统简陋,售后少", "neutral", 876),
    ("Moto Razr 60 Ultra", "摩托罗拉", 5999, 4.2, 36, 189, "6.9英寸 OLED折叠, 骁龙8s Gen3, 12GB+512GB, 45W有线", "折叠屏尝鲜,时尚用户", "超大外屏,折叠小巧,颜值高", "折痕明显,续航一般", "neutral", 1123),
    ("华为 nova 13 Pro", "华为", 2999, 4.3, 25, 187, "6.7英寸 OLED, 麒麟8000, 12GB+256GB, 100W有线", "年轻时尚,拍照社交", "前置双摄,100W快充,鸿蒙", "无5G,性能一般", "neutral", 2345),
    ("小米 Civi 5 Pro", "小米", 2699, 4.3, 30, 182, "6.55英寸 OLED, 骁龙8s Gen3, 12GB+256GB, 67W有线", "女性用户,轻薄党", "超轻薄,徕卡前置,颜值高", "电池小,性能不激进", "positive", 1567),
]
for name, brand, price, rating, rank, wt, spec_str, use_case, pros, cons, sentiment, rev_cnt in phones:
    products_data.append(("智能手机", name, brand, price, rating, rank, wt, {
        "specs_summary": spec_str, "use_case": use_case, "pros": pros,
        "cons": cons, "review_sentiment": sentiment, "review_count": rev_cnt,
    }, None, None, False))

# ════════════════════════════════════════
# 耳机 (Headphones) — 33 products
# ════════════════════════════════════════
headphones = [
    ("索尼 WH-1000XM6", "索尼", 2999, 4.7, 1, 254, "头戴式, 30h续航, 蓝牙5.4, ANC", "商务差旅,音乐发烧", "降噪之王,LDAC,佩戴舒适", "价格高,折叠不够紧凑", "positive", 4532),
    ("索尼 WF-1000XM6", "索尼", 1999, 4.6, 3, 7, "真无线, 8h+24h, 蓝牙5.4, ANC", "通勤,日常降噪", "音质好,降噪强,佩戴稳固", "充电盒略大", "positive", 3245),
    ("Bose QC Ultra Earbuds", "Bose", 2299, 4.6, 4, 9, "真无线, 6h+18h, 蓝牙5.3, ANC", "降噪需求,飞机旅行", "降噪天花板,空间音频,佩戴好", "续航一般,不支持LDAC", "positive", 2876),
    ("Bose QC Ultra Headphones", "Bose", 2799, 4.5, 6, 252, "头戴式, 24h, 蓝牙5.3, ANC", "办公降噪,音乐欣赏", "顶级降噪,舒适,音质均衡", "价格偏高,蓝牙码率低", "positive", 2134),
    ("苹果 AirPods Pro 3", "苹果", 1899, 4.7, 2, 5, "真无线, 6h+30h, 蓝牙5.3, ANC", "苹果生态用户", "无缝切换,空间音频,通透模式", "非苹果设备体验打折", "positive", 5678),
    ("苹果 AirPods 4", "苹果", 1299, 4.4, 10, 4, "真无线半入耳, 5h+30h, 蓝牙5.3", "苹果用户日常", "佩戴无感,空间音频,H2芯片", "无降噪,音质一般", "positive", 4123),
    ("森海塞尔 Momentum 4", "森海塞尔", 2499, 4.5, 7, 293, "头戴式, 60h, 蓝牙5.2, ANC", "音质发烧友", "60h超长续航,音质极佳,佩戴舒适", "降噪不如Bose/索尼", "positive", 1987),
    ("森海塞尔 Momentum True Wireless 4", "森海塞尔", 2199, 4.4, 12, 6, "真无线, 7h+28h, 蓝牙5.4, ANC", "音质党,TWS发烧", "aptX Lossless,音质通透,做工好", "降噪中规中矩", "positive", 1345),
    ("铁三角 ATH-M50xBT2", "铁三角", 1499, 4.3, 18, 307, "头戴式, 50h, 蓝牙5.0, 无ANC", "监听,混音,音乐创作", "监听级音质,50h续航,可折叠", "无降噪,佩戴夹头", "positive", 2345),
    ("拜亚动力 Free BYRD", "拜亚动力", 1599, 4.3, 22, 7, "真无线, 8h+24h, 蓝牙5.2, ANC", "发烧友日常通勤", "拜亚调音,音质细腻,佩戴好", "App简陋,降噪中等", "neutral", 876),
    ("AKG N9 Hybrid", "AKG", 1299, 4.2, 25, 280, "头戴式, 40h, 蓝牙5.3, ANC", "日常音乐,办公", "AKG经典调音,佩戴轻,续航长", "降噪一般,塑料感", "neutral", 1234),
    ("小米 Buds 5 Pro", "小米", 899, 4.4, 8, 5, "真无线, 8h+36h, 蓝牙5.4, ANC", "米粉首选,性价比", "LDAC,11mm动圈,IP55,价格亲民", "降噪中上水平", "positive", 5678),
    ("小米 Buds 5", "小米", 399, 4.2, 19, 4, "真无线半入耳, 6h+30h, 蓝牙5.3", "学生党,预算党", "半入耳舒适,价格极低,音质尚可", "无降噪,无LDAC", "positive", 6432),
    ("华为 FreeBuds Pro 4", "华为", 1399, 4.5, 5, 6, "真无线, 7h+31h, 蓝牙5.4, ANC", "华为生态用户", "星闪连接,降噪强,鸿蒙多设备", "非华为手机功能受限", "positive", 3892),
    ("华为 FreeBuds 6i", "华为", 499, 4.2, 23, 5, "真无线, 6h+26h, 蓝牙5.3, ANC", "入门降噪,通勤", "百元降噪,佩戴舒适,轻巧", "音质一般,无LDAC", "positive", 4567),
    ("OPPO Enco X3", "OPPO", 899, 4.3, 14, 5, "真无线, 7h+28h, 蓝牙5.3, ANC", "OPPO用户,音质党", "丹拿调音,LDAC,降噪好", "通透模式一般", "positive", 2345),
    ("OPPO Enco Air 4 Pro", "OPPO", 299, 4.1, 28, 4, "真无线, 5h+20h, 蓝牙5.3, ANC", "预算降噪,学生", "百元降噪,轻巧,颜值高", "音质一般,通话一般", "positive", 3456),
    ("漫步者 NeoBuds S", "漫步者", 699, 4.3, 16, 6, "真无线, 7h+28h, 蓝牙5.2, ANC", "游戏党,低延迟", "13mm动圈,60ms低延迟,降噪好", "App功能简单", "positive", 3124),
    ("漫步者 W820NB 双金标", "漫步者", 299, 4.2, 20, 265, "头戴式, 50h, 蓝牙5.2, ANC", "办公室,学生宿舍", "Hi-Res双金标,50h续航,价格低", "塑料感强,漏音", "positive", 5432),
    ("倍思 Bowie M3", "倍思", 149, 4.1, 34, 5, "真无线, 5h+25h, 蓝牙5.2, ANC", "极致性价比", "百元级降噪,空间音效", "降噪效果有限,做工一般", "positive", 4321),
    ("韶音 OpenRun Pro 2", "韶音", 1298, 4.5, 9, 26, "骨传导开放式, 10h, 蓝牙5.3, 无ANC", "运动跑步,户外安全", "不入耳安全,10h续航,IP55防水", "音质不能和入耳比,漏音", "positive", 2891),
    ("韶音 OpenFit Air", "韶音", 999, 4.3, 17, 8, "开放式真无线, 6h+28h, 蓝牙5.3, 无ANC", "运动,办公,全天佩戴", "不入耳全天舒适,音质优于骨传导", "无降噪,不适合嘈杂环境", "positive", 1876),
    ("万魔 SonoFlow SE", "万魔", 349, 4.2, 24, 260, "头戴式, 12h, 蓝牙5.3, ANC", "办公室降噪,入门", "40mm单元,12h续航,性价比高", "外观普通,功能不多", "positive", 2109),
    ("三星 Galaxy Buds3 Pro", "三星", 1499, 4.4, 11, 5, "真无线, 7h+30h, 蓝牙5.4, ANC", "三星用户,音质党", "双单元,IP57,360环绕音", "非三星手机功能受限", "positive", 1845),
    ("声阔 Liberty 4 Pro", "声阔", 1099, 4.3, 15, 5, "真无线, 9h+36h, 蓝牙5.3, ANC", "音质发烧友,TWS", "双单元同轴,LDAC,心率监测", "品牌小众,降噪中等", "positive", 1234),
    ("JBL Tour Pro 3", "JBL", 1799, 4.3, 21, 7, "真无线, 8h+32h, 蓝牙5.3, ANC", "功能党,JBL粉丝", "屏幕充电盒,降噪好,JBL调音", "盒子大,价格偏高", "neutral", 987),
    ("Beats Studio Buds+", "Beats", 1199, 4.2, 26, 5, "真无线, 6h+24h, 蓝牙5.3, ANC", "苹果用户,颜值党", "颜值高,通透模式好,iOS兼容", "音质一般,无H2芯片", "neutral", 2109),
    ("水月雨 兰", "水月雨", 199, 4.3, 29, 4, "有线入耳, 10mm动圈, 无蓝牙", "HiFi入门,学生党", "百元HiFi天花板,调音中正", "有线不便,无麦克风", "positive", 1876),
    ("水月雨 竹2", "水月雨", 99, 4.2, 37, 4, "有线入耳, 10mm动圈, 无蓝牙", "HiFi入门极低价", "极致性价比,声音干净", "做工一般,有线不便", "positive", 2345),
    ("飞傲 FH19", "飞傲", 3999, 4.6, 13, 8, "有线入耳, 多单元混合, 无蓝牙", "发烧友退烧塞", "多单元旗舰,声场大,解析力强", "价格高,需要前端", "positive", 654),
    ("JBL Tune 770NC", "JBL", 499, 4.1, 31, 232, "头戴式, 40h, 蓝牙5.3, ANC", "学生,预算头戴", "JBL Pure Bass,40h续航,价格低", "塑料感,降噪一般", "positive", 3210),
    ("声阔 Space One", "声阔", 699, 4.2, 27, 278, "头戴式, 40h, 蓝牙5.3, ANC", "通勤,办公降噪", "降噪好,40h续航,折叠便携", "音质中规中矩", "positive", 1567),
    ("雷蛇 战锤狂鲨 V2", "雷蛇", 399, 4.0, 35, 5, "真无线, 6h+26h, 蓝牙5.2, ANC", "手游玩家,Razer粉", "RGB灯效,游戏低延迟,信仰", "音质一般,降噪弱", "neutral", 1876),
]
for name, brand, price, rating, rank, wt, spec_str, use_case, pros, cons, sentiment, rev_cnt in headphones:
    products_data.append(("耳机", name, brand, price, rating, rank, wt, {
        "specs_summary": spec_str, "use_case": use_case, "pros": pros,
        "cons": cons, "review_sentiment": sentiment, "review_count": rev_cnt,
    }, None, None, False))

# ════════════════════════════════════════
# 显示器 (Monitors) — 33 products
# ════════════════════════════════════════
monitors = [
    ("戴尔 U3224KB", "戴尔", 21999, 4.6, 3, 9200, "32英寸 6K IPS, 60Hz, USB-C 140W", "专业设计,视频剪辑", "6K分辨率,色彩极准,接口丰富", "天价,60Hz不适合游戏", "positive", 432),
    ("戴尔 U2724D", "戴尔", 3299, 4.5, 5, 6800, "27英寸 2K IPS, 120Hz, USB-C 90W", "办公,编程,设计", "120Hz高刷办公,色彩好,接口全", "HDR一般,价格稍高", "positive", 1876),
    ("戴尔 S2722QC", "戴尔", 2199, 4.3, 12, 5800, "27英寸 4K IPS, 60Hz, USB-C 65W", "办公,Mac外接", "4K清晰,Type-C一线连,价格合理", "60Hz,支架不可调高低", "positive", 2345),
    ("LG 27GP95R", "LG", 3999, 4.5, 4, 6100, "27英寸 4K Nano IPS, 160Hz, HDMI2.1", "游戏,兼顾设计", "Nano IPS色彩好,4K160Hz,HDR600", "价格较高,发热较大", "positive", 2134),
    ("LG 27GR93U", "LG", 2999, 4.4, 9, 5900, "27英寸 4K IPS, 144Hz, HDMI2.1", "电竞游戏,次世代主机", "4K144Hz性价比高,响应快", "HDR效果一般", "positive", 3210),
    ("LG 32GS95UE", "LG", 9999, 4.6, 6, 8500, "32英寸 4K OLED, 240/480Hz双模", "顶级电竞,OLED玩家", "OLED画质,双模刷新率,0.03ms", "价格昂贵,OLED烧屏风险", "positive", 987),
    ("三星 Odyssey G9 57\"", "三星", 14999, 4.4, 11, 15200, "57英寸 双4K MiniLED, 240Hz", "模拟赛车,沉浸游戏", "超宽曲面,双4K,MiniLED HDR", "太大占地方,显卡要求高", "positive", 543),
    ("三星 Odyssey G8 OLED 34\"", "三星", 6999, 4.5, 8, 5500, "34英寸 OLED 超宽, 175Hz", "游戏,影音,办公全能", "QD-OLED画质,175Hz,超宽沉浸", "文本显示有彩边,价格高", "positive", 1234),
    ("三星 ViewFinity S80UD", "三星", 3499, 4.3, 15, 6700, "27英寸 4K IPS, 60Hz, USB-C 90W", "办公,设计,Mac外接", "色彩准,USB-C一线连,KVM", "60Hz,无高刷", "positive", 876),
    ("华硕 ROG Swift PG32UCDM", "华硕", 10999, 4.6, 7, 8000, "32英寸 4K QD-OLED, 240Hz", "顶级电竞,ROG信仰", "QD-OLED,240Hz,0.03ms,HDR", "价格高昂", "positive", 765),
    ("华硕 TUF VG27AQML1A", "华硕", 2299, 4.3, 18, 6200, "27英寸 2K IPS, 260Hz", "FPS电竞,高刷党", "260Hz极高刷,ELMB,价格合理", "色彩一般,无USB-C", "positive", 2345),
    ("华硕 ProArt PA279CRV", "华硕", 3499, 4.4, 14, 5800, "27英寸 4K IPS, 60Hz, USB-C 96W", "专业设计,色彩工作", "ΔE<2,4K,USB-C,专业校准", "60Hz,不适合游戏", "positive", 1234),
    ("小米 Redmi 27\" 4K", "小米", 1499, 4.3, 10, 6200, "27英寸 4K IPS, 60Hz, Type-C 65W", "办公影音,预算党", "最便宜4K显示器,色彩不错", "支架简陋,60Hz", "positive", 4321),
    ("小米 34\" 曲面显示器", "小米", 1899, 4.2, 17, 7800, "34英寸 2K VA曲面, 144Hz", "办公多窗口,游戏", "34寸超宽,144Hz,价格低", "VA面板可视角度差", "positive", 3456),
    ("小米 G Pro 27i", "小米", 2499, 4.4, 13, 6500, "27英寸 2K MiniLED, 180Hz", "游戏,HDR影音", "MiniLED HDR1000,180Hz,性价比", "分区数量一般,光晕可见", "positive", 2891),
    ("AOC U27G3X", "AOC", 2699, 4.3, 19, 6100, "27英寸 4K IPS, 160Hz, HDMI2.1", "游戏办公兼顾", "4K160Hz,色域广,价格合理", "HDR一般,支架占地方", "positive", 2109),
    ("AOC CQ27G3Z", "AOC", 1599, 4.2, 25, 7300, "27英寸 2K VA曲面, 240Hz", "入门电竞,学生党", "240Hz,1000R曲面,价格低", "VA面板拖影,色彩一般", "positive", 3987),
    ("AOC 24G4", "AOC", 899, 4.3, 21, 3400, "23.8英寸 FHD IPS, 180Hz", "FPS电竞入门", "180Hz,IPS面板,价格极低", "1080p清晰度有限,支架简陋", "positive", 5432),
    ("明基 PD2706U", "明基", 3999, 4.5, 16, 7000, "27英寸 4K IPS, 60Hz, USB-C 90W", "专业设计,Mac用户", "M-Book色彩模式,ICC Sync,护眼", "60Hz,价格偏高", "positive", 987),
    ("明基 EW3280U", "明基", 4999, 4.3, 23, 8200, "32英寸 4K IPS, 60Hz, USB-C 60W", "影音娱乐,Mac外接", "32寸大屏,treVolo音箱,HDRi", "60Hz,无高刷", "positive", 654),
    ("优派 VX2781-4K-Pro", "优派", 2999, 4.3, 20, 6000, "27英寸 4K IPS, 150Hz, HDMI2.1", "高刷4K,性价比", "4K150Hz,色域好,价格实惠", "OSD菜单不好用", "positive", 1567),
    ("HKC 神盾 MG27Q", "HKC", 1299, 4.2, 28, 5500, "27英寸 2K Nano IPS, 180Hz", "预算游戏,学生党", "Nano IPS,180Hz,极低价", "品牌知名度低,做工一般", "positive", 3456),
    ("HKC 惠科 VG273U PRO", "HKC", 2199, 4.1, 30, 6200, "27英寸 4K IPS, 160Hz", "4K高刷入门", "4K160Hz性价比,色域OK", "做工一般,品控随机", "neutral", 2345),
    ("飞利浦 27E2F7901", "飞利浦", 2599, 4.2, 26, 6300, "27英寸 4K IPS Black, 60Hz, USB-C 96W", "办公,深色模式用户", "IPS Black对比度高,USB-C", "60Hz,亮度一般", "positive", 1234),
    ("联想 ThinkVision P27h-30", "联想", 2999, 4.3, 24, 6800, "27英寸 2K IPS, 60Hz, USB-C 100W+以太网", "企业办公,多设备", "一线连+以太网,KVM,色彩好", "60Hz,价格略高", "positive", 876),
    ("联想 Legion Y27qf-30", "联想", 1999, 4.2, 29, 6400, "27英寸 2K IPS, 240Hz", "电竞游戏,拯救者生态", "240Hz,0.5ms,色彩不错", "无USB-C,支架大", "positive", 1987),
    ("创维 F27G60U", "创维", 3499, 4.3, 22, 6100, "27英寸 4K MiniLED, 160Hz", "游戏HDR,性价比MiniLED", "MiniLED HDR1000,160Hz", "光晕可见,菜单复杂", "positive", 1234),
    ("KTC H27T22S", "KTC", 899, 4.2, 33, 5500, "27英寸 2K IPS, 170Hz", "极致预算游戏", "27寸2K170Hz只要899", "支架简陋,色域一般", "positive", 4321),
    ("KTC M27P20 Pro", "KTC", 2799, 4.3, 27, 6900, "27英寸 4K MiniLED, 160Hz", "MiniLED性价比之选", "4K MiniLED,1152分区,HDR好", "品控抽奖,固件偶尔bug", "neutral", 2345),
    ("泰坦军团 P27A6V", "泰坦军团", 3299, 4.2, 31, 7200, "27英寸 4K MiniLED, 144Hz", "游戏MiniLED", "MiniLED 576分区,4K144Hz", "品牌小众,售后一般", "neutral", 987),
    ("微星 MAG 274QRF QD E2", "微星", 2199, 4.3, 32, 6300, "27英寸 2K QD-IPS, 180Hz", "游戏综合性价比", "QD量子点色彩,180Hz,响应快", "HDR一般,红色过饱和", "positive", 1876),
    ("微星 MPG 321URX QD-OLED", "微星", 8999, 4.5, 2, 7800, "32英寸 4K QD-OLED, 240Hz", "高端电竞,OLED玩家", "QD-OLED,240Hz,顶级画质", "价格高,OLED寿命忧虑", "positive", 654),
    ("联合创新 27M2U-D", "联合创新", 1699, 4.1, 35, 6500, "27英寸 4K MiniLED, 60Hz", "预算MiniLED,Mac外接", "4K MiniLED,色域广,价格低", "60Hz,光晕明显,firmware不稳", "neutral", 1678),
]
for name, brand, price, rating, rank, wt, spec_str, use_case, pros, cons, sentiment, rev_cnt in monitors:
    products_data.append(("显示器", name, brand, price, rating, rank, wt, {
        "specs_summary": spec_str, "use_case": use_case, "pros": pros,
        "cons": cons, "review_sentiment": sentiment, "review_count": rev_cnt,
    }, None, None, False))

# ════════════════════════════════════════
# 键盘 (Keyboards) — 33 products
# ════════════════════════════════════════
keyboards = [
    ("罗技 MX Keys S", "罗技", 799, 4.5, 1, 810, "无线薄膜, USB-C/蓝牙, 全尺寸", "办公打字,多设备用户", "多设备切换,Flow跨屏,按键手感好", "是薄膜非机械,价格偏高", "positive", 4321),
    ("罗技 MX Mechanical Mini", "罗技", 1099, 4.4, 4, 612, "无线矮轴机械, USB-C/蓝牙, 84键", "办公机械,Mac用户", "矮轴手感,多设备,背光智能", "矮轴非传统机械手感", "positive", 2891),
    ("罗技 G Pro X TKL", "罗技", 1299, 4.4, 8, 910, "有线/无线机械, GX轴, 87键", "电竞FPS,竞技玩家", "Lightspeed无线低延迟,热插拔", "价格偏高,无数字区", "positive", 2134),
    ("罗技 G915 TKL", "罗技", 1499, 4.3, 11, 810, "无线矮轴机械, RGB, 87键", "无线游戏,桌面整洁", "超薄,RGB,Lightspeed无线", "键帽无法更换,价格高", "positive", 1876),
    ("雷蛇 BlackWidow V4 Pro", "雷蛇", 1999, 4.3, 9, 1120, "有线机械, 绿轴/黄轴, RGB, 全尺寸", "游戏,Razer生态", "指令拨盘,RGB神光同步,手感好", "有线,软件偶尔抽风", "positive", 2345),
    ("雷蛇 Huntsman V3 Pro", "雷蛇", 2199, 4.4, 10, 980, "有线光轴机械, 模拟光轴, RGB, 全尺寸", "竞技FPS,快速触发", "模拟光轴,快速触发,响应极快", "价格高,只有有线", "positive", 1234),
    ("雷蛇 DeathStalker V2 Pro", "雷蛇", 1399, 4.2, 18, 770, "无线矮轴机械, 光轴, RGB, 全尺寸", "无线游戏,矮轴党", "超薄无线,光轴,RGB", "矮轴手感两极分化", "neutral", 987),
    ("樱桃 MX Board 3.0S", "樱桃", 699, 4.3, 14, 1000, "有线机械, MX轴, 无光, 全尺寸", "纯打字,程序员", "原厂樱桃轴,无钢板手感,办公用", "无光,外观朴素", "positive", 3210),
    ("樱桃 MX 10.0N", "樱桃", 899, 4.2, 22, 920, "有线机械, MX轴, 白光, 全尺寸", "办公,樱桃信仰", "樱桃原厂轴,做工扎实,办公合适", "塑料感,价格偏高", "neutral", 1876),
    ("Filco Majestouch 3", "Filco", 1199, 4.5, 7, 1200, "有线机械, 樱桃MX轴, 无光, 全尺寸", "码字发烧,退烧之选", "顶级做工,键帽手感好,耐用10年+", "无光,有线,价格高", "positive", 1567),
    ("Filco Minila-R", "Filco", 999, 4.4, 15, 680, "无线机械, 樱桃MX轴, 蓝牙, 67键", "便携码字,极客", "小巧精致,Filco做工,蓝牙稳定", "布局特殊需要适应", "positive", 1234),
    ("Keychron Q1 Max", "Keychron", 1499, 4.6, 3, 1600, "无线机械, 佳达隆轴, RGB, 75%", "客制化入门,Mac党", "CNC铝坨坨,热插拔,VIA改键,Mac友好", "重量大,不便携", "positive", 2345),
    ("Keychron K8 Pro", "Keychron", 699, 4.4, 6, 1100, "无线机械, 佳达隆轴, RGB, 87键", "Mac用户,多设备办公", "QMK/VIA,多设备切换,Mac布局", "塑料壳,手感不如全铝", "positive", 3210),
    ("Keychron V1 Max", "Keychron", 599, 4.3, 17, 850, "无线机械, 佳达隆轴, RGB, 75%", "入门客制化,预算党", "热插拔,QMK/VIA,价格亲民", "塑料壳,轴体需升级", "positive", 2876),
    ("达尔优 A98 Master", "达尔优", 599, 4.2, 19, 1150, "无线机械, 天空轴, RGB, 98键", "国产客制化入门", "Gasket结构,大键调教好,三模", "品牌低端印象,软件一般", "positive", 2134),
    ("黑爵 AK820 Pro", "黑爵", 299, 4.2, 24, 780, "无线机械, 定制轴, RGB, 75%", "极致预算客制化", "Gasket,屏幕旋钮,299元超值", "无线偶尔不稳,轴体一般", "positive", 3456),
    ("VGN V87 Pro", "VGN", 299, 4.3, 13, 920, "无线机械, 草莓轴, RGB, 87键", "性价比客制化", "Gasket,热插拔,三模,超低价", "品牌售后弱,细节一般", "positive", 4321),
    ("VGN S99 Pro", "VGN", 399, 4.3, 12, 1100, "无线机械, 极光冰淇淋轴, RGB, 99键", "办公游戏兼修", "Gasket,消音填充,手感柔和", "外观设计一般", "positive", 3567),
    ("狼蛛 F99 Pro", "狼蛛", 349, 4.2, 20, 1080, "无线机械, 收割者轴, RGB, 99键", "办公打字,预算党", "Gasket,填充到位,三模,续航长", "品牌山寨感,细节粗糙", "positive", 4321),
    ("狼蛛 F87 Pro", "狼蛛", 259, 4.2, 25, 900, "无线机械, 灵动轴, RGB, 87键", "电竞入门,学生", "Gasket,热插拔,三模,超低价", "做工一般,无线干扰", "positive", 3987),
    ("Akko 3098B", "Akko", 499, 4.1, 27, 1250, "无线机械, Akko轴, RGB, 98键", "颜值党,二次元", "颜值高,ASA高度键帽,三模", "轴体手感偏轻,大键有杂音", "neutral", 2345),
    ("海盗船 K70 MAX", "海盗船", 1599, 4.3, 21, 1350, "有线机械, 磁轴, RGB, 全尺寸", "游戏,可调触发", "磁轴可调触发点,RGB,iCUE", "有线,软件庞大", "positive", 1876),
    ("海盗船 K100 Air", "海盗船", 1999, 4.1, 30, 780, "无线矮轴机械, 光轴, RGB, 全尺寸", "无线旗舰游戏", "超薄无线,光轴,RGB,iCUE", "价格极高,矮轴小众", "neutral", 876),
    ("京东京造 JZ990 V2", "京东京造", 299, 4.2, 26, 1080, "无线机械, 定制轴, RGB, 99键", "办公入门,京东粉", "Gasket,三模,售后好,价格低", "轴体手感一般", "positive", 3456),
    ("京东京造 JZ750", "京东京造", 199, 4.1, 33, 820, "无线机械, 定制轴, 白光, 75%", "预算办公,小桌面", "便宜,三模,75%紧凑", "轴体拉胯,键帽易打油", "neutral", 4321),
    ("高斯 GS3104T", "高斯", 399, 4.2, 28, 1200, "无线机械, 定制轴, RGB, 104键", "全尺寸办公党", "全尺寸,Gasket,干电池供电", "外观普通,轴体需换", "positive", 2876),
    ("雷柏 V500PRO", "雷柏", 129, 4.0, 36, 950, "有线机械, 雷柏轴, 混光, 104键", "极致预算,网咖", "最便宜机械键盘,全尺寸", "轴体差,做工差,混光灯丑", "neutral", 5432),
    ("雷柏 V700-8A", "雷柏", 249, 4.1, 31, 840, "无线机械, 雷柏轴, 白光, 84键", "无线入门,便携", "三模无线,84键紧凑,价格低", "轴体手感一般,灯光单调", "neutral", 3210),
    ("新贵 GM1000", "新贵", 449, 4.1, 29, 1150, "无线机械, 定制轴, RGB, 100键", "办公游戏均衡", "Gasket,三模,带旋钮,价格适中", "品牌知名度低", "neutral", 1876),
    ("机械革命 Z2 耀", "机械革命", 399, 4.2, 23, 1050, "无线机械, 定制轴, RGB, 87键", "游戏性价比", "热插拔,Gasket,RGB,三模", "驱动一般,细节不行", "positive", 2345),
    ("小米 机械键盘 TKL", "小米", 349, 4.1, 32, 880, "无线机械, 定制轴, 白光, 87键", "小米生态用户", "设计简洁,三模,小米联动", "轴体手感一般,功能少", "neutral", 2345),
    ("华为 智能磁吸键盘", "华为", 699, 4.0, 35, 320, "无线磁吸薄膜, 平板专用, 无背光", "华为平板用户", "磁吸牢固,平板联动,轻薄", "只适配特定平板,按键小", "neutral", 1234),
    ("多彩 M628TU", "多彩", 259, 3.9, 38, 960, "无线机械, 定制轴, 无光, 全尺寸", "预算无线,老人", "便宜三模,全尺寸,还可", "轴体拉胯,做工粗糙", "negative", 1567),
]
for name, brand, price, rating, rank, wt, spec_str, use_case, pros, cons, sentiment, rev_cnt in keyboards:
    products_data.append(("键盘", name, brand, price, rating, rank, wt, {
        "specs_summary": spec_str, "use_case": use_case, "pros": pros,
        "cons": cons, "review_sentiment": sentiment, "review_count": rev_cnt,
    }, None, None, False))

# ════════════════════════════════════════
# 充电宝 (Powerbanks) — 34 products
# ════════════════════════════════════════
powerbanks = [
    ("小米 充电宝 20000mAh 50W", "小米", 199, 4.5, 1, 430, "20000mAh, 50W PD/QC, USB-C×2+USB-A", "笔记本充电,重度使用", "50W可充笔记本,三口同充,性价比", "重量偏重,无屏幕", "positive", 8765),
    ("小米 充电宝 10000mAh 33W", "小米", 129, 4.3, 4, 220, "10000mAh, 33W PD, USB-C+USB-A", "日常通勤,应急", "轻薄便携,33W快充,口袋版", "容量偏小", "positive", 6432),
    ("小米 充电宝 5000mAh 磁吸", "小米", 149, 4.2, 10, 130, "5000mAh, 15W无线+20W有线, MagSafe", "iPhone磁吸,轻便", "磁吸牢固,无线充电,超薄", "容量小仅应急,发热", "positive", 4321),
    ("小米 超级充电宝 25000mAh 140W", "小米", 399, 4.6, 3, 560, "25000mAh, 140W PD3.1, USB-C×2+USB-A", "MacBook,多设备", "140W充MacBook,数码管显示", "重量大,飞机限制", "positive", 4321),
    ("罗马仕 sense8 20000mAh", "罗马仕", 69, 4.1, 8, 420, "20000mAh, 22.5W, USB-C+USB-A×2", "预算党,学生", "20000mAh只要69,三进三出", "快充速度慢,塑料感", "positive", 8765),
    ("罗马仕 sense9 30000mAh", "罗马仕", 99, 4.0, 12, 610, "30000mAh, 22.5W, USB-C+USB-A×3", "多人出行,长途", "30000mAh超大容量,一充四", "超重,快充慢,飞机禁止", "neutral", 6543),
    ("罗马仕 PEA40 40000mAh", "罗马仕", 129, 3.9, 22, 820, "40000mAh, 22.5W, USB-C+USB-A×3", "户外露营,多日续航", "容量巨大,价格极低", "极重,充电慢,品控一般", "neutral", 4321),
    ("罗马仕 自带线 20000mAh", "罗马仕", 79, 4.1, 15, 410, "20000mAh, 22.5W, 自带C口+Lightning线", "带线方便,旅行", "自带双线便携,数显,价格低", "线材质量一般", "positive", 5678),
    ("倍思 充电宝 10000mAh 30W 自带线", "倍思", 89, 4.3, 5, 180, "10000mAh, 30W PD, 自带USB-C+Lightning线", "日常便携,苹果安卓双持", "自带双线超方便,轻薄,30W快", "容量偏小,线材耐久度待验证", "positive", 6543),
    ("倍思 充电宝 20000mAh 65W", "倍思", 199, 4.4, 2, 450, "20000mAh, 65W PD, USB-C×2+USB-A", "笔记本充电,多设备", "65W充笔记本,显示屏,三口", "比小米50W贵,重量不轻", "positive", 4321),
    ("倍思 磁吸充电宝 5000mAh", "倍思", 119, 4.2, 13, 128, "5000mAh, 15W无线, USB-C 20W", "iPhone用户,轻便", "磁吸稳,无线充,超薄口袋", "容量小,发热明显", "positive", 3456),
    ("倍思 Blade 2 超薄 5000mAh", "倍思", 159, 4.3, 11, 135, "5000mAh, 20W PD, USB-C×2, 超薄", "卡片机,西装口袋", "超薄卡片式,精致,20W快充", "容量小,价格偏高", "positive", 2345),
    ("Anker Prime 20000mAh 100W", "Anker", 399, 4.6, 6, 450, "20000mAh, 100W PD, USB-C×2+USB-A", "品质用户,多设备快充", "100W快充,LED显示,做工精良", "价格高,重量不轻", "positive", 3456),
    ("Anker Prime 12000mAh 65W", "Anker", 299, 4.5, 9, 280, "12000mAh, 65W PD, USB-C×2", "商务差旅,轻便", "65W够用,小巧,做工顶级", "价格偏高,容量中等", "positive", 2134),
    ("Anker 733 PowerCore 10000mAh", "Anker", 249, 4.3, 16, 220, "10000mAh, 30W PD, USB-C+USB-A", "日常品质,送礼", "做工精致,充电稳定,品牌好", "性价比不如小米倍思", "positive", 2345),
    ("Anker MagGo 5000mAh", "Anker", 199, 4.2, 20, 130, "5000mAh, 15W无线, USB-C 20W, Qi2", "iPhone磁吸,品质党", "Qi2认证,磁吸牢固,做工好", "贵,容量小,发热", "neutral", 1876),
    ("绿联 磁吸无线充电宝 5000mAh", "绿联", 149, 4.2, 14, 130, "5000mAh, 15W无线+20W有线, MagSafe+支架", "iPhone磁吸,追剧", "磁吸+支架,追剧方便,做工好", "容量小,价格中规中矩", "positive", 2345),
    ("绿联 充电宝 20000mAh 65W", "绿联", 179, 4.3, 7, 440, "20000mAh, 65W PD, USB-C×2+USB-A", "多设备,性价比", "65W充笔记本,三口同充,价格好", "外观朴素,无屏幕", "positive", 3210),
    ("绿联 充电宝 145W 25000mAh", "绿联", 349, 4.4, 17, 550, "25000mAh, 145W PD3.1, USB-C×2+USB-A", "MacBook Pro重度", "145W可充16寸MacBook,数显", "重量大,价格较高", "positive", 1876),
    ("华为 充电宝 12000mAh 66W", "华为", 299, 4.4, 18, 260, "12000mAh, 66W SCP, USB-C+USB-A", "华为手机用户", "66W华为超级快充,双向快,做工好", "非华为设备降速,价格偏高", "positive", 2345),
    ("华为 充电宝 10000mAh 40W", "华为", 199, 4.2, 21, 210, "10000mAh, 40W SCP, USB-C+USB-A", "华为用户日常", "华为超级快充,双向,便携", "非华为手机速度一般", "positive", 1987),
    ("品胜 充电宝 20000mAh 22.5W", "品胜", 79, 4.0, 19, 410, "20000mAh, 22.5W, USB-C+USB-A×2", "预算党,随手买", "便宜,自营品牌,品胜售后", "快充慢,塑料感,无快充协议", "neutral", 4321),
    ("品胜 充电宝 10000mAh 自带线", "品胜", 69, 4.0, 26, 185, "10000mAh, 20W, 自带Lightning+USB-C线", "苹果用户预算", "自带双线,便宜,方便", "做工一般,充电慢", "neutral", 3456),
    ("羽博 EN300WLPD 30000mAh", "羽博", 159, 4.1, 24, 640, "30000mAh, 65W PD, USB-C×2+USB-A×2", "户外露营,团队出行", "大容量65W,四口输出,带手电", "体积大,重,飞机禁止", "positive", 2345),
    ("羽博 充电宝 10000mAh 20W", "羽博", 59, 4.0, 29, 195, "10000mAh, 20W PD, USB-C+USB-A", "便宜应急", "超便宜,轻巧,基本够用", "20W充得慢,做工一般", "neutral", 4321),
    ("台电 C30 Pro 30000mAh", "台电", 119, 3.9, 25, 620, "30000mAh, 22.5W, USB-C+USB-A×3", "大容量预算", "30000mAh便宜大碗", "快充慢,品牌一般", "neutral", 3210),
    ("台电 T100 10000mAh 超薄", "台电", 79, 3.9, 30, 170, "10000mAh, 18W, USB-C+USB-A", "超薄便携,备用", "超薄名片设计,价格低", "充电慢,做工一般", "neutral", 2345),
    ("纽曼 A501 50000mAh", "纽曼", 169, 3.8, 32, 1050, "50000mAh, 22.5W, USB-C+USB-A×4", "极限续航,户外", "50000mAh超大容量", "极其笨重,充电极慢", "neutral", 1234),
    ("公牛 充电宝 10000mAh 22.5W", "公牛", 109, 4.1, 23, 210, "10000mAh, 22.5W, USB-C+USB-A", "安全党,公牛品牌", "公牛安全品质,新国标,做工好", "快充一般,价格偏高", "positive", 2345),
    ("爱国者 充电宝 20000mAh 22.5W", "爱国者", 89, 4.0, 27, 415, "20000mAh, 22.5W, USB-C+USB-A×2", "情怀品牌,日常", "老牌品质,性价比不错", "快充慢,外观老气", "neutral", 3456),
    ("飞利浦 DLP2216 20000mAh", "飞利浦", 129, 4.0, 28, 425, "20000mAh, 22.5W, USB-C+USB-A×2", "飞利浦品牌粉", "飞利浦品质,售后有保障", "快充慢,性价比一般", "neutral", 1876),
    ("紫米 20号 20000mAh 65W", "紫米", 179, 4.3, 31, 440, "20000mAh, 65W PD, USB-C×2+USB-A", "小米生态,品质", "小米生态链做工,65W,可靠", "品牌独立后售后未知", "neutral", 1567),
    ("闪极 130W 20000mAh", "闪极", 349, 4.4, 33, 460, "20000mAh, 130W PD, USB-C×2+USB-A, 透明", "极客,颜值党", "透明探索版设计,130W,数显", "价格高,小众品牌", "positive", 987),
    ("酷态科 15号 20000mAh 165W", "酷态科", 329, 4.3, 34, 470, "20000mAh, 165W PD3.1, USB-C×2+USB-A", "小米生态,多设备", "165W超级闪充,数显屏幕", "品牌知名度低", "positive", 765),
]
for name, brand, price, rating, rank, wt, spec_str, use_case, pros, cons, sentiment, rev_cnt in powerbanks:
    products_data.append(("充电宝", name, brand, price, rating, rank, wt, {
        "specs_summary": spec_str, "use_case": use_case, "pros": pros,
        "cons": cons, "review_sentiment": sentiment, "review_count": rev_cnt,
    }, None, None, False))

# ════════════════════════════════════════
# 智能手表 (Watches) — 34 products
# ════════════════════════════════════════
watches = [
    ("苹果 Watch Series 10", "苹果", 2999, 4.6, 1, 42, "1.9英寸 OLED, 18h续航, WR50, 心率/血氧/ECG/体温", "苹果生态,健康管理", "更大屏更薄,ECG,车祸检测,生态", "续航仅18h,仅iPhone", "positive", 5432),
    ("苹果 Watch Ultra 3", "苹果", 6499, 4.7, 2, 61, "1.92英寸 OLED, 36h续航, WR100, 双频GPS", "户外探险,潜水", "顶级户外,潜水电脑,双频GPS", "价格极高,重,表盘太大", "positive", 2345),
    ("苹果 Watch SE 3", "苹果", 1999, 4.3, 5, 33, "1.7英寸 OLED, 18h续航, WR50, 心率/跌倒检测", "入门苹果手表", "价格相对亲民,核心功能全", "无息屏显示,无ECG", "positive", 4321),
    ("华为 Watch GT 4 46mm", "华为", 1488, 4.5, 4, 48, "1.43英寸 AMOLED, 14天续航, 5ATM, 心率/血氧/体温/GPS", "商务运动兼顾", "14天续航,高尔夫模式,健康全面", "非鸿蒙手机功能受限", "positive", 3456),
    ("华为 Watch GT 4 41mm", "华为", 1288, 4.4, 8, 35, "1.32英寸 AMOLED, 7天续航, 5ATM, 心率/血氧/体温/GPS", "女性用户,日常", "小巧精致,穿搭好看,健康功能全", "续航比46mm短", "positive", 2345),
    ("华为 Watch Ultimate", "华为", 5999, 4.6, 3, 76, "1.5英寸 AMOLED, 14天续航, 10ATM潜水, 北斗卫星", "极限户外,潜水", "100米潜水,卫星消息,液态金属", "价格高,非户外用不上", "positive", 1234),
    ("华为 Watch D2", "华为", 2699, 4.3, 12, 55, "1.43英寸 AMOLED, 7天, IP68, 血压/ECG/心率", "中老年,血压监测", "血压测量,ECG,医疗级功能", "表带充气泵,佩戴一般", "positive", 1876),
    ("小米 Watch S4", "小米", 999, 4.4, 6, 52, "1.43英寸 AMOLED, 15天, 5ATM, 心率/血氧/压力/eSIM", "小米生态,性价比", "eSIM独立通话,15天续航,HyperOS", "第三方App少", "positive", 4321),
    ("小米 Watch S4 Sport", "小米", 1399, 4.3, 10, 48, "1.43英寸 AMOLED, 15天, 5ATM, eSIM+双频GPS", "运动爱好者,米粉", "双频GPS,钛合金,户外运动好", "比标准版贵,功能差别不大", "positive", 2134),
    ("小米 手环 9 Pro", "小米", 399, 4.2, 11, 25, "1.74英寸 AMOLED, 14天, 5ATM, 心率/血氧/睡眠", "入门健康,学生", "价格极低,14天续航,轻薄", "无GPS,无eSIM,功能基础", "positive", 5678),
    ("小米 手环 9", "小米", 239, 4.2, 16, 15, "1.62英寸 AMOLED, 16天, 5ATM, 心率/血氧", "入门运动,送人", "超低价,续航长,基础够用", "屏幕小,无GPS", "positive", 6543),
    ("OPPO Watch X", "OPPO", 1399, 4.4, 9, 49, "1.43英寸 AMOLED, 4天全智能/14天轻智能, 5ATM, 心率/血氧/ECG", "OPPO生态,均衡", "双芯双系统,ECG,流畅体验", "全智能续航短", "positive", 2345),
    ("OPPO Watch 4 Pro", "OPPO", 1999, 4.3, 15, 52, "1.91英寸 AMOLED, 5天全智能/14天轻智能, 5ATM, ECG", "安卓旗舰手表", "双芯,ECG,大屏,独立通信", "价格偏高,表盘厚", "positive", 1876),
    ("荣耀 手表 5", "荣耀", 699, 4.2, 13, 45, "1.43英寸 AMOLED, 14天, 5ATM, 心率/血氧/GPS/eSIM", "预算智能手表", "14天续航,eSIM,价格亲民", "质感一般,功能不如旗舰", "positive", 4321),
    ("荣耀 手表 GS 4", "荣耀", 999, 4.3, 17, 44, "1.43英寸 AMOLED, 14天, 5ATM, 心率/血氧/GPS", "商务用户", "经典设计,14天续航,表盘丰富", "无eSIM,生态不如华为", "positive", 2345),
    ("Amazfit T-Rex 3", "Amazfit", 1799, 4.5, 7, 66, "1.5英寸 AMOLED, 27天, 10ATM/军规, 双频GPS/气压/指南针", "户外硬核,探险", "27天续航,军规认证,100米防水", "外观硬核不适合日常", "positive", 1987),
    ("Amazfit Cheetah Pro", "Amazfit", 1499, 4.3, 18, 40, "1.45英寸 AMOLED, 14天, 5ATM, 双频GPS/跑步教练", "跑者,马拉松", "专业跑步数据,双频GPS,Zepp", "品牌知名度低,市场小", "positive", 1234),
    ("Amazfit Balance", "Amazfit", 1399, 4.3, 19, 36, "1.5英寸 AMOLED, 14天, 5ATM, 身心平衡分析", "健康管理,日常", "身心平衡,AI教练,轻薄", "无eSIM,运动专业度不够", "positive", 987),
    ("三星 Galaxy Watch 7", "三星", 1999, 4.3, 14, 34, "1.5英寸 AMOLED, 2天, 5ATM+IP68, ECG/血压/体温", "三星生态用户", "Wear OS,ECG/血压,旋转表圈", "续航仅2天,非三星手机受限", "positive", 1876),
    ("三星 Galaxy Watch Ultra", "三星", 3999, 4.4, 20, 60, "1.5英寸 AMOLED, 3天, 10ATM, 双频GPS/钛合金", "三星旗舰户外", "钛合金,潜水,双频GPS", "价格高,续航仍短", "neutral", 876),
    ("佳明 Forerunner 965", "佳明", 3999, 4.6, 21, 52, "1.4英寸 AMOLED, 23天/31h GPS, 5ATM, 专业运动", "严肃跑者,铁三", "专业运动数据,AMOLED,续航", "价格高,日常功能少", "positive", 1234),
    ("佳明 Fenix 8", "佳明", 5999, 4.5, 23, 64, "1.4英寸 MIP/AMOLED, 21天/85h GPS, 10ATM, 全运动", "极限户外,多运动", "全运动覆盖,超长GPS续航,地图", "价格极高,日常功能少", "positive", 987),
    ("佳明 Venu 3", "佳明", 2999, 4.3, 24, 45, "1.4英寸 AMOLED, 14天, 5ATM, 进阶健康/运动", "运动+健康+日常", "AMOLED,健康全面,运动专业", "价格偏高,智能功能弱", "positive", 876),
    ("颂拓 Vertical", "颂拓", 4999, 4.3, 29, 72, "1.4英寸 MIP, 30天/140h GPS, 10ATM, 地图导航", "极限户外,探险家", "140h GPS续航,离线地图,MIP常显", "小众,无AMOLED,重", "positive", 543),
    ("颂拓 9 Peak Pro", "颂拓", 3999, 4.2, 33, 55, "1.2英寸 MIP, 21天/40h GPS, 10ATM, 钛合金", "极限运动,轻薄户外", "钛合金轻薄,40h GPS,防水好", "屏幕小,MIP,无地图", "neutral", 432),
    ("出门问问 TicWatch Atlas Pro", "出门问问", 2499, 4.1, 25, 50, "1.43英寸 AMOLED, 2天/45天基础, IP68, Wear OS", "Wear OS旗舰,均衡", "Wear OS,双屏,长续航模式", "续航短,系统更新慢", "neutral", 765),
    ("小天才 Z10", "小天才", 1999, 4.2, 26, 48, "1.78英寸 AMOLED, 3天, IPX8, 4G通话+GPS+双摄", "儿童安全,家长", "精准定位,视频通话,碰一碰交友", "只有儿童用,价格高", "positive", 3456),
    ("小天才 Z9", "小天才", 1499, 4.1, 27, 46, "1.6英寸 AMOLED, 4天, IPX8, 4G通话+GPS+单摄", "儿童入门,安全", "定位准,通话清晰,家长放心", "功能比Z10少", "positive", 4321),
    ("小米 儿童手表 6C", "小米", 599, 4.1, 28, 42, "1.52英寸 TFT, 3天, IPX8, 4G通话+GPS+摄像头", "儿童预算,入门", "价格低,定位准,通话好", "屏幕差,功能基础", "positive", 5432),
    ("酷派 小V 8", "酷派", 499, 3.9, 35, 40, "1.44英寸 TFT, 2天, IPX7, 4G通话+GPS", "儿童超预算", "超低价儿童手表,基本功能有", "做工差,定位不准", "neutral", 2345),
    ("一加 Watch 3", "一加", 1499, 4.2, 30, 50, "1.43英寸 AMOLED, 4天/14天轻智能, 5ATM, 心率/GPS", "一加生态,安卓", "Wear OS,流畅,设计简约", "续航中规中矩", "neutral", 987),
    ("一加 Watch 2R", "一加", 999, 4.1, 31, 39, "1.43英寸 AMOLED, 2天/12天, IP68, 心率/GPS", "一加入门表", "价格亲民,Wear OS,设计", "续航短,功能少", "neutral", 765),
    ("Nothing Watch Pro 2", "Nothing", 1299, 4.2, 32, 42, "1.5英寸 AMOLED, 3天/14天, IP68, 心率/ECG", "颜值党,Nothing粉", "透明设计独特,ECG,灯效", "需要适配安卓,小众", "positive", 876),
    ("魅族 Watch 4", "魅族", 899, 3.9, 36, 35, "1.43英寸 AMOLED, 3天, IP68, 心率/血氧/GPS", "魅族生态,颜值", "设计好看,Flyme联动", "续航短,功能一般", "neutral", 654),
]
for name, brand, price, rating, rank, wt, spec_str, use_case, pros, cons, sentiment, rev_cnt in watches:
    products_data.append(("智能手表", name, brand, price, rating, rank, wt, {
        "specs_summary": spec_str, "use_case": use_case, "pros": pros,
        "cons": cons, "review_sentiment": sentiment, "review_count": rev_cnt,
    }, None, None, False))


# ── Normalize specs ──

def _normalize_specs(specs: dict) -> dict:
    """Convert specs fields to correct types for the new schema."""
    specs = dict(specs)  # copy
    # pros/cons: comma-string → list
    for key in ('pros', 'cons'):
        val = specs.get(key, '')
        if isinstance(val, str):
            specs[key] = [s.strip() for s in val.split(',') if s.strip()]
    # review_sentiment: string → float
    sentiment = specs.get('review_sentiment', 'positive')
    if isinstance(sentiment, str):
        specs['review_sentiment'] = {
            'positive': 0.85, 'neutral': 0.50, 'negative': 0.15
        }.get(sentiment.lower(), 0.50)
    # review_count: ensure int
    specs['review_count'] = int(specs.get('review_count', 0))
    # review_text: generate 3 Chinese review sentences from pros/cons
    if 'review_text' not in specs:
        pros_list = specs.get('pros', [])
        cons_list = specs.get('cons', [])
        reviews = []
        if pros_list:
            reviews.append(f"{pros_list[0]}，真的很不错")
        else:
            reviews.append("产品质量很好，值得购买")
        if len(pros_list) > 1:
            reviews.append(f"{pros_list[1]}，体验很好")
        elif cons_list:
            reviews.append(f"除了{cons_list[0]}，其他都挺满意")
        else:
            reviews.append("使用体验不错，推荐购买")
        if cons_list:
            reviews.append(f"{cons_list[0]}，希望能改进")
        else:
            reviews.append("整体满意，会回购")
        specs['review_text'] = reviews
    return specs


# ── Insert products ──
print(f"\nInserting {len(products_data)} products...")
count = 0
for cat_name, name, brand, price, rating, rank, wt, specs, bt, nc, battery in products_data:
    cat = categories[cat_name]
    specs = _normalize_specs(specs)
    product = Product.objects.create(
        name=name, description=f"{brand} {name} — {specs.get('use_case', '')}",
        price=price, category=cat, seller=seller, shop=shop, is_active=True,
        brand=brand, rating=rating, sales_rank=rank, weight=wt,
        specs=specs,
        battery_life=battery,
        bluetooth_version=bt,
        noise_cancellation=nc,
    )
    # Create inventory record with randomized realistic stock
    if rank <= 5:
        stock = random.randint(80, 300)
    elif rank <= 15:
        stock = random.randint(40, 150)
    elif rank <= 30:
        stock = random.randint(15, 80)
    else:
        stock = random.randint(3, 30)
    Inventory.objects.create(product=product, quantity=stock)
    count += 1
    if count % 20 == 0:
        print(f"  [{count:3d}/{len(products_data)}] inserted...")

print(f"\nDone: {count} products inserted with inventory records.")

# ── Summary ──
from collections import Counter
cat_counts = Counter()
for cat_name, *_ in products_data:
    cat_counts[cat_name] += 1

print("\n=== SUMMARY ===")
for cat_name, cnt in sorted(cat_counts.items()):
    print(f"  {cat_name}: {cnt} products")
print(f"  TOTAL: {count} products")
