# ecommerce_agent_api.py
from fastapi import FastAPI, HTTPException, Body, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import sys
import os
import json
import time
import random
from datetime import datetime
from pymysql import connect
from pymysql.cursors import DictCursor
from langchain.tools import tool
from langchain.agents import create_agent
from my_llm import llm
import jwt
from fastapi.middleware.cors import CORSMiddleware

# 设置当前目录
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="电商助手API", description="电商智能客服助手API服务")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT配置
JWT_SECRET_KEY = "django-insecure-9jal3=*t5n-!8^ns-w9&yw7j9s1g&niy+q!em-x=-wun129zrj"
JWT_ALGORITHM = "HS256"

def verify_jwt_token(token: str) -> Optional[dict]:
    """
    验证JWT token并返回payload
    """
    try:
        # 移除可能的Bearer前缀
        if token.startswith("Bearer "):
            token = token[7:]
        
        payload = jwt.decode(
            token, 
            JWT_SECRET_KEY, 
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True}
        )
        return payload
    except jwt.ExpiredSignatureError:
        print("Token已过期")
        return None
    except jwt.InvalidTokenError as e:
        print(f"无效Token: {e}")
        return None
    except Exception as e:
        print(f"Token验证错误: {e}")
        return None

def get_user_email_from_token(token: Optional[str]) -> Optional[str]:
    """
    从token中获取用户email
    """
    if not token:
        return None
    
    payload = verify_jwt_token(token)
    if not payload:
        return None
    
    # 根据token结构获取username（实际上是email）
    return payload.get("username")

# 数据库配置
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "happiness*gjb",
    "database": "muxi_shop"
}

# 数据库连接函数
def get_db_connection():
    """获取数据库连接"""
    try:
        connection = connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            charset='utf8mb4',
            cursorclass=DictCursor
        )
        return connection
    except Exception as e:
        print(f"数据库连接错误: {e}")
        return None

# --- 复制所有工具函数（与你的原代码相同）---
# 这里省略了具体的工具函数定义，直接复制你的工具函数
@tool
def search_products_by_category(category_name: str, limit: int = 10) -> str:
    """根据分类搜索商品。"""
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        # 分类映射
        category_map = {
            "电子产品": [1], "电子": [1], "数码": [1], "手机": [1], "电脑": [1],
            "平板": [1], "笔记本": [1], "游戏本": [1], "台式机": [1], "耳机": [1],
            "音响": [1], "键盘": [1], "鼠标": [1], "显示器": [1], "摄像头": [1],
            "硬盘": [1], "服装": [2, 3], "衣服": [2, 3], "服饰": [2, 3], "男装": [2],
            "女装": [3], "上衣": [2, 3], "裤子": [2, 3], "鞋子": [2, 3], "食品": [4],
            "零食": [4], "饮料": [4], "水": [4], "酒": [4], "家用电器": [5], "家电": [5],
            "电视": [5], "冰箱": [5], "洗衣机": [5], "空调": [5], "微波炉": [5],
            "书籍": [6], "图书": [6], "教材": [6], "小说": [6], "杂志": [6],
        }
        
        # 查找匹配的分类ID
        category_ids = []
        for key, ids in category_map.items():
            if key in category_name:
                category_ids.extend(ids)
        
        if category_ids:
            placeholders = ','.join(['%s'] * len(category_ids))
            query = f"""SELECT g.sku_id, g.name, g.type_id, ANY_VALUE(c.reference_name) as comment_name
                        FROM goods g
                        LEFT JOIN comment c ON g.sku_id = c.sku_id
                        WHERE g.type_id IN ({placeholders})
                        GROUP BY g.sku_id, g.name, g.type_id
                        LIMIT %s"""
            
            params = tuple(category_ids) + (limit,)
            cursor.execute(query, params)
        else:
            query = """SELECT g.sku_id, g.name, g.type_id, ANY_VALUE(c.reference_name) as comment_name
                        FROM goods g
                        LEFT JOIN comment c ON g.sku_id = c.sku_id
                        WHERE g.name LIKE %s 
                        GROUP BY g.sku_id, g.name, g.type_id
                        LIMIT %s"""
            params = (f"%{category_name}%", limit)
            cursor.execute(query, params)
        
        products = cursor.fetchall()
        
        if not products:
            return f"在分类 '{category_name}' 中没有找到相关商品"
        
        result = f"在分类 '{category_name}' 中找到 {len(products)} 个相关商品：\n"
        for i, p in enumerate(products, 1):
            product_name = p['comment_name'] if p['comment_name'] else p['name']
            result += f"\n{i}. 商品: {product_name}\n"
            result += f"   SKU编号: {p['sku_id']}\n"
            result += f"   分类ID: {p['type_id']}\n"
        
        cursor.close()
        conn.close()
        return result
        
    except Exception as e:
        return f"搜索商品时出错: {str(e)}"

