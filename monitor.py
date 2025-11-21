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
STATE_FILE_PATH = "state/counts.json"
MONTHS = [
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec"
]

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

def get_previous_counts():
    """Reads the last known month counts from the state file."""
    print(f"LOG: Reading previous counts from '{STATE_FILE_PATH}'...")
    try:
        with open(STATE_FILE_PATH, 'r') as f:
            data = json.load(f)
            print(f"LOG: Successfully loaded previous counts: {data}")
            return data
    except FileNotFoundError:
        print("LOG: State file not found. Assuming this is the first run.")
        return {}
    except json.JSONDecodeError:
        print("ERROR: State file is corrupted or empty. Starting fresh.")
        return {}

def save_current_counts(counts):
    """Saves the current month counts to the state file."""
    print(f"LOG: Saving current counts to '{STATE_FILE_PATH}': {counts}")
    # Ensure the directory exists
    os.makedirs(os.path.dirname(STATE_FILE_PATH), exist_ok=True)
    with open(STATE_FILE_PATH, 'w') as f:
        json.dump(counts, f, indent=2)
    print("LOG: Save complete.")

def format_changes(previous, current):
    """Creates a human-readable string detailing the changes."""
    all_keys = sorted(list(set(previous.keys()) | set(current.keys())))
    changes = []
    for key in all_keys:
        old_val = previous.get(key, 0)
        new_val = current.get(key, 0)
        if old_val != new_val:
            changes.append(f"• <b>{key.capitalize()}</b>: {old_val} → <b>{new_val}</b>")
    return "\n".join(changes) if changes else "No specific count changes detected."

def check_for_updates():
    """Main function to perform the check-and-notify process."""
    print(f"\n--- SCRIPT START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

    # 1. Get previous state
    previous_counts = get_previous_counts()

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

    # 3. Parse HTML and find all month occurrences
    soup = BeautifulSoup(response.text, 'html.parser')
    page_text = soup.body.get_text(separator=' ', strip=True).lower()
    
    # Regex to find all 3-letter month abbreviations
    month_pattern = r'\b(' + '|'.join(MONTHS) + r')\b'
    found_months = re.findall(month_pattern, page_text)
    
    current_counts = dict(Counter(found_months))
    print(f"LOG: Found current month counts: {current_counts}")

    # 4. Compare current state with previous state
    if not previous_counts and current_counts:
        # First successful run
        print("LOG: First run. Initializing state and sending welcome message.")
        message = (
            "✅ **PU Monitor Initialized**\n\n"
            "The monitor is now active and has successfully fetched the initial month counts.\n\n"
            "<b>Initial Counts:</b>\n"
            f"```{json.dumps(current_counts, indent=2)}```\n\n"
            f"You will be notified of any future changes.\n"
            f"Page: {NOTICES_URL}"
        )
        send_telegram_message(message)
    elif previous_counts != current_counts:
        print("LOG: Change detected! Preparing notification.")
        changes_summary = format_changes(previous_counts, current_counts)
        message = (
            "🚨 **PU Notices Update Detected** 🚨\n\n"
            "The month counts on the notices page have changed, indicating new or removed notices.\n\n"
            "<b>Changes:</b>\n"
            f"{changes_summary}\n\n"
            f"View the notices page for details:\n{NOTICES_URL}"
        )
        send_telegram_message(message)
    else:
        print("LOG: No changes detected. No notification will be sent.")

    # 5. Save the new state for the next run
    save_current_counts(current_counts)
    
    print(f"--- SCRIPT END: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("FATAL ERROR: Environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
    else:
        check_for_updates()
