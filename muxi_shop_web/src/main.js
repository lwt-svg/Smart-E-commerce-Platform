import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import "@/assets/css/config.css" 
//引入iconfont样式
import "@/assets/iconfont/iconfont.css"
//引入element-plus
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

const app = createApp(App);
app.use(store).use(router).use(ElementPlus).mount('#app')