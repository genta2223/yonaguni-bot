import re
from linebot.models import QuickReply, QuickReplyButton, MessageAction
from config import STANDARDS, TROUBLE_RESPONSES

# Conversation States
STATE_AWAITING_LOT = "AWAITING_LOT" # New entry point
STATE_AWAITING_STAGE = "AWAITING_STAGE"
STATE_AWAITING_VARIETY = "AWAITING_VARIETY"
STATE_AWAITING_ROOM_TEMP = "AWAITING_ROOM_TEMP"
STATE_AWAITING_HUMIDITY = "AWAITING_HUMIDITY"
STATE_AWAITING_PH = "AWAITING_PH"
STATE_AWAITING_EC = "AWAITING_EC"
STATE_AWAITING_WATER_TEMP = "AWAITING_WATER_TEMP"
STATE_AWAITING_DAYS_CONFIRM = "AWAITING_DAYS_CONFIRM" # For Phase 1
STATE_AWAITING_PHOTO_LOT = "AWAITING_PHOTO_LOT"
STATE_AWAITING_PHOTO_CATEGORY = "AWAITING_PHOTO_CATEGORY"
STATE_AWAITING_PHOTO_UPLOAD = "AWAITING_PHOTO_UPLOAD"

import datetime

def get_quick_reply(options):
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label=opt, text=opt)) for opt in options
    ])

def calculate_days_and_phase(seeding_date_str):
    try:
        seeding_date = datetime.datetime.strptime(seeding_date_str, '%Y-%m-%d').date()
        days = (datetime.date.today() - seeding_date).days + 1
        phase = 2 if days >= 22 else 1
        return days, phase
    except Exception:
        return 0, 1

def handle_interactive_step(user_id, state, text, active_lots=[]):
    """
    Handles a single step in the interactive reporting flow.
    Returns (response_msg, next_state, data_to_update, quick_reply)
    """
    if state == STATE_AWAITING_LOT:
        # User selected a lot
        lot = next((l for l in active_lots if l['ロット名/品種'] == text), None)
        if not lot:
            return ("リストからロットを選択してください。", state, {}, get_quick_reply([l['ロット名/品種'] for l in active_lots]))
        
        days, phase = calculate_days_and_phase(str(lot['種まき日']))
        data = {"lot_name": text, "seeding_date": str(lot['種まき日']), "variety": lot.get('品種', 'レタス'), "days": days}
        
        if phase == 1:
            return (f"【{text}】（種まきから{days}日目）を確認しました。現在の状態について一言、または写真を送ってください。", 
                    STATE_AWAITING_DAYS_CONFIRM, data, None)
        else:
            return (f"【{text}】（種まきから{days}日目：本栽培期）の報告を開始します。まずは【栽培段数】を選択してください。", 
                    STATE_AWAITING_STAGE, data, get_quick_reply(["1段目", "2段目", "3段目"]))

    elif state == STATE_AWAITING_PHOTO_LOT:
        # User selected a lot for a PHOTO report
        lot = next((l for l in active_lots if l['ロット名/品種'] == text), None)
        if not lot:
            return ("リストからロットを選択してください。", state, {}, get_quick_reply([l['ロット名/品種'] for l in active_lots]))
        
        days, phase = calculate_days_and_phase(str(lot['種まき日']))
        data = {"lot_name": text, "seeding_date": str(lot['種まき日']), "variety": lot.get('品種', 'レタス'), "days": days, "phase": phase}
        
        categories = ["種から発芽", "定植後（成長期）", "収穫間近", "異常発生"]
        return (f"【{text}】は現在「{days}日目」ですね。現在の状況カテゴリを選択してください。", 
                STATE_AWAITING_PHOTO_CATEGORY, data, get_quick_reply(categories))

    elif state == STATE_AWAITING_PHOTO_CATEGORY:
        # Category selected
        return (f"カテゴリ「{text}」で受け付けました。次に【写真を送信】してください。", 
                STATE_AWAITING_PHOTO_UPLOAD, {"category": text}, None)

    elif state == STATE_AWAITING_DAYS_CONFIRM:
        # Phase 1 completion
        return ("報告ありがとうございます。苗の状態を記録しました。", "DONE", {"remarks": text, "stage": f"{extract_number(text) or ''}日目"}, None)

    elif state == STATE_AWAITING_STAGE:
        return (f"【{text}】を記録しました。次に【pH】を入力してください。", 
                STATE_AWAITING_PH, 
                {"stage": text}, 
                None)

    elif state == STATE_AWAITING_PH:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。pHは？", state, {}, None)
        msg, _ = check_standard("ph", val)
        return (f"{msg}\n次に【EC】を入力してください。", 
                STATE_AWAITING_EC, 
                {"ph": val}, 
                None)

    elif state == STATE_AWAITING_EC:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。ECは？", state, {}, None)
        msg, _ = check_standard("ec", val)
        return (f"{msg}\n次に【水温】を入力してください。", 
                STATE_AWAITING_WATER_TEMP, 
                {"ec": val}, 
                None)

    elif state == STATE_AWAITING_WATER_TEMP:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。水温は？", state, {}, None)
        msg, _ = check_standard("water_temp", val)
        return (f"{msg}\n次に【室温】を入力してください。", 
                STATE_AWAITING_ROOM_TEMP, 
                {"water_temp": val}, 
                None)

    elif state == STATE_AWAITING_ROOM_TEMP:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。室温は？", state, {}, None)
        return ("記録しました。最後に【湿度】を入力してください（％）。", 
                STATE_AWAITING_HUMIDITY, 
                {"room_temp": val}, 
                None)

    elif state == STATE_AWAITING_HUMIDITY:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。湿度は？", state, {}, None)
        return ("すべてのデータの記録が完了しました！お疲れ様でした。", 
                "DONE", 
                {"humidity": val}, 
                None)

    return ("エラーが発生しました。もう一度「数値報告」から開始してください。", None, {}, None)

