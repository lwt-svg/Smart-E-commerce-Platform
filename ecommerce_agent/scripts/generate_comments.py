'''
评论数据表结构优化与数据生成脚本
'''

import os
import random
import pymysql
from datetime import datetime, timedelta
from typing import List, Dict, Any

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
DB_NAME = os.getenv("DB_NAME", "muxi_shop")


DROP_TABLE_SQL = "DROP TABLE IF EXISTS `comment`"

CREATE_TABLE_SQL = """
CREATE TABLE `comment` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `user_id` INT DEFAULT NULL,
    `sku_id` VARCHAR(255) DEFAULT NULL,
    `reference_name` VARCHAR(255) DEFAULT NULL,
    `content` TEXT DEFAULT NULL,
    `score` DECIMAL(2,1) DEFAULT NULL,
    `nickname` VARCHAR(100) DEFAULT NULL,
    `user_image_url` VARCHAR(500) DEFAULT NULL,
    `images` VARCHAR(1000) DEFAULT NULL COMMENT '评论图片JSON数组',
    `is_verified` TINYINT(1) DEFAULT 0 COMMENT '是否验证购买',
    `helpful_count` INT DEFAULT 0 COMMENT '有用数/点赞数',
    `reply_count` INT DEFAULT 0 COMMENT '回复数',
    `sentiment` VARCHAR(20) DEFAULT NULL COMMENT '情感标签: positive/negative/neutral',
    `sentiment_confidence` DECIMAL(3,2) DEFAULT NULL COMMENT '情感置信度',
    `positive_points` TEXT DEFAULT NULL COMMENT '正面观点JSON数组',
    `negative_points` TEXT DEFAULT NULL COMMENT '负面观点JSON数组',
    `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_sku_id` (`sku_id`),
    INDEX `idx_reference_name` (`reference_name`),
    INDEX `idx_sentiment` (`sentiment`),
    INDEX `idx_score` (`score`),
    INDEX `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品评论表';
"""


POSITIVE_TEMPLATES = {
    "手机数码": [
        "拍照效果非常好，夜景模式很清晰",
        "运行速度很快，玩游戏完全不卡",
        "屏幕显示效果细腻，色彩还原度高",
        "电池续航给力，一天一充完全够用",
        "手感很好，做工精细，颜值在线",
        "系统流畅，没有广告，体验很好",
        "充电速度很快，半小时就能充大半",
        "信号稳定，通话质量清晰",
        "性价比很高，这个价位非常值得",
        "面部识别和指纹解锁都很灵敏",
    ],
    "电脑办公": [
        "开机速度很快，几秒钟就进系统",
        "屏幕素质很好，长时间看也不累眼",
        "键盘手感舒适，打字很顺畅",
        "性能强劲，跑大型软件没问题",
        "散热效果不错，长时间使用不烫",
        "轻薄便携，出差携带很方便",
        "续航能力强，不插电也能用很久",
        "接口丰富，外接设备很方便",
        "做工精细，质感很好",
        "性价比高，同配置里算便宜的",
    ],
    "家用电器": [
        "噪音很小，不影响休息",
        "制冷/制热效果很好，速度快",
        "操作简单，老人也能轻松使用",
        "节能省电，电费不高",
        "外观设计好看，放在家里很搭配",
        "质量可靠，用了很久没出问题",
        "容量大，满足全家需求",
        "清洁方便，维护简单",
        "功能齐全，满足各种需求",
        "售后服务好，有问题响应快",
    ],
    "服饰鞋靴": [
        "面料舒适，穿起来很舒服",
        "尺码标准，按平时码买就行",
        "做工精细，没有线头",
        "款式时尚，上身效果好",
        "颜色和图片一致，没有色差",
        "透气性好，夏天穿不闷",
        "质量不错，洗了几次没变形",
        "性价比高，这个价格很值",
        "发货快，包装也很好",
        "很百搭，配什么衣服都好看",
    ],
    "美妆护肤": [
        "保湿效果很好，皮肤水润",
        "吸收快，不油腻",
        "味道好闻，淡淡的香味",
        "用了一段时间，皮肤有改善",
        "温和不刺激，敏感肌也能用",
        "包装精美，送人也不错",
        "性价比高，比专柜便宜",
        "正品保证，用着放心",
        "效果明显，会回购",
        "质地轻薄，上脸很舒服",
    ],
    "食品饮料": [
        "味道很好，家人都喜欢",
        "新鲜度高，日期很新",
        "包装严实，没有破损",
        "分量足，够吃很久",
        "价格实惠，比超市便宜",
        "口感不错，下次还会买",
        "物流快，冷链配送",
        "配料干净，吃着放心",
        "孩子很喜欢吃",
        "生产日期新鲜，保质期长",
    ],
    "运动户外": [
        "穿着舒适，运动时很轻便",
        "透气性好，运动不闷脚",
        "防滑耐磨，质量很好",
        "支撑性好，保护脚踝",
        "颜值高，搭配运动装好看",
        "尺码标准，按平时码买就行",
        "做工精细，没有瑕疵",
        "性价比高，大牌平替",
        "轻便灵活，跑步很舒服",
        "缓震效果好，长时间运动不累",
    ],
    "家居生活": [
        "质量很好，结实耐用",
        "安装简单，自己就能装",
        "设计合理，使用方便",
        "材质环保，没有异味",
        "外观简约，百搭风格",
        "性价比高，比实体店便宜",
        "包装仔细，没有损坏",
        "尺寸合适，放家里刚好",
        "功能实用，满足日常需求",
        "客服态度好，有问题及时解决",
    ],
}

