import logging
import os
import uuid
import re
from urllib.parse import unquote
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from pydantic import BaseModel
import datetime
import pytz
import boto3
from botocore.client import Config

from app.database import SessionLocal
from app import models, schemas
from app.auth_utils import get_current_user

logger = logging.getLogger("app.membership")

router = APIRouter(prefix="/membership", tags=["Membership"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Configure boto3 client for Cloudflare R2
access_key_id = os.getenv('CF_ACCESS_KEY_ID')
secret_access_key = os.getenv('CF_SECRET_ACCESS_KEY')
bucket_name = os.getenv('CLOUDFLARE_R2_BUCKET')
endpoint_url = os.getenv('CLOUDFLARE_R2_ENDPOINT')

# Log environment variables for debugging (without showing secret values)
logger.debug(f"CF_ACCESS_KEY_ID set: {bool(access_key_id)}")
logger.debug(f"CF_SECRET_ACCESS_KEY set: {bool(secret_access_key)}")
logger.debug(f"CLOUDFLARE_R2_BUCKET: {bucket_name}")
logger.debug(f"CLOUDFLARE_R2_ENDPOINT: {endpoint_url}")

# Verify that bucket_name is not None before proceeding
if not bucket_name:
    logger.error("CLOUDFLARE_R2_BUCKET environment variable is not set")
    bucket_name = "specs-nexus-files"  # Fallback to hardcoded value

s3 = boto3.client(
    's3',
    endpoint_url=endpoint_url,
    aws_access_key_id=access_key_id,
    aws_secret_access_key=secret_access_key,
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to make it safe for URLs and file systems.
    Removes spaces and other problematic characters.
    """
    if not filename:
        return "unnamed_file"
    
    # First decode any URL encoding
    try:
        filename = unquote(filename)
    except:
        pass
    
    # Extract the file extension
    if '.' in filename:
        name, ext = filename.rsplit('.', 1)
        ext = f".{ext}"
    else:
        name, ext = filename, ""
    
    # Remove spaces first
    name = name.replace(' ', '')
    
    # Remove or replace other problematic characters
    # Keep only alphanumeric, hyphens, and underscores
    name = re.sub(r'[^a-zA-Z0-9\-_]', '_', name)
    
    # Remove multiple consecutive underscores
    name = re.sub(r'_{2,}', '_', name)
    
    # Remove leading/trailing underscores
    name = name.strip('_')
    
    # Ensure the name isn't empty
    if not name:
        name = "file"
    
    # Limit the length to prevent issues
    if len(name) > 50:
        name = name[:50]
    
    return f"{name}{ext}".lower()

# Make the upload_to_r2 function async
async def upload_to_r2(file: UploadFile, object_key: str):
    try:
        # Get credentials from environment variables
        access_key = os.getenv("CF_ACCESS_KEY_ID")
        secret_key = os.getenv("CF_SECRET_ACCESS_KEY")
        bucket_name = os.getenv("CLOUDFLARE_R2_BUCKET")
        endpoint_url = os.getenv("CLOUDFLARE_R2_ENDPOINT")
        
        # Use worker URL instead of direct R2 public URL
        worker_url = os.getenv("CLOUDFLARE_WORKER_URL", "https://specsnexus-images.senya-videos.workers.dev")
        
        # Log credential availability for debugging
        logger.info(f"R2 Credentials - Access Key: {'Available' if access_key else 'Missing'}")
        logger.info(f"R2 Credentials - Secret Key: {'Available' if secret_key else 'Missing'}")
        logger.info(f"R2 Credentials - Bucket: {bucket_name or 'Missing'}")
        logger.info(f"R2 Credentials - Endpoint: {endpoint_url or 'Missing'}")
        logger.info(f"R2 Credentials - Worker URL: {worker_url or 'Missing'}")
        
        if not all([access_key, secret_key, bucket_name, endpoint_url, worker_url]):
            raise ValueError("Missing R2 credentials or configuration")
        
        # Create S3 client with explicit credentials
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url
        )
        
        # Validate file type - only PNG and JPEG allowed
        allowed_types = ['image/png', 'image/jpeg', 'image/jpg']
        if file.content_type.lower() not in allowed_types:
            logger.error(f"Invalid file type uploaded: {file.content_type}")
            raise HTTPException(status_code=400, detail="Only PNG and JPEG images are allowed.")
        
        # Also check file extension as additional validation
        file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        if file_extension not in ['png', 'jpg', 'jpeg']:
            logger.error(f"Invalid file extension: {file_extension}")
            raise HTTPException(status_code=400, detail="Only PNG and JPEG images are allowed.")
        
        # Upload the file
        logger.info(f"Uploading file to R2: {object_key}")
        s3.upload_fileobj(file.file, bucket_name, object_key)
        
        # Use the worker URL for the uploaded file
        if worker_url.endswith('/'):
            file_url = f"{worker_url}{object_key}"
        else:
            file_url = f"{worker_url}/{object_key}"
            
        logger.info(f"File uploaded successfully: {file_url}")
        return file_url
        
    except Exception as e:
        logger.error(f"Error uploading file to R2: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

# QR Code Endpoints

@router.get("/qrcode", response_model=dict)
def get_qrcode(payment_type: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) fetching QR code for payment type: {payment_type}")
    if payment_type not in ["gcash", "paymaya", "cash"]:
        logger.error(f"User {current_user.id} provided invalid payment type: {payment_type}")
        raise HTTPException(status_code=400, detail="Payment type must be 'gcash', 'paymaya', or 'cash'")
    
    if payment_type == "cash":
        logger.info(f"User {current_user.id} requested QR code for cash payment (not applicable)")
        raise HTTPException(status_code=400, detail="Cash payments do not require QR codes")
    
    qr_record = db.query(models.QRCode).first()
    if not qr_record:
        logger.error(f"No QR code record found for user {current_user.id}")
        raise HTTPException(status_code=404, detail="No QR code record found")
    
    url = qr_record.gcash if payment_type == "gcash" else qr_record.paymaya
    if not url:
        logger.error(f"No QR code uploaded for payment type {payment_type} for user {current_user.id}")
        raise HTTPException(status_code=404, detail=f"No QR code uploaded for {payment_type}")
    
    logger.info(f"User {current_user.id} fetched QR code URL: {url}")
    return {"qr_code_url": url}

@router.post("/officer/upload_qrcode", response_model=dict)
async def upload_officer_qrcode(
    payment_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    logger.debug(f"Uploading QR code for payment_type: {payment_type}")
    if payment_type not in ["gcash", "paymaya"]:
        logger.error(f"Invalid payment type: {payment_type}")
        raise HTTPException(status_code=400, detail="Payment type must be 'gcash' or 'paymaya' (cash does not require QR code)")
    
    # Generate a safe filename
    sanitized_filename = sanitize_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{sanitized_filename}"
    object_key = f"qrcodes/{unique_filename}"
    
    try:
        file_url = await upload_to_r2(file, object_key)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error uploading QR code to R2: {str(e)}")
        raise HTTPException(status_code=500, detail="Error uploading QR code file")
    
    qr_record = db.query(models.QRCode).first()
    if not qr_record:
        qr_record = models.QRCode()
        db.add(qr_record)
    
    if payment_type == "gcash":
        qr_record.gcash = file_url
    else:
        qr_record.paymaya = file_url
    
    db.commit()
    db.refresh(qr_record)
    logger.info(f"Uploaded QR code successfully for {payment_type} at {file_url}")
    return {"qr_code_url": file_url}

# User Endpoints

@router.get("/memberships/{user_id}", response_model=List[schemas.MembershipSchema])
def get_memberships(
    user_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) fetching memberships for user_id: {user_id}")
    if current_user.id != user_id:
        logger.error(f"User {current_user.id} attempted to access memberships for user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Not authorized to access this user's memberships")
    memberships = db.query(models.Clearance)\
        .options(joinedload(models.Clearance.user))\
        .filter(models.Clearance.user_id == user_id, models.Clearance.archived == False)\
        .all()
    logger.info(f"User {current_user.id} fetched {len(memberships)} membership records for user_id: {user_id}")
    return memberships

@router.post("/upload_receipt_file", response_model=dict)
async def upload_receipt_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) uploading a receipt file")
    
    # Validate file type - only PNG and JPEG allowed
    allowed_types = ['image/png', 'image/jpeg', 'image/jpg']
    if file.content_type.lower() not in allowed_types:
        logger.error(f"Invalid file type uploaded: {file.content_type}")
        raise HTTPException(status_code=400, detail="Only PNG and JPEG images are allowed.")
    
    # Also check file extension as additional validation
    file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    if file_extension not in ['png', 'jpg', 'jpeg']:
        logger.error(f"Invalid file extension: {file_extension}")
        raise HTTPException(status_code=400, detail="Only PNG and JPEG images are allowed.")
    
    # Generate a safe filename
    sanitized_filename = sanitize_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{sanitized_filename}"
    object_key = f"receipts/{unique_filename}"
    
    logger.info(f"Original filename: {file.filename}")
    logger.info(f"Sanitized filename: {sanitized_filename}")
    logger.info(f"Object key: {object_key}")
    
    try:
        file_url = await upload_to_r2(file, object_key)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error uploading receipt file to R2 for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error uploading receipt file")
    
    logger.info(f"User {current_user.id} uploaded receipt file to R2: {file_url}")
    return {"file_path": file_url}

class UpdateReceiptPayload(BaseModel):
    membership_id: int
    payment_type: str
    receipt_path: str

@router.put("/update_receipt", response_model=schemas.MembershipSchema)
def update_receipt(
    payload: UpdateReceiptPayload, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) updating receipt for membership_id: {payload.membership_id}")
    payment_type = payload.payment_type.lower().strip()
    if payment_type not in ["gcash", "paymaya", "cash"]:
        logger.error(f"User {current_user.id} provided invalid payment_type: {payment_type}")
        raise HTTPException(status_code=400, detail="Invalid payment_type. Must be 'gcash', 'paymaya', or 'cash'")
    
    membership = db.query(models.Clearance)\
                   .filter(models.Clearance.id == payload.membership_id,
                           models.Clearance.user_id == current_user.id,
                           models.Clearance.archived == False)\
                   .first()
    if not membership:
        logger.error(f"Membership record not found for id: {payload.membership_id} for user {current_user.id}")
        raise HTTPException(status_code=404, detail="Membership not found")
    
    membership.receipt_path = payload.receipt_path
    membership.payment_status = "Verifying"
    membership.status = "Processing"
    membership.payment_method = payment_type
    membership.payment_date = datetime.datetime.now(pytz.timezone('Asia/Manila'))

    db.commit()
    db.refresh(membership)
    logger.info(f"User {current_user.id} updated receipt for membership_id: {payload.membership_id}")
    return membership

# Officer Endpoints (Membership Management)

@router.get("/officer/list", response_model=List[schemas.MembershipSchema])
def officer_list_membership(
    db: Session = Depends(get_db)
):
    logger.debug("Fetching membership records")
    try:
        memberships = db.query(models.Clearance)\
            .options(joinedload(models.Clearance.user))\
            .filter(models.Clearance.archived == False)\
            .all()
        logger.info(f"Fetched {len(memberships)} membership records")
        return memberships
    except Exception as e:
        logger.error(f"Error fetching membership records: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching membership records: {str(e)}")

@router.post("/officer/create", response_model=schemas.MembershipSchema)
def officer_create_membership(
    user_id: int = Form(...),
    amount: float = Form(...),
    payment_status: str = Form(...),
    requirement: str = Form(...),
    db: Session = Depends(get_db)
):
    logger.debug(f"Creating membership record for user_id: {user_id}")
    # Verify user exists
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        logger.error(f"User with ID {user_id} not found")
        raise HTTPException(status_code=404, detail="User not found")
    
    new_record = models.Clearance(
        user_id=user_id,
        amount=amount,
        payment_status=payment_status,
        requirement=requirement,
        status="Not Yet Cleared",
        receipt_path="",
        archived=False
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    logger.info(f"Membership record {new_record.id} created for user_id: {user_id}")
    return new_record

class VerifyMembershipPayload(BaseModel):
    action: str
    denial_reason: Optional[str] = None

@router.put("/officer/verify/{membership_id}", response_model=schemas.MembershipSchema)
def officer_verify_membership(
    membership_id: int,
    payload: VerifyMembershipPayload = Body(...),
    db: Session = Depends(get_db)
):
    logger.debug(f"Verifying membership record id: {membership_id}")
    action = payload.action
    if action not in ["approve", "deny"]:
        logger.error(f"Invalid action: {action} for membership_id: {membership_id}")
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'deny'.")
    
    membership = db.query(models.Clearance)\
        .filter(models.Clearance.id == membership_id, models.Clearance.archived == False)\
        .first()
    if not membership:
        logger.error(f"Membership record {membership_id} not found")
        raise HTTPException(status_code=404, detail="Membership record not found")
    
    if action == "approve":
        membership.payment_status = "Paid"
        membership.status = "Clear"
        membership.approval_date = datetime.datetime.now(pytz.timezone('Asia/Manila'))
        membership.denial_reason = None
    elif action == "deny":
        membership.payment_status = "Not Paid"
        membership.status = "Not Yet Cleared"
        membership.receipt_path = None
        membership.payment_method = None
        membership.denial_reason = payload.denial_reason
        membership.payment_date = None
    
    db.commit()
    db.refresh(membership)
    logger.info(f"Updated membership record {membership_id} with action {action}")
    return membership

@router.get("/officer/requirements", response_model=List[schemas.MembershipSchema])
def get_officer_requirements(
    db: Session = Depends(get_db)
):
    logger.debug("Fetching membership requirements")
    clearances = db.query(models.Clearance).filter(models.Clearance.archived == False).all()
    grouped = {}
    for c in clearances:
        if c.requirement not in grouped:
            grouped[c.requirement] = c
    result = list(grouped.values())
    logger.info(f"Fetched {len(result)} distinct membership requirements")
    return result

@router.put("/officer/requirements/{requirement}", response_model=schemas.MembershipSchema)
def update_officer_requirement(
    requirement: str, 
    payload: dict = Body(...), 
    db: Session = Depends(get_db)
):
    logger.debug(f"Updating membership requirement: {requirement}")
    records = db.query(models.Clearance).filter(models.Clearance.requirement == requirement, models.Clearance.archived == False).all()
    if not records:
        logger.error(f"Requirement {requirement} not found for update")
        raise HTTPException(status_code=404, detail="Requirement not found")
    for r in records:
        if "amount" in payload:
            r.amount = payload["amount"]
    db.commit()
    logger.info(f"Updated requirement {requirement} successfully")
    return records[0]

@router.delete("/officer/requirements/{requirement}", response_model=schemas.MessageResponse)
def delete_officer_requirement(
    requirement: str, 
    db: Session = Depends(get_db)
):
    logger.debug(f"Archiving membership requirement: {requirement}")
    records = db.query(models.Clearance).filter(models.Clearance.requirement == requirement, models.Clearance.archived == False).all()
    if not records:
        logger.error(f"Requirement {requirement} not found for archiving")
        raise HTTPException(status_code=404, detail="Requirement not found")
    for r in records:
        r.archived = True
    db.commit()
    logger.info(f"Archived requirement {requirement} successfully")
    return {"message": "Requirement archived successfully"}

@router.post("/officer/requirement/create", response_model=schemas.MembershipSchema)
def create_officer_requirement(
    requirement: str = Form(...),
    amount: float = Form(...),
    db: Session = Depends(get_db)
):
    try:
        # Validate requirement value matches Enum
        valid_requirements = ["1st Semester Membership", "2nd Semester Membership"]
        requirement = requirement.strip()
        if requirement not in valid_requirements:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid requirement. Must be one of: {', '.join(valid_requirements)}"
            )
        
        # Validate amount
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be greater than 0")
        
        logger.debug(f"Creating new membership requirement: {requirement} with amount: {amount}")
        users = db.query(models.User).all()
        
        if not users:
            raise HTTPException(status_code=404, detail="No users found in the database")
        
        created_records = []
        for user in users:
            existing = db.query(models.Clearance).filter(
                models.Clearance.user_id == user.id,
                models.Clearance.requirement == requirement,
                models.Clearance.archived == False
            ).first()
            if not existing:
                new_clearance = models.Clearance(
                    user_id=user.id,
                    requirement=requirement,
                    amount=amount,
                    payment_status="Not Paid",
                    status="Not Yet Cleared",
                    receipt_path=None,  # Use None instead of empty string
                    archived=False
                )
                db.add(new_clearance)
                created_records.append(new_clearance)
        
        if not created_records:
            logger.warning(f"Membership requirement '{requirement}' already exists for all users")
            raise HTTPException(status_code=400, detail="Requirement already exists for all users")
        
        db.commit()
        db.refresh(created_records[0])
        logger.info(f"Created membership requirement '{requirement}' for {len(created_records)} users")
        return created_records[0]
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Error creating membership requirement: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create requirement: {str(e)}")

@router.get("/receipt/{membership_id}", response_model=dict)
def get_membership_receipt(
    membership_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get receipt details for a specific membership"""
    logger.debug(f"User {current_user.id} ({current_user.full_name}) fetching receipt for membership_id: {membership_id}")
    
    membership = db.query(models.Clearance)\
        .filter(
            models.Clearance.id == membership_id,
            models.Clearance.user_id == current_user.id,
            models.Clearance.archived == False
        )\
        .first()
    
    if not membership:
        logger.error(f"Membership record not found for id: {membership_id} for user {current_user.id}")
        raise HTTPException(status_code=404, detail="Membership not found")
    
    if not membership.receipt_path:
        logger.error(f"No receipt found for membership_id: {membership_id}")
        raise HTTPException(status_code=404, detail="No receipt found for this membership")
    
    logger.info(f"User {current_user.id} fetched receipt for membership_id: {membership_id}")
    return {
        "receipt_url": membership.receipt_path,
        "payment_method": membership.payment_method,
        "payment_status": membership.payment_status,
        "payment_date": membership.payment_date,
        "approval_date": membership.approval_date
    }