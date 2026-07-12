#商品细分类脚本

import json
import re
import time
import traceback
from typing import Optional, Dict, Any, List, Tuple

from app.database import get_db_connection
from my_llm import llm
from langchain_core.messages import HumanMessage, SystemMessage


BATCH_SIZE = 100
LLM_BATCH_SIZE = 10
SLEEP_SECONDS = 0.1
SKIP_EXISTING = True
MAX_RETRY = 2

ALLOWED_CATEGORIES = [
    "手机数码", "电脑办公", "家用电器", "服饰鞋靴", "箱包皮具",
    "美妆护肤", "食品饮料", "母婴玩具", "家居生活", "运动户外",
    "汽车用品", "图书文娱", "宠物生活", "医疗健康", "其他"
]


def safe_str(v) -> str:
    return str(v).strip() if v is not None else ""


def extract_json(text: str) -> Any:
    if not text:
        return None
    text = text.strip()

    # 去掉 markdown code block
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    m = re.search(r"\[[\s\S]*\]|\{[\s\S]*\}", text)
    if m:
        text = m.group(0)

    try:
        return json.loads(text)
    except Exception:
        return None


def normalize_brand(brand: str) -> str:
    b = safe_str(brand)
    if not b:
        return "未知"

    low = b.lower()
    mapping = {
        "apple": "苹果",
        "iphone": "苹果",
        "huawei": "华为",
        "mate": "华为",
        "nova": "华为",
        "pura": "华为",
        "xiaomi": "小米",
        "redmi": "小米",
        "mi": "小米",
        "honor": "荣耀",
        "oppo": "OPPO",
        "vivo": "vivo",
        "samsung": "三星",
        "thinkpad": "联想",
        "lenovo": "联想",
        "acer": "宏碁",
        "asus": "华硕",
        "dell": "戴尔",
        "hp": "惠普",
    }

    for k, v in mapping.items():
        if k in low:
            return v

    if "宏基" in b:
        return "宏碁"

    return b


def normalize_category(category: str) -> str:
    c = safe_str(category)
    if not c:
        return "其他"

    mapping = {
        "手机卡": "流量卡",
        "电话卡": "流量卡",
        "上网卡": "流量卡",
        "sim卡": "流量卡",
        "SIM卡": "流量卡",
        "vr": "VR眼镜",
        "VR": "VR眼镜",
        "智能眼镜": "VR眼镜",
        "手机配件": "配件",
        "附件": "配件",
    }

    if c in mapping:
        return mapping[c]

    if c not in ALLOWED_CATEGORIES:
        return "其他"

    return c


def rule_based_category(name: str) -> Optional[str]:
    if not name:
        return None

    text = name
    low = text.lower()

    if any(k in text for k in ["流量卡", "电话卡", "手机卡", "上网卡"]):
        return "流量卡"
    if any(k in low for k in ["vr眼镜", "虚拟现实", "智能vr", "ar眼镜", "vr "]):
        return "VR眼镜"
    if "电视" in text:
        return "电视"
    if any(k in text for k in ["手机壳", "保护壳", "保护套"]):
        return "手机壳"
    if any(k in text for k in ["贴膜", "钢化膜"]):
        return "贴膜"
    if "膜" in text and any(k in text for k in ["手机", "iPhone", "华为", "小米", "荣耀", "OPPO", "vivo"]):
        return "贴膜"
    if any(k in text for k in ["充电器", "快充", "适配器"]):
        return "充电器"
    if any(k in text for k in ["数据线", "充电线"]):
        return "数据线"
    if any(k in text for k in ["耳机", "耳麦", "蓝牙耳机"]):
        return "耳机"
    if any(k in text for k in ["手表", "watch"]):
        return "手表"
    if any(k in text for k in ["手环", "腕带"]):
        return "手环"
    if any(k in text for k in ["平板", "iPad", "ipad", "MatePad", "matepad", "Pad"]):
        return "平板"
    if any(k in low for k in ["laptop", "notebook", "笔记本", "游戏本", "超薄本"]):
        return "笔记本"
    if any(k in text for k in ["路由器", "wifi", "WiFi"]):
        return "路由器"
    if any(k in text for k in ["相机", "摄像机", "摄影"]):
        return "相机"
    if any(k in text for k in ["音箱", "音响", "speaker"]):
        return "音箱"

    return None


