import os
import re
from groq import Groq
from dotenv import load_dotenv
from app.database import SessionLocal
from app import models
import logging
from functools import lru_cache
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Keyword patterns for dynamic context injection
EVENT_KEYWORDS = re.compile(r'\b(event|events|when|where|register|registration|participate|happening|upcoming|schedule)\b', re.IGNORECASE)
OFFICER_KEYWORDS = re.compile(r'\b(officer|officers|president|vice|secretary|treasurer|who|leader|contact|staff)\b', re.IGNORECASE)
CLEARANCE_KEYWORDS = re.compile(r'\b(pay|paid|payment|status|clearance|clear|fee|membership|balance|amount|receipt|gcash|paymaya)\b', re.IGNORECASE)
ANNOUNCEMENT_KEYWORDS = re.compile(r'\b(announcement|announcements|news|update|updates|notice|info|information)\b', re.IGNORECASE)

# Cache raw database queries for 5 minutes (300 seconds)
@lru_cache(maxsize=1)
def fetch_events_raw(_cache_key: int = int(time.time() // 300)):
    """Fetch all active events from the database (raw data without user-specific info)."""
    db = SessionLocal()
    try:
        events = db.query(models.Event).filter(models.Event.archived == False).all()
        return [
            {
                "id": event.id,
                "title": event.title,
                "date": event.date.isoformat(),
                "location": event.location,
                "registration_start": event.registration_start.isoformat() if event.registration_start else None,
                "registration_end": event.registration_end.isoformat() if event.registration_end else None,
                "participant_ids": [p.id for p in event.participants]
            } for event in events
        ]
    except Exception as e:
        logger.error(f"Error fetching events: {str(e)}")
        return []
    finally:
        db.close()

def get_events_for_user(user_id: int):
    """Get events with user-specific participation status."""
    raw_events = fetch_events_raw()
    return [
        {
            "title": event['title'],
            "date": event['date'],
            "location": event['location'],
            "registration_start": event['registration_start'],
            "registration_end": event['registration_end'],
            "is_registered": user_id in event['participant_ids']
        } for event in raw_events
    ]

@lru_cache(maxsize=1)
def fetch_announcements_cached(_cache_key: int = int(time.time() // 300)):
    """Fetch all active announcements from the database."""
    db = SessionLocal()
    try:
        announcements = db.query(models.Announcement).filter(models.Announcement.archived == False).all()
        return [
            {
                "title": announcement.title,
                "date": announcement.date.isoformat(),
                "content": getattr(announcement, 'content', '')[:100] if hasattr(announcement, 'content') else ''
            } for announcement in announcements
        ]
    except Exception as e:
        logger.error(f"Error fetching announcements: {str(e)}")
        return []
    finally:
        db.close()

def fetch_clearances_for_user(user_id: int):
    """Fetch clearance details for a specific user (not cached - user-specific)."""
    db = SessionLocal()
    try:
        clearances = db.query(models.Clearance).filter(
            models.Clearance.user_id == user_id, 
            models.Clearance.archived == False
        ).all()
        return [
            {
                "requirement": c.requirement,
                "amount": c.amount,
                "payment_status": c.payment_status,
                "status": c.status
            } for c in clearances
        ]
    except Exception as e:
        logger.error(f"Error fetching clearances for user {user_id}: {str(e)}")
        return []
    finally:
        db.close()

@lru_cache(maxsize=1)
def fetch_officers_cached(_cache_key: int = int(time.time() // 300)):
    """Fetch all active officers from the database."""
    db = SessionLocal()
    try:
        officers = db.query(models.Officer).filter(models.Officer.archived == False).all()
        return [
            {"name": o.full_name, "position": o.position} for o in officers
        ]
    except Exception as e:
        logger.error(f"Error fetching officers: {str(e)}")
        return []
    finally:
        db.close()

def build_context(user_query: str, user_id: int) -> str:
    """Build context string based on user query keywords - only fetch what's needed."""
    context_parts = []
    
    # Check for event-related queries
    if EVENT_KEYWORDS.search(user_query):
        events = get_events_for_user(user_id)
        if events:
            events_str = "\n".join([
                f"- {e['title']} on {e['date']} at {e['location']} (Registered: {'Yes' if e['is_registered'] else 'No'})"
                for e in events[:5]  # Limit to 5 events
            ])
            context_parts.append(f"**Events:**\n{events_str}")
    
    # Check for announcement-related queries
    if ANNOUNCEMENT_KEYWORDS.search(user_query):
        announcements = fetch_announcements_cached()
        if announcements:
            ann_str = "\n".join([
                f"- {a['title']} ({a['date']})"
                for a in announcements[:5]  # Limit to 5
            ])
            context_parts.append(f"**Announcements:**\n{ann_str}")
    
    # Check for clearance/payment-related queries
    if CLEARANCE_KEYWORDS.search(user_query):
        clearances = fetch_clearances_for_user(user_id)
        if clearances:
            clear_str = "\n".join([
                f"- {c['requirement']}: ₱{c['amount']} - {c['payment_status']} ({c['status']})"
                for c in clearances
            ])
            context_parts.append(f"**Your Clearances:**\n{clear_str}")
        else:
            context_parts.append("**Your Clearances:** No pending clearances.")
    
    # Check for officer-related queries
    if OFFICER_KEYWORDS.search(user_query):
        officers = fetch_officers_cached()
        if officers:
            off_str = "\n".join([f"- {o['name']}: {o['position']}" for o in officers])
            context_parts.append(f"**Officers:**\n{off_str}")
    
    return "\n\n".join(context_parts) if context_parts else ""

def get_chat_response(user_query: str, user_id: int) -> str:
    """
    Generates a response using Groq API with dynamic context injection.
    Only fetches data relevant to the user's query to save tokens.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY not set")
        return "Error: Chat service unavailable."
    
    # Build dynamic context based on query
    context = build_context(user_query, user_id)
    
    # Optimized short system prompt
    system_prompt = (
        "You are SPECS Nexus Bot, a helpful assistant for SPECS (Society of Programming Enthusiasts in Computer Science) "
        "at Gordon College. Answer questions about events, announcements, membership clearances, and officers. "
        "Be concise and friendly. Use bullet points for lists."
    )
    
    # Build user message with context
    user_message = user_query
    if context:
        user_message = f"Relevant Data:\n{context}\n\nUser Question: {user_query}"
    
    # Log token savings
    logger.info(f"Query: '{user_query[:50]}...' | Context injected: {'Yes' if context else 'No'}")
    
    # Initialize Groq client
    client = Groq(api_key=api_key)
    
    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Fast and free
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=300,
            temperature=0.7,
        )
        response_time = time.time() - start_time
        logger.info(f"Groq response in {response_time:.2f}s")
        return response.choices[0].message.content.strip()
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Groq API error: {str(e)}")
        if "rate" in error_msg:
            return "I'm currently busy. Please try again in a moment."
        return "Sorry, I couldn't process your request. Please try again."