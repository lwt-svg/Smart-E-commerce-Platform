<template>
    <div class="comment">
        <div class="detail" v-for="(item, index) in commentData" :key="index">
            <div class="clearfix">
                <div class="left fl">
                    <div class="header-content">
                        <img :src="'http://' + item.user_image_url" alt="">
                        <span class="nick-name">{{ item.nickname }}</span>
                    </div>
                </div>
                <div class="right fl">
                    <div class="star">
                        <img src="@/assets/images/goods/star.png" alt="" v-for="index in item.score" :key="index">
                        <img src="@/assets/images/goods/star1.png" alt="" v-for="index in (5 - item.score)"
                            :key="index">
                    </div>
                    <div class="text">
                        {{ item.content }}
                    </div>
                    <div class="time">
                        {{ item.create_time.replace("T", " ").replace("Z", " ") }}
                    </div>
                </div>
            </div>
            <hr>
        </div>
        <div class="change_page">
            <div class="block">
                <span class="demonstration"> </span>
                <el-pagination layout="prev, pager, next" 
                :total="commentCount" 
                :page-size="15" 
                @current-change="handleCurrentChange"> </el-pagination>
            </div>
        </div>
    </div>
</template>

<script setup>
import { getCommentCountData, getGoodsCommentData } from '@/network/comment';
import { onMounted, ref } from 'vue';

let skuId = defineProps(["skuId"])
let commentData = ref([])
let commentCount = ref(0)

onMounted(() => {
    getCommentCountData(skuId.skuId).then(res => {
        commentCount.value = res
    })
    getGoodsCommentData(skuId.skuId, 1).then(res => {
        commentData.value = res.data
    })
})

const handleCurrentChange=val=>{
        getGoodsCommentData(skuId.skuId, val).then(res => {
        commentData.value = res.data
    })
}
</script>

<style lang="less" scoped>
.comment {
    .detail {
        margin-top: 10px;
        .left {
            .header-content {
                img {
                    width: 25px;
                    height: 25px;
                    border-radius: 25px;
                }

                .nick-name {
                    margin-left: 10px;
                }
            }
        }

        .right {
            width: 830px;
            margin-left: 70px;

            .star {
                img {
                    width: 14px;
                    height: 14px;
                }
            }

            .text {
                color: #333;
                font-size: 14px;
                margin-top: 10px;

            }

            .time {
                color: #999;
                margin-top: 10px;
            }
        }
        hr{
            margin-top: 10px;
            margin-bottom: 10px;
            border:1px solid #dddddd;
        }
    }
    .change_page{
        margin-top: 20px;
        margin-left: 75%;
        margin-bottom: 20px;
    }
}
</style>