def rule_based_brand(name: str) -> Optional[str]:
    if not name:
        return None

    text = name.strip()
    low = text.lower()

    patterns = [
        (r"^神舟战神", "神舟"),
        (r"^神舟", "神舟"),
        (r"^华为", "华为"),
        (r"^荣耀", "荣耀"),
        (r"^小米", "小米"),
        (r"^红米", "小米"),
        (r"^苹果", "苹果"),
        (r"^iphone", "苹果"),
        (r"^联想", "联想"),
        (r"^thinkpad", "联想"),
        (r"^微星", "微星"),
        (r"^宏碁", "宏碁"),
        (r"^宏基", "宏碁"),
        (r"^戴尔", "戴尔"),
        (r"^惠普", "惠普"),
        (r"^华硕", "华硕"),
        (r"^oppo", "OPPO"),
        (r"^vivo", "vivo"),
        (r"^三星", "三星"),
    ]

    for pat, brand in patterns:
        if re.search(pat, text, re.I):
            return brand

    for keyword, brand in [
        ("神舟战神", "神舟"),
        ("神舟", "神舟"),
        ("华为", "华为"),
        ("荣耀", "荣耀"),
        ("小米", "小米"),
        ("红米", "小米"),
        ("苹果", "苹果"),
        ("iphone", "苹果"),
        ("联想", "联想"),
        ("thinkpad", "联想"),
        ("微星", "微星"),
        ("宏碁", "宏碁"),
        ("宏基", "宏碁"),
        ("戴尔", "戴尔"),
        ("惠普", "惠普"),
        ("华硕", "华硕"),
        ("oppo", "OPPO"),
        ("vivo", "vivo"),
        ("三星", "三星"),
    ]:
        if keyword.lower() in low:
            return brand

    return None


def classify_one_rule(name: str) -> Dict[str, str]:
    brand = rule_based_brand(name)
    category = rule_based_category(name)

    if brand and category:
        return {"main_brand": normalize_brand(brand), "main_category": normalize_category(category)}

    if brand or category:
        return {
            "main_brand": normalize_brand(brand or "未知"),
            "main_category": normalize_category(category or "其他")
        }

    return {"main_brand": "", "main_category": ""}