@tool
def get_product_price(product_name: str) -> str:
    """查询商品价格。"""
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        query = """SELECT g.sku_id, g.name, g.p_price, g.jd_price, g.mk_price, g.type_id,
                            ANY_VALUE(c.reference_name) as comment_name
                    FROM goods g
                    LEFT JOIN comment c ON g.sku_id = c.sku_id
                    WHERE g.name LIKE %s 
                    GROUP BY g.sku_id, g.name, g.p_price, g.jd_price, g.mk_price, g.type_id
                    LIMIT 5"""
        params = (f"%{product_name}%",)
        cursor.execute(query, params)
        products = cursor.fetchall()
        
        if not products:
            # 尝试在comment表中查找
            query = """SELECT DISTINCT sku_id, reference_name 
                        FROM comment 
                        WHERE reference_name LIKE %s 
                        LIMIT 5"""
            cursor.execute(query, params)
            products = cursor.fetchall()
        
        if not products:
            return f"未找到包含 '{product_name}' 的商品"
        
        if len(products) == 1:
            p = products[0]
            product_name_found = p['comment_name'] if 'comment_name' in p else p.get('reference_name', p.get('name', '未知商品'))
            sku_id = p['sku_id']
            
            # 获取价格
            price = None
            if 'p_price' in p and p['p_price']:
                price = p['p_price']
            elif 'jd_price' in p and p['jd_price']:
                price = p['jd_price']
            elif 'mk_price' in p and p['mk_price']:
                price = p['mk_price']
            
            if price:
                result = f"商品信息:\n- 名称: {product_name_found}\n- SKU编号: {sku_id}\n- 促销价: ¥{price}"
            else:
                result = f"商品信息:\n- 名称: {product_name_found}\n- SKU编号: {sku_id}\n- 价格: 暂无价格信息"
        else:
            result = f"找到 {len(products)} 个相关商品：\n"
            for i, p in enumerate(products, 1):
                product_name_found = p['comment_name'] if 'comment_name' in p else p.get('reference_name', p.get('name', '未知商品'))
                result += f"\n{i}. {product_name_found}\n"
                result += f"   SKU编号: {p['sku_id']}\n"
                
                prices = []
                if 'p_price' in p and p['p_price']:
                    prices.append(f"促销价: ¥{p['p_price']}")
                if 'jd_price' in p and p['jd_price']:
                    prices.append(f"京东价: ¥{p['jd_price']}")
                if 'mk_price' in p and p['mk_price']:
                    prices.append(f"市场价: ¥{p['mk_price']}")
                
                if prices:
                    result += f"   价格: {', '.join(prices)}\n"
                else:
                    result += f"   价格: 暂无价格信息\n"
        
        cursor.close()
        conn.close()
        return result
        
    except Exception as e:
        return f"查询商品价格时出错: {str(e)}"

