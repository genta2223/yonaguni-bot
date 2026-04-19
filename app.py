import os
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage,
    QuickReply, QuickReplyButton, MessageAction
)

from bot_logic import (
    parse_and_diagnose, handle_image, handle_interactive_step, get_quick_reply,
    STATE_AWAITING_STAGE, STATE_AWAITING_VARIETY, STATE_AWAITING_LOT
)
from storage import save_log, init_db, get_active_lots

load_dotenv()

# Initialize DB on startup
init_db()

app = Flask(__name__)

# LINE Bot credentials from environment variables
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', 'YOUR_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_ACCESS_TOKEN')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '')
LINE_GROUP_ID = os.getenv('LINE_GROUP_ID', '')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Session states (Reset on server restart)
USER_STATES = {}
USER_DATA = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        app.logger.error(f"Server Error: {str(e)}")
        abort(500)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    source_type = event.source.type
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    
    # 0. Group/Room Support & ID Discovery
    is_group = (source_type == 'group')
    is_room = (source_type == 'room')
    is_private = (source_type == 'user')
    
    # ID for push messages (Group ID or Room ID)
    target_id = None
    if is_group: target_id = event.source.group_id
    elif is_room: target_id = event.source.room_id
    
    # ID Discovery Command (Handle mentions)
    if "探査" in user_text:
        reply = f"この場所の種別: {source_type}\nこの場所のID:\n{target_id if target_id else user_id}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if not is_private:
        # Restrict reporting in groups/rooms (Redirect to solo)
        # Using 'in' to handle mentions
        if "数値報告" in user_text or "写真報告" in user_text:
            reply = "数値報告は【個人チャット】でのみ受け付けています。\nご自身のトーク画面へ移動してメニューから報告を開始してください。完了後にこの場所へ要約を共有します！"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # --- Below this point is Solo Chat (User) logic ---

    # Cancel command
    if user_text in ["キャンセル", "戻る", "中止"]:
        USER_STATES.pop(user_id, None)
        USER_DATA.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="入力を中断しました。"))
        return

    # 1. State-based handling
    if user_id in USER_STATES:
        state = USER_STATES[user_id]
        active_lots = get_active_lots()
        response_msg, next_state, data_update, quick_reply = handle_interactive_step(user_id, state, user_text, active_lots)
        
        if user_id not in USER_DATA: USER_DATA[user_id] = {}
        USER_DATA[user_id].update(data_update)

        if next_state == "DONE":
            # Get user name
            try:
                profile = line_bot_api.get_profile(user_id)
                user_name = profile.display_name
            except Exception:
                user_name = "管理者"
            
            final_data = USER_DATA.pop(user_id, {})
            save_log(user_id, user_name, final_data, f"[Guided] {final_data}")
            USER_STATES.pop(user_id, None)
            
            # Send reply to user
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_msg))
            
            # 2. Push summary to Group
            if LINE_GROUP_ID:
                lot_name = final_data.get('lot_name', '不明')
                days = final_data.get('days', '?')
                if final_data.get('ph'): # Phase 2
                    summary = (f"📢 報告完了：{lot_name}\n"
                               f"（種まきから{days}日目）\n"
                               f"栽培段数: {final_data.get('stage')}\n"
                               f"pH: {final_data.get('ph')}  EC: {final_data.get('ec')}\n"
                               f"水温: {final_data.get('water_temp')}℃\n"
                               f"報告者: {user_name}")
                else: # Phase 1
                    summary = (f"🌱 芽が出ました：{lot_name}\n"
                               f"（種まきから{days}日目）\n"
                               f"状況: {final_data.get('remarks', '順調です')}\n"
                               f"報告者: {user_name}")
                
                try:
                    line_bot_api.push_message(LINE_GROUP_ID, TextSendMessage(text=summary))
                except Exception as e:
                    print(f"Error pushing to group: {e}")
        elif next_state:
            USER_STATES[user_id] = next_state
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_msg, quick_reply=quick_reply))
        else:
            USER_STATES.pop(user_id, None)
            USER_DATA.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_msg))
        return

    # 3. Trigger Numerical Report Flow (Priority)
    if "数値報告" in user_text:
        active_lots = get_active_lots()
        if not active_lots:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="現在、稼働中の栽培ロットがありません。「栽培マスター」シートにロットを追加してください。"))
            return
            
        USER_STATES[user_id] = STATE_AWAITING_LOT
        USER_DATA[user_id] = {}
        reply_text = "【与那国水耕栽培】数値報告を開始します。\nまずは【報告対象のロット】を選択してください。"
        quick_reply = get_quick_reply([l['ロット名/品種'] for l in active_lots])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text, quick_reply=quick_reply))
        return

    # 4. Existing One-off Parser (Solo only)
    try:
        profile = line_bot_api.get_profile(user_id)
        user_name = profile.display_name
    except Exception:
        user_name = "管理者"

    response_msg, parsed_data = parse_and_diagnose(user_text)
    if parsed_data["category"] != "不明":
        save_log(user_id, user_name, parsed_data, user_text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_msg))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    message_id = event.message.id
    try:
        profile = line_bot_api.get_profile(user_id)
        user_name = profile.display_name
    except Exception:
        user_name = "Unknown User"
    
    save_log(user_id, user_name, {"category": "画像報告"}, "[Image Received]", image_url=message_id)
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="葉の様子", text="葉の様子")),
        QuickReplyButton(action=MessageAction(label="根の状態", text="根の状態")),
        QuickReplyButton(action=MessageAction(label="ボックスの汚れ", text="ボックスの汚れ")),
        QuickReplyButton(action=MessageAction(label="その他", text="その他"))
    ])
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="画像を受信しました。カテゴリを選択してください。", quick_reply=quick_reply))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
