from langchain.tools import tool
import time
import random
import json
from datetime import datetime

from ..database import get_db_connection

# ========== 商品卡片相关配置 ==========
BASE_IMAGE_URL = "http://localhost:8001/static/product_images"
BASE_PRODUCT_URL = "http://localhost:8080/detail"
PLACEHOLDER_IMAGE = "https://via.placeholder.com/130"
# ======================================


def get_product_image_url(sku: str) -> str:
    return f"{BASE_IMAGE_URL}/{sku}.jpg"


def get_product_detail_url(sku: str) -> str:
    return f"{BASE_PRODUCT_URL}/{sku}"


def build_product_list_json(products_data: list) -> str:
    """
    将商品数据列表转换为前端可渲染的 JSON 字符串
    """
    if not products_data:
        return ""

    products = []
    for p in products_data:
        product_name = p.get("name") or ""
        price = p.get("p_price") or p.get("jd_price") or p.get("mk_price")
        if price is None:
            price = 0.0
        sku = p.get("sku_id") or p.get("sku", "")
        products.append({
            "name": product_name,
            "price": float(price),
            "image_url": get_product_image_url(sku),
            "product_url": get_product_detail_url(sku),
            "sku": sku
        })

    result = {
        "type": "product_list",
        "products": products
    }
    return json.dumps(result, ensure_ascii=False)


@tool
def check_user_cart(user_email: str) -> str:
    """只查询当前登录用户的购物车信息。"""
    total_start = time.time()
    print(f"[工具] check_user_cart 开始, user_email={user_email}")

    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"

        cursor = conn.cursor()

        # 1. 查询用户
        query = "SELECT id, name, email FROM user WHERE email = %s LIMIT 1"
        cursor.execute(query, (user_email,))
        user = cursor.fetchone()

        if not user:
            cleaned_email = (user_email or "").strip()
            if cleaned_email != user_email:
                cursor.execute(query, (cleaned_email,))
                user = cursor.fetchone()

        if not user:
            cursor.close()
            conn.close()
            return "未找到用户信息。请确认您已登录正确的账户。"

        user_id = user["id"]
        user_name = user["name"] if user["name"] else f"用户{user_id}"

        result = f"您的账户信息:\n- 用户名: {user_name}\n- 用户ID: {user_id}\n- Email: {user['email']}\n"

        # 2. 查询购物车
        t1 = time.time()
        query = """
            SELECT sc.sku_id, sc.nums, g.name, g.p_price, g.jd_price, g.mk_price
            FROM shopping_cart sc
            LEFT JOIN goods g ON sc.sku_id = g.sku_id
            WHERE sc.email = %s AND sc.is_delete = 0
            ORDER BY sc.create_time DESC
        """
        cursor.execute(query, (user["email"],))
        cart_items = cursor.fetchall()
        t2 = time.time()
        print(f"[工具] 查询购物车耗时: {t2 - t1:.3f}s, 商品数: {len(cart_items)}")

        if cart_items:
            products_data = []
            for item in cart_items:
                products_data.append({
                    "sku_id": item["sku_id"],
                    "name": item["name"] or "未知商品",
                    "p_price": item["p_price"],
                    "jd_price": item["jd_price"],
                    "mk_price": item["mk_price"]
                })

            product_json = build_product_list_json(products_data)

            result += f"\n【您的购物车】共 {len(cart_items)} 件商品：\n"
            result += product_json + "\n"

            total_price = 0
            for item in cart_items:
                price = item["p_price"] or item["jd_price"] or item["mk_price"]
                if price:
                    total_price += float(price) * item["nums"]

            result += f"购物车总价: ¥{total_price:.2f}\n"
        else:
            result += "\n【您的购物车】购物车为空\n"

        cursor.close()
        conn.close()

        total_end = time.time()
        print(f"[工具] check_user_cart 总耗时: {total_end - total_start:.3f}s")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[工具] 异常: {e}")
        if conn:
            conn.close()
        return f"查询购物车时出错: {str(e)}"