def call_llm_batch(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    lines = [f'{item["id"]}. {item["name"]}' for item in items]

    prompt = f"""
你是一个电商商品结构化信息抽取助手。

请对下面每条商品标题提取：
- main_brand：主品牌
- main_category：主类目

要求：
- 只输出 JSON 数组，不要输出解释
- 数组里的每个对象必须包含 id、main_brand、main_category
- 如果商品标题中出现“支持/兼容/适配 苹果/华为/小米”等字样，不要把这些兼容品牌当主品牌
- 如果存在多个品牌，优先判断标题最前面的、最像商品真实归属的品牌
- main_category 尽量从以下值中选：
{ALLOWED_CATEGORIES}
- 如果无法判断，main_brand 返回 "未知"，main_category 返回 "其他"

商品列表：
{chr(10).join(lines)}
"""

    print(f"[LLM] 请求开始，批量 {len(items)} 条")

    resp = llm.invoke([
        SystemMessage(content="你是一个严格输出 JSON 数组的电商商品分类助手，只能输出 JSON，不要解释，不要 Markdown。"),
        HumanMessage(content=prompt)
    ])

    content = getattr(resp, "content", str(resp))
    print(f"[LLM] 返回内容前200字：{content[:200]}")

    data = extract_json(content)
    results = []

    if isinstance(data, list):
        for x in data:
            if not isinstance(x, dict):
                continue
            results.append({
                "id": x.get("id"),
                "main_brand": normalize_brand(x.get("main_brand", "未知")),
                "main_category": normalize_category(x.get("main_category", "其他"))
            })
    else:
        print("[LLM] JSON 解析失败")

    return results


def fetch_goods_batch(cursor, offset: int, limit: int):
    sql = """
        SELECT id, name, main_brand, main_category
        FROM goods
        ORDER BY id
        LIMIT %s OFFSET %s
    """
    cursor.execute(sql, (limit, offset))
    return cursor.fetchall()


def update_goods_batch(cursor, rows: List[Tuple[str, str, int]]):
    sql = """
        UPDATE goods
        SET main_brand = %s,
            main_category = %s
        WHERE id = %s
    """
    cursor.executemany(sql, rows)


def run():
    print("=" * 60)
    print("程序开始运行")
    print("=" * 60)

    conn = None

    try:
        print("[DB] 准备连接数据库...")
        conn = get_db_connection()
        if not conn:
            print("[DB] 数据库连接失败，conn=None")
            return
        print("[DB] 数据库连接成功")

        cursor = conn.cursor()

        print("[DB] 查询商品总数...")
        cursor.execute("SELECT COUNT(*) AS cnt FROM goods")
        total = cursor.fetchone()["cnt"]
        print(f"[DB] 商品总数：{total}")

        offset = 0
        processed = 0
        updated = 0

        while offset < total:
            print(f"\n[BATCH] 读取 offset={offset}, limit={BATCH_SIZE}")
            batch = fetch_goods_batch(cursor, offset, BATCH_SIZE)
            print(f"[BATCH] 读取到 {len(batch)} 条")

            if not batch:
                print("[BATCH] 没有更多数据，结束")
                break

            rule_updates = []
            llm_candidates = []

            for row in batch:
                goods_id = row["id"]
                name = safe_str(row.get("name"))
                existing_brand = safe_str(row.get("main_brand"))
                existing_category = safe_str(row.get("main_category"))

                if SKIP_EXISTING and existing_brand and existing_category:
                    print(f"[SKIP] id={goods_id} 已有品牌和类目，跳过")
                    processed += 1
                    continue

                if not name:
                    print(f"[SKIP] id={goods_id} 商品名为空，跳过")
                    processed += 1
                    continue

                rule_result = classify_one_rule(name)
                rb = rule_result["main_brand"]
                rc = rule_result["main_category"]

                if rb and rc:
                    print(f"[RULE] id={goods_id} | brand={rb} | category={rc}")
                    rule_updates.append((rb, rc, goods_id))
                else:
                    print(f"[LLM-NEED] id={goods_id} | name={name}")
                    llm_candidates.append({"id": goods_id, "name": name})

                processed += 1

            llm_updates = []
            if llm_candidates:
                print(f"[LLM] 本批需要模型处理 {len(llm_candidates)} 条")
                for i in range(0, len(llm_candidates), LLM_BATCH_SIZE):
                    sub = llm_candidates[i:i + LLM_BATCH_SIZE]
                    llm_result = None
                    last_err = None

                    for retry in range(MAX_RETRY):
                        try:
                            print(f"[LLM] 第 {i // LLM_BATCH_SIZE + 1} 小批，第 {retry + 1} 次尝试")
                            llm_result = call_llm_batch(sub)
                            break
                        except Exception as e:
                            last_err = e
                            print(f"[LLM] 调用失败：{e}")
                            time.sleep(1)

                    if llm_result is None:
                        print(f"[LLM] 批量失败，跳过这一批：{last_err}")
                        continue

                    result_map = {x["id"]: x for x in llm_result if x.get("id") is not None}
                    for item in sub:
                        rid = item["id"]
                        rr = result_map.get(rid, {})
                        main_brand = rr.get("main_brand", "未知")
                        main_category = rr.get("main_category", "其他")
                        print(f"[LLM-OK] id={rid} | brand={main_brand} | category={main_category}")
                        llm_updates.append((main_brand, main_category, rid))

                    time.sleep(SLEEP_SECONDS)

            all_updates = rule_updates + llm_updates

            if all_updates:
                print(f"[DB] 准备更新 {len(all_updates)} 条")
                update_goods_batch(cursor, all_updates)
                conn.commit()
                updated += len(all_updates)
                print(f"[DB] 更新完成，已提交")

            offset += BATCH_SIZE
            print(f"[BATCH] 本批结束，累计 processed={processed}, updated={updated}")

        print("\n" + "=" * 60)
        print(f"程序完成：processed={processed}, updated={updated}")
        print("=" * 60)

    except Exception:
        print("\n[ERROR] 程序异常，完整堆栈如下：")
        traceback.print_exc()

    finally:
        if conn:
            try:
                conn.close()
                print("[DB] 数据库已关闭")
            except Exception:
                pass


if __name__ == "__main__":
    run()