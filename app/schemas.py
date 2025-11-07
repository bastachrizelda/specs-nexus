from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    student_number: Optional[str] = None
    full_name: Optional[str] = None
    year: Optional[str] = None
    block: Optional[str] = None

class UserLogin(BaseModel):
    email_or_student_number: str
    password: str

class UserInfo(BaseModel):
    full_name: str
    block: Optional[str] = None
    year: Optional[str] = None

    class Config:
        from_attributes = True

class UpdateUser(BaseModel):
    full_name: Optional[str] = None
    year: Optional[str] = None
    block: Optional[str] = None

    class Config:
        from_attributes = True

class ECertificateSchema(BaseModel):
    id: int
    user_id: int
    event_id: int
    certificate_url: str
    thumbnail_url: Optional[str] = None  # Add this field
    file_name: str
    issued_date: datetime
    event_title: str

    class Config:
        orm_mode = True

class User(BaseModel):
    id: int
    email: str
    student_number: Optional[str] = None
    full_name: Optional[str] = None
    year: Optional[str] = None
    block: Optional[str] = None
    last_active: Optional[datetime] = None
    participated_events: Optional[List["EventSchema"]] = None
    certificates: Optional[List[ECertificateSchema]] = None

    class Config:
        from_attributes = True

class ClearanceSchema(BaseModel):
    requirement: str
    status: str

    class Config:
        from_attributes = True

class MembershipSchema(BaseModel):
    id: int
    receipt_path: Optional[str] = None
    status: str
    payment_status: str
    requirement: str
    amount: Optional[float] = None
    qr_code_url: Optional[str] = None
    archived: bool
    user: Optional[UserInfo] = None
    payment_method: Optional[str] = None
    denial_reason: Optional[str] = None
    payment_date: Optional[datetime] = None
    approval_date: Optional[datetime] = None

    class Config:
        from_attributes = True
        use_enum_values = True

class EventSchema(BaseModel):
    id: int
    title: str
    description: str
    date: datetime
    image_url: Optional[str]
    location: Optional[str] = None
    participant_count: int
    registration_start: Optional[datetime] = None
    registration_end: Optional[datetime] = None
    registration_open: bool
    registration_status: str
    is_participant: Optional[bool] = False

    class Config:
        from_attributes = True

class AnnouncementSchema(BaseModel):
    id: int
    title: str
    description: str
    image_url: Optional[str] = None
    location: Optional[str] = None
    date: Optional[datetime] = None

    class Config:
        from_attributes = True

class OfficerLoginSchema(BaseModel):
    email: EmailStr
    password: str

class OfficerSchema(BaseModel):
    id: int
    email: EmailStr
    student_number: str
    full_name: str
    year: str
    block: str
    position: str

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    officer: OfficerSchema

class MessageResponse(BaseModel):
    message: str