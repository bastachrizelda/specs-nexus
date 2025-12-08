from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Table, Enum, Boolean
import enum
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime, timezone

year_enum = Enum('1st Year', '2nd Year', '3rd Year', '4th Year', name='year_enum')

class EventApprovalStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    declined = "declined"

event_participants = Table(
    "event_participants",
    Base.metadata,
    Column("event_id", Integer, ForeignKey("events.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True)
)

class ECertificate(Base):
    __tablename__ = "certificates"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_id = Column(Integer, ForeignKey("events.id"))
    certificate_url = Column(String(255))
    thumbnail_url = Column(String(255), nullable=True)  # Updated to include length
    file_name = Column(String(255))
    issued_date = Column(DateTime)
    event = relationship("Event", back_populates="certificates")
    user = relationship("User", back_populates="certificates")
    
    @property
    def event_title(self):
        """Get event title from the relationship"""
        return self.event.title if self.event else None

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    password = Column(String(255))
    student_number = Column(String(50), unique=True, index=True)
    full_name = Column(String(255))
    year = Column(year_enum, nullable=True)
    block = Column(String(50))
    last_active = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    events_joined = relationship("Event", secondary=event_participants, back_populates="participants")
    clearance = relationship("Clearance", back_populates="user", uselist=False)
    certificates = relationship("ECertificate", back_populates="user")

class Clearance(Base):
    __tablename__ = "clearances"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    requirement = Column(Enum("1st Semester Membership", "2nd Semester Membership", name="clearance_requirement"), nullable=False)
    status = Column(Enum("Clear", "Processing", "Not Yet Cleared", name="clearance_status"), default="Not Yet Cleared", nullable=False)
    payment_status = Column(Enum("Not Paid", "Verifying", "Paid", name="payment_status"), default="Not Paid", nullable=False)
    receipt_path = Column(String(255), nullable=True)
    amount = Column(Float)
    archived = Column(Boolean, default=False)
    payment_method = Column(String(50), nullable=True)
    denial_reason = Column(String(500), nullable=True)
    payment_date = Column(DateTime, nullable=True)
    approval_date = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    user = relationship("User", back_populates="clearance")

class QRCode(Base):
    __tablename__ = "qr_codes"
    id = Column(Integer, primary_key=True, index=True)
    gcash = Column(String(255), nullable=True)
    paymaya = Column(String(255), nullable=True)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(String(1000))
    date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    image_url = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    archived = Column(Boolean, default=False)
    registration_start = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    registration_end = Column(DateTime, nullable=True)
    approval_status = Column(Enum(EventApprovalStatus, name='event_approval_status'), default=EventApprovalStatus.pending, nullable=True)
    decline_reason = Column(String(500), nullable=True)
    participants = relationship("User", secondary=event_participants, back_populates="events_joined")
    certificates = relationship("ECertificate", back_populates="event")

    @property
    def participant_count(self):
        return len(self.participants) if self.participants else 0

    @property
    def registration_open(self):
        now = datetime.now(timezone.utc)
        if self.registration_start:
            # Make registration_start timezone-aware if it's naive
            reg_start = self.registration_start
            if reg_start.tzinfo is None:
                reg_start = reg_start.replace(tzinfo=timezone.utc)
            if now < reg_start:
                return False
        if self.registration_end:
            # Make registration_end timezone-aware if it's naive
            reg_end = self.registration_end
            if reg_end.tzinfo is None:
                reg_end = reg_end.replace(tzinfo=timezone.utc)
            if now > reg_end:
                return False
        return True

    @property
    def registration_status(self):
        now = datetime.now(timezone.utc)
        if self.registration_start:
            # Make registration_start timezone-aware if it's naive
            reg_start = self.registration_start
            if reg_start.tzinfo is None:
                reg_start = reg_start.replace(tzinfo=timezone.utc)
            if now < reg_start:
                return "not_started"
        if self.registration_end:
            # Make registration_end timezone-aware if it's naive
            reg_end = self.registration_end
            if reg_end.tzinfo is None:
                reg_end = reg_end.replace(tzinfo=timezone.utc)
            if now > reg_end:
                return "closed"
        return "open"

class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    description = Column(String(1000))
    image_url = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    date = Column(DateTime, nullable=True)
    archived = Column(Boolean, default=False)

class Officer(Base):
    __tablename__ = "officers"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    student_number = Column(String(50), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    year = Column(String(50))
    block = Column(String(50))
    position = Column(String(255))
    archived = Column(Boolean, default=False)