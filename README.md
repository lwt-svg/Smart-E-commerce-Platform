# 🛍️ 电商智能助手集成项目

## 📖 项目简介

本项目将一个基于LangChain的智能电商助手集成到现有的Django后端+Vue3前端的电商平台中。智能助手能够通过自然语言处理用户查询，提供商品搜索、价格查询、购物车管理、订单操作等功能，为用户提供智能化的购物咨询服务。

## 🏗️ 系统架构

系统由三个独立运行的组件构成：

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Vue3前端      │───▶│   Django后端    │───▶│   FastAPI       │
│   (端口:8080)   │    │   (端口:8000)   │    │   智能助手      │
│                 │◀───│                 │◀───│   (端口:8001)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
      用户界面             请求代理转发            AI逻辑处理
```

## 📁 项目结构说明

```
your_project/
├── agent_service/           # 独立的FastAPI智能助手服务
├── django_project/          # 原有的Django电商后端
└── vue_project/            # 原有的Vue3电商前端
```

## 🚀 快速启动指南

### 环境准备
1. 确保Python 3.8+、Node.js环境已安装
2. MySQL数据库服务已启动并运行

### 第一步：启动FastAPI智能助手服务
```bash
# 进入agent_service目录
cd agent_service

# 安装Python依赖
pip install -r requirements.txt

# 启动服务（使用8001端口）
uvicorn ecommerce_agent_api:app --host 0.0.0.0 --port 8001 --reload
```
**验证**：访问 http://localhost:8001/docs 查看API文档。

### 第二步：启动Django后端
```bash
# 进入Django项目目录
cd django_project

# 应用数据库迁移（如果需要）
python manage.py migrate

# 启动Django服务（使用8000端口）
python manage.py runserver 8000
```
**关键配置**：确保 `settings.py` 中的 `AGENT_API_URL = 'http://localhost:8001'`。

### 第三步：启动Vue3前端
```bash
# 进入Vue项目目录
cd vue_project

# 安装依赖（首次需要）
npm install

# 启动开发服务器
npm run serve
```
**关键配置**：确保项目根目录存在 `vue.config.js` 文件并配置了代理。

## 🔌 核心接口说明

### FastAPI智能助手服务（端口:8001）
- `GET /health` - 服务健康检查
- `POST /chat` - 处理用户聊天请求
- `GET /tools` - 查看可用工具列表
- `GET /examples` - 获取示例查询语句

### Django代理接口（端口:8000）
- `GET /api/agent/health/` - 检查Agent服务状态
- `POST /api/agent/chat/` - 转发聊天请求到FastAPI
- `GET /api/agent/examples/` - 获取示例查询

## ✅ 系统验证步骤

按照以下顺序验证集成是否成功：

1. **验证FastAPI服务**  
   访问 http://localhost:8001/health  
   期望：返回 `{"status": "healthy"}`

2. **验证Django代理连接**  
   访问 http://localhost:8000/api/agent/health/  
   期望：返回Agent健康状态

3. **验证Vue前端**  
   访问 http://localhost:8080  
   点击"智能购物助手"按钮，应跳转到助手页面并显示"在线"状态

## 🛠️ 关键配置文件

### Django配置（settings.py）
```python
# 智能助手服务地址
AGENT_API_URL = 'http://localhost:8001'
```

### Vue配置（vue.config.js）
```javascript
// 代理配置，将/api请求转发到Django
proxy: {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true
  }
}
```

### Agent环境配置（.env）
```
# 数据库连接
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=muxi_shop

# 大模型API密钥
DASHSCOPE_API_KEY=your_api_key
```

## 🔧 故障排查

### 常见问题1：助手显示"离线"
- 检查FastAPI服务是否运行在8001端口
- 验证Django的 `AGENT_API_URL` 配置
- 查看浏览器控制台网络请求是否成功

### 常见问题2：端口冲突
- Django默认使用8000端口
- FastAPI智能助手需使用其他端口（如8001）
- 确保两个服务使用不同端口

### 常见问题3：代理配置错误
- 确认 `vue.config.js` 中的代理配置正确
- 确保请求路径匹配Django路由配置
- 重启Vue开发服务器使配置生效

## 📞 使用流程

1. 用户访问电商网站首页
2. 点击"智能购物助手"按钮（右上角或浮动按钮）
3. 在新页面中与助手对话，可：
   - 搜索商品（"帮我找笔记本电脑"）
   - 查询价格（"华为手机多少钱"）
   - 查看购物车（"我的购物车有什么"）
   - 管理订单（"取消订单ORD123"）

## 📋 注意事项

1. 三个服务需按顺序启动：数据库 → FastAPI → Django → Vue
2. 开发环境下注意CORS跨域配置
3. 生产环境需使用更安全的部署方式
4. 定期检查API密钥的有效性和额度

---

通过以上步骤，您的电商平台即可拥有智能对话助手功能，提升用户体验和购物效率。
