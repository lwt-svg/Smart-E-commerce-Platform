<!-- AgentChat.vue - 智能助手聊天页面 -->
<template>
  <div class="agent-chat-page">
    <!-- 页头 -->
    <div class="agent-header">
      <Shortcut />
      <div class="agent-nav">
        <div class="nav-container">
          <router-link to="/" class="back-home">
            <span>← 返回首页</span>
          </router-link>
          <div class="agent-title">
            <span class="agent-icon">🤖</span>
            <h1>电商智能助手</h1>
            <div class="agent-status" :class="{ 'online': isOnline }">
              <span class="status-dot"></span>
              {{ isOnline ? '在线' : '离线' }}
            </div>
          </div>
          <div class="nav-right">
            <button class="help-btn" @click="showHelp = true">
              <span>❓ 使用帮助</span>
            </button>
            <button class="debug-btn" @click="testTokenDebug" v-if="false">
              🔧 调试
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="agent-main">
      <!-- 侧边栏（可选功能） -->
      <div class="agent-sidebar" v-if="showSidebar">
        <div class="sidebar-section">
          <h3>📋 快速功能</h3>
          <button 
            v-for="(action, index) in quickActions" 
            :key="index"
            @click="selectQuickAction(action)"
            class="sidebar-btn"
          >
            {{ action }}
          </button>
        </div>
        
        <div class="sidebar-section">
          <h3>📊 使用记录</h3>
          <div class="history-list">
            <div 
              v-for="(item, index) in history" 
              :key="index"
              class="history-item"
              @click="loadHistory(item)"
            >
              <div class="history-preview">{{ item.preview }}</div>
              <div class="history-time">{{ formatTime(item.time) }}</div>
            </div>
          </div>
        </div>

        <div class="sidebar-section">
          <h3>🔒 登录状态</h3>
          <div class="user-status">
            <div v-if="isUserLoggedIn" class="logged-in">
              <div class="user-info">
                <span class="user-icon">👤</span>
                <div>
                  <div class="user-email">{{ currentUserEmail }}</div>
                  <div class="login-status online">已登录</div>
                </div>
              </div>
              <button @click="logout" class="logout-btn">退出登录</button>
            </div>
            <div v-else class="logged-out">
              <div class="login-prompt">
                <span class="warning-icon">⚠️</span>
                <div>未登录</div>
              </div>
              <router-link to="/login" class="login-link">
                <button class="login-btn">前往登录</button>
              </router-link>
              <p class="login-hint">登录后可使用购物车、订单等功能</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 聊天主区域 -->
      <div class="chat-container" :class="{ 'full-width': !showSidebar }">
        <!-- 聊天框 -->
        <div class="chat-box">
          <!-- 消息区域 -->
          <div class="messages-area" ref="messagesContainer">
            <!-- 欢迎消息 -->
            <div v-if="messages.length === 0" class="welcome-message">
              <div class="welcome-avatar">
                <span>🤖</span>
              </div>
              <div class="welcome-content">
                <h3>👋 欢迎使用电商智能助手！</h3>
                <p>我是您的专属购物助手，可以帮您：</p>
                <ul>
                  <li><strong>🔍 搜索商品</strong> - 根据关键词或分类查找商品</li>
                  <li><strong>💰 查询价格</strong> - 查看商品详细价格信息</li>
                  <li><strong>⭐ 查看评论</strong> - 了解其他用户的评价</li>
                  <li v-if="isUserLoggedIn"><strong>🛒 管理购物车</strong> - 查询、修改购物车商品</li>
                  <li v-if="isUserLoggedIn"><strong>📦 订单管理</strong> - 查看订单、支付、取消等操作</li>
                  <li><strong>🎯 智能推荐</strong> - 根据预算推荐合适商品</li>
                </ul>
                <p v-if="!isUserLoggedIn" class="login-reminder">
                  <strong>🔒 提示：</strong>登录后可以使用购物车、订单管理等个人功能。
                </p>
                <p>试试下面的快速提问或直接输入您的问题！</p>
              </div>
            </div>

            <!-- 聊天消息 -->
            <div 
              v-for="(message, index) in messages" 
              :key="index" 
              :class="['message', message.role]"
            >
              <div class="message-avatar">
                <span v-if="message.role === 'user'">👤</span>
                <span v-if="message.role === 'assistant'">🤖</span>
              </div>
              <div class="message-content">
                <div class="message-text" v-html="formatMessage(message.content)"></div>
                <div class="message-meta">
                  <span class="message-time">{{ formatTime(message.timestamp) }}</span>
                  <span v-if="message.role === 'assistant'" class="message-actions">
                    <button 
                      class="action-btn" 
                      @click="copyToClipboard(message.content)"
                      title="复制"
                    >
                      📋
                    </button>
                  </span>
                </div>
              </div>
            </div>

            <!-- 加载指示器 -->
            <div v-if="isLoading" class="message assistant">
              <div class="message-avatar">
                <span>🤖</span>
              </div>
              <div class="message-content">
                <div class="loading-indicator">
                  <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <span>正在思考中...</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 输入区域 -->
          <div class="input-area">
            <div class="input-wrapper">
              <textarea
                v-model="userInput"
                placeholder="输入您的问题，例如：帮我找一个预算3000元以内的电子产品"
                @keydown.enter.exact.prevent="sendMessage"
                @keydown.enter.shift.exact.prevent="userInput += '\n'"
                :disabled="isLoading || !isOnline"
                rows="2"
                ref="textArea"
              ></textarea>
              <div class="input-controls">
                <button 
                  @click="toggleSidebar"
                  class="control-btn"
                  :title="showSidebar ? '隐藏侧边栏' : '显示侧边栏'"
                >
                  {{ showSidebar ? '◀' : '▶' }}
                </button>
                <button 
                  @click="clearChat"
                  class="control-btn"
                  :disabled="messages.length === 0"
                  title="清空对话"
                >
                  🗑️
                </button>
                <button 
                  @click="sendMessage" 
                  :disabled="!userInput.trim() || isLoading || !isOnline"
                  class="send-btn"
                >
                  <span v-if="!isLoading">发送</span>
                  <span v-else class="sending">发送中...</span>
                  <span class="send-icon">📤</span>
                </button>
              </div>
            </div>
            <div class="input-hints">
              <span>按 Enter 发送，Shift+Enter 换行</span>
              <span v-if="!isOnline" class="offline-warning">⚠️ 助手暂时离线，请稍后再试</span>
            </div>
          </div>

          <!-- 快捷操作 -->
          <div class="quick-actions-bar">
            <div class="quick-actions-title">💡 快速提问：</div>
            <div class="quick-actions-grid">
              <button 
                v-for="(action, index) in quickActions" 
                :key="index"
                @click="selectQuickAction(action)"
                class="quick-action-btn"
                :disabled="isLoading"
              >
                {{ action }}
              </button>
            </div>
          </div>
        </div>

        <!-- 右侧信息面板（可选） -->
        <div class="info-panel" v-if="showInfoPanel">
          <div class="panel-header">
            <h3>ℹ️ 助手信息</h3>
            <button @click="showInfoPanel = false" class="close-panel-btn">×</button>
          </div>
          <div class="panel-content">
            <div class="info-section">
              <h4>可用功能</h4>
              <ul>
                <li>商品搜索与推荐</li>
                <li>价格查询与比较</li>
                <li>评论查看与分析</li>
                <li v-if="isUserLoggedIn">购物车管理</li>
                <li v-if="isUserLoggedIn">订单操作</li>
                <li>预算内推荐</li>
              </ul>
            </div>
            <div class="info-section">
              <h4>使用提示</h4>
              <ul>
                <li>描述越详细，推荐越精准</li>
                <li>可以指定预算范围</li>
                <li>支持自然语言查询</li>
                <li v-if="isUserLoggedIn">可管理您的购物车和订单</li>
                <li v-if="!isUserLoggedIn">登录后可使用个人功能</li>
              </ul>
            </div>
            <div class="info-section" v-if="debugInfo">
              <h4>调试信息</h4>
              <div class="debug-info">
                <div><strong>Token状态:</strong> {{ debugInfo.tokenStatus }}</div>
                <div v-if="debugInfo.userEmail"><strong>用户:</strong> {{ debugInfo.userEmail }}</div>
                <div><strong>服务:</strong> {{ isOnline ? '在线' : '离线' }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 帮助对话框 -->
    <div v-if="showHelp" class="modal-overlay" @click.self="showHelp = false">
      <div class="help-modal">
        <div class="modal-header">
          <h2>❓ 使用帮助</h2>
          <button @click="showHelp = false" class="close-btn">×</button>
        </div>
        <div class="modal-content">
          <div class="help-section">
            <h3>🤖 助手介绍</h3>
            <p>电商智能助手是基于AI技术的购物助手，能够理解您的自然语言需求，提供个性化的购物建议和服务。</p>
          </div>
          <div class="help-section">
            <h3>🎯 常用功能</h3>
            <div class="help-examples">
              <div class="example">
                <strong>搜索商品：</strong>
                <code>"帮我找一款适合打游戏的笔记本电脑"</code>
              </div>
              <div class="example">
                <strong>查询价格：</strong>
                <code>"华为P50的价格是多少"</code>
              </div>
              <div class="example">
                <strong>查看评论：</strong>
                <code>"想看看小米电视的评论怎么样"</code>
              </div>
              <div class="example" v-if="isUserLoggedIn">
                <strong>管理购物车：</strong>
                <code>"查看我的购物车"</code>
              </div>
              <div class="example" v-if="isUserLoggedIn">
                <strong>订单操作：</strong>
                <code>"我想取消订单ORD123456"</code>
              </div>
            </div>
          </div>
          <div class="help-section">
            <h3>🔒 登录状态</h3>
            <p v-if="isUserLoggedIn">
              ✅ 您已登录，可以使用所有功能，包括个人购物车和订单管理。
            </p>
            <p v-else>
              ⚠️ 您尚未登录，部分个人功能（购物车、订单）无法使用。
            </p>
          </div>
          <div class="help-section">
            <h3>📞 技术支持</h3>
            <p>如遇到问题，请联系技术支持：</p>
            <ul>
              <li>邮箱：support@example.com</li>
              <li>电话：400-123-4567</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import Shortcut from '@/components/common/Shortcut.vue'
import { useStore } from 'vuex'

const store = useStore()
const router = useRouter()

// 响应式数据
const messages = ref([])
const userInput = ref('')
const isLoading = ref(false)
const isOnline = ref(false)
const showSidebar = ref(true)
const showInfoPanel = ref(false)
const showHelp = ref(false)
const messagesContainer = ref(null)
const textArea = ref(null)
const history = ref([])
const debugInfo = ref(null)

// 用户登录状态
const isUserLoggedIn = computed(() => store.state.user.isLogin)
const currentUserEmail = computed(() => {
  const token = localStorage.getItem('token')
  if (token) {
    try {
      // 解析JWT token获取用户信息
      const payload = JSON.parse(atob(token.split('.')[1]))
      return payload.data?.username || ''
    } catch (error) {
      console.error('解析token失败:', error)
      return ''
    }
  }
  return ''
})

// 快速提问示例（根据登录状态调整）
const quickActions = computed(() => {
  const baseActions = [
    '帮我找一个预算3000元以内的电子产品',
    '华为手机的价格是多少？',
    '查看笔记本电脑的评论',
    '推荐一些2000元以下的服装',
  ]
  
  if (isUserLoggedIn.value) {
    return [
      ...baseActions,
      '查询我的购物车',
      '如何支付订单？',
      '查看我的订单'
    ]
  }
  
  return baseActions
})

// 检查Agent服务状态
const checkAgentStatus = async () => {
  try {
    console.log('[Agent] 开始检查Agent状态...')
    const response = await axios.get('http://localhost:8001/health', {
      timeout: 5000
    })
    console.log('[Agent] 收到响应:', response.data)
    
    if (response.data.status === 'healthy') {
      console.log('[Agent] 状态判断: 健康 -> 设置在线')
      isOnline.value = true
    } else {
      console.log('[Agent] 状态判断: 不健康 -> 设置离线')
      isOnline.value = false
    }
    
  } catch (error) {
    console.log('[Agent] 请求出错 -> 设置离线', error)
    isOnline.value = false
    console.error('无法连接到Agent服务:', error)
  }
}

// 发送消息
const sendMessage = async () => {
  const message = userInput.value.trim()
  if (!message || isLoading.value || !isOnline.value) return
  
  // 检查是否需要登录的操作
  const needLoginKeywords = ['购物车', '订单', '我的', '结算', '支付', '取消订单', '查看我的']
  const needsLogin = needLoginKeywords.some(keyword => 
    message.includes(keyword)
  )
  
  // 如果操作需要登录但用户未登录
  if (needsLogin && !isUserLoggedIn.value) {
    const warningMessage = {
      role: 'assistant',
      content: '🔒 此功能需要登录后才能使用！请先登录。',
      timestamp: new Date()
    }
    messages.value.push(warningMessage)
    scrollToBottom()
    return
  }
  
  // 添加用户消息
  const userMessage = {
    role: 'user',
    content: message,
    timestamp: new Date()
  }
  messages.value.push(userMessage)
  userInput.value = ''
  
  // 滚动到底部
  scrollToBottom()
  
  // 添加到历史记录
  addToHistory(message)
  
  // 发送请求
  isLoading.value = true
  
  try {
    // 获取token
    const token = localStorage.getItem('token') || ''
    console.log('[Agent] 发送消息，token存在:', !!token)
    
    // 准备请求数据
    const payload = {
      message: message,
      session_id: 'session_' + Date.now(),
      token: token  // 传递token给FastAPI
    }
    
    console.log('[Agent] 发送请求到FastAPI:', payload)
    
    // 直接调用FastAPI智能体服务（端口8001）
    const response = await axios.post('http://localhost:8001/chat', payload, {
      headers: {
        'Content-Type': 'application/json'
      },
      timeout: 60000
    })
    
    console.log('[Agent] 收到响应:', response.data)
    
    if (response.data.response) {
      const assistantMessage = {
        role: 'assistant',
        content: response.data.response,
        timestamp: new Date(response.data.timestamp)
      }
      messages.value.push(assistantMessage)
    }
    
    // 滚动到底部
    scrollToBottom()
    
  } catch (error) {
    console.error('[Agent] 发送消息失败:', error)
    
    let errorText = '抱歉，处理请求时出错了。'
    if (error.response) {
      console.error('[Agent] 错误响应:', error.response.data)
      
      if (error.response.status === 401) {
        errorText = '🔒 身份验证失败，请重新登录。'
        // 清除无效的token
        localStorage.removeItem('token')
        store.commit('setIsLogin', false)
        
        setTimeout(() => {
          alert('您的登录已过期，请重新登录。')
          router.push('/login')
        }, 1000)
      } else if (error.response.status === 500) {
        errorText = '🤖 智能助手服务内部错误，请稍后重试。'
      } else {
        errorText = `请求失败 (${error.response.status}): ${error.response.data.detail || '未知错误'}`
      }
    } else if (error.request) {
      console.error('[Agent] 无响应:', error.request)
      errorText = '🌐 无法连接到智能助手服务，请检查网络连接或服务是否运行。'
    }
    
    const errorMessage = {
      role: 'assistant',
      content: errorText,
      timestamp: new Date()
    }
    messages.value.push(errorMessage)
    
  } finally {
    isLoading.value = false
    scrollToBottom()
  }
}

// 测试token调试
const testTokenDebug = async () => {
  try {
    const token = localStorage.getItem('token') || ''
    if (!token) {
      alert('未找到token')
      return
    }
    
    const response = await axios.get('http://localhost:8001/debug/token', {
      headers: {
        'Authorization': token
      }
    })
    
    console.log('Token调试结果:', response.data)
    debugInfo.value = {
      tokenStatus: response.data.status,
      userEmail: response.data.user_email
    }
    
    alert(`Token状态: ${response.data.status}\n用户: ${response.data.user_email || '未解析'}`)
  } catch (error) {
    console.error('Token调试失败:', error)
    alert('Token调试失败，请检查服务')
  }
}

// 选择快速提问
const selectQuickAction = (action) => {
  userInput.value = action
  sendMessage()
}

// 清空对话
const clearChat = () => {
  if (messages.value.length > 0 && confirm('确定要清空对话历史吗？')) {
    messages.value = []
  }
}

// 复制到剪贴板
const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text)
    alert('已复制到剪贴板！')
  } catch (err) {
    console.error('复制失败:', err)
  }
}

