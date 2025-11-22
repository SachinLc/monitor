import os
import re
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# --- Load Environment Variables for Local Testing ---
load_dotenv()

# --- Configuration ---
NOTICES_URL = "https://pu.edu.np/notices/"
STATE_FILE_PATH = "state/dates.json" # Changed to track dates

# --- Telegram Configuration ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    """Sends a formatted message to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Telegram credentials are not set. Cannot send message.")
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    
    try:
        response = requests.post(api_url, data=payload, timeout=10)
        if response.status_code == 200:
            print("LOG: Successfully sent Telegram notification.")
        else:
            print(f"ERROR: Telegram API returned status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"ERROR: An exception occurred while sending Telegram message: {e}")

def get_previous_dates():
    """Reads the last known list of dates from the state file."""
    print(f"LOG: Reading previous dates from '{STATE_FILE_PATH}'...")
    try:
        with open(STATE_FILE_PATH, 'r') as f:
            data = json.load(f)
            print(f"LOG: Successfully loaded {len(data)} previous dates.")
            return data
    except FileNotFoundError:
        print("LOG: State file not found. Assuming this is the first run.")
        return []
    except json.JSONDecodeError:
        print("ERROR: State file is corrupted or empty. Starting fresh.")
        return []

def save_current_dates(dates):
    """Saves the current list of dates to the state file."""
    print(f"LOG: Saving {len(dates)} current dates to '{STATE_FILE_PATH}'...")
    os.makedirs(os.path.dirname(STATE_FILE_PATH), exist_ok=True)
    with open(STATE_FILE_PATH, 'w') as f:
        json.dump(dates, f, indent=2)
    print("LOG: Save complete.")

def format_changes(previous_list, current_list):
    """Creates a human-readable string detailing added and removed dates."""
    previous_set = set(previous_list)
    current_set = set(current_list)
    
    added = sorted(list(current_set - previous_set), reverse=True)
    removed = sorted(list(previous_set - current_set), reverse=True)
    
    message_parts = []
    if added:
        message_parts.append("<b>✅ New Notices Found:</b>\n" + "\n".join(f"  • {d}" for d in added))
    if removed:
        message_parts.append("<b>❌ Old Notices Removed:</b>\n" + "\n".join(f"  • {d}" for d in removed))
        
    return "\n\n".join(message_parts)

def check_for_updates():
    """Main function to perform the check-and-notify process."""
    print(f"\n--- SCRIPT START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

    # 1. Get previous state
    previous_dates = get_previous_dates()

    # 2. Fetch live website content
    print(f"LOG: Fetching content from {NOTICES_URL}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(NOTICES_URL, headers=headers, timeout=20)
        response.raise_for_status()
        print("LOG: Website fetched successfully.")
    except requests.exceptions.RequestException as e:
        print(f"FATAL ERROR: Could not fetch the website. Stopping script. Reason: {e}")
        return

    # 3. Parse HTML and extract all full dates
    soup = BeautifulSoup(response.text, 'html.parser')
    page_text = soup.body.get_text(separator=' ', strip=True)
    
    # Regex to find dates like "20 Nov 2025". This is the core of the fix.
    date_pattern = r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\b'
    found_dates = re.findall(date_pattern, page_text, re.IGNORECASE)
    
    # Create a canonical (sorted, unique) list of dates for reliable comparison
    current_dates = sorted(list(set(found_dates)))
    print(f"LOG: Found {len(current_dates)} unique dates on the page.")

    # 4. Compare current state with previous state
    if not previous_dates and current_dates:
        # First successful run
        print("LOG: First run. Initializing state and sending welcome message.")
        message = (
            "✅ **PU Monitor Initialized**\n\n"
            "The monitor is now active and will track specific notice dates.\n\n"
            f"<b>Found {len(current_dates)} notices:</b>\n" +
            "\n".join(f"  • {d}" for d in current_dates[:15]) + # Show a sample
            (f"\n  • ...and {len(current_dates) - 15} more." if len(current_dates) > 15 else "") +
            f"\n\nPage: {NOTICES_URL}"
        )
        send_telegram_message(message)
    elif previous_dates != current_dates:
        print("LOG: Change detected! Preparing notification.")
        changes_summary = format_changes(previous_dates, current_dates)
        message = (
            "🚨 **PU Notices Update Detected** 🚨\n\n"
            "The list of notices on the page has changed.\n\n"
            f"{changes_summary}\n\n"
            f"View the notices page for details:\n{NOTICES_URL}"
        )
        send_telegram_message(message)
    else:
        print("LOG: No changes detected. The list of notice dates is identical.")

    # 5. Save the new state for the next run
    save_current_dates(current_dates)
    
    print(f"--- SCRIPT END: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("FATAL ERROR: Environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
    else:
        check_for_updates()
