import os
import re
import json
from collections import Counter
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# --- Load Environment Variables for Local Testing ---
load_dotenv()

# --- Configuration ---
NOTICES_URL = "https://pu.edu.np/notices/"
# The state file will now be created in the main (root) directory
STATE_FILE_PATH = "date_counts.json" 

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
        response.raise_for_status()
        print("LOG: Successfully sent Telegram notification.")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Telegram API request failed: {e}")

def get_previous_counts():
    """Reads the last known date counts from the state file."""
    print(f"LOG: Reading previous date counts from '{STATE_FILE_PATH}'...")
    try:
        with open(STATE_FILE_PATH, 'r') as f:
            data = json.load(f)
            print(f"LOG: Successfully loaded previous counts for {len(data)} dates.")
            return data
    except FileNotFoundError:
        print("LOG: State file not found. Assuming this is the first run.")
        return {}
    except json.JSONDecodeError:
        print("ERROR: State file is corrupted or empty. Starting fresh.")
        return {}

def save_current_counts(counts):
    """Saves the current date counts to the state file."""
    print(f"LOG: Saving current counts for {len(counts)} dates to '{STATE_FILE_PATH}'...")
    # No longer need to create a directory, saving to root.
    with open(STATE_FILE_PATH, 'w') as f:
        json.dump(counts, f, indent=2, sort_keys=True)
    print("LOG: Save complete.")

def format_changes(previous, current):
    """Creates a human-readable string detailing changes in date counts."""
    all_dates = sorted(list(set(previous.keys()) | set(current.keys())), reverse=True)
    
    changes = []
    for date in all_dates:
        old_count = previous.get(date, 0)
        new_count = current.get(date, 0)
        
        if old_count != new_count:
            if old_count == 0:
                changes.append(f"✅ <b>New:</b> {date} (Count: {new_count})")
            elif new_count == 0:
                changes.append(f"❌ <b>Removed:</b> {date} (Was: {old_count})")
            else:
                changes.append(f"🔄 <b>Changed:</b> {date} (Count: {old_count} → <b>{new_count}</b>)")
                
    return "\n".join(changes)

def check_for_updates():
    """Main function to perform the check-and-notify process."""
    print(f"\n--- SCRIPT START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

    previous_counts = get_previous_counts()

    print(f"LOG: Fetching content from {NOTICES_URL}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(NOTICES_URL, headers=headers, timeout=20)
        response.raise_for_status()
        print("LOG: Website fetched successfully.")
    except requests.exceptions.RequestException as e:
        print(f"FATAL ERROR: Could not fetch the website. Stopping script. Reason: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    page_text = soup.body.get_text(separator=' ', strip=True)
    
    date_pattern = r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\b'
    found_dates = re.findall(date_pattern, page_text, re.IGNORECASE)
    
    current_counts = dict(Counter(found_dates))
    print(f"LOG: Found {len(found_dates)} total notices across {len(current_counts)} unique dates.")

    if not previous_counts and current_counts:
        print("LOG: First run. Initializing state and sending welcome message.")
        message = (
            "✅ **PU Monitor Initialized**\n\n"
            "The monitor is now active and will track the count of each notice date.\n\n"
            f"<b>Initial counts found:</b>\n"
            f"```{json.dumps(current_counts, indent=2, sort_keys=True)}```\n\n"
            f"Page: {NOTICES_URL}"
        )
        send_telegram_message(message)
    elif previous_counts != current_counts:
        print("LOG: Change detected! Preparing notification.")
        changes_summary = format_changes(previous_counts, current_counts)
        message = (
            "🚨 **PU Notices Update Detected** 🚨\n\n"
            "The list or count of notices on the page has changed.\n\n"
            f"{changes_summary}\n\n"
            f"View the notices page for details:\n{NOTICES_URL}"
        )
        send_telegram_message(message)
    else:
        print("LOG: No changes detected. The date counts are identical.")

    save_current_counts(current_counts)
    
    print(f"--- SCRIPT END: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("FATAL ERROR: Environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
    else:
        check_for_updates()