@tool
def get_product_comments(product_name: str, limit: int = 5) -> str:
    """查询商品评论和评分。"""
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        query = """SELECT DISTINCT sku_id, reference_name 
                    FROM comment 
                    WHERE reference_name LIKE %s"""
        params = (f"%{product_name}%",)
        cursor.execute(query, params)
        products = cursor.fetchall()
        
        if not products:
            return f"未找到包含 '{product_name}' 的商品"
        
        result = ""
        for product in products:
            sku_id = product['sku_id']
            product_name_found = product['reference_name']
            
            # 获取评论
            query = """SELECT id, content, score, create_time, nickname 
                        FROM comment 
                        WHERE sku_id = %s 
                        ORDER BY create_time DESC 
                        LIMIT %s"""
            params = (sku_id, limit)
            cursor.execute(query, params)
            comments = cursor.fetchall()
            
            if not comments:
                result += f"\n商品 '{product_name_found}' 暂无评论\n"
                continue
            
            # 计算平均评分
            query = "SELECT AVG(score) as avg_score, COUNT(*) as total_comments FROM comment WHERE sku_id = %s"
            cursor.execute(query, (sku_id,))
            stats = cursor.fetchone()
            
            avg_score = float(stats['avg_score']) if stats['avg_score'] else 0
            total_comments = stats['total_comments']
            
            result += f"\n【{product_name_found} 的评论】\n"
            result += f"平均评分: {avg_score:.1f} 分，共 {total_comments} 条评论\n"
            result += f"\n最新 {len(comments)} 条评论：\n"
            
            for i, c in enumerate(comments, 1):
                result += f"\n{i}. 用户 {c['nickname']} - {c['score']} 星\n"
                result += f"   评论: {c['content']}\n"
                result += f"   时间: {c['create_time']}\n"
        
        cursor.close()
        conn.close()
        return result if result else f"商品 '{product_name}' 暂无评论"
        
    except Exception as e:
        return f"查询商品评论时出错: {str(e)}"

@tool
def recommend_products_by_budget(budget: float, category: str = None) -> str:
    """根据预算推荐商品。"""
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        if category:
            category_map = {
                "电子产品": [1], "电子": [1], "数码": [1], "手机": [1], "电脑": [1],
                "平板": [1], "笔记本": [1], "游戏本": [1], "台式机": [1], "耳机": [1],
                "音响": [1], "键盘": [1], "鼠标": [1], "显示器": [1], "摄像头": [1],
                "硬盘": [1], "服装": [2, 3], "衣服": [2, 3], "服饰": [2, 3], "男装": [2],
                "女装": [3], "食品": [4], "零食": [4], "饮料": [4], "家用电器": [5],
                "家电": [5], "电视": [5], "冰箱": [5], "洗衣机": [5], "空调": [5],
                "微波炉": [5], "书籍": [6], "图书": [6], "教材": [6], "小说": [6],
                "杂志": [6],
            }
            
            category_ids = []
            for key, ids in category_map.items():
                if key in category:
                    category_ids.extend(ids)
            
            if category_ids:
                placeholders = ','.join(['%s'] * len(category_ids))
                query = f"""SELECT g.sku_id, g.name, g.p_price, g.jd_price, g.mk_price, g.type_id,
                                    ANY_VALUE(c.reference_name) as comment_name
                            FROM goods g
                            LEFT JOIN comment c ON g.sku_id = c.sku_id
                            WHERE g.type_id IN ({placeholders})
                            AND (g.p_price <= %s OR g.jd_price <= %s)
                            GROUP BY g.sku_id, g.name, g.p_price, g.jd_price, g.mk_price, g.type_id
                            ORDER BY COALESCE(g.p_price, g.jd_price, g.mk_price) DESC
                            LIMIT 10"""
                
                params = tuple(category_ids) + (budget, budget)
                cursor.execute(query, params)
            else:
                query = """SELECT g.sku_id, g.name, g.p_price, g.jd_price, g.mk_price, g.type_id,
                                    ANY_VALUE(c.reference_name) as comment_name
                            FROM goods g
                            LEFT JOIN comment c ON g.sku_id = c.sku_id
                            WHERE g.name LIKE %s 
                            AND (g.p_price <= %s OR g.jd_price <= %s)
                            GROUP BY g.sku_id, g.name, g.p_price, g.jd_price, g.mk_price, g.type_id
                            ORDER BY COALESCE(g.p_price, g.jd_price, g.mk_price) DESC
                            LIMIT 10"""
                params = (f"%{category}%", budget, budget)
                cursor.execute(query, params)
        else:
            query = """SELECT g.sku_id, g.name, g.p_price, g.jd_price, g.mk_price, g.type_id,
                                ANY_VALUE(c.reference_name) as comment_name
                        FROM goods g
                        LEFT JOIN comment c ON g.sku_id = c.sku_id
                        WHERE (g.p_price <= %s OR g.jd_price <= %s)
                        GROUP BY g.sku_id, g.name, g.p_price, g.jd_price, g.mk_price, g.type_id
                        ORDER BY COALESCE(g.p_price, g.jd_price, g.mk_price) DESC
                        LIMIT 10"""
            params = (budget, budget)
            cursor.execute(query, params)
        
        products = cursor.fetchall()
        
        if not products:
            if category:
                return f"在分类 '{category}' 中，预算 ¥{budget} 内没有找到商品"
            else:
                return f"预算 ¥{budget} 内没有找到商品"
        
        result = f"在预算 ¥{budget} 内找到 {len(products)} 个商品：\n"
        
        for i, p in enumerate(products, 1):
            product_name = p['comment_name'] if p['comment_name'] else p['name']
            result += f"\n{i}. {product_name}\n"
            result += f"   SKU编号: {p['sku_id']}\n"
            
            prices = []
            if p['p_price']:
                prices.append(f"促销价: ¥{p['p_price']}")
            if p['jd_price']:
                prices.append(f"京东价: ¥{p['jd_price']}")
            if p['mk_price']:
                prices.append(f"市场价: ¥{p['mk_price']}")
            
            if prices:
                result += f"   价格: {', '.join(prices)}\n"
            else:
                result += f"   价格: 暂无价格信息\n"
            result += f"   分类ID: {p['type_id']}\n"
        
        cursor.close()
        conn.close()
        return result
        
    except Exception as e:
        return f"推荐商品时出错: {str(e)}"