@tool
def check_user_orders(user_email: str, limit: int = 10) -> str:
    """只查询当前登录用户的订单列表。"""
    total_start = time.time()
    print(f"[工具] check_user_orders 开始, user_email={user_email}, limit={limit}")

    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"

        cursor = conn.cursor()

        # 1. 查询用户
        query = "SELECT id, name, email FROM user WHERE email = %s LIMIT 1"
        cursor.execute(query, (user_email,))
        user = cursor.fetchone()

        if not user:
            cleaned_email = (user_email or "").strip()
            if cleaned_email != user_email:
                cursor.execute(query, (cleaned_email,))
                user = cursor.fetchone()

        if not user:
            cursor.close()
            conn.close()
            return "未找到用户信息。请确认您已登录正确的账户。"

        user_id = user["id"]
        user_name = user["name"] if user["name"] else f"用户{user_id}"

        result = f"您的账户信息:\n- 用户名: {user_name}\n- 用户ID: {user_id}\n- Email: {user['email']}\n"

        # 2. 查询订单
        t1 = time.time()
        query = """
            SELECT id, trade_no, order_amount, pay_status, pay_time, create_time
            FROM `order`
            WHERE email = %s AND is_delete = 0
            ORDER BY create_time DESC
            LIMIT %s
        """
        cursor.execute(query, (user["email"], limit))
        orders = cursor.fetchall()
        t2 = time.time()
        print(f"[工具] 查询订单耗时: {t2 - t1:.3f}s, 订单数: {len(orders)}")

        if orders:
            result += f"\n【您的订单】共 {len(orders)} 个订单：\n"
            for i, order in enumerate(orders, 1):
                result += f"\n{i}. 订单编号: {order['trade_no']}\n"
                result += f"   订单ID: {order['id']}\n"
                result += f"   订单金额: ¥{order['order_amount']}\n"
                result += f"   支付状态: {order['pay_status']}\n"
                if order["pay_time"]:
                    result += f"   支付时间: {order['pay_time']}\n"
                result += f"   创建时间: {order['create_time']}\n"
        else:
            result += "\n【您的订单】暂无订单记录\n"

        cursor.close()
        conn.close()

        total_end = time.time()
        print(f"[工具] check_user_orders 总耗时: {total_end - total_start:.3f}s")
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[工具] 异常: {e}")
        if conn:
            conn.close()
        return f"查询订单时出错: {str(e)}"


