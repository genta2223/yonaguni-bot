import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# Configuration from environment variables
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SERVICE_ACCOUNT_JSON = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')

def get_gsheet_client():
    # Use the specific file uploaded by the user
    json_path = os.path.join(os.path.dirname(__file__), 'gen-lang-client-0030599774-9463e82c6afb.json')
    print(f"DEBUG: Looking for credentials at: {json_path}")
    
    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # 1. Try local file path (Best for local development)
        if os.path.exists(json_path):
            return gspread.authorize(Credentials.from_service_account_file(json_path, scopes=scopes))
        
        # 2. Try environment variable (Required for Render deployment)
        service_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
        if service_json:
            # Handle potential escaping issues in the env var string
            try:
                creds_dict = json.loads(service_json)
            except json.JSONDecodeError:
                creds_dict = json.loads(service_json.replace('\\n', '\n'))
            
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            return gspread.authorize(creds)
        else:
            print("Error: Neither credentials file nor GOOGLE_SERVICE_ACCOUNT_JSON found.")
            return None
    except Exception as e:
        print(f"Error initializing Google Sheets client: {e}")
        return None

def setup_headers():
    """
    Inserts the header row if the sheet is empty.
    """
    client = get_gsheet_client()
    if not client:
        return

    try:
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        # Check if 1st row is empty
        first_row = sheet.row_values(1)
        if not first_row:
            headers = [
                "タイムスタンプ",
                "ユーザー名",
                "品種",
                "栽培段数/週数",
                "pH",
                "EC",
                "水温",
                "室温",
                "湿度",
                "画像URL",
                "外気温",
                "備考/トラブル"
            ]
            sheet.insert_row(headers, 1)
            print("Spreadsheet headers initialized.")
    except Exception as e:
        print(f"Error setting up headers: {e}")

def init_db():
    """
    Initializes the storage by ensuring connection and setting up headers.
    """
    client = get_gsheet_client()
    if client:
        print("Google Sheets storage connection verified.")
        setup_headers()
        print("Google Sheets storage initialization complete.")
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
        import traceback
        print(f"Error saving to Google Sheets: {e}")
        traceback.print_exc()
