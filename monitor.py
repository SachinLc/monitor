import os
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# --- Load Environment Variables for Local Testing ---
load_dotenv()

# --- Configuration ---
NOTICES_URL = "https://pu.edu.np/notices/"
STATE_FILE_PATH = "state/notices.json"

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

def get_previous_notices():
    """Reads the last known list of notice identifiers from the state file."""
    print(f"LOG: Reading previous notices from '{STATE_FILE_PATH}'...")
    try:
        with open(STATE_FILE_PATH, 'r') as f:
            data = json.load(f)
            print(f"LOG: Successfully loaded {len(data)} previous notices.")
            return set(data)
    except FileNotFoundError:
        print("LOG: State file not found. Assuming this is the first run.")
        return set()
    except json.JSONDecodeError:
        print("ERROR: State file is corrupted or empty. Starting fresh.")
        return set()

def save_current_notices(notices_set):
    """Saves the current list of notice identifiers to the state file."""
    print(f"LOG: Saving {len(notices_set)} current notices to '{STATE_FILE_PATH}'...")
    os.makedirs(os.path.dirname(STATE_FILE_PATH), exist_ok=True)
    with open(STATE_FILE_PATH, 'w') as f:
        json.dump(list(notices_set), f, indent=2)
    print("LOG: Save complete.")

def check_for_updates():
    """Main function to perform the check-and-notify process."""
    print(f"\n--- SCRIPT START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

    # 1. Get previous state
    previous_notices_set = get_previous_notices()

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

    # 3. Parse HTML and extract unique notice identifiers
    soup = BeautifulSoup(response.text, 'html.parser')
    current_notices_set = set()
    
    # --- IMPROVED SELECTOR AND LOGGING ---
    # This selector is more general and looks for any list item within a div that seems to contain the notices.
    notice_list = soup.select(".card-body ul li") 
    
    if not notice_list:
        print("ERROR: Could not find any notice list items using the selector '.card-body ul li'. The website structure has likely changed.")
        # Attempt a broader fallback selector
        print("LOG: Attempting a broader fallback selector 'ul li'...")
        notice_list = soup.select("ul li")
        if not notice_list:
            print("ERROR: Fallback selector also failed. The page structure is unrecognized. Stopping script.")
            return

    print(f"LOG: Found {len(notice_list)} potential notice items. Parsing them now...")
    
    for i, item in enumerate(notice_list):
        title_tag = item.find('a')
        date_tag = item.find('span')
        
        if title_tag and date_tag:
            title = " ".join(title_tag.get_text(strip=True).split())
            date = " ".join(date_tag.get_text(strip=True).split())
            
            # A simple filter to avoid parsing navigation links etc.
            if len(date) < 25 and any(char.isdigit() for char in date):
                unique_id = f"{title} - {date}"
                current_notices_set.add(unique_id)
            else:
                print(f"LOG: Skipping item #{i+1} as it does not look like a valid notice (Date: '{date}')")
        else:
            print(f"LOG: Skipping item #{i+1} as it's missing a title or date tag.")
            
    if not current_notices_set:
        print("ERROR: Parsed the page but could not extract any valid notices. Please check the HTML structure and selectors.")
        return # Exit if we found nothing, to avoid overwriting good state with empty state

    print(f"LOG: Successfully extracted {len(current_notices_set)} unique notices.")

    # 4. Compare current state with previous state
    if previous_notices_set == current_notices_set:
        print("LOG: No changes detected. The list of notices is identical to the last run.")
    else:
        new_notices = current_notices_set - previous_notices_set
        
        if not previous_notices_set and current_notices_set:
            print("LOG: First run or state was empty. Initializing state.")
            message = (
                "✅ **PU Monitor Initialized**\n\n"
                "The monitor is now active and has fetched the initial list of notices. "
                "You will be notified of any future changes."
            )
            send_telegram_message(message)
        elif new_notices:
            print(f"LOG: Change detected! New notices: {len(new_notices)}")
            new_notices_str = "\n".join([f"• {notice}" for notice in sorted(list(new_notices))])
            message = (
                "🚨 **New PU Notice(s) Detected** 🚨\n\n"
                "The following new notice(s) have been published:\n\n"
                f"<b>{new_notices_str}</b>\n\n"
                f"View all notices here:\n{NOTICES_URL}"
            )
            send_telegram_message(message)
        else:
            print("LOG: Change detected, but it appears notices were removed, not added. No notification sent.")

    # 5. Save the new state for the next run
    save_current_notices(current_notices_set)
    
    print(f"--- SCRIPT END: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("FATAL ERROR: Environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
    else:
        check_for_updates()
