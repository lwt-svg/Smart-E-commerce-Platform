#JWT验证相关

import jwt
from typing import Optional
from .config import JWT_SECRET_KEY,JWT_ALGORITHM

def verify_jwt_token(token:str) -> Optional[dict]:
    '''验证JWT token并返回payload'''
    try:
        #移除可能的Bearer前缀
        if token.startswith("Bearer "):
            token = token[7:]
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={'verify_exp':True}
        )
        return payload
    except jwt.ExpiredSignatureError:
        print('token已过期')
        return None
    except jwt.InvalidSignatureError as e:
        print(f"无效的token:{e}")
    except Exception as e:
        print(f"token验证错误:{e}")
        return None

def get_user_email_from_token(token:Optional[str]) -> Optional[str]:
    '''从token中获取用户email'''
    if not token:
        return None
    payload = verify_jwt_token(token)
    if not payload:
        return None
    
    #根据token结构获取username(实际是email)
    return payload.get("username")