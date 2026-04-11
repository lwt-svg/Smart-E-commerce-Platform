import os
import json
import hashlib
import asyncio
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Header, BackgroundTasks
from pydantic import BaseModel

from .auth import get_user_email_from_token
from .profile import profile_manager
from my_llm import llm

router = APIRouter(prefix="/chat/sessions", tags=["sessions"])

# 会话存储根目录
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

# ================== 请求模型 ==================
class SaveSessionRequest(BaseModel):
    messages: list
    end_time: str          # ISO 格式时间
    token: Optional[str] = None  # 用于 sendBeacon 无 header 时
    file_name: Optional[str] = None

# ================== 辅助函数 ==================
def get_user_id_from_token(token: Optional[str]) -> Optional[str]:
    """
    根据 token 获取用户标识：
    - 如果 token 有效，返回 "user_{email}"
    - 如果 token 无效或不存在，返回 None
    """
    if token:
        try:
            email = get_user_email_from_token(token)
            print(f"[get_user_id_from_token] 解析出的 email: {email}")
            if email:
                # 邮箱中可能包含特殊字符，做安全替换
                safe_email = email.replace('@', '_at_').replace('.', '_dot_')
                return f"user_{safe_email}"
        except Exception as e:
            print(f"[get_user_id_from_token] 解析失败: {e}")
    return None

def get_user_dir(user_id: str) -> str:
    """返回用户会话目录，不存在则创建"""
    user_dir = os.path.join(SESSIONS_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

# ================== 路由 ==================

@router.post("/save")
async def save_session(
    request: Request,
    req: SaveSessionRequest,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None)
):
    """
    保存当前会话到文件，并更新用户画像
    优先使用 header 中的 Authorization，否则使用 body 中的 token
    """
    print(f"[save_session] 收到保存请求，消息数: {len(req.messages)}")
    print(f"[save_session] Authorization header: {authorization}")
    print(f"[save_session] Body token: {req.token}")
    print(f"[save_session] file_name: {req.file_name}")

    token_to_use = authorization or req.token
    user_id = get_user_id_from_token(token_to_use)
    print(f"[save_session] 解析出的 user_id: {user_id}")

    if not user_id:
        client_ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.md5(client_ip.encode()).hexdigest()[:8]
        user_id = f"anonymous_{ip_hash}"
        print(f"[save_session] 使用匿名标识: {user_id}")

    user_dir = get_user_dir(user_id)

    if req.file_name:
        file_name = req.file_name
        print(f"[save_session] 使用提供的文件名: {file_name}")
    else:
        try:
            dt = datetime.fromisoformat(req.end_time.replace('Z', '+00:00'))
        except:
            dt = datetime.now()
        file_name = dt.strftime("%Y%m%d-%H%M%S") + ".json"
        print(f"[save_session] 生成新文件名: {file_name}")

    file_path = os.path.join(user_dir, file_name)
    print(f"[save_session] 文件路径: {file_path}")

    session_data = {
        "created_at": req.end_time,
        "updated_at": req.end_time,
        "messages": req.messages
    }

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        print(f"[save_session] 文件写入成功")
    except Exception as e:
        print(f"[save_session] 文件写入失败: {e}")
        return {"status": "error", "detail": str(e)}

    if not req.file_name:
        files = [f for f in os.listdir(user_dir) if f.endswith(".json")]
        if len(files) > 10:
            files.sort()
            for old_file in files[:len(files)-10]:
                os.remove(os.path.join(user_dir, old_file))
                print(f"[save_session] 删除旧文件: {old_file}")

    if req.messages and len(req.messages) > 0 and not user_id.startswith("anonymous_"):
        background_tasks.add_task(
            update_user_profile_task,
            user_id=user_id,
            messages=req.messages
        )
        print(f"[save_session] 已添加画像更新任务到后台队列")

    return {"status": "ok", "file": file_name}


async def update_user_profile_task(user_id: str, messages: list):
    """
    后台任务：更新用户画像
    """
    try:
        print(f"[update_user_profile_task] 开始为用户 {user_id} 提取偏好...")
        
        preferences = await asyncio.wait_for(
            profile_manager.extract_preferences_from_session(
                messages=messages,
                llm=llm
            ),
            timeout=30.0
        )
        
        if preferences:
            await profile_manager.update_user_profile(
                user_id=user_id,
                new_preferences=preferences
            )
            print(f"[update_user_profile_task] 用户画像更新完成")
        else:
            print(f"[update_user_profile_task] 未提取到有效偏好")
            
    except asyncio.TimeoutError:
        print(f"[update_user_profile_task] 偏好提取超时(30s)，跳过")
    except Exception as e:
        print(f"[update_user_profile_task] 画像更新失败: {e}")


@router.get("/list")
async def list_sessions(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    获取当前用户的所有历史会话列表（按时间倒序）
    """
    print(f"[list_sessions] 收到的 Authorization: {authorization}")
    user_id = get_user_id_from_token(authorization)
    print(f"[list_sessions] 解析出的 user_id: {user_id}")

    if not user_id:
        client_ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.md5(client_ip.encode()).hexdigest()[:8]
        user_id = f"anonymous_{ip_hash}"
        print(f"[list_sessions] 使用匿名标识: {user_id}")

    user_dir = get_user_dir(user_id)
    print(f"[list_sessions] 用户目录: {user_dir}")

    if not os.path.exists(user_dir):
        print(f"[list_sessions] 目录不存在，返回空列表")
        return []

    files = os.listdir(user_dir)
    print(f"[list_sessions] 目录下文件: {files}")

    sessions = []
    for f in files:
        if not f.endswith(".json"):
            continue
        file_path = os.path.join(user_dir, f)
        try:
            with open(file_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            # 生成预览：取第一条用户消息，否则取第一条消息
            preview = ""
            for msg in data.get("messages", []):
                if msg.get("role") == "user":
                    preview = msg.get("content", "")[:30]
                    break
            if not preview and data.get("messages"):
                preview = data["messages"][0].get("content", "")[:30]
            sessions.append({
                "file_name": f,
                "preview": preview + ("..." if len(preview) == 30 else ""),
                "time": data.get("created_at", "")
            })
        except Exception as e:
            print(f"[list_sessions] 读取文件 {f} 出错: {e}")
            continue

    # 按时间倒序（最新的在前）
    sessions.sort(key=lambda x: x["time"], reverse=True)
    print(f"[list_sessions] 最终返回 sessions 数量: {len(sessions)}")
    return sessions


@router.get("/load/{file_name}")
async def load_session(
    file_name: str,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    加载指定文件名的历史会话
    """
    print(f"[load_session] 加载文件: {file_name}")
    print(f"[load_session] 收到的 Authorization: {authorization}")
    user_id = get_user_id_from_token(authorization)
    print(f"[load_session] 解析出的 user_id: {user_id}")

    if not user_id:
        client_ip = request.client.host if request.client else "unknown"
        ip_hash = hashlib.md5(client_ip.encode()).hexdigest()[:8]
        user_id = f"anonymous_{ip_hash}"
        print(f"[load_session] 使用匿名标识: {user_id}")

    user_dir = get_user_dir(user_id)
    file_path = os.path.join(user_dir, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="会话不存在")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data