def extract_number(text):
    match = re.search(r'([\d\.]+)', text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def parse_and_diagnose(text):
    """
    Parses user text for one-off reports, identifies metrics or trouble keywords.
    """
    text = text.lower()
    
    # Initialize data
    data = {
        "category": "不明",
        "status": "情報",
        "metric_type": "Unknown",
        "value": None,
        "humidity": None,
        "stage": None,
        "variety": "レタス"
    }

    # Variety and Stage Parsing
    stage_match = re.search(r'(\d+)\s*[段週]', text)
    if stage_match:
        data["stage"] = f"{stage_match.group(1)}段/週"
    
    varieties = ["レタス", "水菜", "ルッコラ", "その他"]
    for v in varieties:
        if v in text:
            data["variety"] = v
            break

    # Trouble Keywords
    for key, response in TROUBLE_RESPONSES.items():
        if key in text or key in text.replace(" ", ""):
            data.update({"category": "トラブル報告", "status": "異常", "metric_type": "Trouble", "value": key})
            return response, data

    # Metric Parsing
    # pH
    match = re.search(r'ph[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("ph", val)
        data.update({"category": "数値報告", "status": status, "metric_type": "pH", "value": val, "ph": val})
        return msg, data

    # EC
    match = re.search(r'ec[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("ec", val)
        data.update({"category": "数値報告", "status": status, "metric_type": "EC", "value": val, "ec": val})
        return msg, data

    # Water Temp
    match = re.search(r'水温[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("water_temp", val)
        data.update({"category": "数値報告", "status": status, "metric_type": "Water Temp", "value": val, "water_temp": val})
        return msg, data

    # Room Temp
    match = re.search(r'室温[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("room_temp", val)
        data.update({"category": "数値報告", "status": status, "metric_type": "Room Temp", "value": val, "room_temp": val})
        return msg, data

    # Humidity
    match = re.search(r'湿度[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        data.update({"category": "数値報告", "status": "情報", "metric_type": "Humidity", "value": val, "humidity": val})
        return f"湿度 {val}% を記録しました。", data

    # Image Labels from Quick Reply
    labels = ["葉の様子", "根の状態", "ボックスの汚れ", "その他"]
    for label in labels:
        if label in text:
            data.update({"category": "画像報告", "status": "情報", "metric_type": "Image Category", "value": label})
            return f"「{label}」として分類・保存しました。", data

    return None, data

def check_standard(metric_key, val):
    std = STANDARDS.get(metric_key)
    if not std:
        return f"{metric_key} の基準値設定が見つかりません", "異常"

    lbl_map = {"ph": "pH", "ec": "EC", "water_temp": "水温", "room_temp": "室温"}
    label = lbl_map.get(metric_key, metric_key)
    min_val, max_val = std["min"], std["max"]

    if val < min_val:
        return f"基準値({min_val}-{max_val})を下回っています。{std['low_action']}", "異常"
    elif val > max_val:
        return f"基準値({min_val}-{max_val})を超えています。{std['high_action']}", "異常"
    else:
        return f"【{label}】は正常です（基準: {min_val}-{max_val}）。", "正常"

def handle_image():
    return "画像を確認しました。異常があれば通知します。"
