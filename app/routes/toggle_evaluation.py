from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models
from app.auth_utils import get_current_officer
import logging

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

logger = logging.getLogger(__name__)
router = APIRouter()

@router.patch("/admin/events/{event_id}/toggle-evaluation")
async def toggle_evaluation(
    event_id: int,
    evaluation_open: bool = Form(...),
    db: Session = Depends(get_db),
    current_officer: models.Officer = Depends(get_current_officer)
):
    """Toggle evaluation form access for an event"""
    logger.debug(f"Officer {current_officer.id} toggling evaluation for event {event_id} to {evaluation_open}")
    
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        logger.error(f"Event {event_id} not found")
        raise HTTPException(status_code=404, detail="Event not found")
    
    event.evaluation_open = evaluation_open
    db.commit()
    db.refresh(event)
    
    logger.info(f"Officer {current_officer.id} set evaluation_open={evaluation_open} for event {event_id}")
    return {"detail": f"Evaluation form {'enabled' if evaluation_open else 'disabled'} successfully", "evaluation_open": evaluation_open}