NEGATIVE_TEMPLATES = {
    "手机数码": [
        "电池续航不行，半天就没电了",
        "拍照效果一般，不如宣传的好",
        "运行有点卡，打开APP要等",
        "发热严重，玩一会儿就烫手",
        "信号不太好，有时候会断",
        "充电口松动，接触不良",
        "系统有bug，偶尔会闪退",
        "屏幕容易留指纹",
        "扬声器音质一般",
        "性价比不高，同价位有更好的",
    ],
    "电脑办公": [
        "散热不好，风扇声音大",
        "续航没有宣传的那么长",
        "屏幕有漏光现象",
        "键盘手感偏硬",
        "接口太少，需要转接头",
        "运行大型软件会卡",
        "开机速度慢",
        "外壳容易留指纹",
        "WiFi信号不稳定",
        "售后服务差，有问题推诿",
    ],
    "家用电器": [
        "噪音太大，影响休息",
        "制冷/制热效果不理想",
        "耗电量大，电费高",
        "操作复杂，说明书看不懂",
        "做工粗糙，有瑕疵",
        "用了一段时间就出问题",
        "容量太小，不够用",
        "清洁很麻烦",
        "售后服务差",
        "性价比低，不推荐",
    ],
    "服饰鞋靴": [
        "尺码偏大/偏小，建议拍小/大一码",
        "面料有点硬，不太舒服",
        "做工一般，有线头",
        "颜色和图片有差异",
        "洗了一次就掉色了",
        "透气性不好，穿着闷",
        "质量一般，不值这个价",
        "发货太慢了",
        "和描述不符",
        "穿了几次就开胶了",
    ],
    "美妆护肤": [
        "用了过敏，皮肤发红",
        "效果不明显，感觉没用",
        "味道刺鼻，不好闻",
        "质地厚重，不好推开",
        "包装简陋，不像正品",
        "价格虚高，不值",
        "保质期短，快过期了",
        "和专柜买的不一样",
        "吸收慢，脸上黏黏的",
        "客服态度差",
    ],
    "食品饮料": [
        "味道一般，没有想象中好",
        "日期不新鲜，快过期了",
        "包装破损，东西洒了",
        "分量不足，感觉少了",
        "价格比超市贵",
        "口感不好，吃不惯",
        "物流太慢，等了好久",
        "配料表和描述不符",
        "孩子不爱吃",
        "有异味，不敢吃",
    ],
    "运动户外": [
        "尺码不准，买大了/小了",
        "透气性差，运动时闷脚",
        "鞋底太硬，穿着不舒服",
        "做工粗糙，有胶水痕迹",
        "防滑效果不好",
        "穿了几次就开胶了",
        "颜色和图片不一样",
        "支撑性不够",
        "性价比低",
        "客服态度差，退换麻烦",
    ],
    "家居生活": [
        "质量一般，不够结实",
        "安装复杂，要请人装",
        "设计不合理，不好用",
        "有异味，散了好久",
        "做工粗糙，有毛刺",
        "尺寸比描述的小",
        "价格贵，不值这个价",
        "物流慢，等了很久",
        "包装简陋，有损坏",
        "客服回复慢",
    ],
}

