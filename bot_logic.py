import re
from linebot.models import QuickReply, QuickReplyButton, MessageAction
from config import STANDARDS, TROUBLE_RESPONSES
import datetime

# Conversation States
STATE_AWAITING_LOT = "AWAITING_LOT"
STATE_AWAITING_CATEGORY = "AWAITING_CATEGORY"
STATE_AWAITING_STAGE = "AWAITING_STAGE"
STATE_AWAITING_PH = "AWAITING_PH"
STATE_AWAITING_EC = "AWAITING_EC"
STATE_AWAITING_WATER_TEMP = "AWAITING_WATER_TEMP"
STATE_AWAITING_ROOM_TEMP = "AWAITING_ROOM_TEMP"
STATE_AWAITING_HUMIDITY = "AWAITING_HUMIDITY"
STATE_AWAITING_PHOTO_UPLOAD = "AWAITING_PHOTO_UPLOAD"

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
        data = {"lot_name": text, "seeding_date": str(lot['種まき日']), "variety": lot.get('品種', 'レタス'), "days": days, "phase": phase}
        
        categories = ["種から発芽", "定植後（成長期）", "収穫間近", "異常発生"]
        return (f"【{text}】（種まきから{days}日目）を確認しました。現在の状況カテゴリを選択してください。", 
                STATE_AWAITING_CATEGORY, data, get_quick_reply(categories))

    elif state == STATE_AWAITING_CATEGORY:
        return (f"カテゴリ「{text}」で受け付けました。次に環境数値の入力を開始します。", 
                "DECIDE_PHASE", {"category": text}, None)

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
        return ("数値の入力がすべて完了しました！最後に【現在の様子の写真】を送ってください。\n（写真はスキップする場合「なし」と入力してください）", 
                STATE_AWAITING_PHOTO_UPLOAD, 
                {"humidity": val}, 
                None)

    elif state == STATE_AWAITING_PHOTO_UPLOAD:
        if text in ["なし", "スキップ", "skip"]:
            return ("写真をスキップしました。すべての記録が完了しました！お疲れ様でした。", "DONE", {"image_url": "なし"}, None)
        return ("写真は最後に送ってください。または「なし」と入力してください。", state, {}, None)

    return ("エラーが発生しました。もう一度メニューから報告を開始してください。", None, {}, None)

def extract_number(text):
    match = re.search(r'([\d\.]+)', text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def parse_and_diagnose(text):
    data = {"category": "不明", "status": "情報", "metric_type": "Unknown", "value": None}
    return None, data

def check_standard(metric_key, val):
    std = STANDARDS.get(metric_key)
    if not std: return f"{metric_key} の基準値設定が見つかりません", "異常"
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
