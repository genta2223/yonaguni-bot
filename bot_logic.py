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

# Planting Report States
STATE_AWAITING_PLANT_VARIETY = "AWAITING_PLANT_VARIETY"
STATE_AWAITING_PLANT_DATE = "AWAITING_PLANT_DATE"
STATE_AWAITING_PLANT_QTY = "AWAITING_PLANT_QTY"

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

def handle_interactive_step(user_id, state, text, active_lots=None):
    """
    Handles a single step in the interactive reporting flow.
    Returns (response_msg, next_state, data_to_update, quick_reply)
    """
    if active_lots is None:
        active_lots = []
    if state == STATE_AWAITING_PLANT_VARIETY:
        return (f"【{text}】ですね。次に「種まき日」を入力してください。\n（例: 2026-04-19 または 本日）", 
                STATE_AWAITING_PLANT_DATE, {"variety": text}, get_quick_reply(["戻る"]))

    elif state == STATE_AWAITING_PLANT_DATE:
        if "本日" in text or "今日" in text:
            jst = datetime.timezone(datetime.timedelta(hours=9))
            date_str = datetime.datetime.now(jst).strftime('%Y-%m-%d')
        else:
            match = re.search(r'20\d{2}-\d{1,2}-\d{1,2}', text)
            if not match: return ("形式が正しくありません。「YYYY-MM-DD」または「本日」と入力してください。", state, {}, get_quick_reply(["戻る"]))
            # Ensure correct formatting with zero-padding
            try:
                date_str = datetime.datetime.strptime(match.group(0), '%Y-%m-%d').strftime('%Y-%m-%d')
            except ValueError:
                return ("無効な日付です。「YYYY-MM-DD」で入力してください。", state, {}, get_quick_reply(["戻る"]))
            
        return (f"種まき日を【{date_str}】で設定しました。最後に「予定数量」を数字で入力してください。（例: 100）", 
                STATE_AWAITING_PLANT_QTY, {"seeding_date": date_str}, get_quick_reply(["戻る"]))

    elif state == STATE_AWAITING_PLANT_QTY:
        qty = extract_number(text)
        if qty is None: return ("予定数量を数字で入力してください。", state, {}, get_quick_reply(["戻る"]))
        return ("予定数量を受け付けました。\n次に、作付けに関するメモや特記事項があれば自由に入力してください。\n（特になければ「なし」と送ってください）", 
                "AWAITING_PLANT_MEMO", {"qty": int(qty)}, get_quick_reply(["戻る", "なし"]))

    elif state == "AWAITING_PLANT_MEMO":
        memo = text if text not in ["なし", "スキップ", "skip"] else ""
        return ("最後に、作付け直後の様子の写真を1枚送信してください。\n（写真はスキップする場合「なし」と入力してください）", 
                "AWAITING_PLANT_PHOTO", {"memo": memo}, get_quick_reply(["戻る", "なし"]))

    elif state == STATE_AWAITING_LOT:
        # User selected a lot
        lot = next((l for l in active_lots if l['ロット名/品種'] == text), None)
        if not lot:
            return ("リストからロットを選択してください。", state, {}, get_quick_reply([l['ロット名/品種'] for l in active_lots]))
        
        days, phase = calculate_days_and_phase(str(lot['種まき日']))
        data = {"lot_name": text, "seeding_date": str(lot['種まき日']), "variety": lot.get('品種', 'レタス'), "days": days, "phase": phase}
        
        categories = ["種から発芽", "発芽後定植前", "定植後（成長期）", "収穫間近", "異常発生"]
        return (f"【{text}】（種まきから{days}日目）を確認しました。現在の状況カテゴリを選択してください。", 
                STATE_AWAITING_CATEGORY, data, get_quick_reply(categories + ["戻る"]))

    elif state == STATE_AWAITING_CATEGORY:
        return (f"カテゴリ「{text}」で受け付けました。次に環境数値の入力を開始します。", 
                "DECIDE_PHASE", {"category": text}, None)

    elif state == STATE_AWAITING_STAGE:
        return (f"【{text}】を記録しました。次に【pH】を入力してください。", 
                STATE_AWAITING_PH, 
                {"stage": text}, 
                get_quick_reply(["戻る"]))

    elif state == STATE_AWAITING_PH:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。pHは？", state, {}, get_quick_reply(["戻る"]))
        msg, _ = check_standard("ph", val)
        return (f"{msg}\n次に【EC】を入力してください。", 
                STATE_AWAITING_EC, 
                {"ph": val}, 
                get_quick_reply(["戻る"]))

    elif state == STATE_AWAITING_EC:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。ECは？", state, {}, get_quick_reply(["戻る"]))
        msg, _ = check_standard("ec", val)
        return (f"{msg}\n次に【水温】を入力してください。", 
                STATE_AWAITING_WATER_TEMP, 
                {"ec": val}, 
                get_quick_reply(["戻る"]))

    elif state == STATE_AWAITING_WATER_TEMP:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。水温は？", state, {}, get_quick_reply(["戻る"]))
        msg, _ = check_standard("water_temp", val)
        return (f"{msg}\n次に【室温】を入力してください。", 
                STATE_AWAITING_ROOM_TEMP, 
                {"water_temp": val}, 
                get_quick_reply(["戻る"]))

    elif state == STATE_AWAITING_ROOM_TEMP:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。室温は？", state, {}, get_quick_reply(["戻る"]))
        return ("記録しました。最後に【湿度】を入力してください（％）。", 
                STATE_AWAITING_HUMIDITY, 
                {"room_temp": val}, 
                get_quick_reply(["戻る"]))

    elif state == STATE_AWAITING_HUMIDITY:
        val = extract_number(text)
        if val is None: return ("数字で入力してください。湿度は？", state, {}, get_quick_reply(["戻る"]))
        return ("数値の入力がすべて完了しました！\n次に、メモや特記事項があれば自由に入力してください。\n（特になければ「なし」と送ってください）", 
                "AWAITING_NUMERIC_MEMO", 
                {"humidity": val}, 
                get_quick_reply(["戻る", "なし"]))

    elif state == "AWAITING_NUMERIC_MEMO":
        memo = text if text not in ["なし", "スキップ", "skip"] else ""
        return ("それでは、最後に**横向き（ランドスケープ）**で作物の写真を**1枚だけ**撮影して送信してください。\n※横向きで撮ることで、成長の比較がしやすくなります！\n（写真はスキップする場合「なし」と入力してください）", 
                STATE_AWAITING_PHOTO_UPLOAD, 
                {"memo": memo}, 
                get_quick_reply(["戻る", "なし"]))

    elif state == STATE_AWAITING_PHOTO_UPLOAD:
        if text in ["なし", "スキップ", "skip"]:
            return ("写真をスキップしました。すべての記録が完了しました！お疲れ様でした。", "DONE", {"image_url": "なし"}, None)
        return ("写真は最後に送ってください。または「なし」と入力してください。", state, {}, get_quick_reply(["戻る", "なし"]))

    elif state == "AWAITING_PLANT_PHOTO":
        if text in ["なし", "スキップ", "skip"]:
            return ("写真をスキップしました。作付け登録を完了します！", "DONE_PLANTING", {"image_url": "なし"}, None)
        return ("写真は最後に送ってください。または「なし」と入力してください。", state, {}, get_quick_reply(["戻る", "なし"]))

    return ("エラーが発生しました。もう一度メニューから報告を開始してください。", None, {}, None)