// 切换侧边栏
const toggleSidebar = () => {
  showSidebar.value = !showSidebar.value
}

// 添加到历史记录
const addToHistory = (message) => {
  const historyItem = {
    preview: message.length > 30 ? message.substring(0, 30) + '...' : message,
    fullMessage: message,
    time: new Date()
  }
  
  history.value.unshift(historyItem)
  
  // 只保留最近的10条记录
  if (history.value.length > 10) {
    history.value = history.value.slice(0, 10)
  }
}

// 加载历史记录
const loadHistory = (item) => {
  userInput.value = item.fullMessage
  if (textArea.value) {
    textArea.value.focus()
  }
}

// 退出登录
const logout = () => {
  localStorage.removeItem('token')
  store.commit('setIsLogin', false)
  messages.value = [] // 清空聊天记录
  router.push('/login')
}

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 格式化消息内容
const formatMessage = (text) => {
  if (!text) return ''
  
  // 保留换行
  let formatted = text.replace(/\n/g, '<br>')
  
  // 高亮价格
  formatted = formatted.replace(/¥\d+(\.\d{2})?/g, '<span class="price-highlight">$&</span>')
  
  // 高亮商品名称
  formatted = formatted.replace(/商品[:：]\s*([^<>\n]+)/g, '商品: <span class="product-highlight">$1</span>')
  
  // 高亮SKU
  formatted = formatted.replace(/SKU[:：]\s*([^<>\n]+)/g, 'SKU: <span class="sku-highlight">$1</span>')
  
  // 高亮成功/错误消息
  if (text.includes('✅')) {
    formatted = formatted.replace(/✅/g, '<span class="success-icon">✅</span>')
  }
  if (text.includes('❌')) {
    formatted = formatted.replace(/❌/g, '<span class="error-icon">❌</span>')
  }
  
  // 高亮安全提示
  if (text.includes('请先登录')) {
    formatted = formatted.replace(/请先登录/g, '<span class="security-highlight">请先登录</span>')
  }
  
  return formatted
}

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now - date
  
  // 如果是今天
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: false 
    })
  } else {
    return date.toLocaleDateString([], { 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }
}

// 初始化
onMounted(() => {
  // 检查服务状态
  checkAgentStatus()
  
  // 定期检查状态（每30秒）
  const statusInterval = setInterval(checkAgentStatus, 30000)
  
  // 聚焦输入框
  if (textArea.value) {
    textArea.value.focus()
  }
  
  // 更新调试信息
  debugInfo.value = {
    tokenStatus: isUserLoggedIn.value ? '有效' : '未登录',
    userEmail: currentUserEmail.value
  }
  
  // 清理定时器
  return () => clearInterval(statusInterval)
})

// 监听输入变化，自动调整高度
watch(userInput, () => {
  nextTick(() => {
    if (textArea.value) {
      textArea.value.style.height = 'auto'
      textArea.value.style.height = Math.min(textArea.value.scrollHeight, 120) + 'px'
    }
  })
})

// 监听登录状态变化
watch(isUserLoggedIn, (newValue) => {
  if (newValue) {
    debugInfo.value = {
      tokenStatus: '有效',
      userEmail: currentUserEmail.value
    }
  } else {
    debugInfo.value = {
      tokenStatus: '未登录',
      userEmail: ''
    }
  }
})
</script>

<style lang="less" scoped>
.agent-chat-page {
  min-height: 100vh;
  background: #f8f9fa;
}

.agent-header {
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.agent-nav {
  background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
  color: white;
  padding: 12px 0;
}

.nav-container {
  width: var(--content-width);
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.back-home {
  color: white;
  text-decoration: none;
  font-size: 14px;
  padding: 6px 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.2);
  transition: all 0.2s;
  
  &:hover {
    background: rgba(255, 255, 255, 0.3);
  }
}

.agent-title {
  display: flex;
  align-items: center;
  gap: 12px;
  
  h1 {
    margin: 0;
    font-size: 24px;
    font-weight: 600;
  }
}

.agent-icon {
  font-size: 32px;
}

.agent-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 15px;
  
  &.online {
    background: rgba(46, 213, 115, 0.3);
  }
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ff4757;
  
  .online & {
    background: #2ed573;
  }
}

.nav-right {
  display: flex;
  gap: 10px;
  
  .help-btn, .debug-btn {
    background: rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.3);
    color: white;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    
    &:hover {
      background: rgba(255, 255, 255, 0.3);
    }
  }
}