@tool
def get_order_details(trade_no: str) -> str:
    """查询订单的详细信息，包括订单商品。"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"

        cursor = conn.cursor()

        # 查询订单基本信息
        query = """
            SELECT id, trade_no, email, order_amount, address_id,
                   pay_status, pay_time, ali_trade_no, create_time
            FROM `order`
            WHERE trade_no = %s AND is_delete = 0
        """
        cursor.execute(query, (trade_no,))
        order = cursor.fetchone()

        if not order:
            cursor.close()
            conn.close()
            return f"未找到交易号为 '{trade_no}' 的订单"

        # 获取用户信息
        user_query = "SELECT name FROM user WHERE email = %s"
        cursor.execute(user_query, (order["email"],))
        user = cursor.fetchone()
        user_name = user["name"] if user else order["email"]

        result = f"订单详情：\n"
        result += f"订单编号: {order['trade_no']}\n"
        result += f"订单ID: {order['id']}\n"
        result += f"用户名: {user_name}\n"
        result += f"用户邮箱: {order['email']}\n"
        result += f"订单金额: ¥{order['order_amount']}\n"
        result += f"地址ID: {order['address_id']}\n"
        result += f"支付状态: {order['pay_status']}\n"
        if order["pay_time"]:
            result += f"支付时间: {order['pay_time']}\n"
        if order["ali_trade_no"]:
            result += f"支付宝交易号: {order['ali_trade_no']}\n"
        result += f"创建时间: {order['create_time']}\n"

        # 查询订单商品
        query = """
            SELECT og.sku_id, og.goods_num, og.create_time,
                   g.name, g.p_price, g.jd_price, g.mk_price
            FROM order_goods og
            LEFT JOIN goods g ON og.sku_id = g.sku_id
            WHERE og.trade_no = %s
        """
        cursor.execute(query, (trade_no,))
        order_items = cursor.fetchall()

        if order_items:
            products_data = []
            for item in order_items:
                products_data.append({
                    "sku_id": item["sku_id"],
                    "name": item["name"] or "未知商品",
                    "p_price": item["p_price"],
                    "jd_price": item["jd_price"],
                    "mk_price": item["mk_price"]
                })

            product_json = build_product_list_json(products_data)
            result += f"\n订单商品（共 {len(order_items)} 件）：\n"
            result += product_json + "\n"

            total_price = 0
            for item in order_items:
                price = item["p_price"] or item["jd_price"] or item["mk_price"]
                if price:
                    total_price += float(price) * item["goods_num"]

            result += f"订单商品总价: ¥{total_price:.2f}\n"
        else:
            result += "\n此订单暂无商品信息\n"

        cursor.close()
        conn.close()
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        if conn:
            conn.close()
        return f"查询订单详情时出错: {str(e)}"


@tool
def checkout_cart(user_email: str, address_id: int = 1) -> str:
    """将用户的购物车商品结算生成订单。"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"

        cursor = conn.cursor()

        if not user_email:
            return "无法确定当前用户身份。请确保您已登录，系统会自动识别您的身份。"

        # 1. 验证用户存在
        query = "SELECT id, name FROM user WHERE email = %s"
        cursor.execute(query, (user_email,))
        user = cursor.fetchone()

        if not user:
            cursor.close()
            conn.close()
            return f"未找到Email为 '{user_email}' 的用户"

        # 2. 查询购物车商品
        query = """
            SELECT sc.sku_id, sc.nums, g.name, g.p_price, g.jd_price, g.mk_price
            FROM shopping_cart sc
            LEFT JOIN goods g ON sc.sku_id = g.sku_id
            WHERE sc.email = %s AND sc.is_delete = 0
        """
        cursor.execute(query, (user_email,))
        cart_items = cursor.fetchall()

        if not cart_items:
            cursor.close()
            conn.close()
            return "购物车为空，无法结算"

        # 3. 计算总金额
        total_amount = 0
        for item in cart_items:
            price = item["p_price"] or item["jd_price"] or item["mk_price"]
            if price:
                total_amount += float(price) * item["nums"]

        # 4. 生成订单号
        trade_no = f"ORD{int(time.time())}{random.randint(1000, 9999)}"

        # 5. 创建订单
        order_query = """
            INSERT INTO `order`
                (trade_no, email, order_amount, address_id, pay_status, create_time)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """
        order_params = (trade_no, user_email, total_amount, address_id, "待支付")
        cursor.execute(order_query, order_params)
        order_id = cursor.lastrowid

        # 6. 添加订单商品
        for item in cart_items:
            goods_query = """
                INSERT INTO order_goods
                    (trade_no, sku_id, goods_num, create_time)
                VALUES (%s, %s, %s, NOW())
            """
            goods_params = (trade_no, item["sku_id"], item["nums"])
            cursor.execute(goods_query, goods_params)

        # 7. 清空购物车（标记为删除）
        clear_cart_query = """
            UPDATE shopping_cart
            SET is_delete = 1, update_time = NOW()
            WHERE email = %s AND is_delete = 0
        """
        cursor.execute(clear_cart_query, (user_email,))

        conn.commit()

        result = "✅ 订单创建成功！\n\n"
        result += "订单信息：\n"
        result += f"- 订单编号: {trade_no}\n"
        result += f"- 订单ID: {order_id}\n"
        result += f"- 订单金额: ¥{total_amount:.2f}\n"
        result += f"- 收货地址ID: {address_id}\n"
        result += f"- 支付状态: 待支付\n"
        result += f"- 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        result += f"共结算 {len(cart_items)} 件商品，购物车已清空。\n"
        result += "请尽快完成支付！"

        cursor.close()
        conn.close()
        return result

    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        return f"结算购物车时出错: {str(e)}"