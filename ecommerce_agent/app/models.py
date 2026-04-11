#定义Pydantic模型

from pydantic import BaseModel
from typing import Optional,List,Dict

class ChatRequest(BaseModel):
    message:str
    session_id:Optional[str] = None
    token:Optional[str] = None
    user_email: Optional[str] = None
    history:Optional[List[Dict[str,str]]] = None
    use_rag:bool = True

class ChatResponse(BaseModel):
    response : str
    session_id : Optional[str] = None
    timestamp : str
    source:Optional[str] = None