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
    STATE_AWAITING_STAGE, STATE_AWAITING_VARIETY
)
from storage import save_log, init_db

load_dotenv()

# Initialize DB on startup
init_db()

app = Flask(__name__)

# LINE Bot credentials from environment variables
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', 'YOUR_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_ACCESS_TOKEN')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID', '')

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
    
    # 0. Group Support & Mention Logic
    is_group = (source_type == 'group')
    mention_found = False
    
    # Check for mention (LINE SDK v3 property if available, but let's check text)
    if is_group:
        # Check if the message is specifically for the bot
        # Typical mention format: "@BotName Numerical Report"
        if user_text.startswith("@") or "数値報告" in user_text or "写真報告" in user_text:
            mention_found = True
        
        # If no mention and not a direct command, ignore to avoid cluttering spreadsheet
        if not mention_found and user_text not in ["数値報告", "写真報告", "栽培状況確認", "キャンセル"]:
            return

    # Cancel command
    if user_text in ["キャンセル", "戻る", "中止"]:
        USER_STATES.pop(user_id, None)
        USER_DATA.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="入力を中断しました。"))
        return

    # 1. State-based handling
    if user_id in USER_STATES:
        state = USER_STATES[user_id]
        response_msg, next_state, data_update, quick_reply = handle_interactive_step(user_id, state, user_text)
        
        if user_id not in USER_DATA: USER_DATA[user_id] = {}
        USER_DATA[user_id].update(data_update)

        if next_state == "DONE":
            # Get user name (Handle groups)
            try:
                if is_group:
                    profile = line_bot_api.get_group_member_profile(event.source.group_id, user_id)
                else:
                    profile = line_bot_api.get_profile(user_id)
                user_name = profile.display_name
            except Exception:
                user_name = "Unknown User"
            
            final_data = USER_DATA.pop(user_id, {})
            save_log(user_id, user_name, final_data, f"[Guided] {final_data}")
            USER_STATES.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_msg))
        elif next_state:
            USER_STATES[user_id] = next_state
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_msg, quick_reply=quick_reply))
        else:
            USER_STATES.pop(user_id, None)
            USER_DATA.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response_msg))
        return

    # 2. Trigger Numerical Report Flow (Priority)
    if "数値報告" in user_text:
        USER_STATES[user_id] = STATE_AWAITING_STAGE
        USER_DATA[user_id] = {}
        reply_text = "【与那国水耕栽培】数値報告を開始します。中止する場合は「キャンセル」と打ってください。\n\nまずは【栽培段数】を選択してください。"
        quick_reply = get_quick_reply(["1段目（1-2週目）", "2段目（3-4週目）", "3段目（5-6週目）"])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text, quick_reply=quick_reply))
        return

    # 3. Existing One-off Parser
    try:
        if is_group:
            profile = line_bot_api.get_group_member_profile(event.source.group_id, user_id)
        else:
            profile = line_bot_api.get_profile(user_id)
        user_name = profile.display_name
    except Exception:
        user_name = "Unknown User"

    response_msg, parsed_data = parse_and_diagnose(user_text)
    # Check if the text actually looks like a report before logging (to avoid junk in groups)
    if is_group and parsed_data["category"] == "不明":
        return

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
