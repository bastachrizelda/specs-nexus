# chat.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.chat_nlp import get_chat_response
from app.auth_utils import get_current_user
from app import models
import traceback

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str
    userId: int

class ChatResponse(BaseModel):
    response: str

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest, current_user: models.User = Depends(get_current_user)):
    try:
        if current_user.id != chat_request.userId:
            raise HTTPException(status_code=403, detail="Unauthorized user ID")
        user_message = chat_request.message.strip()
        response_text = get_chat_response(user_message, current_user.id)
        return ChatResponse(response=response_text)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")