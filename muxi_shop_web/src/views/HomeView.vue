<template>
    <div>
        <Shortcut></Shortcut>
        <Header></Header>
        <div class="inner">
            <Navigation></Navigation>
            
            <!-- 添加Agent助手按钮 -->
            <div class="agent-shortcut">
                <el-button 
                    type="success" 
                    class="agent-btn"
                    @click="openAgent"
                    icon="🤖"
                >
                    <span class="btn-text">智能购物助手</span>
                    <span class="btn-hint">免费咨询</span>
                </el-button>
            </div>
            
            <div class="category clearfix">
                <div class="content fl" v-for="(item, index) in category" :key="index">
                    <div @click="toCategory(item.typeId)">
                        <!--当selected为true的时候就有select_title和select_content的效果-->
                        <div class="category-title" :class="{ select_title: item.selected }">{{ item.title }}</div>
                        <div class="category-content" :class="{ select_content: item.selected }">{{ item.content }}</div>
                    </div>
                </div>
            </div>
            <Category :categoryId="categoryId"></Category>
        </div>
        <!--Element-plus 返回顶部功能-->
        <el-backtop right="300" bottom="10"></el-backtop>
    </div>
</template>

<script setup>
import Shortcut from '@/components/common/Shortcut.vue';
import Header from '@/components/home/Header.vue';
import Navigation from '@/components/home/Navigation.vue';
import Category from '@/components/home/Category.vue';
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()

let category = ref([    
    { typeId: 1, title: "精选", content: "猜你喜欢", selected: true },
    { typeId: 2, title: "智能先锋", content: "大电器城", selected: false },
    { typeId: 3, title: "居家优品", content: "品质生活", selected: false },
    { typeId: 4, title: "超市百货", content: "百货生鲜", selected: false },
    { typeId: 5, title: "时尚达人", content: "美妆穿搭", selected: false },
    { typeId: 6, title: "进口好物", content: "京东国际", selected: false },
])

let categoryId = ref(1)
const toCategory = (typeId) => {
    categoryId.value = typeId
    for(let i in category.value){
        category.value[i].selected=false;
        if(typeId==(parseInt(i)+1)){
            category.value[i].selected=true;
        }
    }
}

// 打开Agent助手页面
const openAgent = () => {
    // 在新标签页打开
    const routeData = router.resolve({ name: 'agent' })
    window.open(routeData.href, '_blank')
    
    // 或者直接在当前页跳转
    // router.push({ name: 'agent' })
}
</script>

<style lang="less" scoped>
.inner {
    background-color: #f4f4f4;

    // Agent按钮样式
    .agent-shortcut {
        width: var(--content-width);
        margin: 15px auto;
        text-align: right;
        
        .agent-btn {
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            border: none;
            border-radius: 25px;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 600;
            color: white;
            box-shadow: 0 4px 15px rgba(76, 175, 80, 0.3);
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            
            &:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(76, 175, 80, 0.4);
                background: linear-gradient(135deg, #45a049 0%, #3d8b40 100%);
            }
            
            &:active {
                transform: translateY(0);
            }
            
            .btn-text {
                font-size: 15px;
            }
            
            .btn-hint {
                font-size: 12px;
                opacity: 0.9;
                font-weight: normal;
            }
        }
    }

    .find-goods {
        padding-top: 25px;
        margin-bottom: 25px;
    }

    .category {
        width: var(--content-width);
        margin: 0 auto;
        height: 70px;
        text-align: center;
        background-color: #fff;
        margin-top: 10px;
        .content {
            width: 198px;
            margin-top: 10px;

            &:not(:last-child) {
                //最后一个元素没有其他都有以下元素
                border-right: 1px solid #e8e8e8;
            }

            .category-title {
                font-size: 16px;
                font-weight: 700;
                height: 30px;
                line-height: 30px;
            }

            .category-content {
                font-size: 14px;
                color: #999;
            }

            &:hover {
                cursor: pointer;
                color: #e1251b;
            }

            &:hover div:last-child {
                cursor: pointer;
                color: #e1251b;
            }

            div {
                width: 80px;
                margin: 0 auto;
            }
            //当谁的selected为true的时候谁就有以下效果
            .select_title {
                background-color: #e1251b;
                color: #fff;
                border-radius: 15px;
            }

            .select_content {
                color: #e1251b;
            }
        }
    }
}
</style>