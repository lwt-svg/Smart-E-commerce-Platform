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
        <div class="sidebar-section history-section">
          <h3>📊 历史会话</h3>
          <div class="history-list">
            <div 
              v-for="(session, index) in savedSessions" 
              :key="index"
              class="history-item"
              @click="loadSession(session.file_name)"
            >
              <div class="history-preview">{{ session.preview }}</div>
              <div class="history-time">{{ formatTime(session.time) }}</div>
            </div>
            <div v-if="savedSessions.length === 0" class="no-history">
              暂无历史会话
            </div>
          </div>
        </div>
        
        <div class="sidebar-section usage-section">
          <h3>📊 使用记录</h3>
          <div class="usage-list">
            <div 
              v-for="(msg, index) in currentUserMessages" 
              :key="index"
              class="usage-item"
              @click="selectQuickAction(msg.content)"
            >
              {{ msg.content }}
            </div>
            <div v-if="currentUserMessages.length === 0" class="no-usage">
              暂无使用记录
            </div>
          </div>
        </div>

        <div class="sidebar-section user-section">
          <h3>🔒 登录状态</h3>
          <div class="user-status">
            <div v-if="isUserLoggedIn" class="logged-in">
              <div class="user-info">
                <span class="user-icon">👤</span>
                <div>
                  <div class="user-name">{{ userNickname }}</div>      
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
import { ref, onMounted, onUnmounted ,nextTick, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import Shortcut from '@/components/common/Shortcut.vue'
import { useStore } from 'vuex'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

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
// const history = ref([])
const debugInfo = ref(null)
// 保存从后端获取的历史会话列表
const savedSessions = ref([])

// 会话ID，用于保持对话上下文
const sessionId = ref(null)

const token = localStorage.getItem('token') || ''

const currentSessionFile = ref(null)
const userNickname = computed(() => {
  // 从 Vuex 中获取用户昵称，如果不存在则回退为邮箱前缀
  return store.state.user.name || currentUserEmail.value.split('@')[0] || '用户'
})

// 当前会话的用户提问记录（最近5条，最新在前）
const currentUserMessages = computed(() => {
  return messages.value
    .filter(m => m.role === 'user')
    .slice(-5)
    .reverse(); // 如果想按时间正序（旧到新），去掉 reverse()
})
// 用户登录状态
const isUserLoggedIn = computed(() => store.state.user.isLogin)
const currentUserEmail = computed(() => {
  const token = localStorage.getItem('token')
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      return payload.username || ''
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
      timeout: 10000
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
  if (!message || isLoading.value) return
  
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
  // addToHistory(message)
  
  // 发送请求
  isLoading.value = true
  
  try {
    // 获取token
    const token = localStorage.getItem('token') || ''
    console.log('[Agent] 发送消息，token存在:', !!token)
    
    // 构建历史消息列表
    const historyMessages = messages.value.slice(-10).map(msg => ({
      role: msg.role,
      content: msg.content || ''
    })).filter(msg => msg.role && msg.content.trim() !== '')
    
    // ========== 关键修改：管理会话ID ==========
    // 如果还没有 sessionId，则创建并保存
    if (!sessionId.value) {
      sessionId.value = 'session_' + Date.now()
      // 可选：保存到 localStorage，以便页面刷新后继续同一会话
      localStorage.setItem('chat_session_id', sessionId.value)
      console.log('[Agent] 生成新的 sessionId:', sessionId.value)
    } else {
      console.log('[Agent] 复用 sessionId:', sessionId.value)
    }
    
    // 准备请求数据
    const payload = {
      message: message,
      session_id: sessionId.value,  // 使用保存的 sessionId
      token: token,
      history: historyMessages
    }
    
    console.log('[Agent] 发送请求到FastAPI:', payload)
    
    // 直接调用FastAPI智能体服务（端口8001）
    const response = await axios.post('http://localhost:8001/chat', payload, {
      headers: {
        'Content-Type': 'application/json'
      },
      timeout: 120000
    })
    //请求成功 更新在线状态为true
    isOnline.value = true
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
    //请求失败 设置在线状态为false
    isOnline.value = false
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

const fetchSessions = async () => {
  const token = localStorage.getItem('token')
  console.log('获取会话列表，token:', token)  
  try {
    const res = await axios.get('http://localhost:8001/chat/sessions/list', {
      headers: { Authorization: token }
    })
    console.log('获取到的会话列表:', res.data)  
    savedSessions.value = res.data
  } catch (err) {
    console.error('获取会话列表失败', err)
  }
}

const saveCurrentSession = async () => {
  if (messages.value.length === 0) return
  const token = localStorage.getItem('token')
  console.log('保存会话，token:', token)
  try {
    await axios.post('http://localhost:8001/chat/sessions/save', {
      messages: messages.value.map(m => ({
        role: m.role,
        content: m.content,
        timestamp: m.timestamp
      })),
      end_time: new Date().toISOString(),
      file_name: currentSessionFile.value // 新增：如果是历史会话，传原文件名
    }, {
      headers: { Authorization: token }
    })
    fetchSessions() // 刷新会话列表
  } catch (err) {
    console.error('保存会话失败', err)
  }
}


const loadSession = async (fileName) => {
  await saveCurrentSession() // 先保存当前会话
  try {
    const token = localStorage.getItem('token')
    const res = await axios.get(`http://localhost:8001/chat/sessions/load/${fileName}`, {
      headers: { Authorization: token }
    })
    messages.value = res.data.messages
    currentSessionFile.value = fileName // 记录当前会话文件名
    scrollToBottom()
  } catch (err) {
    console.error('加载会话失败', err)
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
const clearChat = async () => {
  if (messages.value.length > 0 && confirm('确定要清空对话历史吗？')) {
    await saveCurrentSession()  // 先保存
    messages.value = []
    currentSessionFile.value = null // 开始全新会话
    sessionId.value = 'session_' + Date.now()
    localStorage.setItem('chat_session_id', sessionId.value)
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
// const addToHistory = (message) => {
//   const historyItem = {
//     preview: message.length > 30 ? message.substring(0, 30) + '...' : message,
//     fullMessage: message,
//     time: new Date()
//   }
  
//   history.value.unshift(historyItem)
  
//   // 只保留最近的10条记录
//   if (history.value.length > 10) {
//     history.value = history.value.slice(0, 10)
//   }
// }

// // 加载历史记录
// const loadHistory = (item) => {
//   userInput.value = item.fullMessage
//   if (textArea.value) {
//     textArea.value.focus()
//   }
// }

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
// 提取字符串中所有可能的 JSON 对象，返回 {json, start, end} 数组
// 提取字符串中最后一个合法的 JSON 对象
function extractLastJson(text) {
  let stack = [];
  let start = -1;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '{') {
      if (stack.length === 0) start = i;
      stack.push('{');
    } else if (text[i] === '}') {
      if (stack.length > 0) {
        stack.pop();
        if (stack.length === 0 && start !== -1) {
          const candidate = text.substring(start, i + 1);
          try {
            JSON.parse(candidate);
            return candidate; // 返回最后一个合法的 JSON
          } catch (e) {
            // 解析失败，继续寻找
          }
        }
      }
    }
  }
  return null;
}

// 常规文本格式化（换行、高亮价格等）
const formatPlainText = (text) => {
  if (!text) return '';
  let formatted = text.replace(/\n/g, '<br>');
  formatted = formatted.replace(/¥\d+(\.\d{2})?/g, '<span class="price-highlight">$&</span>');
  // 可以添加更多高亮规则
  return formatted;
}

// HTML 转义
function escapeHtml(unsafe) {
  if (!unsafe) return '';
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}


// 主格式化函数
const formatMessage = (text) => {
  if (!text) return '';

  const lastJson = extractLastJson(text);
  if (lastJson) {
    try {
      const data = JSON.parse(lastJson);

      // ========== 商品列表 ==========
      if (data.type === 'product_list' && Array.isArray(data.products)) {
        let items = [];
        data.products.forEach((p, index) => {
          items.push(`
            <div style="display:block; width:fit-content; max-width:100%; margin:0; padding:0;">
              <a href="${p.product_url || '#'}" target="_blank" style="display:block; width:fit-content; text-decoration:none; color:inherit;">
                <div style="display:flex; align-items:center; background:#f9f9f9; border:1px solid #e9ecef; border-radius:8px; padding:8px; margin:0;">
                  <img src="${p.image_url || ''}" alt="${escapeHtml(p.name)}" 
                       style="width:80px; height:80px; object-fit:cover; border-radius:6px; margin-right:12px; flex-shrink:0; background-color:#f0f0f0; display:block;"
                       onerror="this.onerror=null; this.src='https://via.placeholder.com/80';">
                  <div style="flex:0 1 auto; min-width:0; max-width:280px;">
                    <div style="font-size:14px; font-weight:500; color:#333; margin-bottom:4px; line-height:1.4; word-break:break-word;">${escapeHtml(p.name)}</div>
                    <div style="font-size:16px; font-weight:bold; color:#ff6b6b; margin-top:4px;">¥${p.price ? p.price.toFixed(2) : ''}</div>
                  </div>
                </div>
              </a>
            </div>
          `);

          if (index < data.products.length - 1) {
            items.push(`<div style="height:2px; overflow:hidden;"></div>`);
          }
        });

        const intro = text.split(lastJson)[0].trim();
        return (intro ? formatPlainText(intro) : '') +
          `<div style="margin:10px 0; padding:0; line-height:0; font-size:0;">${items.join('')}</div>` +
          `<div style="margin-top:12px; color:#666; font-size:14px; border-top:1px dashed #ddd; padding-top:8px;">✨ 以上商品均为预算内推荐，性价比高，如有特定需求可进一步咨询。</div>`;
      }

      // ========== 评分摘要 ==========
      if (data.type === 'score_summary') {
        const products = Array.isArray(data.products) ? data.products : [];

        let html = `
          <div style="margin:0 0 6px 0; padding:0;">
            <div style="font-size:15px; font-weight:600; color:#333; line-height:1.4;">
              ⭐ 评分摘要
            </div>
          </div>
        `;

        products.forEach((p) => {
          html += `
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; padding:6px 10px; background:#f9f9f9; border:1px solid #e9ecef; border-radius:8px; margin:2px 0;">
              <div style="flex:1; min-width:0;">
                <div style="font-size:14px; color:#333; font-weight:500; line-height:1.4; word-break:break-word;">
                  ${escapeHtml(p.name || '')}
                </div>
                <div style="font-size:12px; color:#888; margin-top:2px; line-height:1.3;">
                  共 ${p.total_comments ?? 0} 条评论
                </div>
              </div>
              <div style="flex-shrink:0; text-align:right;">
                <div style="font-size:18px; font-weight:bold; color:#ff6b6b; line-height:1;">
                  ${p.avg_score ?? '-'}
                </div>
                <div style="font-size:12px; color:#999; line-height:1;">
                  / 5
                </div>
              </div>
            </div>
          `;
        });

        return html;
      }

      // ========== 评论列表 ==========

      if (data.type === 'comment_list') {
        const d = data;
        const productName = d.product_name || '该商品';
        const comments = Array.isArray(d.comments) ? d.comments : [];

        let html = `
          <div style="margin:0 0 4px 0; padding:0;">
            <div style="font-size:15px; font-weight:600; color:#333; line-height:1.3; margin-bottom:2px;">
              💬 ${escapeHtml(productName)} 的评论
            </div>
            <div style="font-size:12px; color:#ff6b6b; line-height:1.2;">
              综合评分：${d.avg_score ?? '-'} / 5
              <span style="color:#999; margin-left:6px;">共 ${d.total_comments ?? 0} 条</span>
            </div>
          </div>
        `;

        comments.slice(0, 3).forEach((c) => {
          // 清理内容里的“商品名称：xxx”
          let content = (c.content || '').trim();
          content = content.replace(/商品名称[:：][^\n\r]*[\n\r]?/g, '');

          // 如果内容里还混有“评论内容：”“评分：”“昵称：”，也一起去掉
          content = content.replace(/评论内容[:：]/g, '');
          content = content.replace(/评分[:：][^\n\r]*/g, '');
          content = content.replace(/昵称[:：][^\n\r]*/g, '');

          html += `
            <div style="
              padding:3px 5px;
              margin:2px 0;
              background:#fafafa;
              border:1px solid #ececec;
              border-radius:6px;
              box-sizing:border-box;
            ">
              <div style="
                display:flex;
                justify-content:space-between;
                align-items:center;
                gap:6px;
                font-size:11px;
                color:#888;
                margin-bottom:1px;
                line-height:1.1;
              ">
                <div style="
                  min-width:0;
                  overflow:hidden;
                  text-overflow:ellipsis;
                  white-space:nowrap;
                  max-width:52%;
                ">
                  <strong style="color:#555;">${escapeHtml(c.nickname || '匿名')}</strong>
                </div>
                <div style="flex-shrink:0; white-space:nowrap;">
                  ${c.score ?? '-'}${c.create_time ? ` | ${escapeHtml(c.create_time)}` : ''}
                </div>
              </div>

              <div style="
                font-size:12px;
                line-height:1.25;
                color:#333;
                white-space:pre-wrap;
                word-break:break-word;
                margin:0;
                padding:0;
              ">
                ${escapeHtml(content)}
              </div>
            </div>
          `;
        });

        if (comments.length > 3) {
          html += `
            <div style="margin-top:3px; font-size:11px; color:#999; line-height:1.2;">
              仅显示前 3 条评论
            </div>
          `;
        }

        return html;
      }

      // ========== 正面观点 ==========
      if (data.type === 'positive_points' && Array.isArray(data.points)) {
        let items = [];
        data.points.forEach((p, index) => {
          items.push(`<div style="background:#e8f5e9; border-left:3px solid #4caf50; padding:4px 8px; margin:3px 0; border-radius:0 4px 4px 0;"><span style="font-weight:600; font-size:13px; color:#2e7d32;">👍 ${escapeHtml(p.point || '')}</span><span style="font-size:11px; color:#666; margin-left:8px;">评分:${p.score || '-'} | 置信度:${(p.confidence * 100).toFixed(0)}%</span></div>`);
        });
        const intro = text.split(lastJson)[0].trim();
        return (intro ? formatPlainText(intro) : '') + `<div style="margin:6px 0;"><div style="font-size:14px; font-weight:600; color:#4caf50; margin-bottom:4px;">✅ 正面评价 (共${data.total}条)</div>${items.join('')}</div>`;
      }

      // ========== 负面观点 ==========
      if (data.type === 'negative_points' && Array.isArray(data.points)) {
        let items = [];
        data.points.forEach((p, index) => {
          items.push(`<div style="background:#ffebee; border-left:3px solid #f44336; padding:4px 8px; margin:3px 0; border-radius:0 4px 4px 0;"><span style="font-weight:600; font-size:13px; color:#c62828;">👎 ${escapeHtml(p.point || '')}</span><span style="font-size:11px; color:#666; margin-left:8px;">评分:${p.score || '-'} | 置信度:${(p.confidence * 100).toFixed(0)}%</span></div>`);
        });
        const intro = text.split(lastJson)[0].trim();
        return (intro ? formatPlainText(intro) : '') + `<div style="margin:6px 0;"><div style="font-size:14px; font-weight:600; color:#f44336; margin-bottom:4px;">⚠️ 负面评价 (共${data.total}条)</div>${items.join('')}</div>`;
      }

      // ========== 情感分析 ==========
      if (data.type === 'sentiment_analysis') {
        const dist = data.sentiment_distribution || {};
        const contradictions = data.contradictions || [];
        
        let contradictionHtml = '';
        if (contradictions.length > 0) {
          let items = [];
          contradictions.slice(0, 3).forEach(c => {
            items.push(`<span style="display:inline-block; background:#fff3e0; border:1px solid #ffcc80; padding:2px 6px; margin:2px; border-radius:4px; font-size:12px;"><span style="font-weight:600; color:#e65100;">⚡ ${c.topic}</span><span style="color:#666;"> - ${c.conflict_level === 'high' ? '分歧较高' : '分歧中等'}</span></span>`);
          });
          contradictionHtml = `<div style="margin-top:6px;"><span style="font-size:12px; color:#e65100; font-weight:600;">📊 评价分歧点：</span>${items.join('')}</div>`;
        }

        let positiveHtml = '';
        if (data.top_positive_points && data.top_positive_points.length > 0) {
          let items = data.top_positive_points.slice(0, 3).map(p => 
            `<span style="display:inline-block; background:#e8f5e9; color:#2e7d32; padding:2px 6px; border-radius:12px; font-size:11px; margin:2px;">${escapeHtml(p.point || '').substring(0, 15)}...</span>`
          ).join('');
          positiveHtml = `<div style="margin-top:6px;"><span style="font-size:12px; color:#4caf50; font-weight:600;">✅ 优点：</span>${items}</div>`;
        }

        let negativeHtml = '';
        if (data.top_negative_points && data.top_negative_points.length > 0) {
          let items = data.top_negative_points.slice(0, 3).map(p => 
            `<span style="display:inline-block; background:#ffebee; color:#c62828; padding:2px 6px; border-radius:12px; font-size:11px; margin:2px;">${escapeHtml(p.point || '').substring(0, 15)}...</span>`
          ).join('');
          negativeHtml = `<div style="margin-top:6px;"><span style="font-size:12px; color:#f44336; font-weight:600;">⚠️ 槽点：</span>${items}</div>`;
        }

        const intro = text.split(lastJson)[0].trim();
        return (intro ? formatPlainText(intro) : '') +
          `<div style="margin:6px 0; padding:8px; background:#fafafa; border-radius:6px; border:1px solid #eee;">` +
          `<div style="font-size:14px; font-weight:600; color:#333; margin-bottom:6px;">📊 ${escapeHtml(data.product_name || '')} 口碑分析</div>` +
          `<div style="display:flex; gap:8px; margin-bottom:6px;">` +
          `<div style="flex:1; text-align:center; padding:6px; background:#e8f5e9; border-radius:4px;"><div style="font-size:20px; font-weight:bold; color:#4caf50;">${dist.positive_rate || 0}%</div><div style="font-size:11px; color:#666;">好评率</div></div>` +
          `<div style="flex:1; text-align:center; padding:6px; background:#e3f2fd; border-radius:4px;"><div style="font-size:20px; font-weight:bold; color:#1976d2;">${data.total_reviews || 0}</div><div style="font-size:11px; color:#666;">评论数</div></div>` +
          `<div style="flex:1; text-align:center; padding:6px; background:#fff3e0; border-radius:4px;"><div style="font-size:20px; font-weight:bold; color:#f57c00;">${data.divergence_score || 0}</div><div style="font-size:11px; color:#666;">分歧度</div></div>` +
          `</div>` +
          `<div style="display:flex; gap:6px; font-size:11px; margin-bottom:4px;">` +
          `<span style="background:#4caf50; color:white; padding:1px 6px; border-radius:3px;">👍 ${dist.positive || 0}</span>` +
          `<span style="background:#f44336; color:white; padding:1px 6px; border-radius:3px;">👎 ${dist.negative || 0}</span>` +
          `<span style="background:#9e9e9e; color:white; padding:1px 6px; border-radius:3px;">😐 ${dist.neutral || 0}</span>` +
          `</div>` +
          `${positiveHtml}${negativeHtml}${contradictionHtml}` +
          `<div style="margin-top:6px; padding:6px; background:#e3f2fd; border-radius:4px; border-left:2px solid #1976d2;"><span style="font-size:12px; font-weight:600; color:#1565c0;">📝 综合评价：</span><span style="font-size:12px; color:#333;">${escapeHtml(data.summary || '')}</span></div>` +
          `</div>`;
      }

      // ========== 情感对比 ==========
      if (data.type === 'sentiment_comparison' && Array.isArray(data.products)) {
        let items = [];
        data.products.forEach((p, index) => {
          const positiveRate = p.positive_rate || 0;
          const barColor = positiveRate >= 70 ? '#4caf50' : positiveRate >= 50 ? '#ff9800' : '#f44336';
          items.push(`<div style="background:#fff; border:1px solid #e0e0e0; border-radius:6px; padding:6px 8px; margin:4px 0;"><div style="font-size:13px; font-weight:600; color:#333; margin-bottom:4px;">${escapeHtml(p.product_name || '')}</div><div style="display:flex; align-items:center; gap:6px;"><div style="flex:1; background:#eee; border-radius:3px; height:6px; overflow:hidden;"><div style="width:${positiveRate}%; background:${barColor}; height:100%;"></div></div><span style="font-size:12px; font-weight:bold; color:${barColor};">${positiveRate}%</span></div><div style="font-size:11px; color:#666;">${p.total_reviews || 0}条评论 | 分歧度 ${p.divergence_score || 0}</div></div>`);
        });
        const intro = text.split(lastJson)[0].trim();
        return (intro ? formatPlainText(intro) : '') + `<div style="margin:6px 0;"><div style="font-size:14px; font-weight:600; color:#333; margin-bottom:4px;">📊 商品口碑对比</div>${items.join('')}</div>`;
      }
      // ========== 购买建议 ==========
if (data.type === 'purchase_recommendation') {
  const recColor = data.recommendation === 'recommended' ? '#4caf50' : 
                   data.recommendation === 'neutral' ? '#ff9800' : '#f44336';
  const recIcon = data.recommendation === 'recommended' ? '✅' : 
                  data.recommendation === 'neutral' ? '🤔' : '❌';
  
  let prosHtml = '';
  if (data.pros && data.pros.length > 0) {
    const items = data.pros.slice(0, 3).map(p => 
      `<span style="display:inline-block; background:#e8f5e9; color:#2e7d32; padding:2px 6px; border-radius:12px; font-size:11px; margin:2px;">👍 ${escapeHtml(p)}</span>`
    ).join('');
    prosHtml = `<div style="margin-top:6px;"><span style="font-size:12px; color:#4caf50; font-weight:600;">优点：</span>${items}</div>`;
  }
  
  let consHtml = '';
  if (data.cons && data.cons.length > 0) {
    const items = data.cons.slice(0, 3).map(c => 
      `<span style="display:inline-block; background:#ffebee; color:#c62828; padding:2px 6px; border-radius:12px; font-size:11px; margin:2px;">⚠️ ${escapeHtml(c)}</span>`
    ).join('');
    consHtml = `<div style="margin-top:6px;"><span style="font-size:12px; color:#f44336; font-weight:600;">注意：</span>${items}</div>`;
  }
  
  return `<div style="margin:6px 0; padding:10px; background:#fafafa; border-radius:8px; border:1px solid #eee;">` +
    `<div style="font-size:14px; font-weight:600; color:#333; margin-bottom:8px;">🛒 ${escapeHtml(data.product_name || '')}</div>` +
    `<div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">` +
    `<div style="font-size:24px;">${recIcon}</div>` +
    `<div>` +
    `<div style="font-size:18px; font-weight:bold; color:${recColor};">${data.recommendation_text || ''}</div>` +
    `<div style="font-size:12px; color:#666;">好评率 ${data.positive_rate || 0}% | ${data.total_reviews || 0}条评价</div>` +
    `</div>` +
    `</div>` +
    `${prosHtml}${consHtml}` +
    `<div style="margin-top:8px; padding:6px; background:#e3f2fd; border-radius:4px; border-left:2px solid #1976d2;">` +
    `<span style="font-size:12px; font-weight:600; color:#1565c0;">📝 总结：</span>` +
    `<span style="font-size:12px; color:#333;">${escapeHtml(data.summary || '')}</span>` +
    `</div>` +
    `</div>`;
}
    } catch (e) {
      console.error('解析JSON失败', e);
    }
  }
  return formatPlainText(text);
};

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

const handleBeforeUnload = () => {
  if (messages.value.length === 0) return
  const token = localStorage.getItem('token')
  const data = {
    messages: messages.value.map(m => ({
      role: m.role,
      content: m.content,
      timestamp: m.timestamp
    })),
    end_time: new Date().toISOString(),
    token: token,
    file_name: currentSessionFile.value // 新增
  }
  const blob = new Blob([JSON.stringify(data)], { type: 'application/json' })
  navigator.sendBeacon('http://localhost:8001/chat/sessions/save', blob)
}

// 初始化
onMounted(() => {
  console.log('用户登录状态:', isUserLoggedIn.value, '邮箱:', currentUserEmail.value)
  // 检查是否有保存的 sessionId（用于页面刷新后继续会话）
  const savedSessionId = localStorage.getItem('chat_session_id')
  if (savedSessionId) {
    sessionId.value = savedSessionId
    console.log('[Agent] 从 localStorage 恢复 sessionId:', sessionId.value)
  }
  
  // 检查服务状态
  checkAgentStatus()
  
  // 定期检查状态（每60秒）
  const statusInterval = setInterval(checkAgentStatus, 60000)
  
  // 聚焦输入框
  if (textArea.value) {
    textArea.value.focus()
  }
  
  // 更新调试信息
  debugInfo.value = {
    tokenStatus: isUserLoggedIn.value ? '有效' : '未登录',
    userEmail: currentUserEmail.value
  }
  currentSessionFile.value = null // 初始为全新会话
  fetchSessions()
  window.addEventListener('beforeunload', handleBeforeUnload)
  // 清理定时器
  return () => clearInterval(statusInterval)
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
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

watch(isUserLoggedIn, (newVal) => {
  if (newVal) {
    fetchSessions()
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
  height: calc(100vh - 180px);
}

.agent-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  width: 280px;
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  gap: 10px;
  .sidebar-section {
    
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
    // max-height: 300px;
    // overflow-y: auto;
    overflow-y: visible;
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
  .usage-list {
  padding: 0 5px 0 0;    /* 右侧留出滚动条空间 */
}

.usage-item {
  padding: 8px 12px;
  margin-bottom: 6px;
  background: #f8f9fa;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #555;
  word-break: break-word;
  transition: background 0.2s;
}

.usage-item:hover {
  background: #e9ecef;
  color: #4CAF50;
}

.no-usage {
  color: #999;
  font-size: 13px;
  text-align: center;
  padding: 20px 0;
}
/* 历史会话区域：固定最大高度 400px，超出滚动 */
.history-section {
  flex: 0 0 auto;
  height: 400px;
  overflow-y: auto;
}

/* 使用记录区域：占据剩余空间，超出滚动 */
.usage-section {
  flex: 1 1 auto;
  min-height: 0;         /* 允许收缩 */
  overflow-y: auto;
}

/* 登录状态区域：固定最大高度 225px，超出滚动 */
.user-section {
  flex: 0 0 auto;
  max-height: 225px;
  overflow-y: auto;
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

/* 商品卡片链接：由内容决定宽度，避免占满 */
.product-card-link {
  display: inline-block;        /* 改为内联块，宽度由内容撑开 */
  max-width: 100%;              /* 但不超过父容器宽度 */
  text-decoration: none;
  color: inherit;
}

/* 卡片本身：内联 flex，宽度由内容决定 */
.product-card {
  display: inline-flex;         /* 关键：内联 flex，宽度由内容决定 */
  align-items: center;
  background: #f9f9f9;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 8px;
  transition: box-shadow 0.2s;
  max-width: 100%;              /* 防止溢出 */
}

/* 图片固定尺寸 */
.product-card img {
  width: 80px !important;
  height: 80px !important;
  object-fit: cover;
  border-radius: 6px;
  margin-right: 12px;
  flex-shrink: 0;
  background-color: #f0f0f0;
}

/* 右侧信息区域：不强制拉伸，允许收缩，限制最大宽度 */
.product-info {
  flex: 0 1 auto;               /* 不伸展，可收缩 */
  min-width: 0;
  max-width: 280px;             /* 限制文字区域最大宽度，避免卡片过宽 */
  display: flex;
  flex-direction: column;
  justify-content: center;
}

/* 商品名称 */
.product-name {
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
  line-height: 1.4;
  word-break: break-word;
  display: -webkit-box;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 价格 */
.product-price {
  font-size: 16px;
  font-weight: bold;
  color: #ff6b6b;
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
    font-size: 16px;
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
  font-size: 16px;
}

.assistant .message-content {
  background: #f8f9fa;
  color: #333;
  font-size: 16px;
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
.user-name {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  line-height: 1.4;
}

.user-email {
  font-size: 12px;
  color: #999;
  margin: 2px 0;
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