NEUTRAL_TEMPLATES = [
    "东西收到了，还没用，用后再评",
    "一般般吧，没有特别好也没有特别差",
    "凑合能用，对得起这个价格",
    "和描述基本一致",
    "物流还可以，包装一般",
    "中规中矩，没什么惊喜",
    "还行吧，看个人需求",
    "正常水平，符合预期",
    "不好不坏，一般般",
    "有待观察，先用着看看",
]

NICKNAMES = [
    "用户***{}号", "jd_***{}", "淘宝用户{}", "会员用户{}", "匿名用户{}",
    "小王{}", "张三{}", "李四{}", "王五{}", "赵六{}",
    "购物达人{}", "品质控{}", "性价比猎人{}", "剁手党{}", "资深买家{}",
]


def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )


def get_all_goods() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT sku_id, name, main_brand, main_category
            FROM goods
            WHERE sku_id IS NOT NULL AND name IS NOT NULL
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def get_category_key(main_category: str) -> str:
    if not main_category:
        return "家居生活"
    
    category_map = {
        "手机数码": ["手机", "数码", "平板", "耳机", "相机", "智能"],
        "电脑办公": ["电脑", "笔记本", "办公", "显示器", "键盘", "鼠标"],
        "家用电器": ["家电", "空调", "冰箱", "洗衣机", "电视", "热水器"],
        "服饰鞋靴": ["服饰", "衣服", "鞋", "靴", "T恤", "外套", "裤子"],
        "美妆护肤": ["美妆", "护肤", "化妆品", "面膜", "口红"],
        "食品饮料": ["食品", "饮料", "零食", "水果", "牛奶"],
        "运动户外": ["运动", "户外", "健身", "跑步", "篮球"],
        "家居生活": ["家居", "家具", "床", "沙发", "收纳"],
    }
    
    for key, keywords in category_map.items():
        if any(kw in main_category for kw in keywords):
            return key
    
    return "家居生活"


def generate_comment(
    goods: Dict[str, Any],
    sentiment: str,
    score: float
) -> Dict[str, Any]:
    category_key = get_category_key(goods.get("main_category", ""))
    
    if sentiment == "positive":
        templates = POSITIVE_TEMPLATES.get(category_key, POSITIVE_TEMPLATES["家居生活"])
        num_points = random.randint(1, 3)
        content_parts = random.sample(templates, min(num_points, len(templates)))
        content = "，".join(content_parts) + "。"
        positive_points = content_parts
        negative_points = []
        confidence = random.uniform(0.75, 0.95)
    elif sentiment == "negative":
        templates = NEGATIVE_TEMPLATES.get(category_key, NEGATIVE_TEMPLATES["家居生活"])
        num_points = random.randint(1, 2)
        content_parts = random.sample(templates, min(num_points, len(templates)))
        content = "，".join(content_parts) + "。"
        positive_points = []
        negative_points = content_parts
        confidence = random.uniform(0.75, 0.95)
    else:
        content = random.choice(NEUTRAL_TEMPLATES)
        positive_points = []
        negative_points = []
        confidence = random.uniform(0.5, 0.7)
    
    import json
    return {
        "sku_id": goods.get("sku_id"),
        "reference_name": goods.get("name"),
        "content": content,
        "score": score,
        "nickname": random.choice(NICKNAMES).format(random.randint(1000, 9999)),
        "user_image_url": None,
        "images": None,
        "is_verified": random.choice([0, 1, 1, 1]),
        "helpful_count": random.randint(0, 50) if sentiment != "neutral" else random.randint(0, 10),
        "reply_count": random.randint(0, 5),
        "sentiment": sentiment,
        "sentiment_confidence": round(confidence, 2),
        "positive_points": json.dumps(positive_points, ensure_ascii=False) if positive_points else None,
        "negative_points": json.dumps(negative_points, ensure_ascii=False) if negative_points else None,
        "create_time": datetime.now() - timedelta(days=random.randint(0, 180)),
    }


