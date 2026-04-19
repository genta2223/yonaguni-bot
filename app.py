import os
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage,
    PostbackEvent, QuickReply, QuickReplyButton, MessageAction, PostbackAction
)
from bot_logic import (
    handle_interactive_step, get_quick_reply,
    STATE_AWAITING_LOT, STATE_AWAITING_CATEGORY, STATE_AWAITING_STAGE,
    STATE_AWAITING_PH, STATE_AWAITING_ROOM_TEMP, STATE_AWAITING_HUMIDITY,
    STATE_AWAITING_PHOTO_UPLOAD, STATE_AWAITING_PLANT_VARIETY
)
from storage import save_log, init_db, get_active_lots

load_dotenv()
init_db()
app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_GROUP_ID = os.getenv('LINE_GROUP_ID', 'C8b9dbb6dc99308366f28c0e136f67a55')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

USER_STATES = {}
USER_DATA = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    data = event.postback.data
    
    # Always reset state on new button press for reliability
    USER_STATES.pop(user_id, None)
    USER_DATA.pop(user_id, None)

    if data == "action=planting_report":
        USER_STATES[user_id] = STATE_AWAITING_PLANT_VARIETY
        USER_DATA[user_id] = {"mode": "planting"}
        reply_text = "【与那国水耕栽培】作付け報告（新規登録）を開始します。\nまずは【野菜の種類】を選択してください。"
        quick_reply = get_quick_reply(["レタス", "水菜", "ルッコラ"])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text, quick_reply=quick_reply))

    elif data == "action=numeric_report":
        active_lots = get_active_lots()
        if not active_lots:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="現在稼働中のロットがありません。"))
            return
        USER_STATES[user_id] = STATE_AWAITING_LOT
        USER_DATA[user_id] = {"mode": "numerical"}
        reply_text = "【与那国水耕栽培】数値報告を開始します。まずは【対象ロット】を選択してください。"
        quick_reply = get_quick_reply([l['ロット名/品種'] for l in active_lots])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text, quick_reply=quick_reply))

    elif data == "action=status_check":
        active_lots = get_active_lots()
        if not active_lots:
            reply = "現在稼働中のロットはありません。"
        else:
            lot_list = []
            for l in active_lots:
                from bot_logic import calculate_days_and_phase
                days, _ = calculate_days_and_phase(str(l['種まき日']))
                lot_list.append(f"・{l['ロット名/品種']} ({days}日目)")
            reply = "【現在の稼働ロット】\n" + "\n".join(lot_list)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    elif data == "action=inquiry":
        reply = ("【お問い合わせ】管理責任者まで直接ご連絡ください。\n"
                 "マニュアル：https://docs.google.com/spreadsheets/d/1hV0EgMDl0lE6DdD5hlstK4Bnc_CuP5r18fKNnO_8aYw/edit")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    
    if event.source.type != 'user':
        return # Ignore group messages for guided flow

    if user_text in ["キャンセル", "中止"]:
        USER_STATES.pop(user_id, None)
        USER_DATA.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="中断しました。"))
        return

    if user_id in USER_STATES:
        state = USER_STATES[user_id]
        active_lots = get_active_lots()
        msg, next_state, data_update, qr = handle_interactive_step(user_id, state, user_text, active_lots)
        
        if user_id not in USER_DATA: USER_DATA[user_id] = {}
        USER_DATA[user_id].update(data_update)

        if next_state == "DECIDE_PHASE":
            phase = USER_DATA[user_id].get("phase", 1)
            if phase == 1:
                USER_STATES[user_id] = STATE_AWAITING_ROOM_TEMP
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="苗期（第1-3週）のためpH計測は不要です。現在の【室温】を入力してください。"))
            else:
                USER_STATES[user_id] = STATE_AWAITING_STAGE
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="【栽培段数】を選択してください。", quick_reply=get_quick_reply(["1段目", "2段目", "3段目"])))
            return

        if next_state == "DONE_PLANTING":
            final_data = USER_DATA.pop(user_id, {})
            try: profile = line_bot_api.get_profile(user_id); user_name = profile.display_name
            except: user_name = "管理者"
            
            from storage import save_new_lot
            lot_name = save_new_lot(user_name, final_data.get("variety"), final_data.get("seeding_date"), final_data.get("qty"))
            USER_STATES.pop(user_id, None)
            
            reply = f"作付け登録を完了しました！新しいロット【{lot_name}】を作成しました。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            
            if LINE_GROUP_ID:
                summary = f"🌱 【新規作付け報告】\n報告者：{user_name}\n野菜：{final_data.get('variety')}\n種まき日：{final_data.get('seeding_date')}\n予定数量：{final_data.get('qty')}"
                try: line_bot_api.push_message(LINE_GROUP_ID, TextSendMessage(text=summary))
                except: pass
            return

        if next_state == "DONE":
            final_data = USER_DATA.pop(user_id, {})
            try: profile = line_bot_api.get_profile(user_id); user_name = profile.display_name
            except: user_name = "管理者"
            save_log(user_id, user_name, final_data, f"[Flow] {final_data}")
            USER_STATES.pop(user_id, None)
            reply = f"報告を完了しました。記録ありがとうございました！\n（カテゴリ：{final_data.get('category')}）"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            send_group_summary(user_name, final_data)
            return

        if next_state:
            USER_STATES[user_id] = next_state
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg, quick_reply=qr))
        else:
            USER_STATES.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    if USER_STATES.get(user_id) == STATE_AWAITING_PHOTO_UPLOAD:
        final_data = USER_DATA.pop(user_id, {})
        final_data["image_url"] = event.message.id
        try: profile = line_bot_api.get_profile(user_id); user_name = profile.display_name
        except: user_name = "管理者"
        save_log(user_id, user_name, final_data, f"[Image Flow]", image_url=event.message.id)
        USER_STATES.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="写真を保存し、すべての報告を完了しました！"))
        send_group_summary(user_name, final_data, has_photo=True)
    elif user_id in USER_STATES:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="数値の入力が完了していません。まずは数値を入力してください。"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="報告を開始してから写真を送ってください（メニューを選択）。"))

def send_group_summary(user_name, data, has_photo=False):
    if not LINE_GROUP_ID: return
    category = data.get('category', '一般')
    header = "🌱 発芽報告" if category == "種から発芽" else "【与那国水耕栽培 報告】"
    metrics = f"pH: {data.get('ph','-')} / EC: {data.get('ec','-')}\n室温: {data.get('room_temp','-')}℃ / 湿度: {data.get('humidity','-')}%"
    summary = f"{header}\n報告者：{user_name}\nロット：{data.get('lot_name')}\n{metrics}\n写真：{'あり' if has_photo else 'なし'}"
    try: line_bot_api.push_message(LINE_GROUP_ID, TextSendMessage(text=summary))
    except: pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
