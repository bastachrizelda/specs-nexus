import logging
import os
import uuid
import secrets
import string
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Dict, Optional, Tuple
import requests
from PIL import Image, ImageDraw, ImageFont
import qrcode
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app import models

logger = logging.getLogger("app.certificate_service")


def generate_certificate_code() -> str:
    """Generate a unique certificate verification code."""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(secrets.choice(chars) for _ in range(12))
    return f"SPECS-{code[:4]}-{code[4:8]}-{code[8:]}"


def sanitize_event_title(title: str) -> str:
    """Sanitize event title for use in filenames."""
    import re
    sanitized = re.sub(r'[^\w\s-]', '', title)
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    return sanitized[:50]


def download_template(template_url: str) -> Image.Image:
    """Download certificate template from URL and return as PIL Image."""
    try:
        response = requests.get(template_url, timeout=30)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        return img
    except Exception as e:
        logger.error(f"Failed to download template from {template_url}: {str(e)}")
        raise ValueError(f"Could not download certificate template: {str(e)}")


def get_font(font_family: str, font_size: int, font_weight: str = "400") -> ImageFont.FreeTypeFont:
    """Get font for certificate rendering. Falls back to default if specified font not available."""
    try:
        # Map font families and weights to system fonts
        if font_family.lower() in ['arial', 'arial.ttf']:
            if font_weight == "700":
                return ImageFont.truetype("arialbd.ttf", font_size)
            return ImageFont.truetype("arial.ttf", font_size)
        elif font_family.lower() in ['times', 'times new roman', 'times.ttf']:
            if font_weight == "700":
                return ImageFont.truetype("timesbd.ttf", font_size)
            return ImageFont.truetype("times.ttf", font_size)
        elif font_family.lower() == 'georgia':
            if font_weight == "700":
                return ImageFont.truetype("georgiab.ttf", font_size)
            return ImageFont.truetype("georgia.ttf", font_size)
        elif font_family.lower() == 'verdana':
            if font_weight == "700":
                return ImageFont.truetype("verdanab.ttf", font_size)
            return ImageFont.truetype("verdana.ttf", font_size)
        elif font_family.lower() in ['poppins', 'montserrat']:
            # Fallback to Arial Bold for web fonts
            if font_weight == "700":
                return ImageFont.truetype("arialbd.ttf", font_size)
            return ImageFont.truetype("arial.ttf", font_size)
        else:
            return ImageFont.truetype(font_family, font_size)
    except Exception as e:
        logger.warning(f"Could not load font {font_family}, using default: {str(e)}")
        try:
            if font_weight == "700":
                return ImageFont.truetype("arialbd.ttf", font_size)
            return ImageFont.truetype("arial.ttf", font_size)
        except:
            return ImageFont.load_default()


def auto_scale_text(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, 
                     max_width: int, min_font_size: int = 24) -> Tuple[ImageFont.FreeTypeFont, str]:
    """Auto-scale font size or wrap text to fit within max_width."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    
    if text_width <= max_width:
        return font, text
    
    current_size = font.size
    while current_size > min_font_size:
        current_size -= 2
        try:
            scaled_font = ImageFont.truetype(font.path, current_size)
        except:
            scaled_font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), text, font=scaled_font)
        text_width = bbox[2] - bbox[0]
        
        if text_width <= max_width:
            return scaled_font, text
    
    return font, text


def render_certificate(
    template: Image.Image,
    full_name: str,
    certificate_code: str,
    name_x: int,
    name_y: int,
    font_size: int,
    font_color: str,
    font_family: str,
    font_weight: str = "400",
    add_qr: bool = True
) -> Image.Image:
    """Render a personalized certificate on the template."""
    cert_img = template.copy()
    draw = ImageDraw.Draw(cert_img)
    
    font = get_font(font_family, font_size, font_weight)
    
    max_width = int(cert_img.width * 0.6)
    font, full_name = auto_scale_text(draw, full_name, font, max_width)
    
    bbox = draw.textbbox((0, 0), full_name, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    centered_x = name_x - (text_width // 2)
    centered_y = name_y - (text_height // 2)
    
    draw.text((centered_x, centered_y), full_name, fill=font_color, font=font)
    
    code_font_size = max(16, font_size // 3)
    code_font = get_font(font_family, code_font_size, "400")
    code_y = cert_img.height - 80
    code_bbox = draw.textbbox((0, 0), certificate_code, font=code_font)
    code_width = code_bbox[2] - code_bbox[0]
    code_x = (cert_img.width - code_width) // 2
    draw.text((code_x, code_y), certificate_code, fill="#666666", font=code_font)
    
    if add_qr:
        try:
            qr = qrcode.QRCode(version=1, box_size=3, border=1)
            qr.add_data(certificate_code)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_img = qr_img.resize((80, 80))
            qr_x = cert_img.width - 100
            qr_y = cert_img.height - 100
            cert_img.paste(qr_img, (qr_x, qr_y))
        except Exception as e:
            logger.warning(f"Could not add QR code: {str(e)}")
    
    return cert_img


def get_eligible_users(db: Session, event_id: int) -> List[models.User]:
    """
    Get all users eligible for certificate generation for an event.
    
    Eligibility rules:
    - User is in event_participants
    - Event is not archived
    - User has checked_in_at OR evaluation_completed = TRUE in event_attendance
    - User does NOT already have a certificate for this event
    """
    event = db.query(models.Event).filter(
        models.Event.id == event_id,
        models.Event.archived == False
    ).first()
    
    if not event:
        raise ValueError(f"Event {event_id} not found or is archived")
    
    eligible_attendance = db.query(models.EventAttendance).filter(
        models.EventAttendance.event_id == event_id,
        or_(
            models.EventAttendance.checked_in_at.isnot(None),
            models.EventAttendance.evaluation_completed == True
        )
    ).all()
    
    eligible_user_ids = {att.user_id for att in eligible_attendance}
    
    if not eligible_user_ids:
        return []
    
    existing_cert_user_ids = {
        cert.user_id for cert in 
        db.query(models.ECertificate.user_id).filter(
            models.ECertificate.event_id == event_id
        ).all()
    }
    
    new_eligible_user_ids = eligible_user_ids - existing_cert_user_ids
    
    if not new_eligible_user_ids:
        return []
    
    users = db.query(models.User).filter(
        models.User.id.in_(new_eligible_user_ids)
    ).all()
    
    return users


def generate_certificate_filename(event_title: str, full_name: str) -> str:
    """Generate standardized certificate filename."""
    sanitized_title = sanitize_event_title(event_title)
    sanitized_name = sanitize_event_title(full_name)
    return f"SpecsNexus_{sanitized_title}_{sanitized_name}.pdf"


def certificate_to_pdf_bytes(cert_img: Image.Image) -> BytesIO:
    """Convert PIL Image to PDF bytes."""
    pdf_buffer = BytesIO()
    cert_img.save(pdf_buffer, format='PDF', resolution=100.0)
    pdf_buffer.seek(0)
    return pdf_buffer