.agent-main {
  width: var(--content-width);
  margin: 20px auto;
  display: flex;
  gap: 20px;
  min-height: calc(100vh - 180px);
}

.agent-sidebar {
  width: 280px;
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  
  .sidebar-section {
    margin-bottom: 30px;
    
    h3 {
      margin: 0 0 15px 0;
      color: #333;
      font-size: 16px;
      font-weight: 600;
    }
  }
  
  .sidebar-btn {
    width: 100%;
    padding: 10px 15px;
    margin-bottom: 8px;
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    text-align: left;
    cursor: pointer;
    transition: all 0.2s;
    color: #555;
    font-size: 14px;
    
    &:hover {
      background: #e9ecef;
      border-color: #4CAF50;
      color: #4CAF50;
    }
  }
  
  .history-list {
    max-height: 300px;
    overflow-y: auto;
  }
  
  .history-item {
    padding: 10px;
    border-bottom: 1px solid #f0f0f0;
    cursor: pointer;
    transition: all 0.2s;
    
    &:hover {
      background: #f8f9fa;
    }
  }
  
  .history-preview {
    font-size: 13px;
    color: #666;
    margin-bottom: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .history-time {
    font-size: 12px;
    color: #999;
  }
  
  .user-status {
    .logged-in, .logged-out {
      padding: 15px;
      border-radius: 8px;
      background: #f8f9fa;
      border: 1px solid #e9ecef;
    }
    
    .user-info {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 15px;
      
      .user-icon {
        font-size: 24px;
      }
      
      .user-email {
        font-size: 14px;
        font-weight: 500;
        color: #333;
      }
      
      .login-status {
        font-size: 12px;
        color: #999;
        
        &.online {
          color: #2ed573;
        }
      }
    }
    
    .logout-btn {
      width: 100%;
      padding: 8px 12px;
      background: #ff4757;
      color: white;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      transition: all 0.2s;
      
      &:hover {
        background: #ff3742;
      }
    }
    
    .login-prompt {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      color: #ff6b6b;
      
      .warning-icon {
        font-size: 20px;
      }
    }
    
    .login-link {
      text-decoration: none;
      
      .login-btn {
        width: 100%;
        padding: 8px 12px;
        background: #4CAF50;
        color: white;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        font-size: 14px;
        transition: all 0.2s;
        
        &:hover {
          background: #45a049;
        }
      }
    }
    
    .login-hint {
      font-size: 12px;
      color: #999;
      margin-top: 10px;
      text-align: center;
    }
  }
}

.chat-container {
  flex: 1;
  display: flex;
  gap: 20px;
  
  &.full-width {
    .chat-box {
      width: 100%;
    }
  }
}

.chat-box {
  flex: 1;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.messages-area {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  max-height: 500px;
  min-height: 400px;
}

.welcome-message {
  display: flex;
  align-items: center;
  gap: 20px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  padding: 30px;
  border-radius: 12px;
  margin-bottom: 30px;
}

.welcome-avatar {
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 40px;
  flex-shrink: 0;
}

.welcome-content {
  flex: 1;
  
  h3 {
    margin: 0 0 15px 0;
    color: #333;
  }
  
  p {
    margin: 10px 0;
    color: #666;
  }
  
  ul {
    margin: 15px 0;
    padding-left: 20px;
    
    li {
      margin: 8px 0;
      color: #555;
    }
  }
  
  .login-reminder {
    background: #fff3cd;
    border: 1px solid #ffeaa7;
    padding: 10px 15px;
    border-radius: 8px;
    color: #856404;
    font-size: 14px;
  }
}

.message {
  display: flex;
  margin-bottom: 20px;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #f8f9fa;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
  margin-right: 12px;
}

.user .message-avatar {
  background: #4CAF50;
  color: white;
}

.message-content {
  max-width: 75%;
  background: #f8f9fa;
  padding: 12px 16px;
  border-radius: 12px;
  position: relative;
}

.user .message-content {
  background: #4CAF50;
  color: white;
  margin-left: auto;
}

.assistant .message-content {
  background: #f8f9fa;
  color: #333;
}

.message-text {
  line-height: 1.5;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.message-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  font-size: 12px;
  opacity: 0.7;
}

.user .message-meta {
  color: rgba(255, 255, 255, 0.8);
}

.action-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.6;
  transition: opacity 0.2s;
  padding: 2px 4px;
  border-radius: 4px;
  
  &:hover {
    opacity: 1;
    background: rgba(0, 0, 0, 0.05);
  }
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #666;
}

.typing-dots {
  display: flex;
  gap: 4px;
}

.typing-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4CAF50;
  opacity: 0.6;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-dots span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
  0%, 80%, 100% { opacity: 0.6; }
  40% { opacity: 1; }
}

