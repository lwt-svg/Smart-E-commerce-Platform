# Text2Sql工具
import pymysql
from .config import DB_CONFIG

def get_database_schema() -> str:
    """获取数据库结构描述，返回格式化的字符串"""
    conn = None
    cursor = None
    try:
        # 直接创建连接，使用默认的元组游标（cursorclass=None 或 pymysql.cursors.Cursor）
        conn = pymysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.Cursor  # 使用元组游标
        )
        cursor = conn.cursor()

        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        schema_lines = ["数据库包含以下表："]

        for row in tables:
            # row 现在是元组，第一个元素是表名
            table_name = row[0]
            schema_lines.append(f"\n表 {table_name} 的列：")
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = cursor.fetchall()
            for col in columns:
                col_name, col_type, is_null, key, default, extra = col
                schema_lines.append(f"  - {col_name} ({col_type}){' PRIMARY KEY' if key == 'PRI' else ''}")

        return "\n".join(schema_lines)

    except Exception as e:
        return f"获取数据库结构时出错: {str(e)}"
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()