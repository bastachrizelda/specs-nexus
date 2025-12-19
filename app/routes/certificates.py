import logging
import os
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Optional
import boto3
from botocore.client import Config
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app import models, schemas
from app.auth_utils import get_current_user, get_current_officer
from app.certificate_service import (
    generate_certificate_code,
    download_template,
    render_certificate,
    get_eligible_users,
    generate_certificate_filename,
    certificate_to_pdf_bytes,
)

logger = logging.getLogger("app.certificates")
router = APIRouter(prefix="/certificates", tags=["Certificates"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


access_key_id = os.getenv('CF_ACCESS_KEY_ID')
secret_access_key = os.getenv('CF_SECRET_ACCESS_KEY')
bucket_name = os.getenv('CLOUDFLARE_R2_BUCKET')
endpoint_url = os.getenv('CLOUDFLARE_R2_ENDPOINT')
worker_url = os.getenv('CLOUDFLARE_WORKER_URL', 'https://specsnexus-images.senya-videos.workers.dev')

s3 = boto3.client(
    's3',
    endpoint_url=endpoint_url,
    aws_access_key_id=access_key_id,
    aws_secret_access_key=secret_access_key,
    config=Config(signature_version='s3v4'),
    region_name='auto'
)


async def upload_certificate_to_r2(pdf_buffer: BytesIO, object_key: str) -> str:
    """Upload certificate PDF to Cloudflare R2 and return public URL."""
    try:
        s3.upload_fileobj(pdf_buffer, bucket_name, object_key)
        if worker_url.endswith('/'):
            file_url = f"{worker_url}{object_key}"
        else:
            file_url = f"{worker_url}/{object_key}"
        logger.info(f"Certificate uploaded to R2: {file_url}")
        return file_url
    except Exception as e:
        logger.error(f"Failed to upload certificate to R2: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload certificate: {str(e)}")


@router.post("/events/{event_id}/template", response_model=schemas.CertificateTemplateSchema)
async def create_or_update_certificate_template(
    event_id: int,
    template_file: UploadFile = File(...),
    name_x: int = Form(...),
    name_y: int = Form(...),
    font_size: int = Form(48),
    font_color: str = Form("#000000"),
    font_family: str = Form("Arial"),
    font_weight: str = Form("400"),
    db: Session = Depends(get_db),
    current_officer: models.Officer = Depends(get_current_officer)
):
    """Create or update certificate template for an event (Officer only)."""
    logger.debug(f"Officer {current_officer.id} creating/updating certificate template for event {event_id}")
    
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    filename = f"{uuid.uuid4()}-{template_file.filename}"
    object_key = f"certificate_templates/{filename}"
    
    try:
        s3.upload_fileobj(template_file.file, bucket_name, object_key)
        if worker_url.endswith('/'):
            template_url = f"{worker_url}{object_key}"
        else:
            template_url = f"{worker_url}/{object_key}"
    except Exception as e:
        logger.error(f"Failed to upload template: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload template")
    
    existing_template = db.query(models.CertificateTemplate).filter(
        models.CertificateTemplate.event_id == event_id
    ).first()
    
    if existing_template:
        existing_template.template_url = template_url
        existing_template.name_x = name_x
        existing_template.name_y = name_y
        existing_template.font_size = font_size
        existing_template.font_color = font_color
        existing_template.font_family = font_family
        existing_template.font_weight = font_weight
        existing_template.archived = False
        db.commit()
        db.refresh(existing_template)
        logger.info(f"Updated certificate template for event {event_id}")
        return existing_template
    else:
        new_template = models.CertificateTemplate(
            event_id=event_id,
            template_url=template_url,
            name_x=name_x,
            name_y=name_y,
            font_size=font_size,
            font_color=font_color,
            font_family=font_family,
            font_weight=font_weight,
            archived=False
        )
        db.add(new_template)
        db.commit()
        db.refresh(new_template)
        logger.info(f"Created certificate template for event {event_id}")
        return new_template


@router.get("/events/{event_id}/template", response_model=Optional[schemas.CertificateTemplateSchema])
def get_certificate_template(
    event_id: int,
    db: Session = Depends(get_db),
    current_officer: models.Officer = Depends(get_current_officer)
):
    """Get certificate template for an event (Officer only)."""
    template = db.query(models.CertificateTemplate).filter(
        models.CertificateTemplate.event_id == event_id,
        models.CertificateTemplate.archived == False
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="No certificate template found for this event")
    
    return template


@router.post("/events/{event_id}/generate-bulk")
async def generate_bulk_certificates(
    event_id: int,
    db: Session = Depends(get_db),
    current_officer: models.Officer = Depends(get_current_officer)
):
    """
    Generate certificates for all eligible participants of an event.
    
    Idempotent: Safe to re-run, will only generate for users who don't have certificates yet.
    """
    logger.info(f"Officer {current_officer.id} initiating bulk certificate generation for event {event_id}")
    
    event = db.query(models.Event).filter(
        models.Event.id == event_id,
        models.Event.archived == False
    ).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Event not found or is archived")
    
    template = db.query(models.CertificateTemplate).filter(
        models.CertificateTemplate.event_id == event_id,
        models.CertificateTemplate.archived == False
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=400,
            detail="No active certificate template found for this event. Please upload a template first."
        )
    
    try:
        eligible_users = get_eligible_users(db, event_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not eligible_users:
        return {
            "message": "No eligible users found for certificate generation",
            "generated_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "eligible_user_ids": []
        }
    
    logger.info(f"Found {len(eligible_users)} eligible users for certificate generation")
    
    try:
        template_img = download_template(template.template_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load certificate template: {str(e)}")
    
    generated_count = 0
    failed_count = 0
    failed_users = []
    
    for user in eligible_users:
        try:
            cert_code = generate_certificate_code()
            
            while db.query(models.ECertificate).filter(
                models.ECertificate.certificate_code == cert_code
            ).first():
                cert_code = generate_certificate_code()
            
            cert_img = render_certificate(
                template=template_img,
                full_name=user.full_name,
                certificate_code=cert_code,
                name_x=template.name_x,
                name_y=template.name_y,
                font_size=template.font_size,
                font_color=template.font_color,
                font_family=template.font_family,
                font_weight=template.font_weight,
                add_qr=True
            )
            
            pdf_buffer = certificate_to_pdf_bytes(cert_img)
            
            filename = generate_certificate_filename(event.title, user.full_name)
            object_key = f"certificates/{event_id}/{uuid.uuid4().hex}_{filename}"
            
            certificate_url = await upload_certificate_to_r2(pdf_buffer, object_key)
            
            manila_tz = timezone(timedelta(hours=8))
            new_certificate = models.ECertificate(
                user_id=user.id,
                event_id=event_id,
                certificate_url=certificate_url,
                thumbnail_url=None,
                file_name=filename,
                issued_date=datetime.now(manila_tz).replace(tzinfo=None),
                certificate_code=cert_code
            )
            db.add(new_certificate)
            db.commit()
            
            generated_count += 1
            logger.info(f"Generated certificate for user {user.id} ({user.full_name})")
            
        except Exception as e:
            failed_count += 1
            failed_users.append({"user_id": user.id, "full_name": user.full_name, "error": str(e)})
            logger.error(f"Failed to generate certificate for user {user.id}: {str(e)}")
            db.rollback()
            continue
    
    logger.info(f"Bulk generation complete: {generated_count} generated, {failed_count} failed")
    
    return {
        "message": f"Bulk certificate generation completed",
        "generated_count": generated_count,
        "failed_count": failed_count,
        "failed_users": failed_users,
        "eligible_user_ids": [u.id for u in eligible_users]
    }


@router.get("/verify/{certificate_code}")
def verify_certificate(certificate_code: str, db: Session = Depends(get_db)):
    """Public endpoint to verify a certificate by its code."""
    certificate = db.query(models.ECertificate).filter(
        models.ECertificate.certificate_code == certificate_code
    ).first()
    
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    event = db.query(models.Event).filter(models.Event.id == certificate.event_id).first()
    user = db.query(models.User).filter(models.User.id == certificate.user_id).first()
    
    return {
        "valid": True,
        "certificate_code": certificate.certificate_code,
        "recipient_name": user.full_name if user else "Unknown",
        "event_title": event.title if event else "Unknown Event",
        "issued_date": certificate.issued_date,
        "certificate_url": certificate.certificate_url
    }


@router.get("/download/{certificate_id}")
async def download_certificate(
    certificate_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Download a single certificate (user must own it)."""
    certificate = db.query(models.ECertificate).filter(
        models.ECertificate.id == certificate_id,
        models.ECertificate.user_id == current_user.id
    ).first()
    
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found or not authorized")
    
    return JSONResponse(content={
        "certificate_url": certificate.certificate_url,
        "file_name": certificate.file_name
    })


@router.get("/events/{event_id}/download-all")
async def download_all_certificates_zip(
    event_id: int,
    db: Session = Depends(get_db),
    current_officer: models.Officer = Depends(get_current_officer)
):
    """Download all certificates for an event as a ZIP file (Officer only)."""
    logger.info(f"Officer {current_officer.id} downloading all certificates for event {event_id}")
    
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    certificates = db.query(models.ECertificate).filter(
        models.ECertificate.event_id == event_id
    ).all()
    
    if not certificates:
        raise HTTPException(status_code=404, detail="No certificates found for this event")
    
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for cert in certificates:
            try:
                if cert.certificate_url.startswith(worker_url):
                    object_key = cert.certificate_url[len(worker_url):].lstrip('/')
                else:
                    object_key = cert.certificate_url.split('/')[-1]
                
                response = s3.get_object(Bucket=bucket_name, Key=object_key)
                pdf_data = response['Body'].read()
                
                zip_file.writestr(cert.file_name, pdf_data)
                logger.debug(f"Added {cert.file_name} to ZIP")
                
            except Exception as e:
                logger.error(f"Failed to add certificate {cert.id} to ZIP: {str(e)}")
                continue
    
    zip_buffer.seek(0)
    
    from app.certificate_service import sanitize_event_title
    zip_filename = f"Certificates_{sanitize_event_title(event.title)}.zip"
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )


@router.get("/events/{event_id}/eligible-count")
def get_eligible_count(
    event_id: int,
    db: Session = Depends(get_db),
    current_officer: models.Officer = Depends(get_current_officer)
):
    """Get count of eligible users for certificate generation (Officer only)."""
    try:
        eligible_users = get_eligible_users(db, event_id)
        return {
            "event_id": event_id,
            "eligible_count": len(eligible_users),
            "eligible_user_ids": [u.id for u in eligible_users]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
