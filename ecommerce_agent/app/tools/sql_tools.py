# app/tools/sql_tool.py
import pymysql
from langchain.tools import tool
from ..database import get_db_connection

@tool
def execute_sql(sql: str) -> str:
    """
    执行 SQL 查询并返回结果。只能执行 SELECT 语句，严禁执行修改数据的操作。
    输入应为完整的 SQL SELECT 查询语句。
    """
    # 安全检查：只允许 SELECT 语句（忽略大小写和前后空格）
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return "错误：只允许执行 SELECT 查询。如果您想查询数据，请使用 SELECT 语句。"

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return "数据库连接失败"
        cursor = conn.cursor(pymysql.cursors.DictCursor)  # 返回字典格式
        cursor.execute(sql)
        results = cursor.fetchall()
        if not results:
            return "查询无结果。"
        # 将结果列表格式化为易读的文本
        # 这里简单返回 JSON 格式，模型会自己解读
        import json
        return json.dumps(results, ensure_ascii=False, default=str)
    except Exception as e:
        return f"执行 SQL 出错: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()