@tool
def check_user_cart_and_orders(user_email: str) -> str:
    """查询当前登录用户的购物车和订单信息。
    
    Args:
        user_email: 用户Email地址。如果未提供，将从系统上下文中获取。
    
    注意：此工具只能查询当前登录用户自己的信息。
    """
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        # 如果没有提供user_email参数，说明应该从系统上下文中获取
        if not user_email:
            return "无法确定当前用户身份。请确保您已登录，系统会自动识别您的身份。"
        
        # 1. 查找用户信息
        query = """SELECT id, name, email 
                    FROM user 
                    WHERE email = %s 
                    LIMIT 1"""
        params = (user_email,)
        cursor.execute(query, params)
        user = cursor.fetchone()
        
        if not user:
            cleaned_email = user_email.strip()
            if cleaned_email != user_email:
                cursor.execute(query, (cleaned_email,))
                user = cursor.fetchone()
            
            if not user:
                return f"未找到用户信息。请确认您已登录正确的账户。"
        
        user_id = user['id']
        user_name = user['name'] if user['name'] else f"用户{user_id}"
        
        result = f"您的账户信息:\n- 用户名: {user_name}\n- 用户ID: {user_id}\n- Email: {user['email']}\n"
        
        # 2. 查询用户的购物车商品
        query = """SELECT sc.sku_id, sc.nums, g.name, g.p_price, g.jd_price, g.mk_price
                    FROM shopping_cart sc
                    LEFT JOIN goods g ON sc.sku_id = g.sku_id
                    WHERE sc.email = %s AND sc.is_delete = 0
                    ORDER BY sc.create_time DESC"""
        params = (user['email'],)
        cursor.execute(query, params)
        cart_items = cursor.fetchall()
        
        if cart_items:
            result += f"\n【您的购物车】共 {len(cart_items)} 件商品：\n"
            total_price = 0
            
            for i, item in enumerate(cart_items, 1):
                product_name = item['name'] if item['name'] else '未知商品'
                result += f"\n{i}. 商品: {product_name}\n"
                result += f"   SKU编号: {item['sku_id']}\n"
                result += f"   数量: {item['nums']}件\n"
                
                price = None
                if item['p_price']:
                    price = item['p_price']
                elif item['jd_price']:
                    price = item['jd_price']
                elif item['mk_price']:
                    price = item['mk_price']
                
                if price:
                    item_total = float(price) * item['nums']
                    total_price += item_total
                    result += f"   单价: ¥{price}\n"
                    result += f"   小计: ¥{item_total:.2f}\n"
                else:
                    result += f"   价格: 暂无价格信息\n"
            
            result += f"\n购物车总价: ¥{total_price:.2f}\n"
        else:
            result += "\n【您的购物车】购物车为空\n"
        
        # 3. 查询用户的订单
        query = """SELECT id, trade_no, order_amount, pay_status, pay_time, create_time 
                    FROM `order` 
                    WHERE email = %s AND is_delete = 0 
                    ORDER BY create_time DESC 
                    LIMIT 10"""
        params = (user['email'],)
        cursor.execute(query, params)
        orders = cursor.fetchall()
        
        if orders:
            result += f"\n【您的订单】共 {len(orders)} 个订单：\n"
            for i, order in enumerate(orders, 1):
                result += f"\n{i}. 订单编号: {order['trade_no']}\n"
                result += f"   订单ID: {order['id']}\n"
                result += f"   订单金额: ¥{order['order_amount']}\n"
                result += f"   支付状态: {order['pay_status']}\n"
                if order['pay_time']:
                    result += f"   支付时间: {order['pay_time']}\n"
                result += f"   创建时间: {order['create_time']}\n"
        else:
            result += "\n【您的订单】暂无订单记录\n"
        
        cursor.close()
        conn.close()
        return result
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"查询用户购物车和订单时出错: {str(e)}"

