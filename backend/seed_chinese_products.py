"""Seed script: insert 50 Chinese products with full specs."""
import django, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
django.setup()

from products.models import Product, Category, Shop
from django.contrib.auth import get_user_model

User = get_user_model()
seller = User.objects.get(id=1)
shop = Shop.objects.filter(status='approved').first()

# ── Create Chinese subcategories ──
parent_map = {
    "蓝牙耳机": "Tv, Audio & Cameras",
    "智能手机": "Accessories",
    "智能手表": "Accessories",
    "蓝牙音箱": "Tv, Audio & Cameras",
    "笔记本电脑": "Accessories",
    "平板电脑": "Accessories",
    "充电宝": "Accessories",
}

categories = {}
for name, parent_name in parent_map.items():
    parent = Category.objects.get(name=parent_name, parent__isnull=True)
    cat, created = Category.objects.get_or_create(
        name=name, parent=parent,
        defaults={"slug": f"cn-{name}", "is_active": True},
    )
    categories[name] = cat
    print(f"Category: {name} (id={cat.id}, created={created})")

# ── Products data ──
products_data = [
    # ── 蓝牙耳机 (8 products) ──
    {"cat": "蓝牙耳机", "name": "小米Buds 5 Pro", "price": 899, "battery": 8, "bt": "5.3", "nc": True, "wt": 48, "specs": {"防水":"IP55","驱动单元":"11mm","编码":"LDAC/AAC/SBC"}, "desc": "小米旗舰真无线降噪耳机，11mm动圈单元，LDAC高清编码，8小时续航搭配充电盒可达36小时。"},
    {"cat": "蓝牙耳机", "name": "华为FreeBuds 6i", "price": 699, "battery": 6, "bt": "5.2", "nc": True, "wt": 42, "specs": {"防水":"IP54","驱动单元":"10mm","编码":"AAC/SBC"}, "desc": "华为入门级主动降噪耳机，轻巧舒适，适合日常通勤使用。"},
    {"cat": "蓝牙耳机", "name": "漫步者NeoBuds S", "price": 499, "battery": 7, "bt": "5.2", "nc": True, "wt": 55, "specs": {"防水":"IPX5","驱动单元":"13mm","低延迟":"游戏模式60ms"}, "desc": "漫步者游戏低延迟降噪耳机，13mm大动圈，60ms超低延迟，适合手游玩家。"},
    {"cat": "蓝牙耳机", "name": "OPPO Enco Air4", "price": 299, "battery": 5, "bt": "5.3", "nc": False, "wt": 38, "specs": {"防水":"IPX4","驱动单元":"12.4mm","特色":"空间音效"}, "desc": "OPPO半入耳式轻量耳机，12.4mm超大动圈，空间音效，性价比之选。"},
    {"cat": "蓝牙耳机", "name": "韶音OpenRun Pro", "price": 1298, "battery": 10, "bt": "5.1", "nc": False, "wt": 26, "specs": {"类型":"骨传导","防水":"IP55","特色":"不塞耳朵","续航":"10h"}, "desc": "韶音旗舰骨传导运动耳机，不入耳设计，跑步骑行更安全，10小时超长续航。"},
    {"cat": "蓝牙耳机", "name": "倍思Bowie M2", "price": 129, "battery": 5, "bt": "5.2", "nc": True, "wt": 45, "specs": {"防水":"IPX5","编码":"AAC","特色":"百元级降噪"}, "desc": "倍思百元级主动降噪耳机，性价比天花板，学生党首选。"},
    {"cat": "蓝牙耳机", "name": "三星Galaxy Buds3 Pro", "price": 1499, "battery": 7, "bt": "5.4", "nc": True, "wt": 52, "specs": {"防水":"IP57","驱动单元":"双单元","编码":"SSC/AAC/SBC","特色":"360环绕音"}, "desc": "三星旗舰级降噪耳机，双单元驱动，IP57防水防尘，360度环绕音效。"},
    {"cat": "蓝牙耳机", "name": "万魔SonoFlow SE", "price": 349, "battery": 12, "bt": "5.3", "nc": True, "wt": 260, "specs": {"类型":"头戴式","防水":"IPX4","驱动单元":"40mm","特色":"头戴降噪"}, "desc": "万魔头戴式降噪耳机，40mm大单元，12小时续航，适合办公室和家中使用。"},

    # ── 智能手机 (7 products) ──
    {"cat": "智能手机", "name": "小米14 Ultra", "price": 6499, "battery": None, "bt": "5.4", "nc": False, "wt": 224, "specs": {"屏幕":"6.73英寸2K OLED","芯片":"骁龙8 Gen3","内存":"16GB+512GB","快充":"90W有线+80W无线"}, "desc": "小米年度影像旗舰，徕卡四摄系统，骁龙8 Gen3旗舰芯片，双向卫星通信。"},
    {"cat": "智能手机", "name": "华为Mate 70 Pro", "price": 6999, "battery": None, "bt": "5.4", "nc": False, "wt": 215, "specs": {"屏幕":"6.82英寸OLED","芯片":"麒麟9100","内存":"12GB+512GB","快充":"100W有线+80W无线"}, "desc": "华为商务旗舰，麒麟9100芯片，鸿蒙系统，卫星通信，XMAGE影像。"},
    {"cat": "智能手机", "name": "OPPO Find X8", "price": 3999, "battery": None, "bt": "5.4", "nc": False, "wt": 193, "specs": {"屏幕":"6.7英寸OLED","芯片":"天玑9400","内存":"12GB+256GB","快充":"80W有线"}, "desc": "OPPO全能影像旗舰，天玑9400，哈苏人像模式，轻薄手感。"},
    {"cat": "智能手机", "name": "vivo X200", "price": 3499, "battery": None, "bt": "5.4", "nc": False, "wt": 198, "specs": {"屏幕":"6.67英寸OLED","芯片":"天玑9300","内存":"12GB+256GB","快充":"80W有线"}, "desc": "vivo影像性能双修旗舰，蔡司超级长焦，天玑9300旗舰性能。"},
    {"cat": "智能手机", "name": "Redmi K80 Pro", "price": 2499, "battery": None, "bt": "5.4", "nc": False, "wt": 208, "specs": {"屏幕":"6.67英寸2K","芯片":"骁龙8 Gen3","内存":"12GB+256GB","快充":"120W有线"}, "desc": "Redmi性能旗舰，骁龙8 Gen3，120W超级快充，2K直屏，性价比之王。"},
    {"cat": "智能手机", "name": "荣耀200 Pro", "price": 2699, "battery": None, "bt": "5.3", "nc": False, "wt": 199, "specs": {"屏幕":"6.7英寸OLED","芯片":"骁龙8s Gen3","内存":"12GB+256GB","快充":"100W有线+66W无线"}, "desc": "荣耀主打影像和续航，骁龙8s Gen3，100W快充，5200mAh大电池。"},
    {"cat": "智能手机", "name": "真我GT6", "price": 1999, "battery": None, "bt": "5.4", "nc": False, "wt": 195, "specs": {"屏幕":"6.78英寸OLED","芯片":"骁龙8 Gen3","内存":"8GB+128GB","快充":"120W有线"}, "desc": "真我性能旗舰，最便宜的骁龙8 Gen3机型，120W快充，性价比之选。"},

    # ── 智能手表 (6 products) ──
    {"cat": "智能手表", "name": "华为Watch GT4", "price": 1488, "battery": None, "bt": "5.2", "nc": False, "wt": 48, "specs": {"屏幕":"1.43英寸AMOLED","续航":"14天","防水":"5ATM","传感器":"心率/血氧/体温/GPS"}, "desc": "华为经典圆形智能手表，14天长续航，高尔夫模式，健康管理全面升级。"},
    {"cat": "智能手表", "name": "小米Watch S4", "price": 999, "battery": None, "bt": "5.3", "nc": False, "wt": 52, "specs": {"屏幕":"1.43英寸AMOLED","续航":"15天","防水":"5ATM","传感器":"心率/血氧/压力/eSIM"}, "desc": "小米新款智能手表，eSIM独立通话，15天长续航，HyperOS生态联动。"},
    {"cat": "智能手表", "name": "苹果Watch Series 10", "price": 2999, "battery": None, "bt": "5.3", "nc": False, "wt": 42, "specs": {"屏幕":"1.9英寸OLED","续航":"18h","防水":"WR50","传感器":"心率/血氧/ECG/体温"}, "desc": "苹果最新款智能手表，更大屏幕，更薄机身，ECG心电图，车祸检测。"},
    {"cat": "智能手表", "name": "Amazfit T-Rex 3", "price": 1799, "battery": None, "bt": "5.2", "nc": False, "wt": 66, "specs": {"屏幕":"1.5英寸AMOLED","续航":"27天","防水":"10ATM","传感器":"GPS/气压/指南针/心率"}, "desc": "华米户外军工手表，27天超长续航，军规认证，100米防水，户外探险首选。"},
    {"cat": "智能手表", "name": "OPPO Watch X", "price": 1399, "battery": None, "bt": "5.3", "nc": False, "wt": 49, "specs": {"屏幕":"1.43英寸AMOLED","续航":"4天全智能/14天轻智能","防水":"5ATM","传感器":"心率/血氧/ECG"}, "desc": "OPPO旗舰智能手表，双芯双系统，ECG心电图功能，流畅体验。"},
    {"cat": "智能手表", "name": "荣耀手表5", "price": 699, "battery": None, "bt": "5.2", "nc": False, "wt": 45, "specs": {"屏幕":"1.43英寸AMOLED","续航":"14天","防水":"5ATM","传感器":"心率/血氧/GPS"}, "desc": "荣耀入门级智能手表，14天长续航，eSIM独立通话，高性价比之选。"},

    # ── 蓝牙音箱 (5 products) ──
    {"cat": "蓝牙音箱", "name": "JBL Go 4", "price": 299, "battery": 6, "bt": "5.3", "nc": False, "wt": 210, "specs": {"功率":"5W","防水":"IP67","特色":"口袋尺寸"}, "desc": "JBL口袋蓝牙音箱，IP67防尘防水，小巧便携，户外露营随身带。"},
    {"cat": "蓝牙音箱", "name": "Bose SoundLink Flex", "price": 1399, "battery": 12, "bt": "5.1", "nc": False, "wt": 590, "specs": {"功率":"10W","防水":"IP67","特色":"PositionIQ自动调音"}, "desc": "Bose便携蓝牙音箱，12小时续航，IP67防水，PositionIQ自动调音技术。"},
    {"cat": "蓝牙音箱", "name": "哈曼卡顿Aura Studio 3", "price": 1999, "battery": None, "bt": "4.2", "nc": False, "wt": 3600, "specs": {"功率":"130W","类型":"桌面音箱","特色":"水母造型/360度环绕"}, "desc": "哈曼卡顿经典水母音箱，130W澎湃功率，360度环绕声，桌面艺术品。"},
    {"cat": "蓝牙音箱", "name": "小米Sound Move", "price": 499, "battery": 10, "bt": "5.3", "nc": False, "wt": 800, "specs": {"功率":"15W","防水":"IPX7","特色":"哈曼调音/小爱同学"}, "desc": "小米便携蓝牙音箱，哈曼联合调音，内置小爱同学，10小时续航。"},
    {"cat": "蓝牙音箱", "name": "漫步者M330", "price": 699, "battery": 8, "bt": "5.0", "nc": False, "wt": 1500, "specs": {"功率":"40W","类型":"桌面音箱","特色":"木质箱体/Hi-Res"}, "desc": "漫步者Hi-Res桌面音箱，木质箱体，40W大功率，复古颜值。"},

    # ── 笔记本电脑 (5 products) ──
    {"cat": "笔记本电脑", "name": "MacBook Pro 14 M4", "price": 12999, "battery": None, "bt": "5.3", "nc": False, "wt": 1550, "specs": {"屏幕":"14.2英寸Liquid Retina XDR","芯片":"M4 Pro","内存":"18GB+512GB","续航":"17h"}, "desc": "苹果最新MacBook Pro，M4 Pro芯片，Liquid Retina XDR显示屏，17小时续航。"},
    {"cat": "笔记本电脑", "name": "华为MateBook X Pro", "price": 8999, "battery": None, "bt": "5.3", "nc": False, "wt": 980, "specs": {"屏幕":"14.2英寸OLED","芯片":"酷睿Ultra 9","内存":"16GB+1TB","续航":"12h"}, "desc": "华为旗舰轻薄本，980g超轻机身，OLED触控屏，超级终端多设备协同。"},
    {"cat": "笔记本电脑", "name": "联想YOGA Pro 14s", "price": 6499, "battery": None, "bt": "5.3", "nc": False, "wt": 1400, "specs": {"屏幕":"14.5英寸3K OLED","芯片":"酷睿Ultra 7","内存":"16GB+512GB","续航":"10h"}, "desc": "联想YOGA高端轻薄本，3K OLED触控屏，酷睿Ultra 7，AI智能办公。"},
    {"cat": "笔记本电脑", "name": "小米RedmiBook Pro 16", "price": 4499, "battery": None, "bt": "5.3", "nc": False, "wt": 1800, "specs": {"屏幕":"16英寸2.5K","芯片":"酷睿Ultra 5","内存":"16GB+512GB","续航":"12h"}, "desc": "小米大屏性价比笔记本，16英寸2.5K高刷屏，酷睿Ultra 5，学生党首选。"},
    {"cat": "笔记本电脑", "name": "华硕无畏Pro 15", "price": 5299, "battery": None, "bt": "5.3", "nc": False, "wt": 1600, "specs": {"屏幕":"15.6英寸OLED","芯片":"锐龙7 8845H","内存":"16GB+512GB","续航":"8h"}, "desc": "华硕OLED笔记本，锐龙7高性能处理器，15.6英寸OLED好屏，创意工作利器。"},

    # ── 平板电脑 (5 products) ──
    {"cat": "平板电脑", "name": "iPad Air M2", "price": 4799, "battery": None, "bt": "5.3", "nc": False, "wt": 462, "specs": {"屏幕":"11英寸Liquid Retina","芯片":"M2","内存":"8GB+128GB","特色":"支持Apple Pencil Pro"}, "desc": "苹果iPad Air M2芯片版，11英寸全面屏，支持新款Apple Pencil Pro。"},
    {"cat": "平板电脑", "name": "华为MatePad Pro 13.2", "price": 5499, "battery": None, "bt": "5.3", "nc": False, "wt": 580, "specs": {"屏幕":"13.2英寸OLED","芯片":"麒麟9000S","内存":"12GB+256GB","特色":"星闪手写笔/PC级WPS"}, "desc": "华为旗舰平板，13.2英寸OLED柔性屏，星闪手写笔，PC级办公体验。"},
    {"cat": "平板电脑", "name": "小米Pad 7 Pro", "price": 2499, "battery": None, "bt": "5.3", "nc": False, "wt": 490, "specs": {"屏幕":"11英寸2.8K","芯片":"骁龙8s Gen3","内存":"8GB+256GB","特色":"HyperOS/键盘套装"}, "desc": "小米新款旗舰平板，骁龙8s Gen3，2.8K高刷屏，HyperOS多设备协同。"},
    {"cat": "平板电脑", "name": "荣耀Pad V9", "price": 1999, "battery": None, "bt": "5.2", "nc": False, "wt": 510, "specs": {"屏幕":"12.1英寸2.5K","芯片":"骁龙8s Gen3","内存":"8GB+256GB","特色":"AI学习助手"}, "desc": "荣耀大屏学习平板，12.1英寸2.5K护眼屏，AI学习助手，学生网课首选。"},
    {"cat": "平板电脑", "name": "联想小新Pad Pro", "price": 1499, "battery": None, "bt": "5.1", "nc": False, "wt": 480, "specs": {"屏幕":"12.7英寸2.9K","芯片":"天玑8300","内存":"8GB+128GB","特色":"电脑模式/JBL四扬声器"}, "desc": "联想高性价比大屏平板，12.7英寸超大屏，JBL四扬声器，影音娱乐神器。"},

    # ── 充电宝 (5 products) ──
    {"cat": "充电宝", "name": "小米充电宝20000mAh 50W", "price": 199, "battery": None, "bt": None, "nc": False, "wt": 430, "specs": {"容量":"20000mAh","快充":"50W PD/QC","接口":"USB-C×2+USB-A","特色":"笔记本充电"}, "desc": "小米大容量快充充电宝，20000mAh可充笔记本，50W双向快充，三口同充。"},
    {"cat": "充电宝", "name": "倍思充电宝10000mAh 30W", "price": 89, "battery": None, "bt": None, "nc": False, "wt": 180, "specs": {"容量":"10000mAh","快充":"30W PD","接口":"USB-C+Lightning","特色":"自带线"}, "desc": "倍思自带线充电宝，10000mAh轻薄便携，30W快充，苹果安卓都兼容。"},
    {"cat": "充电宝", "name": "Anker Prime 20000mAh", "price": 399, "battery": None, "bt": None, "nc": False, "wt": 450, "specs": {"容量":"20000mAh","快充":"100W PD","接口":"USB-C×2+USB-A","特色":"LED显示屏/可充笔记本"}, "desc": "Anker旗舰快充充电宝，100W超级快充，LED电量显示，可充MacBook。"},
    {"cat": "充电宝", "name": "罗马仕sense8 20000mAh", "price": 69, "battery": None, "bt": None, "nc": False, "wt": 420, "specs": {"容量":"20000mAh","快充":"22.5W","接口":"USB-C+USB-A×2","特色":"3入3出/数显"}, "desc": "罗马仕大容量性价比充电宝，20000mAh，三进三出，数字电量显示。"},
    {"cat": "充电宝", "name": "绿联磁吸无线充电宝5000mAh", "price": 149, "battery": None, "bt": None, "nc": False, "wt": 130, "specs": {"容量":"5000mAh","快充":"15W无线+20W有线","接口":"USB-C","特色":"MagSafe磁吸/支架"}, "desc": "绿联MagSafe磁吸充电宝，5000mAh小巧便携，无线充电+支架功能，苹果最佳伴侣。"},
]

# ── Insert products ──
count = 0
for pdata in products_data:
    cat = categories[pdata["cat"]]
    specs = dict(pdata.get("specs", {}))
    desc = pdata.get("desc", "")
    product = Product.objects.create(
        name=pdata["name"],
        description=desc,
        price=pdata["price"],
        category=cat,
        seller=seller,
        shop=shop,
        is_active=True,
        battery_life=pdata.get("battery"),
        bluetooth_version=pdata.get("bt"),
        noise_cancellation=pdata.get("nc", False),
        weight=pdata.get("wt"),
        specs=specs,
    )
    count += 1
    print(f"  [{count:2d}] {product.name} — ¥{product.price} — {cat.name}")

print(f"\nDone: {count} products inserted.")
