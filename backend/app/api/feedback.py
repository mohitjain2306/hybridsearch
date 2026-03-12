from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.db import get_db
import sqlite3, logging, uuid
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

class FeedbackRequest(BaseModel):
    request_id: str
    doc_id: str
    relevant: bool
    comment: str | None = None

@router.post("/api/v1/feedback")
def post_feedback(body: FeedbackRequest, db: sqlite3.Connection = Depends(get_db)):
    db.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            relevant INTEGER NOT NULL,
            comment TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    db.execute(
        "INSERT INTO feedback (request_id, doc_id, relevant, comment, timestamp) VALUES (?,?,?,?,?)",
        (body.request_id, body.doc_id, int(body.relevant), body.comment,
         datetime.now(timezone.utc).isoformat())
    )
    db.commit()
    logger.info("feedback logged", extra={"request_id": body.request_id, "doc_id": body.doc_id})
    return {"status": "ok"}