@tool
def get_order_details(trade_no: str) -> str:
    """查询订单的详细信息，包括订单商品。"""
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        # 查询订单基本信息
        query = """SELECT id, trade_no, email, order_amount, address_id, 
                            pay_status, pay_time, ali_trade_no, create_time 
                    FROM `order` 
                    WHERE trade_no = %s AND is_delete = 0"""
        params = (trade_no,)
        cursor.execute(query, params)
        order = cursor.fetchone()
        
        if not order:
            return f"未找到交易号为 '{trade_no}' 的订单"
        
        # 获取用户信息
        user_query = """SELECT name FROM user WHERE email = %s"""
        cursor.execute(user_query, (order['email'],))
        user = cursor.fetchone()
        user_name = user['name'] if user else order['email']
        
        result = f"订单详情：\n"
        result += f"订单编号: {order['trade_no']}\n"
        result += f"订单ID: {order['id']}\n"
        result += f"用户名: {user_name}\n"
        result += f"用户邮箱: {order['email']}\n"
        result += f"订单金额: ¥{order['order_amount']}\n"
        result += f"地址ID: {order['address_id']}\n"
        result += f"支付状态: {order['pay_status']}\n"
        if order['pay_time']:
            result += f"支付时间: {order['pay_time']}\n"
        if order['ali_trade_no']:
            result += f"支付宝交易号: {order['ali_trade_no']}\n"
        result += f"创建时间: {order['create_time']}\n"
        
        # 查询订单商品
        query = """SELECT og.sku_id, og.goods_num, og.create_time,
                            g.name, g.p_price, g.jd_price, g.mk_price
                    FROM order_goods og
                    LEFT JOIN goods g ON og.sku_id = g.sku_id
                    WHERE og.trade_no = %s"""
        cursor.execute(query, (trade_no,))
        order_items = cursor.fetchall()
        
        if order_items:
            result += f"\n订单商品（共 {len(order_items)} 件）：\n"
            total_price = 0
            
            for i, item in enumerate(order_items, 1):
                product_name = item['name'] if item['name'] else '未知商品'
                result += f"\n{i}. 商品: {product_name}\n"
                result += f"   SKU编号: {item['sku_id']}\n"
                result += f"   数量: {item['goods_num']}件\n"
                
                # 计算价格（优先使用促销价）
                price = None
                if item['p_price']:
                    price = item['p_price']
                elif item['jd_price']:
                    price = item['jd_price']
                elif item['mk_price']:
                    price = item['mk_price']
                
                if price:
                    item_total = float(price) * item['goods_num']
                    total_price += item_total
                    result += f"   单价: ¥{price}\n"
                    result += f"   小计: ¥{item_total:.2f}\n"
                else:
                    result += f"   价格: 暂无价格信息\n"
            
            result += f"\n订单商品总价: ¥{total_price:.2f}\n"
        else:
            result += "\n此订单暂无商品信息\n"
        
        cursor.close()
        conn.close()
        return result
        
    except Exception as e:
        return f"查询订单详情时出错: {str(e)}"

