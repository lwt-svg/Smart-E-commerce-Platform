"""
生成覆盖数据分析Agent所有功能的测试数据
1. 补充近期评论数据（近30天500条，覆盖1-5星）
2. 添加"电子产品"品类（把电子相关品类统一标记）
"""
import pymysql
import random
from datetime import datetime, timedelta

conn = pymysql.connect(host='localhost', user='root', password='123456', database='muxi_shop', charset='utf8mb4')
cursor = conn.cursor(pymysql.cursors.DictCursor)

print("=" * 60)
print("生成覆盖数据分析Agent所有功能的测试数据")
print("=" * 60)

# ============ 1. 添加"电子产品"品类 ============
# 把"手机数码"改为"电子产品"，同时给"电脑办公"也添加"电子产品"标签
print("\n[1] 更新品类：添加'电子产品'...")

# 把"手机数码"改为"电子产品"
cursor.execute("UPDATE goods SET main_category = '电子产品' WHERE main_category = '手机数码'")
r1 = cursor.rowcount
print(f"  '手机数码' → '电子产品': {r1}件")

# 把"电脑办公"改为"电子产品"
cursor.execute("UPDATE goods SET main_category = '电子产品' WHERE main_category = '电脑办公'")
r2 = cursor.rowcount
print(f"  '电脑办公' → '电子产品': {r2}件")

conn.commit()

# 验证品类分布
cursor.execute("SELECT main_category, COUNT(*) as cnt FROM goods WHERE main_category IN ('电子产品','手机','平板','耳机','音箱','手表','笔记本','显示器','充电器','手环') GROUP BY main_category ORDER BY cnt DESC")
print("  电子相关品类分布:")
for r in cursor.fetchall():
    print(f"    {r['main_category']}: {r['cnt']}件")

# ============ 2. 补充近期评论数据 ============
print("\n[2] 生成近期评论数据（近30天500条）...")

# 获取有订单的商品（确保评论关联到有销售记录的商品）
cursor.execute("""
    SELECT DISTINCT g.sku_id, g.name, g.main_brand, g.main_category
    FROM goods g
    INNER JOIN order_goods og ON g.sku_id = og.sku_id
    WHERE g.sku_id IS NOT NULL AND g.sku_id != ''
""")
goods_with_sales = cursor.fetchall()
print(f"  有销售记录的商品数: {len(goods_with_sales)}")

# 获取用户
cursor.execute("SELECT id, email FROM user WHERE email IS NOT NULL AND email != '' LIMIT 100")
users = cursor.fetchall()
print(f"  可用用户数: {len(users)}")

# 评论内容模板
positive_templates = [
    "质量很好，物超所值！", "发货速度快，包装完好。", "用了一段时间，体验很棒。",
    "性价比很高，推荐购买。", "正品行货，值得信赖。", "做工精细，手感很好。",
    "性能强劲，满足需求。", "客服态度好，售后服务到位。", "第二次购买了，一如既往的好。",
    "外观漂亮，功能齐全。"
]
neutral_templates = [
    "一般般，符合预期。", "还行吧，没有特别惊喜。", "功能正常，做工普通。",
    "价格适中，性能一般。", "用着还行，没有大问题。"
]
negative_templates = [
    "质量不太行，有点失望。", "发货太慢了，等了一周。", "跟描述不符，有瑕疵。",
    "用了一周就坏了。", "客服回复慢，问题没解决。", "性价比低，不推荐。",
    "包装破损，商品有划痕。", "功能不稳定，经常出问题。"
]

now = datetime.now()
comments_created = 0

for i in range(500):
    # 随机日期（近30天，近期更多）
    days_ago = random.choices(range(30), weights=[max(1, 30 - d) for d in range(30)], k=1)[0]
    hours_ago = random.randint(0, 23)
    create_time = now - timedelta(days=days_ago, hours=hours_ago, minutes=random.randint(0, 59))

    # 随机选商品和用户
    g = random.choice(goods_with_sales)
    u = random.choice(users)

    # 随机评分（70%好评，15%中评，15%差评）
    score = random.choices(
        [5.0, 4.5, 4.0, 3.0, 2.0, 1.0],
        weights=[40, 20, 10, 15, 10, 5],
        k=1
    )[0]

    # 根据评分选评论内容
    if score >= 4.0:
        content = random.choice(positive_templates)
        sentiment = "positive"
    elif score == 3.0:
        content = random.choice(neutral_templates)
        sentiment = "neutral"
    else:
        content = random.choice(negative_templates)
        sentiment = "negative"

    # 插入评论
    cursor.execute(
        """INSERT INTO comment
           (user_id, sku_id, reference_name, content, score, nickname,
            is_verified, helpful_count, reply_count, sentiment, sentiment_confidence,
            create_time)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            u['id'],
            g['sku_id'],
            g['name'],
            content,
            score,
            u['email'].split('@')[0] if u.get('email') else '匿名用户',
            random.choice([0, 1]),
            random.randint(0, 50),
            random.randint(0, 5),
            sentiment,
            round(random.uniform(0.7, 0.99), 2),
            create_time
        )
    )
    comments_created += 1

conn.commit()
print(f"  新增评论: {comments_created}条")

# ============ 3. 验证数据覆盖情况 ============
print("\n[3] 数据覆盖验证:")

# 订单数据
cursor.execute("SELECT COUNT(*) as cnt FROM `order`")
print(f"  订单总数: {cursor.fetchone()['cnt']}")

cursor.execute("SELECT COUNT(*) as cnt FROM `order` WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND pay_status='1'")
print(f"  近一周已支付订单: {cursor.fetchone()['cnt']}")

# 评论数据
cursor.execute("SELECT COUNT(*) as cnt FROM comment WHERE create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)")
print(f"  近30天评论数: {cursor.fetchone()['cnt']}")

cursor.execute("SELECT COUNT(*) as cnt FROM comment WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)")
print(f"  近一周评论数: {cursor.fetchone()['cnt']}")

# 差评数据
cursor.execute("SELECT COUNT(*) as cnt FROM comment WHERE score <= 2 AND create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)")
print(f"  近30天差评数: {cursor.fetchone()['cnt']}")

# 电子产品销售
cursor.execute("""
    SELECT COUNT(*) as orders, SUM(o.order_amount) as gmv
    FROM order_goods og
    JOIN goods g ON og.sku_id = g.sku_id
    JOIN `order` o ON og.trade_no = o.trade_no
    WHERE g.main_category = '电子产品' AND o.pay_status = '1'
    AND o.create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
""")
r = cursor.fetchone()
print(f"  近一周电子产品销售: {r['orders']}笔, GMV=¥{r['gmv'] or 0}")

# RFM分析数据
cursor.execute("SELECT COUNT(DISTINCT email) as cnt FROM `order` WHERE pay_status='1' AND email IS NOT NULL AND email != ''")
print(f"  有购买记录的用户数: {cursor.fetchone()['cnt']}")

# 品类销售覆盖
cursor.execute("""
    SELECT g.main_category, COUNT(*) as orders
    FROM order_goods og
    JOIN goods g ON og.sku_id = g.sku_id
    JOIN `order` o ON og.trade_no = o.trade_no
    WHERE o.pay_status = '1' AND o.create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    GROUP BY g.main_category
    ORDER BY orders DESC
    LIMIT 10
""")
print(f"  近30天品类销售覆盖:")
for r in cursor.fetchall():
    print(f"    {r['main_category']}: {r['orders']}笔")

conn.close()
print("\n✅ 测试数据生成完成")
