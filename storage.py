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

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

_cached_creds = None
_cached_gsheet_client = None
_cached_drive_client = None

def _get_credentials():
    global _cached_creds
    if _cached_creds:
        return _cached_creds

    from google.oauth2.credentials import Credentials
    
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN')

    if not (client_id and client_secret and refresh_token):
        print("Error: Missing OAuth2 environment variables (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN).")
        return None

    _cached_creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    return _cached_creds

def get_gsheet_client():
    global _cached_gsheet_client
    if _cached_gsheet_client:
        return _cached_gsheet_client
    
    creds = _get_credentials()
    if creds:
        _cached_gsheet_client = gspread.authorize(creds)
    return _cached_gsheet_client

def get_drive_client():
    global _cached_drive_client
    if _cached_drive_client:
        return _cached_drive_client
    
    creds = _get_credentials()
    if creds:
        _cached_drive_client = build('drive', 'v3', credentials=creds, cache_discovery=False)
    return _cached_drive_client

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
                "タイムスタンプ", "種まき日", "ユーザー名", "ロット名/品種", "栽培段数/経過日数",
                "pH", "EC", "水温", "室温", "湿度", "画像URL", "カテゴリ", "外気温", "備考/トラブル"
            ]
            sheet.insert_row(headers, 1)
            print("Spreadsheet headers initialized.")
    except Exception as e:
        print(f"Error setting up headers: {e}")

def init_db():
    client = get_gsheet_client()
    if not client:
        print("Google Sheets storage initialization FAILED. Please check credentials.")
        return

    print("Google Sheets storage connection verified.")
    setup_headers()
    
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        try:
            master_sheet = sh.worksheet("栽培マスター")
        except gspread.exceptions.WorksheetNotFound:
            master_sheet = sh.add_worksheet(title="栽培マスター", rows="100", cols="6")
            master_sheet.insert_row(["ロットID", "ロット名/品種", "種まき日", "ステータス", "予定数量", "登録者", "画像URL", "メモ"], 1)
            jst = timezone(timedelta(hours=9))
            today = (datetime.now(jst)).strftime('%Y-%m-%d')
            master_sheet.append_row(["LOT-001", "レタス-A", today, "稼働中", "100", "システム"])
            print("Master Lots sheet initialized with example data.")
    except Exception as e:
        print(f"Error initializing Master sheet: {e}")

    print("Google Sheets storage initialization complete.")

def get_active_lots(debug=False):
    client = get_gsheet_client()
    if not client: 
        if debug: raise Exception("Google Sheets client init failed.")
        return []
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("栽培マスター")
        values = sheet.get_all_values()
        if len(values) <= 1:
            return []
        
        headers = [str(h).strip() for h in values[0]]
        try:
            status_idx = headers.index("ステータス")
            name_idx = headers.index("ロット名/品種")
            date_idx = headers.index("種まき日")
        except ValueError as e:
            print(f"Error finding column index: {e}")
            return []
            
        active_lots = []
        for row in values[1:]:
            if len(row) > status_idx and row[status_idx].strip() == "稼働中":
                name = row[name_idx].strip() if len(row) > name_idx else ""
                date = row[date_idx].strip() if len(row) > date_idx else ""
                active_lots.append({
                    "ロット名/品種": name,
                    "種まき日": date,
                    "品種": name.split('-')[0].strip() if '-' in name else name
                })
        return active_lots
    except Exception as e:
        if debug: raise e
        print(f"Error fetching lots: {e}")
        return []

def save_new_lot(user_name, variety, seeding_date, qty, image_url="", memo=""):
    client = get_gsheet_client()
    if not client: return None

    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("栽培マスター")
        jst = timezone(timedelta(hours=9))
        now = datetime.now(jst)
        lot_id = f"LOT-{now.strftime('%Y%m%d-%H%M')}"
        lot_name = f"{variety}-{now.strftime('%m%d')}"
        
        row = [lot_id, lot_name, seeding_date, "稼働中", qty, user_name, image_url, memo]
        sheet.append_row(row)
        print(f"Successfully registered new planting: {lot_id}")
        return lot_name
    except Exception as e:
        print(f"Error saving new lot: {e}")
        return None

def save_log(user_id, user_name, data_dict, raw_message, image_url=None):
    client = get_gsheet_client()
    if not client:
        print("Skipping log: Google Sheets client not available.")
        raise Exception("Google Sheets API (client) not initialized")

    try:
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        
        jst = timezone(timedelta(hours=9))
        now = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')

        metric_type = data_dict.get("metric_type")
        val = data_dict.get("value")
        seeding_date = data_dict.get("seeding_date", "")
        
        ph = data_dict.get("ph") if data_dict.get("ph") is not None else (val if metric_type == "pH" else "")
        ec = data_dict.get("ec") if data_dict.get("ec") is not None else (val if metric_type == "EC" else "")
        water_temp = data_dict.get("water_temp") if data_dict.get("water_temp") is not None else (val if metric_type == "Water Temp" else "")
        room_temp = data_dict.get("room_temp") if data_dict.get("room_temp") is not None else (val if metric_type == "Room Temp" else "")
        humidity = data_dict.get("humidity") if data_dict.get("humidity") is not None else ""
        
        base_row = [
            now,
            seeding_date,
            user_name,
            data_dict.get("lot_name", data_dict.get("variety", "レタス")),
            data_dict.get("stage", ""),
            ph,
            ec,
            water_temp,
            room_temp,
            humidity,
            image_url or data_dict.get("image_url", ""),
            data_dict.get("category", ""),
            "",
            raw_message
        ]
        
        row = [str(x) if x is not None else "" for x in base_row]
        
        # table_range="A1" と insert_data_option="INSERT_ROWS" を指定して、右へズレる不具合(階段現象)を防ぎます。
        res = sheet.append_row(row, table_range="A1", insert_data_option="INSERT_ROWS")
        updated_range = res.get('updates', {}).get('updatedRange', 'Unknown Range')
        print(f"Sheet update success! Data appended to: {updated_range}")
        print(f"Successfully logged to Google Sheets for user {user_name}")
        
        try:
            return res.get('updates', {}).get('updatedRange', '').split('!')[-1]
        except:
            return "登録完了"

    except Exception as e:
        import traceback
        print(f"Error saving to Google Sheets: {e}")
        traceback.print_exc()
        raise e

def upload_image_to_drive(image_bytes, filename):
    client = get_drive_client()
    if not client:
        return "処理エラー: Driveクライアント初期化失敗"

    folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    if not folder_id:
        return "処理エラー: GOOGLE_DRIVE_FOLDER_ID 環境変数が設定されていません"

    try:
        media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype='image/jpeg', resumable=True)
        file_metadata = {
            'name': filename,
            'mimeType': 'image/jpeg',
            'parents': [folder_id]
        }
        file = client.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webContentLink, webViewLink'
        ).execute()
        file_id = file.get('id')
        
        permission = {
            'type': 'anyone',
            'role': 'reader',
        }
        client.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id'
        ).execute()
        
        direct_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        print(f"Successfully uploaded {filename} to Google Drive: {direct_url}")
        return direct_url
    except Exception as e:
        print(f"Google Drive upload err: {e}")
        return f"処理エラー: {e}"
