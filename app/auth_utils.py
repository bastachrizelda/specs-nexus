import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from app.database import SessionLocal
from sqlalchemy.orm import Session
from app import models
import logging

logger = logging.getLogger(__name__)

SECRET_KEY = "cybercats"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_student_number(db: Session, student_number: str):
    return db.query(models.User).filter(models.User.student_number == student_number).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Created access token for data: {data} with expiration: {expire}")
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user = get_user_by_id(db, int(user_id))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_officer(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Officer:
    logger.debug(f"Token received: {token}")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        officer_id = payload.get("sub")
        logger.debug(f"Decoded officer id: {officer_id}")
        if officer_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except jwt.PyJWTError as e:
        logger.error("Token decoding failed", exc_info=e)
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    officer = db.query(models.Officer).filter(models.Officer.id == int(officer_id), models.Officer.archived == False).first()
    if officer is None:
        logger.error("Officer not found or archived")
        raise HTTPException(status_code=401, detail="Officer not found")
    
    logger.debug(f"Authenticated Officer: {officer.id} - {officer.full_name}")
    return officer

def admin_required(officer = Depends(get_current_officer)):
    if not officer or officer.position.lower() != "admin":
        raise HTTPException(status_code=403, detail="Only admin officers can access this resource.")
    return officer