@tool
def checkout_cart(user_email: str, address_id: int = 1) -> str:
    """将用户的购物车商品结算生成订单。
                    
    Args:
        user_email: 用户的Email地址
        address_id: 收货地址ID（默认为1）
    """
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        if not user_email:
            return "无法确定当前用户身份。请确保您已登录，系统会自动识别您的身份。"
        
        # 1. 验证用户存在
        query = """SELECT id, name FROM user WHERE email = %s"""
        cursor.execute(query, (user_email,))
        user = cursor.fetchone()
        
        if not user:
            return f"未找到Email为 '{user_email}' 的用户"
        
        # 2. 查询购物车商品
        query = """SELECT sc.sku_id, sc.nums, g.name, g.p_price, g.jd_price, g.mk_price
                    FROM shopping_cart sc
                    LEFT JOIN goods g ON sc.sku_id = g.sku_id
                    WHERE sc.email = %s AND sc.is_delete = 0"""
        cursor.execute(query, (user_email,))
        cart_items = cursor.fetchall()
        
        if not cart_items:
            return "购物车为空，无法结算"
        
        # 3. 计算总金额
        total_amount = 0
        for item in cart_items:
            price = None
            if item['p_price']:
                price = item['p_price']
            elif item['jd_price']:
                price = item['jd_price']
            elif item['mk_price']:
                price = item['mk_price']
            
            if price:
                total_amount += float(price) * item['nums']
        
        # 4. 生成订单号
        trade_no = f"ORD{int(time.time())}{random.randint(1000, 9999)}"
        
        # 5. 创建订单
        order_query = """INSERT INTO `order` 
                            (trade_no, email, order_amount, address_id, pay_status, create_time) 
                            VALUES (%s, %s, %s, %s, %s, NOW())"""
        order_params = (trade_no, user_email, total_amount, address_id, "待支付")
        
        cursor.execute(order_query, order_params)
        order_id = cursor.lastrowid
        
        # 6. 添加订单商品
        for item in cart_items:
            goods_query = """INSERT INTO order_goods 
                                (trade_no, sku_id, goods_num, create_time) 
                                VALUES (%s, %s, %s, NOW())"""
            goods_params = (trade_no, item['sku_id'], item['nums'])
            cursor.execute(goods_query, goods_params)
        
        # 7. 清空购物车（标记为删除）
        clear_cart_query = """UPDATE shopping_cart 
                                SET is_delete = 1, update_time = NOW() 
                                WHERE email = %s AND is_delete = 0"""
        cursor.execute(clear_cart_query, (user_email,))
        
        # 提交事务
        conn.commit()
        
        result = f"✅ 订单创建成功！\n\n"
        result += f"订单信息：\n"
        result += f"- 订单编号: {trade_no}\n"
        result += f"- 订单ID: {order_id}\n"
        result += f"- 订单金额: ¥{total_amount:.2f}\n"
        result += f"- 收货地址ID: {address_id}\n"
        result += f"- 支付状态: 待支付\n"
        result += f"- 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        result += f"共结算 {len(cart_items)} 件商品，购物车已清空。\n"
        result += f"请尽快完成支付！"
        
        cursor.close()
        conn.close()
        return result
        
    except Exception as e:
        # 回滚事务
        if conn:
            conn.rollback()
        return f"结算购物车时出错: {str(e)}"

@tool
def cancel_order(trade_no: str) -> str:
    """取消订单（将订单标记为删除状态）。
                    
    Args:
        trade_no: 订单交易号
    """
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        # 1. 检查订单是否存在且未删除
        query = """SELECT id, trade_no, pay_status FROM `order` 
                    WHERE trade_no = %s AND is_delete = 0"""
        cursor.execute(query, (trade_no,))
        order = cursor.fetchone()
        
        if not order:
            return f"未找到交易号为 '{trade_no}' 的有效订单"
        
        # 2. 检查订单状态（已支付的订单可能不能取消）
        if order['pay_status'] == "已支付":
            return f"订单 {trade_no} 已支付，无法取消。请联系客服处理。"
        
        # 3. 取消订单（标记为删除）
        cancel_query = """UPDATE `order` 
                            SET is_delete = 1, update_time = NOW() 
                            WHERE trade_no = %s"""
        cursor.execute(cancel_query, (trade_no,))
        
        conn.commit()
        
        result = f"✅ 订单取消成功！\n\n"
        result += f"订单编号: {trade_no}\n"
        result += f"订单ID: {order['id']}\n"
        result += f"取消时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += f"状态: 已取消"
        
        cursor.close()
        conn.close()
        return result
    except Exception as e:
        if conn:
            conn.rollback()
            return f"取消订单时出错: {str(e)}"
   

