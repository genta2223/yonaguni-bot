import os
from storage import save_log, init_db

def run_test():
    print("--- Storage Verification Test ---")
    
    # 1. Test data as requested
    test_data = {
        "variety": "レタス",
        "stage": "2段目",
        "ph": 6.2,
        "ec": 1.4,
        "water_temp": 23.0,
        "room_temp": 26.5,
        "humidity": 60.0
    }
    raw_message = "システム連携テスト（自動投入）"
    
    print(f"Attempting to write test data: {test_data}")
    
    # Simulate a data entry
    try:
        # Note: This requires valid GOOGLE_SERVICE_ACCOUNT_JSON and SPREADSHEET_ID in .env
        save_log(
            user_id="test_user_id",
            user_name="Anty_Test_System",
            data_dict=test_data,
            raw_message=raw_message
        )
        print("Success: Log entry sent to Google Sheets logic.")
        print("Please check the spreadsheet (12 columns A-L) for the new row.")
    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    init_db()
    run_test()
