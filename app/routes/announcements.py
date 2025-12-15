import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
import boto3
from botocore.client import Config
import os
import uuid

from app.database import SessionLocal
from app import models, schemas
from app.auth_utils import get_current_user

logger = logging.getLogger("app.announcements")

router = APIRouter(prefix="/announcements", tags=["Announcements"])

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

async def upload_to_r2(file: UploadFile, object_key: str):
    try:
        access_key = os.getenv("CF_ACCESS_KEY_ID")
        secret_key = os.getenv("CF_SECRET_ACCESS_KEY")
        bucket_name = os.getenv("CLOUDFLARE_R2_BUCKET")
        endpoint_url = os.getenv("CLOUDFLARE_R2_ENDPOINT")
        
        worker_url = os.getenv("CLOUDFLARE_WORKER_URL", "https://specsnexus-images.senya-videos.workers.dev")
        
        logger.info(f"R2 Credentials - Access Key: {'Available' if access_key else 'Missing'}")
        logger.info(f"R2 Credentials - Secret Key: {'Available' if secret_key else 'Missing'}")
        logger.info(f"R2 Credentials - Bucket: {bucket_name or 'Missing'}")
        logger.info(f"R2 Credentials - Endpoint: {endpoint_url or 'Missing'}")
        logger.info(f"R2 Credentials - Worker URL: {worker_url or 'Missing'}")
        
        if not all([access_key, secret_key, bucket_name, endpoint_url, worker_url]):
            raise ValueError("Missing R2 credentials or configuration")
        
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url
        )
        
        logger.info(f"Uploading file to R2: {object_key}")
        s3.upload_fileobj(file.file, bucket_name, object_key)
        
        if worker_url.endswith('/'):
            file_url = f"{worker_url}{object_key}"
        else:
            file_url = f"{worker_url}/{object_key}"
            
        logger.info(f"File uploaded successfully: {file_url}")
        return file_url
        
    except Exception as e:
        logger.error(f"Error uploading file to R2: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

# Endpoint: GET /announcements/
# Description: Returns a list of non-archived announcements for authenticated users.
@router.get("/", response_model=List[schemas.AnnouncementSchema])
def get_announcements(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    logger.debug(f"User {current_user.id} ({current_user.full_name}) fetching non-archived announcements")
    announcements = db.query(models.Announcement).filter(models.Announcement.archived == False).all()
    logger.info(f"User {current_user.id} fetched {len(announcements)} announcements")
    return announcements

# Endpoint: GET /announcements/officer/list
# Description: Fetches a list of announcements, with an option to include archived ones.
@router.get("/officer/list", response_model=List[schemas.AnnouncementSchema])
def admin_list_announcements(
    archived: bool = False,
    db: Session = Depends(get_db)
):
    logger.debug(f"Fetching announcements with archived={archived}")
    announcements = db.query(models.Announcement).filter(models.Announcement.archived == archived).all()
    logger.info(f"Fetched {len(announcements)} announcements with archived={archived}")
    return announcements

# Endpoint: POST /announcements/officer/create
# Description: Creates a new announcement. An image can be optionally uploaded to R2.
@router.post("/officer/create", response_model=schemas.AnnouncementSchema)
async def admin_create_announcement(
    title: str = Form(...),
    description: str = Form(...),
    date: datetime = Form(...),
    location: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    logger.debug(f"Creating announcement with title: {title}")
    
    image_url = None
    if image and image.filename:
        filename = f"{uuid.uuid4()}-{image.filename}"
        object_key = f"announcement_images/{filename}"
        image_url = await upload_to_r2(image, object_key)
        logger.debug(f"Uploaded announcement image to R2: {image_url}")
    
    new_announcement = models.Announcement(
        title=title,
        description=description,
        date=date,
        location=location,
        image_url=image_url,
        archived=False
    )
    db.add(new_announcement)
    db.commit()
    db.refresh(new_announcement)
    logger.info(f"Created announcement successfully with id: {new_announcement.id}")
    return new_announcement

# Endpoint: PUT /announcements/officer/update/{announcement_id}
# Description: Updates an existing announcement, including its image in R2.
@router.put("/officer/update/{announcement_id}", response_model=schemas.AnnouncementSchema)
async def admin_update_announcement(
    announcement_id: int,
    title: str = Form(...),
    description: str = Form(...),
    date: datetime = Form(...),
    location: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    logger.debug(f"Updating announcement id: {announcement_id}")
    announcement = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not announcement:
        logger.error(f"Announcement {announcement_id} not found for update")
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    if image and image.filename:
        filename = f"{uuid.uuid4()}-{image.filename}"
        object_key = f"announcement_images/{filename}"
        announcement.image_url = await upload_to_r2(image, object_key)
        logger.debug(f"Updated announcement image in R2: {announcement.image_url}")
    
    announcement.title = title
    announcement.description = description
    announcement.date = date
    announcement.location = location
    db.commit()
    db.refresh(announcement)
    logger.info(f"Updated announcement {announcement_id} successfully")
    return announcement

# Endpoint: DELETE /announcements/officer/delete/{announcement_id}
# Description: Archives an announcement.
@router.delete("/officer/delete/{announcement_id}", response_model=dict)
def admin_delete_announcement(
    announcement_id: int,
    db: Session = Depends(get_db)
):
    logger.debug(f"Attempting to archive announcement id: {announcement_id}")
    announcement = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not announcement:
        logger.error(f"Announcement {announcement_id} not found for deletion")
        raise HTTPException(status_code=404, detail="Announcement not found")
    announcement.archived = True
    db.commit()
    logger.info(f"Archived announcement {announcement_id} successfully")
    return {"detail": "Announcement archived successfully"}