def generate_comments_for_goods(goods: Dict[str, Any], count: int = 50) -> List[Dict[str, Any]]:
    comments = []
    
    positive_ratio = random.uniform(0.60, 0.80)
    negative_ratio = random.uniform(0.20, 0.40)
    
    positive_count = int(count * positive_ratio)
    negative_count = int(count * negative_ratio)
    neutral_count = count - positive_count - negative_count
    
    if neutral_count < 0:
        neutral_count = 0
        negative_count = count - positive_count
    
    for _ in range(positive_count):
        score = random.choice([4.0, 4.5, 5.0])
        comments.append(generate_comment(goods, "positive", score))
    
    for _ in range(negative_count):
        score = random.choice([1.0, 1.5, 2.0, 2.5, 3.0])
        comments.append(generate_comment(goods, "negative", score))
    
    for _ in range(neutral_count):
        score = random.choice([3.0, 3.5])
        comments.append(generate_comment(goods, "neutral", score))
    
    random.shuffle(comments)
    return comments


def create_new_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        print("正在删除旧的comment表...")
        cursor.execute(DROP_TABLE_SQL)
        conn.commit()
        print("正在创建新的comment表...")
        cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
        print("comment表创建成功！")
    except Exception as e:
        print(f"创建表失败: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def insert_comments(comments: List[Dict[str, Any]]):
    if not comments:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = """
            INSERT INTO comment (
                sku_id, reference_name, content, score, nickname,
                user_image_url, images, is_verified, helpful_count, reply_count,
                sentiment, sentiment_confidence, positive_points, negative_points, create_time
            ) VALUES (
                %(sku_id)s, %(reference_name)s, %(content)s, %(score)s, %(nickname)s,
                %(user_image_url)s, %(images)s, %(is_verified)s, %(helpful_count)s, %(reply_count)s,
                %(sentiment)s, %(sentiment_confidence)s, %(positive_points)s, %(negative_points)s, %(create_time)s
            )
        """
        cursor.executemany(sql, comments)
        conn.commit()
    except Exception as e:
        print(f"插入评论失败: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def main():
    print("=" * 50)
    print("评论数据生成脚本")
    print("=" * 50)
    
    create_new_table()
    
    print("\n正在获取商品列表...")
    goods_list = get_all_goods()
    print(f"共获取 {len(goods_list)} 个商品")
    
    if not goods_list:
        print("没有商品数据，请先导入商品数据")
        return
    
    print("\n正在生成评论数据...")
    total_comments = 0
    
    for i, goods in enumerate(goods_list):
        comments = generate_comments_for_goods(goods, count=50)
        insert_comments(comments)
        total_comments += len(comments)
        
        if (i + 1) % 10 == 0:
            print(f"已处理 {i + 1}/{len(goods_list)} 个商品，共生成 {total_comments} 条评论")
    
    print(f"\n完成！共生成 {total_comments} 条评论")


if __name__ == "__main__":
    main()
