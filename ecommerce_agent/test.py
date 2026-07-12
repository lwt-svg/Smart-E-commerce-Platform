import pandas as pd
import os
from sqlalchemy import create_engine, text
import glob
import pyarrow.parquet as pq

# ===== 配置 =====
MYSQL_HOST = 'localhost'
MYSQL_PORT = 3306
MYSQL_USER = 'root'
MYSQL_PASSWORD = '123456'   # 改成你的密码
MYSQL_DB = 'jddata_db'
DATA_DIR = r'D:\迅雷下载\JD_data\JD_data'   # 原始字符串，避免转义
BATCH_SIZE = 50000   # 每批写入的行数
# =================

# 1. 创建数据库引擎并建库
engine = create_engine(f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}')
with engine.connect() as conn:
    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DB}"))
    print(f"数据库 '{MYSQL_DB}' 已就绪。")

engine = create_engine(f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}')

# 2. 找到所有 bo_ 开头的文件夹
folders = glob.glob(os.path.join(DATA_DIR, 'bo_*'))
print(f"发现 {len(folders)} 个数据文件夹: {[os.path.basename(f) for f in folders]}")

for folder_path in folders:
    table_name = os.path.basename(folder_path)
    print(f"\n开始处理表: {table_name}")
    
    parquet_files = glob.glob(os.path.join(folder_path, '*.parquet'))
    if not parquet_files:
        print(f"  跳过（无 parquet 文件）")
        continue
    
    first_batch = True
    total_rows = 0
    
    for file_path in parquet_files:
        print(f"  处理文件: {os.path.basename(file_path)}")
        pf = pq.ParquetFile(file_path)
        
        for batch in pf.iter_batches(batch_size=BATCH_SIZE):
            df_batch = batch.to_pandas()
            
            if first_batch:
                df_batch.to_sql(table_name, con=engine, if_exists='replace', index=False)
                first_batch = False
            else:
                df_batch.to_sql(table_name, con=engine, if_exists='append', index=False)
            
            total_rows += len(df_batch)
            print(f"    已写入 {total_rows} 行", end='\r')
    
    print(f"\n  表 {table_name} 完成，总行数: {total_rows}")

print("\n所有数据导入完成！")