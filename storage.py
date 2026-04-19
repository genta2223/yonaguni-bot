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
        
        # Initialize columns with priority to specific keys (used in interactive mode)
        ph = data_dict.get("ph") if data_dict.get("ph") is not None else (val if metric_type == "pH" else "")
        ec = data_dict.get("ec") if data_dict.get("ec") is not None else (val if metric_type == "EC" else "")
        water_temp = data_dict.get("water_temp") if data_dict.get("water_temp") is not None else (val if metric_type == "Water Temp" else "")
        room_temp = data_dict.get("room_temp") if data_dict.get("room_temp") is not None else (val if metric_type == "Room Temp" else "")
        humidity = data_dict.get("humidity") if data_dict.get("humidity") is not None else ""
        
        # Prepare row data (12 columns as specified by user)
        # 1: Timestamp, 2: User Name, 3: Variety, 4: Stage, 5: pH, 6: EC, 
        # 7: Water Temp, 8: Room Temp, 9: Humidity, 10: Image URL, 11: External Temp, 12: Remarks
        row = [
            now,                        # 1. タイムスタンプ
            user_name,                  # 2. ユーザー名
            data_dict.get("variety", "レタス"), # 3. 品種
            data_dict.get("stage", ""), # 4. 栽培段数/週数
            ph,                         # 5. pH
            ec,                         # 6. EC
            water_temp,                 # 7. 水温
            room_temp,                  # 8. 室温
            humidity,                   # 9. 湿度
            image_url or "",            # 10. 画像URL
            "",                         # 11. 外気温 (将来用)
            raw_message                 # 12. 備考/トラブル
        ]
        
        sheet.append_row(row)
        print(f"Successfully logged to Google Sheets for user {user_name}")

    except Exception as e:
        print(f"Error saving to Google Sheets: {e}")