def handle_back_step(user_id, current_state, user_data, active_lots):
    """
    Handles returning to the previous state.
    Returns (response_msg, prev_state, data_keys_to_remove, quick_reply)
    """
    if active_lots is None:
        active_lots = []

    # Planting Report Back Steps
    if current_state == STATE_AWAITING_PLANT_DATE:
        return ("【野菜の種類】を再度選択してください。", 
                STATE_AWAITING_PLANT_VARIETY, ["variety"], get_quick_reply(["レタス", "水菜", "ルッコラ"]))
                
    elif current_state == STATE_AWAITING_PLANT_QTY:
        variety = user_data.get('variety', '')
        return (f"【{variety}】ですね。次に「種まき日」を再度入力してください。\n（例: 2026-04-19 または 本日）", 
                STATE_AWAITING_PLANT_DATE, ["seeding_date"], get_quick_reply(["戻る"]))

    elif current_state == "AWAITING_PLANT_MEMO":
        return ("種まき日を再設定しました。「予定数量」を再度数字で入力してください。（例: 100）", 
                STATE_AWAITING_PLANT_QTY, ["qty"], get_quick_reply(["戻る"]))

    elif current_state == "AWAITING_PLANT_PHOTO":
        return ("予定数量を受け付けました。\n作付けに関するメモや特記事項を再度入力してください。\n（特になければ「なし」と送ってください）", 
                "AWAITING_PLANT_MEMO", ["memo"], get_quick_reply(["戻る", "なし"]))

    # Numeric Report Back Steps
    elif current_state == STATE_AWAITING_CATEGORY:
        return ("対象ロットを再度選択してください。", 
                STATE_AWAITING_LOT, ["lot_name", "seeding_date", "variety", "days", "phase"], get_quick_reply([l['ロット名/品種'] for l in active_lots]))

    elif current_state == STATE_AWAITING_STAGE:
        categories = ["種から発芽", "発芽後定植前", "定植後（成長期）", "収穫間近", "異常発生"]
        lot_name = user_data.get("lot_name", "")
        days = user_data.get("days", "")
        return (f"【{lot_name}】（種まきから{days}日目）を確認しました。現在の状況カテゴリを再度選択してください。", 
                STATE_AWAITING_CATEGORY, ["category"], get_quick_reply(categories + ["戻る"]))

    elif current_state == STATE_AWAITING_PH:
        return ("【栽培段数】を再度選択してください。", 
                STATE_AWAITING_STAGE, ["stage"], get_quick_reply(["1段目", "2段目", "3段目", "戻る"]))

    elif current_state == STATE_AWAITING_EC:
        stage = user_data.get("stage", "")
        return (f"【{stage}】を記録しました。再度【pH】を入力してください。", 
                STATE_AWAITING_PH, ["ph"], get_quick_reply(["戻る"]))

    elif current_state == STATE_AWAITING_WATER_TEMP:
        return ("1つ前の項目に戻りました。再度【EC】を入力してください。", 
                STATE_AWAITING_EC, ["ec"], get_quick_reply(["戻る"]))

    elif current_state == STATE_AWAITING_ROOM_TEMP:
        phase = user_data.get("phase", 1)
        if phase == 1:
            categories = ["種から発芽", "発芽後定植前", "定植後（成長期）", "収穫間近", "異常発生"]
            lot_name = user_data.get("lot_name", "")
            days = user_data.get("days", "")
            return (f"【{lot_name}】（種まきから{days}日目）を確認しました。現在の状況カテゴリを再度選択してください。", 
                    STATE_AWAITING_CATEGORY, ["category"], get_quick_reply(categories + ["戻る"]))
        else:
            return ("1つ前の項目に戻りました。再度【水温】を入力してください。", 
                    STATE_AWAITING_WATER_TEMP, ["water_temp"], get_quick_reply(["戻る"]))

    elif current_state == STATE_AWAITING_HUMIDITY:
        return ("記録しました。再度【室温】を入力してください。", 
                STATE_AWAITING_ROOM_TEMP, ["room_temp"], get_quick_reply(["戻る"]))

    elif current_state == "AWAITING_NUMERIC_MEMO":
        return ("記録しました。再度【湿度】を入力してください（％）。", 
                STATE_AWAITING_HUMIDITY, ["humidity"], get_quick_reply(["戻る"]))

    elif current_state == STATE_AWAITING_PHOTO_UPLOAD:
        return ("数値の入力がすべて完了しました！\n再度、メモや特記事項を入力してください。\n（特になければ「なし」と送ってください）", 
                "AWAITING_NUMERIC_MEMO", ["memo"], get_quick_reply(["戻る", "なし"]))

    return (None, None, [], None)

def extract_number(text):
    match = re.search(r'([\d\.]+)', text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

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
