"""In-app support chat + support links.

Chat is backed by the admin-managed chat model of the app (deepseek / glm / minimax / claude),
with a knowledge-base system prompt so the bot can answer "how do I use this tool?".
It costs nothing by default (CHAT_CREDIT_COST=0); admins can set a price in .env.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import ai, ratelimit
from ..chat_knowledge import SYSTEM_PROMPT
from ..db import get_db
from ..deps import current_user
from ..llm import resolve_llm
from ..models import ChatMessage, User

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)

MAX_HISTORY = 12
MAX_MESSAGE = 2000
HOURLY_LIMIT = 40


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE)
    history: list[dict] = Field(default_factory=list)


@router.get("/support")
def support_links(db: Session = Depends(get_db)):
    """Public support links shown in the UI (no auth needed for viewing)."""
    from .. import support as support_mod
    return support_mod.get_links(db)


@router.get("/chat/history")
def chat_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Lịch sử chat của riêng tài khoản này (không dùng chung với user khác)."""
    rows = db.scalars(
        select(ChatMessage).where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    ).all()
    msgs = [{"role": r.role, "content": r.content,
             "created_at": r.created_at.isoformat() if r.created_at else ""} for r in rows]
    return {"messages": msgs[-200:]}


@router.delete("/chat/history")
def chat_history_clear(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Xoá lịch sử chat của tài khoản hiện tại."""
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    db.commit()
    return {"ok": True}


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    key = f"chat:{user.id}"
    if ratelimit.hit(key, 3600) > HOURLY_LIMIT:
        raise HTTPException(429, f"Bạn gửi quá nhiều câu hỏi ({HOURLY_LIMIT}/giờ). Thử lại sau hoặc liên hệ hỗ trợ trực tiếp.")

    llm = resolve_llm(db)
    if not llm:
        raise HTTPException(503, "Trợ lý AI chưa được cấu hình model. Vui lòng liên hệ quản trị viên.")

    # Lịch sử do SERVER lưu theo user_id — không tin history client gửi lên (tránh trộn dữ liệu).
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    rows = db.scalars(
        select(ChatMessage).where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        ).all()
    for r in rows[-MAX_HISTORY:]:
        messages.append({"role": r.role, "content": (r.content or "")[:MAX_MESSAGE]})
    messages.append({"role": "user", "content": body.message.strip()})

    # Reserve configured chat policy plus exact selected-model API unit cost before external call.
    from .. import featurebilling
    usage = featurebilling.reserve(db, user.id, "support_chat", model_id=llm["id"],
                                   model_cost=float(llm.get("price", 0.0) or 0.0))
    try:
        msg = ai.chat(llm["creds"]["model_name"], messages,
                      base_url=llm["creds"].get("base_url"),
                      api_key=llm["creds"].get("api_key"),
                      timeout=60)
    except Exception as e:
        from .. import featurebilling
        featurebilling.finish(db, usage.id, success=False)
        logger.warning("[chat] LLM error: %s", e)
        raise HTTPException(502, "Trợ lý AI đang bận. Vui lòng thử lại sau ít phút hoặc liên hệ hỗ trợ qua Zalo/Facebook.")

    reply = (msg or {}).get("content") or ""
    reply = reply.strip()
    if not reply:
        from .. import featurebilling
        featurebilling.finish(db, usage.id, success=False)
        raise HTTPException(502, "Trợ lý AI không trả lời được. Thử lại hoặc liên hệ hỗ trợ trực tiếp.")

    # Lưu lịch sử riêng cho tài khoản này
    try:
        db.add(ChatMessage(user_id=user.id, role="user", content=body.message.strip()))
        db.add(ChatMessage(user_id=user.id, role="assistant", content=reply))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("[chat] persist history failed: %s", e)

    from .. import featurebilling
    featurebilling.finish(db, usage.id, success=True)
    return {"reply": reply, "model": llm["name"]}