.input-area {
  border-top: 1px solid #e9ecef;
  padding: 20px;
  background: white;
}

.input-wrapper {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.input-wrapper textarea {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  resize: none;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  transition: all 0.2s;
  background: #f8f9fa;
  
  &:focus {
    outline: none;
    border-color: #4CAF50;
    background: white;
    box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.1);
  }
  
  &:disabled {
    background: #f1f3f4;
    cursor: not-allowed;
  }
}

.input-controls {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.control-btn {
  width: 44px;
  height: 44px;
  border: 1px solid #e9ecef;
  background: white;
  border-radius: 8px;
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  
  &:hover:not(:disabled) {
    border-color: #4CAF50;
    color: #4CAF50;
  }
  
  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.send-btn {
  height: 44px;
  background: #4CAF50;
  color: white;
  border: none;
  padding: 0 24px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 100px;
  justify-content: center;
  
  &:hover:not(:disabled) {
    background: #45a049;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);
  }
  
  &:disabled {
    background: #cccccc;
    cursor: not-allowed;
    transform: none;
  }
}

.send-icon {
  font-size: 16px;
}

.sending {
  opacity: 0.8;
}

.input-hints {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #999;
}

.offline-warning {
  color: #ff6b6b;
}

.quick-actions-bar {
  border-top: 1px solid #e9ecef;
  padding: 15px 20px;
  background: #f8f9fa;
}

.quick-actions-title {
  font-size: 14px;
  font-weight: 600;
  color: #555;
  margin-bottom: 10px;
}

.quick-actions-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quick-action-btn {
  background: white;
  border: 1px solid #e9ecef;
  padding: 8px 12px;
  border-radius: 20px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  color: #555;
  white-space: nowrap;
  
  &:hover:not(:disabled) {
    background: #e9ecef;
    border-color: #4CAF50;
    color: #4CAF50;
  }
  
  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.info-panel {
  width: 300px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  
  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
}

.close-panel-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
  
  &:hover {
    color: #333;
  }
}

.panel-content {
  padding: 20px;
  
  .info-section {
    margin-bottom: 25px;
    
    h4 {
      margin: 0 0 10px 0;
      color: #333;
      font-size: 14px;
      font-weight: 600;
    }
    
    ul {
      margin: 0;
      padding-left: 20px;
      
      li {
        margin: 6px 0;
        color: #666;
        font-size: 13px;
      }
    }
    
    .debug-info {
      background: #f8f9fa;
      padding: 12px;
      border-radius: 8px;
      border-left: 4px solid #3498db;
      font-size: 13px;
      
      div {
        margin: 4px 0;
      }
      
      strong {
        color: #333;
      }
    }
  }
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.help-modal {
  width: 600px;
  max-height: 80vh;
  background: white;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 30px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  
  h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
  }
}

.close-btn {
  background: none;
  border: none;
  font-size: 28px;
  cursor: pointer;
  color: #999;
  
  &:hover {
    color: #333;
  }
}

.modal-content {
  flex: 1;
  padding: 30px;
  overflow-y: auto;
}

.help-section {
  margin-bottom: 30px;
  
  h3 {
    margin: 0 0 15px 0;
    color: #333;
    font-size: 18px;
    font-weight: 600;
  }
  
  p {
    margin: 10px 0;
    color: #666;
    line-height: 1.6;
  }
}

.help-examples {
  .example {
    margin: 12px 0;
    padding: 12px;
    background: #f8f9fa;
    border-radius: 8px;
    border-left: 4px solid #4CAF50;
    
    strong {
      color: #333;
    }
    
    code {
      display: block;
      margin-top: 8px;
      padding: 8px 12px;
      background: white;
      border-radius: 6px;
      font-family: monospace;
      color: #4CAF50;
      border: 1px solid #e9ecef;
    }
  }
}
</style>

<style lang="less">
/* 全局样式 */
.price-highlight {
  color: #ff6b6b;
  font-weight: bold;
}

.product-highlight {
  color: #4CAF50;
  font-weight: 500;
}

.sku-highlight {
  color: #3498db;
  font-weight: 500;
  font-family: monospace;
}

.success-icon {
  color: #2ed573;
}

.error-icon {
  color: #ff4757;
}

.security-highlight {
  color: #ff6b6b;
  font-weight: bold;
  background: #fff3cd;
  padding: 2px 4px;
  border-radius: 4px;
}
</style>
