# 智能电商平台（Django + Vue3 + FastAPI + LangChain）

<div align="center">

![Django](https://img.shields.io/badge/Django-4.2-092E20?style=flat&logo=django)
![Vue](https://img.shields.io/badge/Vue-3.x-4FC08D?style=flat&logo=vue.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=flat&logo=fastapi)
![LangChain](https://img.shields.io/badge/LangChain-0.1-1C3C3C?style=flat)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?style=flat&logo=mysql)
![Redis](https://img.shields.io/badge/Redis-6.0+-DC382D?style=flat&logo=redis)

**前后端分离的电商平台，集成基于大模型的电商智能助手**

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [API文档](#-api-文档) • [部署指南](#-部署指南)

</div>

---

## 📋 项目概述

本项目是一个完整的电商解决方案，包含三大核心模块：

| 模块 | 技术 | 端口 | 职责 |
|------|------|------|------|
| **前端** | Vue3 + Element Plus | 8080 | 用户界面、交互 |
| **后端** | Django + DRF | 8000 | 业务逻辑、数据管理、JWT认证 |
| **智能体** | FastAPI + LangChain | 8001 | AI对话、意图识别、工具调用 |

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              用户浏览器                                   │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Nginx 反向代理 (:80)                             │
└───────────────┬─────────────────────┬─────────────────────┬─────────────┘
                │                     │                     │
                ▼                     ▼                     ▼
      ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
      │   Vue3 前端      │   │  Django 后端     │   │ FastAPI 智能体  │
      │   (端口: 8080)  │   │  (端口: 8000)   │   │  (端口: 8001)   │
      └─────────────────┘   └────────┬────────┘   └────────┬────────┘
                                     │                     │
                                     └──────────┬──────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
           ┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
           │   MySQL 8.0     │        │   Redis 6.0+    │        │  Ollama (本地)   │
           │   (端口: 3306)  │        │   (端口: 6379)  │        │  (端口: 11434)  │
           └─────────────────┘        └─────────────────┘        └─────────────────┘
```

---

## ✨ 功能特性

### 🛒 电商核心功能
- ✅ 用户注册/登录/JWT认证
- ✅ 商品分类浏览与搜索
- ✅ 购物车管理（增删改查）
- ✅ 订单创建与管理
- ✅ 支付宝沙箱支付集成
- ✅ 商品评论与评分
- ✅ 收货地址管理

### 🤖 智能助手功能
- ✅ **智能商品推荐** - 基于品牌、品类、预算的精准推荐
- ✅ **情感分析** - 自动分析商品评论情感倾向，提取正负面观点
- ✅ **观点检索** - 语义化检索商品优点/缺点
- ✅ **知识问答** - 售前/售后知识库智能问答
- ✅ **商品对比** - 多商品口碑对比分析
- ✅ **会话管理** - 支持多轮对话上下文
- ✅ **购物车操作** - 添加/查看/删除
- ✅ **订单查询** - 状态跟踪

---

## 📁 项目结构

```
ecommerce-project/
│
├── muxi_shop_web/              # Vue3 前端项目
│   ├── src/
│   │   ├── views/
│   │   │   ├── Agent/          # 智能助手聊天页
│   │   │   ├── Cart/           # 购物车
│   │   │   ├── Goods/          # 商品详情/列表
│   │   │   ├── Order/          # 订单
│   │   │   └── Payment/        # 支付
│   │   ├── components/
│   │   ├── network/            # API 请求封装
│   │   ├── router/
│   │   └── store/
│   ├── package.json
│   └── vue.config.js
│
├── muxi_shop_api/              # Django 后端项目
│   ├── apps/
│   │   ├── user/               # 用户管理
│   │   ├── goods/              # 商品管理
│   │   ├── cart/               # 购物车
│   │   ├── order/              # 订单
│   │   ├── pay/                # 支付(支付宝)
│   │   ├── comment/            # 评论
│   │   ├── address/            # 收货地址
│   │   └── agent/              # 智能助手代理
│   ├── utils/
│   │   ├── jwt_auth.py         # JWT 认证
│   │   └── ResponseMessage.py  # 统一响应封装
│   ├── static/
│   ├── manage.py
│   └── requirements.txt
│
└── ecommerce_agent/            # FastAPI 智能体项目
    ├── app/
    │   ├── agent.py            # 智能体核心逻辑
    │   ├── main.py             # FastAPI 入口
    │   ├── config.py           # 配置文件
    │   ├── database.py         # 数据库连接
    │   ├── auth.py             # JWT 认证
    │   └── tools/
    │       ├── product_tools.py        # 商品检索工具
    │       ├── review_analysis_tools.py # 评论分析工具
    │       ├── sentiment_analyzer.py   # 情感分析引擎
    │       ├── knowledge_tools.py      # 知识库工具
    │       └── order_cart_tools.py     # 订单购物车工具
    ├── knowledge/
    │   ├── presales/           # 售前知识库
    │   └── aftersales/         # 售后知识库
    ├── chroma_db/              # 向量数据库
    ├── build_knowledge_base.py # 构建知识库向量库
    ├── build_sentiment_reviews_db.py # 构建情感分析向量库
    ├── generate_comments.py    # 生成测试评论数据
    ├── run.py
    └── requirements.txt
```

---

## 🚀 快速开始

### 环境要求

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 后端 & 智能体 |
| Node.js | 18+ | 前端 |
| MySQL | 8.0+ | 数据库 |
| Redis | 6.0+ | 缓存 & 会话 |
| Ollama | latest | 本地大模型 |

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd ecommerce-project
```

### 2. 配置数据库

```sql
CREATE DATABASE muxi_shop DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. 启动后端 (Django)

```bash
cd muxi_shop_api

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 数据库迁移
python manage.py migrate

# 创建超级用户
python manage.py createsuperuser

# 启动服务
python manage.py runserver 8000
```

### 4. 启动前端 (Vue3)

```bash
cd muxi_shop_web

# 安装依赖
npm install

# 开发模式启动
npm run serve
```

### 5. 安装 Ollama 模型

```bash
# 安装嵌入模型
ollama pull bge-m3

# 安装对话模型
ollama pull qwen2.5
```

### 6. 启动智能体 (FastAPI)

```bash
cd ecommerce_agent

# 安装依赖
pip install -r requirements.txt

# 生成测试评论数据（可选）
python generate_comments.py

# 构建知识库向量库
python build_knowledge_base.py

# 构建情感分析向量库
python build_sentiment_reviews_db.py

# 启动服务
python run.py
```

---

## 🔧 配置说明

### 后端配置 (muxi_shop_api/muxi_shop_api/settings.py)

```python
# 数据库配置
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'muxi_shop',
        'USER': 'root',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}

# JWT 配置
JWT_SECRET_KEY = 'your-secret-key'

# 智能体服务地址
AGENT_API_URL = 'http://localhost:8001'
```

### 前端配置 (muxi_shop_web/.env)

```
VUE_APP_API_URL=http://localhost:8000
VUE_APP_AGENT_URL=http://localhost:8001
```

### 智能体配置 (ecommerce_agent/app/config.py)

```python
# 数据库配置
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your_password",
    "database": "muxi_shop"
}

# Redis 配置
REDIS_URL = "redis://localhost:6379/0"

# JWT 配置（与 Django 保持一致）
JWT_SECRET_KEY = "your-secret-key"
```

---

## 📚 API 文档

### 电商接口 (Django :8000)

#### 用户认证
| 接口 | 方法 | 描述 |
|------|------|------|
| `/user/register/` | POST | 用户注册 |
| `/user/login/` | POST | 用户登录 |
| `/user/info/` | GET | 获取用户信息 |

#### 商品管理
| 接口 | 方法 | 描述 |
|------|------|------|
| `/goods/category/<id>/<page>/` | GET | 商品分类列表 |
| `/goods/detail/<sku_id>/` | GET | 商品详情 |
| `/goods/search/<keyword>/<page>/<order>/` | GET | 商品搜索 |

#### 购物车 & 订单
| 接口 | 方法 | 描述 |
|------|------|------|
| `/cart/` | GET/POST | 购物车操作 |
| `/order/` | GET/POST | 订单操作 |
| `/pay/create/` | POST | 创建支付订单 |

### 智能体接口 (FastAPI :8001)

| 接口 | 方法 | 描述 |
|------|------|------|
| `/chat` | POST | 对话接口 |
| `/chat/sessions/list` | GET | 会话列表 |
| `/chat/sessions/{session_id}` | GET | 加载会话 |

### 请求示例

```bash
# 智能对话
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "推荐一款华为手机",
    "user_email": "user@example.com"
  }'
```

---

## 💬 使用示例

### 商品推荐
```
用户: 推荐一款华为手机
用户: 预算3000以内
用户: 第一款手机有什么优点？
```

### 情感分析
```
用户: 帮我分析一下这款手机的口碑
用户: 有什么缺点？
用户: 综合评价一下
```

### 商品对比
```
用户: 推荐两款手机
用户: 这两个手机哪个好？
```

### 知识问答
```
用户: 你们支持什么支付方式？
用户: 退货流程是什么？
```

---

## 🧠 意图识别

系统支持以下意图识别：

| 意图 | 关键词示例 |
|------|-----------|
| 商品搜索 | 推荐、查找、搜索、有没有 |
| 正面观点 | 优点、好评、值得买 |
| 负面观点 | 缺点、差评、槽点、避坑 |
| 情感分析 | 口碑分析、综合评价、咋样、怎么样 |
| 商品对比 | 对比、比较、哪个好 |
| 知识问答 | 支付方式、退货流程、配送 |
| 购物车 | 加购物车、购物车 |
| 订单查询 | 订单、我的订单 |

---

## 🗄️ 向量库说明

### 知识库向量库

```bash
python build_knowledge_base.py
```

| 输入 | 输出 | 用途 |
|------|------|------|
| `knowledge/presales/*.txt` | `chroma_db/presales/` | 售前知识问答 |
| `knowledge/aftersales/*.txt` | `chroma_db/aftersales/` | 售后知识问答 |

### 情感分析向量库

```bash
python build_sentiment_reviews_db.py
```

| 输入 | 输出 | 用途 |
|------|------|------|
| MySQL 评论表 | `chroma_db/reviews/` | 全部评论检索 |
| MySQL 评论表 | `chroma_db/reviews_positive/` | 正面观点检索 |
| MySQL 评论表 | `chroma_db/reviews_negative/` | 负面观点检索 |

---

## 🚀 部署指南

### Docker 部署（推荐）

#### 目录结构

```
/opt/ecommerce/
├── docker-compose.yml
├── muxi_shop_api/          # Django 后端
│   ├── Dockerfile
│   └── static/             # 静态文件目录
├── muxi_shop_web/          # Vue3 前端
│   ├── Dockerfile
│   └── nginx.conf
├── ecommerce_agent/        # FastAPI 智能体
│   ├── Dockerfile
│   ├── chroma_db/          # 向量数据库
│   └── knowledge/          # 知识库
├── mysql/
│   └── init/               # 数据库初始化脚本
└── nginx.conf
```

#### 服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network (app-network)              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   frontend (nginx:80) ──┬──► django:8000 ──► mysql:3306     │
│        │                │         │                          │
│        │                │         └──► redis:6379 (外部)     │
│        │                │                                      │
│        │                └──► fastapi:8001 ──► ollama:11434   │
│        │                              │                       │
│        └──► 静态文件 (/static/) ◄─────┘                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### 快速启动

```bash
cd /opt/ecommerce

# 构建并启动所有服务
docker-compose up -d --build

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f fastapi

# 停止服务
docker-compose down
```

#### 初始化 Ollama 模型

```bash
# 查看已有模型
docker exec -it ecommerce-ollama-1 ollama list

# 下载嵌入模型
docker exec -it ecommerce-ollama-1 ollama pull bge-m3

# 下载对话模型（可选）
docker exec -it ecommerce-ollama-1 ollama pull qwen2.5
```

#### 构建向量数据库

```bash
# 进入 fastapi 容器
docker exec -it ecommerce-fastapi-1 bash

# 构建知识库向量库
python build_knowledge_base.py

# 构建情感分析向量库
python build_sentiment_reviews_db.py
```

---

### Docker 部署踩坑指南

#### 踩坑一：CORS 跨域错误

**错误现象：**
```
Access to XMLHttpRequest at 'http://localhost:8001/health' from origin 'http://localhost' 
has been blocked by CORS policy
```

**解决方案：** 修改 `ecommerce_agent/app/config.py`

```python
ALLOWED_ORIGINS=[
    "http://localhost",
    "http://localhost:80",
    "http://127.0.0.1",
    "http://localhost:8080",
    "http://127.0.0.1:8080"
]
```

---

#### 踩坑二：商品图片 404

**错误现象：**
```
GET http://localhost/static/product_images/xxx.jpg 404 (Not Found)
```

**解决方案：**

1. 修改 `docker-compose.yml`，挂载静态文件：
```yaml
frontend:
  volumes:
    - ./muxi_shop_api/static:/usr/share/nginx/static:ro
```

2. 修改 `muxi_shop_web/nginx.conf`：
```nginx
location /static/ {
    alias /usr/share/nginx/static/;
    expires 30d;
}
```

---

#### 踩坑三：Agent 服务无法连接

**错误现象：**
```
[Agent] 请求出错 -> 设置离线 AxiosError: Network Error
```

**解决方案：** 修改 `muxi_shop_web/nginx.conf`，添加 FastAPI 路由代理：

```nginx
location /health {
    proxy_pass http://fastapi:8001;
}

location /chat {
    proxy_pass http://fastapi:8001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}

location /chat/sessions {
    proxy_pass http://fastapi:8001;
}
```

---

#### 踩坑四：数据库连接失败

**错误现象：**
```
response: "数据库连接失败"
```

**原因：** 容器内 `localhost` 指向容器自身，无法访问 MySQL 容器。

**解决方案：** 修改 `ecommerce_agent/app/config.py`，使用环境变量：

```python
import os

DB_CONFIG={
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "123456"),
    "database": os.getenv("DB_NAME", "muxi_shop")
}
```

`docker-compose.yml` 中配置：
```yaml
fastapi:
  environment:
    - DB_HOST=mysql
```

---

#### 踩坑五：Ollama 连接失败

**错误现象：**
```
Failed to connect to Ollama. Please check that Ollama is downloaded
```

**原因：** 代码中硬编码 `localhost:11434`，容器内无法访问。

**解决方案：**

1. 修改 `docker-compose.yml`：
```yaml
fastapi:
  environment:
    - OLLAMA_BASE_URL=http://ollama:11434
```

2. 修改 `app/tools/knowledge_tools.py`：
```python
import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

_embeddings = OllamaEmbeddings(
    model="bge-m3",
    base_url=OLLAMA_BASE_URL
)
```

3. 同样修改 `app/tools/review_analysis_tools.py` 和 `app/tools/product_tools.py`。

---

### Docker 容器间通信核心原则

| 场景 | 错误做法 | 正确做法 |
|------|----------|----------|
| 数据库连接 | `host: "localhost"` | `host: os.getenv("DB_HOST")` |
| Redis 连接 | `redis://localhost:6379` | `redis://host.docker.internal:6379` |
| Ollama 连接 | `http://localhost:11434` | `os.getenv("OLLAMA_BASE_URL")` |
| 服务间调用 | `proxy_pass http://localhost:8000` | `proxy_pass http://服务名:端口` |

> **核心原则：** 在 Docker 容器内，`localhost` 指向容器自身，必须使用服务名或环境变量访问其他容器。

---

### 完整配置文件

#### docker-compose.yml

```yaml
services:
  frontend:
    build: ./muxi_shop_web
    ports:
      - "80:80"
    volumes:
      - ./muxi_shop_api/static:/usr/share/nginx/static:ro
    depends_on:
      - django
      - fastapi
    networks:
      - app-network

  django:
    build: ./muxi_shop_api
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=mysql
      - DB_USER=root
      - DB_PASSWORD=123456
      - DB_NAME=muxi_shop
    volumes:
      - ./muxi_shop_api/static/product_images:/app/staticfiles/product_images
    depends_on:
      - mysql
    networks:
      - app-network

  fastapi:
    build: ./ecommerce_agent
    ports:
      - "8001:8001"
    environment:
      - DB_HOST=mysql
      - DB_USER=root
      - DB_PASSWORD=123456
      - DB_NAME=muxi_shop
      - REDIS_URL=redis://host.docker.internal:6379/0
      - OLLAMA_BASE_URL=http://ollama:11434
    volumes:
      - ./ecommerce_agent/chroma_db:/app/chroma_db
      - ./ecommerce_agent/knowledge:/app/knowledge
    depends_on:
      - mysql
      - ollama
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - app-network

  mysql:
    image: mysql:8.0
    environment:
      - MYSQL_ROOT_PASSWORD=123456
      - MYSQL_DATABASE=muxi_shop
    volumes:
      - ./mysql/init:/docker-entrypoint-initdb.d
      - mysql_data:/var/lib/mysql
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
    networks:
      - app-network

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

volumes:
  mysql_data:
  ollama_data:
```

#### nginx.conf

```nginx
server {
    listen 80;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # 静态文件
    location /static/ {
        alias /usr/share/nginx/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Django API
    location /goods/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /user/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /cart/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /order/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /address/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /comment/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /pay/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /main_menu/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /sub_menu/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /admin/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/agent/ {
        proxy_pass http://django:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # FastAPI Agent
    location /health {
        proxy_pass http://fastapi:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /chat {
        proxy_pass http://fastapi:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /chat/sessions {
        proxy_pass http://fastapi:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /tools {
        proxy_pass http://fastapi:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /debug/ {
        proxy_pass http://fastapi:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /test/ {
        proxy_pass http://fastapi:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

### 生产环境部署

#### 1. Django (Gunicorn + Nginx)
```bash
pip install gunicorn
gunicorn muxi_shop_api.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

#### 2. Vue3 (构建静态文件)
```bash
npm run build
# 将 dist/ 目录部署到 Nginx
```

#### 3. FastAPI (Uvicorn)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
```

---

## 🔒 安全建议

1. **关闭 DEBUG** - 生产环境设置 `DEBUG = False`
2. **环境变量管理密钥** - 使用 `.env` 文件管理敏感配置
3. **启用 HTTPS** - 配置 SSL 证书
4. **数据库权限控制** - 使用专用数据库用户
5. **定期备份数据** - `mysqldump -u root -p muxi_shop > backup.sql`

---

## 🛠️ 技术栈

### 前端
- Vue 3 + Composition API
- Element Plus 组件库
- Vuex 状态管理
- Axios 请求封装

### 后端
- Django 4.2 + DRF 3.16
- JWT 认证
- 支付宝 SDK 集成
- MySQL 数据库

### 智能体
- FastAPI 异步框架
- LangChain Agent 框架
- Ollama 本地大模型 (bge-m3 / qwen2.5)
- ChromaDB 向量数据库
- Redis 会话存储

---

## 📝 开发计划

- [ ] 引入 Elasticsearch 优化商品搜索
- [ ] 添加商品库存管理
- [ ] 实现优惠券和促销活动
- [ ] 集成物流跟踪
- [ ] 添加数据分析和报表
- [ ] 实现多 Agent 协作
- [ ] 流式输出优化响应速度

---

## 📄 许可证

本项目仅供学习交流使用，禁止用于商业用途。

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给一个 Star！⭐**

</div>
