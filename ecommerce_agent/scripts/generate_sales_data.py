"""
生成真实电商销售数据
依据goods表中的已有商品，生成订单(order)和订单商品(order_goods)数据
"""
import pymysql
import random
from datetime import datetime, timedelta

conn = pymysql.connect(host='localhost', user='root', password='123456', database='muxi_shop', charset='utf8mb4')
cursor = conn.cursor(pymysql.cursors.DictCursor)

print("=" * 60)
print("开始生成真实电商销售数据")
print("=" * 60)

# 1. 获取所有商品
cursor.execute("SELECT sku_id, name, main_brand, main_category, p_price, jd_price, mk_price FROM goods WHERE sku_id IS NOT NULL AND sku_id != ''")
goods = cursor.fetchall()
print(f"可用商品数: {len(goods)}")

# 2. 获取所有用户email
cursor.execute("SELECT email FROM user WHERE email IS NOT NULL AND email != ''")
users = [r['email'] for r in cursor.fetchall()]
print(f"可用用户数: {len(users)}")

# 3. 获取当前最大订单ID
cursor.execute("SELECT MAX(id) as max_id FROM `order`")
max_id = cursor.fetchone()['max_id'] or 0
print(f"当前最大订单ID: {max_id}")

# 4. 生成数据参数
NUM_ORDERS = 500  # 生成500条新订单
DAYS_BACK = 30    # 日期分布在近30天
now = datetime.now()

print(f"将生成 {NUM_ORDERS} 条订单，日期分布在近 {DAYS_BACK} 天内")

# 5. 生成订单
orders_created = 0
order_goods_created = 0

for i in range(NUM_ORDERS):
    # 随机日期（近期更多）
    days_ago = random.choices(
        range(DAYS_BACK),
        weights=[max(1, DAYS_BACK - d) for d in range(DAYS_BACK)],  # 近期权重更高
        k=1
    )[0]
    hours_ago = random.randint(0, 23)
    minutes_ago = random.randint(0, 59)
    create_time = now - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)

    # 随机用户
    email = random.choice(users)

    # 随机选1-4件商品
    num_items = random.choices([1, 2, 3, 4], weights=[50, 30, 15, 5], k=1)[0]
    selected_goods = random.sample(goods, min(num_items, len(goods)))

    # 计算订单总金额
    total_amount = 0
    items_info = []
    for g in selected_goods:
        price = float(g.get('p_price') or g.get('jd_price') or g.get('mk_price') or 0)
        if price <= 0:
            price = round(random.uniform(50, 5000), 2)
        qty = random.choices([1, 2, 3], weights=[70, 20, 10], k=1)[0]
        total_amount += price * qty
        items_info.append({
            'sku_id': str(g['sku_id']),
            'name': g['name'],
            'price': price,
            'qty': qty
        })

    total_amount = round(total_amount, 2)

    # 生成trade_no
    trade_no = f"ORD{create_time.strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"

    # 插入order表
    pay_status = random.choices(['1', '2', '3'], weights=[70, 20, 10], k=1)[0]  # 1=已支付, 2=待支付, 3=已取消
    cursor.execute(
        "INSERT INTO `order` (trade_no, email, order_amount, address_id, pay_status, pay_time, is_delete, create_time, update_time) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (trade_no, email, total_amount, 1, pay_status, create_time, 0, create_time, create_time)
    )
    orders_created += 1

    # 插入order_goods表
    for item in items_info:
        cursor.execute(
            "INSERT INTO order_goods (trade_no, sku_id, goods_num, create_time) VALUES (%s, %s, %s, %s)",
            (trade_no, item['sku_id'], item['qty'], create_time)
        )
        order_goods_created += 1

conn.commit()

print(f"\n✅ 生成完成:")
print(f"  新增订单: {orders_created} 条")
print(f"  新增订单商品: {order_goods_created} 条")

# 6. 验证数据
cursor.execute("SELECT COUNT(*) as cnt FROM `order`")
print(f"\n订单总数: {cursor.fetchone()['cnt']}")

cursor.execute("SELECT COUNT(*) as cnt FROM order_goods")
print(f"订单商品总数: {cursor.fetchone()['cnt']}")

cursor.execute("SELECT COUNT(*) as cnt FROM `order` WHERE create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)")
print(f"近一周订单数: {cursor.fetchone()['cnt']}")

cursor.execute("SELECT COUNT(*) as cnt FROM `order` WHERE create_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)")
print(f"近一月订单数: {cursor.fetchone()['cnt']}")

# 7. 验证品类分布（通过join order_goods和goods）
cursor.execute("""
    SELECT g.main_category, COUNT(*) as cnt, SUM(og.goods_num) as total_qty
    FROM order_goods og
    JOIN goods g ON og.sku_id = g.sku_id
    JOIN `order` o ON og.trade_no = o.trade_no
    WHERE o.create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    AND o.pay_status = '1'
    GROUP BY g.main_category
    ORDER BY cnt DESC
    LIMIT 10
""")
print(f"\n近一周各品类销售情况（已支付）:")
for r in cursor.fetchall():
    print(f"  {r['main_category']}: {r['cnt']}笔, {r['total_qty']}件")

# 8. 查看近一周GMV
cursor.execute("""
    SELECT SUM(o.order_amount) as gmv, COUNT(*) as cnt
    FROM `order` o
    WHERE o.create_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    AND o.pay_status = '1'
""")
r = cursor.fetchone()
print(f"\n近一周GMV: ¥{r['gmv']}, 订单数: {r['cnt']}")

conn.close()
print("\n✅ 数据生成完成")
