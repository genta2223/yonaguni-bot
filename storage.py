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
                "種まき日",
                "ユーザー名",
                "ロット名/品種",
                "栽培段数/経過日数",
                "pH",
                "EC",
                "水温",
                "室温",
                "湿度",
                "画像URL",
                "カテゴリ",
                "外気温",
                "備考/トラブル"
            ]
            sheet.insert_row(headers, 1)
            print("Spreadsheet headers initialized.")
    except Exception as e:
        print(f"Error setting up headers: {e}")

def init_db():
    """
    Initializes the storage by ensuring connection and setting up sheets.
    """
    client = get_gsheet_client()
    if not client:
        print("Google Sheets storage initialization FAILED. Please check credentials.")
        return

    print("Google Sheets storage connection verified.")
    setup_headers()
    
    # Initialize Master Lots sheet if missing
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            master_sheet = sh.worksheet("栽培マスター")
        except gspread.exceptions.WorksheetNotFound:
            master_sheet = sh.add_worksheet(title="栽培マスター", rows="100", cols="5")
            master_sheet.insert_row(["ロットID", "ロット名/品種", "種まき日", "ステータス"], 1)
            # Add example data
            jst = timezone(timedelta(hours=9))
            today = (datetime.now(jst)).strftime('%Y-%m-%d')
            master_sheet.append_row(["LOT-001", "レタス-A", today, "稼働中"])
            print("Master Lots sheet initialized with example data.")
    except Exception as e:
        print(f"Error initializing Master sheet: {e}")

    print("Google Sheets storage initialization complete.")

def get_active_lots():
    """
    Returns a list of active lots from the '栽培マスター' sheet.
    """
    client = get_gsheet_client()
    if not client: return []
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("栽培マスター")
        records = sheet.get_all_records()
        return [r for r in records if r["ステータス"] == "稼働中"]
    except Exception as e:
        print(f"Error fetching lots: {e}")
        return []

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
        seeding_date = data_dict.get("seeding_date", "")
        
        # Initialize columns with priority to specific keys (used in interactive mode)
        ph = data_dict.get("ph") if data_dict.get("ph") is not None else (val if metric_type == "pH" else "")
        ec = data_dict.get("ec") if data_dict.get("ec") is not None else (val if metric_type == "EC" else "")
        water_temp = data_dict.get("water_temp") if data_dict.get("water_temp") is not None else (val if metric_type == "Water Temp" else "")
        room_temp = data_dict.get("room_temp") if data_dict.get("room_temp") is not None else (val if metric_type == "Room Temp" else "")
        humidity = data_dict.get("humidity") if data_dict.get("humidity") is not None else ""
        
        # Prepare row data (14 columns)
        row = [
            now,                                # 1. タイムスタンプ
            seeding_date,                       # 2. 種まき日
            user_name,                          # 3. ユーザー名
            data_dict.get("lot_name", data_dict.get("variety", "レタス")), # 4. ロット名/品種
            data_dict.get("stage", ""),         # 5. 栽培段数/経過日数
            ph,                                 # 6. pH
            ec,                                 # 7. EC
            water_temp,                         # 8. 水温
            room_temp,                          # 9. 室温
            humidity,                           # 10. 湿度
            image_url or "",                    # 11. 画像URL
            data_dict.get("category", ""),     # 12. カテゴリ
            "",                                 # 13. 外気温 (将来用)
            raw_message                         # 14. 備考/トラブル
        ]
        
        res = sheet.append_row(row)
        print(f"Successfully logged to Google Sheets for user {user_name}")
        
        # Return row number or info
        try:
            return res.get('updates', {}).get('updatedRange', '').split('!')[-1]
        except:
            return "登録完了"

    except Exception as e:
        import traceback
        print(f"Error saving to Google Sheets: {e}")
        traceback.print_exc()