@tool
def pay_order(trade_no: str, ali_trade_no: str = None) -> str:
    '''支付订单工具'''
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        # 1. 检查订单是否存在且未删除
        query = """SELECT id, trade_no, pay_status FROM `order` 
                    WHERE trade_no = %s AND is_delete = 0"""
        cursor.execute(query, (trade_no,))
        order = cursor.fetchone()
        
        if not order:
            return f"未找到交易号为 '{trade_no}' 的有效订单"
        
        # 2. 检查订单状态
        if order['pay_status'] == "已支付":
            return f"订单 {trade_no} 已经是已支付状态，无需重复支付。"
        
        # 3. 更新订单支付状态
        if ali_trade_no:
            pay_query = """UPDATE `order` 
                            SET pay_status = '已支付', 
                                pay_time = NOW(),
                                ali_trade_no = %s,
                                update_time = NOW() 
                            WHERE trade_no = %s"""
            cursor.execute(pay_query, (ali_trade_no, trade_no))
        else:
            pay_query = """UPDATE `order` 
                            SET pay_status = '已支付', 
                                pay_time = NOW(),
                                update_time = NOW() 
                            WHERE trade_no = %s"""
            cursor.execute(pay_query, (trade_no,))
        
        conn.commit()
        
        result = f"✅ 订单支付成功！\n\n"
        result += f"订单编号: {trade_no}\n"
        result += f"订单ID: {order['id']}\n"
        result += f"支付状态: 已支付\n"
        result += f"支付时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        if ali_trade_no:
            result += f"支付宝交易号: {ali_trade_no}\n"
        
        cursor.close()
        conn.close()
        return result
        
    except Exception as e:
        if conn:
            conn.rollback()
        return f"支付订单时出错: {str(e)}"

@tool
def remove_cart_item(user_email: str, sku_id: str) -> str:
    """从购物车中删除指定商品。"""
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        
        cursor = conn.cursor()
        
        # 如果没有提供user_email参数
        if not user_email:
            return "请先登录以操作购物车。"
        if not sku_id:
            return "请指定要删除的商品SKU编号。"
        # 1. 检查商品是否在购物车中
        query = """SELECT id, sku_id, nums 
                    FROM shopping_cart 
                    WHERE email = %s AND sku_id = %s AND is_delete = 0"""
        cursor.execute(query, (user_email, sku_id))
        cart_item = cursor.fetchone()
        
        if not cart_item:
            return f"购物车中没有找到SKU为 '{sku_id}' 的商品"
        
        # 2. 删除商品（标记为删除）
        delete_query = """UPDATE shopping_cart 
                            SET is_delete = 1, update_time = NOW() 
                            WHERE email = %s AND sku_id = %s"""
        cursor.execute(delete_query, (user_email, sku_id))
        
        conn.commit()
        
        result = f"✅ 已从购物车中删除商品！\n\n"
        result += f"用户邮箱: {user_email}\n"
        result += f"SKU编号: {sku_id}\n"
        result += f"删除时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        cursor.close()
        conn.close()
        return result
        
    except Exception as e:
        if conn:
            conn.rollback()
        return f"删除购物车商品时出错: {str(e)}"

# 系统提示词
system_prompt = """你是一个专业的电商客服助手。

你的职责是：
1. 根据用户的需求搜索和推荐商品
2. 查询商品的价格、库存、评论等信息
3. 根据用户的预算推荐合适的商品
4. 查询当前登录用户的购物车和订单信息（注意：只能查询当前登录用户的信息）
5. 处理当前登录用户的订单相关操作：结算购物车、取消订单、支付订单、查询订单详情
6. 回答用户关于订单和购物的问题

重要安全规则：
- 用户只能查询和操作自己的购物车和订单
- 当系统提供当前登录用户的Email时，你必须使用这个Email来查询相关信息
- 如果系统没有提供用户Email，请提示用户先登录
- 绝对不要尝试查询其他用户的信息

注意：当前数据库有完整的商品信息和价格信息。

在与用户交互时：
- 始终保持友好和专业的态度
- 使用中文回复用户
- 提供清晰、有帮助的信息
- 如果找不到所需信息，诚实地告知用户
- 积极推荐商品，但要基于用户的实际需求
- 对于订单操作，要确认用户的操作意图，避免误操作"""

# 创建工具列表
all_tools = [
    search_products_by_category,
    get_product_price,
    get_product_comments,
    recommend_products_by_budget,
    check_user_cart_and_orders,
    get_order_details,
    checkout_cart,
    cancel_order,
    pay_order,
    remove_cart_item
]

