import logging
import datetime
import pytz
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app import models, schemas
from app.auth_utils import get_current_officer

logger = logging.getLogger("app.cash_payments")

router = APIRouter(prefix="/officer", tags=["Cash Payments"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/cash-payment", response_model=schemas.MembershipSchema)
def officer_cash_payment(
    payload: schemas.CashPaymentConfirmRequest,
    db: Session = Depends(get_db),
    current_officer: models.Officer = Depends(get_current_officer),
):
    receipt_number = (payload.receipt_number or "").strip()
    if not receipt_number:
        raise HTTPException(status_code=400, detail="Receipt/reference number is required")

    requirement = (payload.requirement or "").strip()
    valid_requirements = ["1st Semester Membership", "2nd Semester Membership"]
    if requirement not in valid_requirements:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid requirement. Must be one of: {', '.join(valid_requirements)}",
        )

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    try:
        with db.begin():
            existing_receipt = db.query(models.Clearance).filter(
                models.Clearance.receipt_number == receipt_number,
                models.Clearance.archived == False,
            ).first()
            if existing_receipt:
                raise HTTPException(status_code=409, detail="Receipt/reference number already used")

            membership = db.query(models.Clearance).filter(
                models.Clearance.user_id == payload.user_id,
                models.Clearance.requirement == requirement,
                models.Clearance.archived == False,
            ).with_for_update().first()

            if not membership:
                raise HTTPException(status_code=404, detail="Membership record not found for user/semester")

            if membership.payment_status == "Paid":
                raise HTTPException(status_code=409, detail="Membership is already paid")

            if membership.payment_method not in [None, "cash"]:
                raise HTTPException(status_code=409, detail="Membership is not marked as cash payment")

            manila_tz = pytz.timezone('Asia/Manila')
            now_manila = datetime.datetime.now(manila_tz).replace(tzinfo=None)
            membership.amount = payload.amount
            membership.payment_method = "cash"
            membership.receipt_number = receipt_number
            membership.payment_status = "Paid"
            membership.status = "Clear"
            membership.verified_by = current_officer.id
            membership.verified_at = now_manila
            membership.payment_date = now_manila
            membership.approval_date = now_manila
            membership.approved_by = current_officer.full_name
            membership.denial_reason = None

        db.refresh(membership)
        logger.info(
            f"Cash payment verified by officer {current_officer.id} for user_id={payload.user_id} requirement={requirement} receipt_number={receipt_number}"
        )
        return membership

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming cash payment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to confirm cash payment")
