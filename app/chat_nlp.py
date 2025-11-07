import os
from openai import OpenAI
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

# Cache database queries for 5 minutes (300 seconds)
@lru_cache(maxsize=128)
def fetch_events_cached(_cache_key: int = int(time.time() // 300)):
    """Fetch all active events from the database with participation status."""
    db = SessionLocal()
    try:
        events = db.query(models.Event).filter(models.Event.archived == False).all()
        current_user_id = getattr(db.query(models.User).filter_by(id=1).first(), 'id', None)  # Example user ID; adjust dynamically
        return [
            {
                "title": event.title,
                "date": event.date.isoformat(),
                "location": event.location,
                "registration_start": event.registration_start.isoformat() if event.registration_start else None,
                "registration_end": event.registration_end.isoformat() if event.registration_end else None,
                "is_participant": any(participant.id == current_user_id for participant in event.participants)
            } for event in events
        ]
    except Exception as e:
        logger.error(f"Error fetching events: {str(e)}")
        return f"Error fetching events"
    finally:
        db.close()

@lru_cache(maxsize=128)
def fetch_announcements_cached(_cache_key: int = int(time.time() // 300)):
    """Fetch all active announcements from the database."""
    db = SessionLocal()
    try:
        announcements = db.query(models.Announcement).filter(models.Announcement.archived == False).all()
        return [
            {
                "title": announcement.title,
                "date": announcement.date.isoformat(),
                "location": announcement.location
            } for announcement in announcements
        ]
    except Exception as e:
        logger.error(f"Error fetching announcements: {str(e)}")
        return f"Error fetching announcements"
    finally:
        db.close()

@lru_cache(maxsize=128)
def fetch_clearances_cached(user_id: int, _cache_key: int = int(time.time() // 300)):
    """Fetch clearance details for a user from the database."""
    db = SessionLocal()
    try:
        clearances = db.query(models.Clearance).filter(models.Clearance.user_id == user_id, models.Clearance.archived == False).all()
        return [
            {
                "requirement": clearance.requirement,
                "amount": clearance.amount,
                "payment_status": clearance.payment_status,
                "status": clearance.status,
                "payment_method": clearance.payment_method,
                "payment_date": clearance.payment_date.isoformat() if clearance.payment_date else None,
                "approval_date": clearance.approval_date.isoformat() if clearance.approval_date else None,
                "denial_reason": clearance.denial_reason
            } for clearance in clearances
        ]
    except Exception as e:
        logger.error(f"Error fetching clearances for user {user_id}: {str(e)}")
        return f"Error fetching clearances"
    finally:
        db.close()

@lru_cache(maxsize=128)
def fetch_officers_cached(_cache_key: int = int(time.time() // 300)):
    """Fetch all active officers from the database."""
    db = SessionLocal()
    try:
        officers = db.query(models.Officer).filter(models.Officer.archived == False).all()
        return [
            {"full_name": officer.full_name, "position": officer.position} for officer in officers
        ]
    except Exception as e:
        logger.error(f"Error fetching officers: {str(e)}")
        return f"Error fetching officers"
    finally:
        db.close()

def get_chat_response(user_query: str, user_id: int) -> str:
    """
    Generates a response to a user query using OpenRouter's Llama 3.3 8B Instruct model.
    Args:
        user_query (str): The user's input query.
        user_id (int): The ID of the user making the query.
    Returns:
        str: The generated response or an error message.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    logger.info(f"OpenRouter API Key loaded: {'Yes' if api_key else 'No'}")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable not set")

    # Fetch data from database (cached)
    events = fetch_events_cached()
    announcements = fetch_announcements_cached()
    clearances = fetch_clearances_cached(user_id)
    officers = fetch_officers_cached()

    # Format context for the prompt
    events_str = "\n".join([
        f"## {event['title']}\n"
        f"  - Date: {event['date']}\n"
        f"  - Location: {event['location']}\n"
        f"  - Registration Start: {event['registration_start'] or 'Not specified'}\n"
        f"  - Registration End: {event['registration_end'] or 'Not specified'}\n"
        f"  - Registered: {'Yes' if event['is_participant'] else 'No'}"
        for event in events
    ]) if isinstance(events, list) else str(events)

    announcements_str = "\n".join([
        f"## {ann['title']}\n"
        f"  - Date: {ann['date']}\n"
        f"  - Location: {ann['location']}"
        for ann in announcements
    ]) if isinstance(announcements, list) else str(announcements)

    clearances_str = "\n".join([
        f"## Clearance\n"
        f"  - Requirement: {c['requirement']}\n"
        f"  - Amount: {c['amount']}\n"
        f"  - Payment Status: {c['payment_status']}\n"
        f"  - Status: {c['status']}\n"
        f"  - Payment Method: {c['payment_method'] or 'None'}\n"
        f"  - Payment Date: {c['payment_date'] or 'None'}\n"
        f"  - Approval Date: {c['approval_date'] or 'None'}\n"
        f"  - Denial Reason: {c['denial_reason'] or 'None'}"
        for c in clearances
    ]) if isinstance(clearances, list) else str(clearances)

    officers_str = "\n".join([
        f"- **{o['full_name']}**: {o['position']}"
        for o in officers
    ]) if isinstance(officers, list) else str(officers)

    # Construct the full prompt
    full_prompt = (
        "You are SPECS NEXUS Assistance, a helpful chatbot for the SPECS Nexus platform, designed for the Society of Programming Enthusiasts in Computer Science (SPECS) at Gordon College. SPECS is a student organization under the College of Computer Studies (CCS) department, dedicated to fostering learning, innovation, and community involvement in computer science, specifically for the Bachelor of Science in Computer Science (BSCS) program. SPECS Nexus streamlines membership registration, event participation, and announcement updates, helping members stay connected and informed in a user-friendly environment. The platform has five main pages: Dashboard, Profile, Events, Announcements, and Membership. Below are details about each:\n\n"
        "**Dashboard Page**: The central hub where users can view their current requirements and clearance status, including an overview of pending tasks.\n\n"
        "**Profile Page**: Displays all personal details, providing a snapshot of the user's account information.\n\n"
        "**Events Page**: Lists all current SPECS events with details. Users can browse and choose to participate.\n\n"
        "**Announcements Page**: The source for SPECS updates and news.\n\n"
        "**Membership Page**: Shows clearance status and payment history. Users can view clearance details and payment progress. Payment options include GCash and PayMaya. After payment, users upload a digital receipt, and the system updates the status to 'Verifying' while an officer reviews it. If verified, the status changes to 'Clear'; otherwise, it remains 'Not Yet Cleared'.\n\n"
        "**Payment Methods**: GCash and PayMaya.\n\n"
        "**Current Events**:\n" + (events_str if events_str else "No events available.") + "\n\n"
        "**Current Announcements**:\n" + (announcements_str if announcements_str else "No announcements available.") + "\n\n"
        "**User Clearances**:\n" + (clearances_str if clearances_str else "No clearances available.") + "\n\n"
        "**Current Officers**:\n" + (officers_str if officers_str else "No officers available.") + "\n\n"
        "Instructions for responses:\n"
        "- Format responses using markdown-like formatting.\n"
        "- For events, use a heading (##) for each event title, followed by indented bullet points (  -) for details (Description, Date, Location, Registration Start, Registration End, Registered).\n"
        "- For clearances, use a heading (##) for each Clearance followed by the ID (e.g., Clearance 123), followed by indented bullet points for details (Requirement, Amount, Payment Status, Status, Payment Method, Payment Date, Approval Date, Denial Reason).\n"
        "- For announcements, use a heading (##) for each announcement title, followed by indented bullet points for details (Description, Date, Location).\n"
        "- For officer queries, list officers with their full name and position in a bullet-point list (e.g., - **Name**: Position).\n"
        "- If you lack specific information to answer a query, respond with: 'I'm sorry, I do not have that information.'\n"
        "- Ensure responses are concise and easy to read with clear section headings and spacing.\n\n"
        f"User Query: {user_query}\n"
        "Answer:"
    )

    # Initialize OpenRouter client
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1"
    )

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model="meta-llama/llama-3.3-8b-instruct:free",
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": user_query}
            ],
            max_tokens=512,
            temperature=0.7,
            extra_headers={
                "HTTP-Referer": "https://specs-nexus.gordoncollege.edu",  # Replace with your actual site URL
                "X-Title": "SPECS Nexus"  # Replace with your actual app name
            }
        )
        response_time = time.time() - start_time
        logger.info(f"OpenRouter API response received in {response_time:.2f} seconds, tokens used: input={response.usage.prompt_tokens}, output={response.usage.completion_tokens}")
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Failed to get response from OpenRouter API: {str(e)}")
        if "rate limit" in str(e).lower():
            return "Error: Rate limit exceeded. Please try again later."
        elif "quota" in str(e).lower():
            return "Error: API quota exhausted. Please check your OpenRouter account."
        elif "no endpoints found" in str(e).lower():
            return "Error: Invalid model name. Please contact support."
        return f"Error: Failed to get response from API: {str(e)}"