# 初始化Agent
agent = create_agent(
    model=llm,
    tools=all_tools,
    system_prompt=system_prompt
)

# Pydantic模型定义
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    token: Optional[str] = None
    user_email: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    timestamp: str

# API端点
@app.get("/")
async def root():
    return {"message": "电商助手API服务已启动", "status": "running"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest,authorization: Optional[str] = Header(None)):
    """处理用户聊天请求"""
    try:
        print(f"收到聊天请求: {request.message[:50]}...")
        print(f"请求token参数: {request.token}")
        print(f"Authorization头部: {authorization}")
        
        # 确定使用哪个token来源
        # 优先级：1. 请求体中的token 2. Authorization头部
        token_to_use = None
        if request.token:
            token_to_use = request.token
            print("使用请求体中的token")
        elif authorization:
            token_to_use = authorization
            print("使用Authorization头部中的token")
        else:
            print("没有提供token")
        
        # 从token中获取用户email
        user_email = None
        if token_to_use:
            user_email = get_user_email_from_token(token_to_use)
            print(f"从token解析的用户email: {user_email}")
        elif request.user_email:
            # 向后兼容：如果直接提供了user_email参数
            user_email = request.user_email
            print(f"使用直接提供的user_email: {user_email}")
        
        # 构建用户上下文
        if user_email:
            # 创建带用户上下文的系统提示
            user_context_prompt = f"""当前登录用户: {user_email}
                重要安全规则：
                - 只能查询和操作用户 {user_email} 自己的购物车、订单等信息
                - 当用户询问购物车或订单时，必须使用用户email: {user_email}
                - 绝对不要使用其他用户的email或允许用户查询他人信息
            """
            
            # 将用户上下文添加到消息中
            user_message_with_context = f"{user_context_prompt}\n用户问题: {request.message}"
            
            result = agent.invoke({
                "messages": [
                    {"role": "user", "content": user_message_with_context}
                ]
            })
        else:
            # 没有用户身份的情况
            no_user_context_prompt = """注意：用户尚未登录或未提供身份验证信息。
                当用户询问购物车、订单等个人信息时，请提示用户先登录。"""
            
            no_user_message = f"{no_user_context_prompt}\n用户问题: {request.message}"
            
            result = agent.invoke({
                "messages": [
                    {"role": "user", "content": no_user_message}
                ]
            })
        
        response_text = result['messages'][-1].content
        
        return ChatResponse(
            response=response_text,
            session_id=request.session_id,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理请求时出错: {str(e)}")

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_initialized": True
    }

@app.get("/tools")
async def list_tools():
    """列出所有可用工具"""
    tool_list = [{
        "name": tool.name,
        "description": tool.description,
        "args": str(tool.args)
    } for tool in all_tools]
    
    return {
        "tools": tool_list,
        "count": len(tool_list)
    }

@app.get("/debug/token")
async def debug_token(authorization: Optional[str] = Header(None)):
    """调试JWT token解析"""
    if not authorization:
        return {"error": "没有提供token", "note": "你的token应该放在Authorization头部，没有'Bearer '前缀"}
    
    try:
        # 显示token信息
        token_preview = authorization[:50] + "..." if len(authorization) > 50 else authorization
        
        # 尝试验证token
        payload = verify_jwt_token(authorization)
        
        if payload:
            # 检查token是否过期
            exp_time = payload.get("exp")
            if exp_time:
                from datetime import datetime
                exp_datetime = datetime.fromtimestamp(exp_time)
                is_expired = datetime.now() > exp_datetime
            else:
                is_expired = False
            
            return {
                "status": "valid",
                "token_preview": token_preview,
                "payload": payload,
                "user_email": payload.get("username"),
                "expired": is_expired,
                "exp_time": exp_time,
                "exp_datetime": exp_datetime.isoformat() if exp_time else None
            }
        else:
            return {
                "status": "invalid",
                "token_preview": token_preview,
                "error": "无法验证token"
            }
    except Exception as e:
        return {
            "status": "error",
            "token_preview": token_preview,
            "error": str(e)
        }

@app.get("/test/connection")
async def test_connection():
    """测试数据库连接"""
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM user")
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return {
                "status": "success",
                "database": "connected",
                "user_count": result['count']
            }
        else:
            return {
                "status": "error",
                "database": "disconnected"
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
