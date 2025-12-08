import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app import models, schemas
from app.auth_utils import get_current_user

logger = logging.getLogger("app.clearance")

router = APIRouter(prefix="/clearance", tags=["Clearance"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Endpoint: GET /clearance/{user_id}
# Description: Returns a list of clearance records for the given user_id.
# Only non-archived clearance records are returned.
@router.get("/{user_id}", response_model=list[schemas.ClearanceSchema])
def get_clearance(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) is fetching clearance for user_id: {user_id}")
    clearances = db.query(models.Clearance).filter(
        models.Clearance.user_id == user_id,
        models.Clearance.archived == False  # Exclude archived data
    ).all()
    logger.info(f"User {current_user.id} ({current_user.full_name}) fetched {len(clearances)} clearance records for user_id: {user_id}")
    return clearances
