import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

# Configuration from environment variables
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')

def get_gsheet_client():
    if not SERVICE_ACCOUNT_JSON:
        print("Error: GOOGLE_SERVICE_ACCOUNT_JSON not set.")
        return None
    
    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        # Load credentials from JSON string in env var
        creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Error initializing Google Sheets client: {e}")
        return None

def init_db():
    """
    In the Google Sheets version, we assume the sheet and header exist.
    If we wanted to be robust, we could create them if missing.
    For now, we'll just log an initialization message.
    """
    client = get_gsheet_client()
    if client:
        print("Google Sheets storage initialized successfully.")
    else:
        print("Google Sheets storage initialization FAILED. Please check credentials.")

def save_log(user_id, user_name, data_dict, raw_message, image_url=None):
    """
    Saves a log entry to Google Sheets.
    data_dict contains parsed fields from bot_logic.
    """
    client = get_gsheet_client()
    if not client:
        print("Skipping log: Google Sheets client not available.")
        return

    try:
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        
        # 1. Timestamp (JST: UTC+9)
        jst = timezone(timedelta(hours=9))
        now = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')

        # 2. Extract metrics from data_dict
        metric_type = data_dict.get("metric_type")
        val = data_dict.get("value")
        
        # Initialize columns
        ph = val if metric_type == "pH" else ""
        ec = val if metric_type == "EC" else ""
        water_temp = val if metric_type == "Water Temp" else ""
        room_temp = val if metric_type == "Room Temp" else ""
        humidity = data_dict.get("humidity", "")
        
        # Prepare row data (14 columns)
        row = [
            now,                        # Timestamp
            user_name,                  # User Name
            user_id,                    # User ID
            data_dict.get("stage", ""), # Growth Stage
            data_dict.get("variety", "レタス"), # Variety
            ph,                         # pH
            ec,                         # EC
            water_temp,                 # Water Temp
            room_temp,                  # Room Temp
            humidity,                   # Humidity
            image_url or "",            # Image URL / ID
            "",                         # External Temp (Placeholder)
            "",                         # External Humidity (Placeholder)
            raw_message                 # Raw Message
        ]
        
        sheet.append_row(row)
        print(f"Successfully logged to Google Sheets for user {user_name}")

    except Exception as e:
        print(f"Error saving to Google Sheets: {e}")
