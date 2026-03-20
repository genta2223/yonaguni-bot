import os
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage
)

from bot_logic import parse_and_diagnose, handle_image
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

# Add QuickReply imports
from linebot.models import QuickReply, QuickReplyButton, MessageAction

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error(f"Invalid signature detected from IP: {request.remote_addr}")
        if ADMIN_USER_ID:
            try:
                line_bot_api.push_message(ADMIN_USER_ID, TextSendMessage(text=f"[警告] 不正な署名(Invalid Signature)のアクセスがありました。IP: {request.remote_addr}"))
            except Exception as e:
                pass
        abort(400)
    except Exception as e:
        app.logger.error(f"Server Error: {str(e)}")
        if ADMIN_USER_ID:
            try:
                line_bot_api.push_message(ADMIN_USER_ID, TextSendMessage(text=f"[エラー] システムエラーが発生しました: {str(e)}"))
            except Exception:
                pass

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text

    # Parse logic
    response_msg, parsed_data = parse_and_diagnose(user_text)

    # Save to CSV
    if parsed_data:
        category, status, metric_type, val = parsed_data
        save_log(user_id, category, status, metric_type, val, user_text)
    else:
        save_log(user_id, "不明", "情報", "Unknown", None, user_text)

    # Reply
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=response_msg)
    )

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id
    
    # Save log for image
    save_log(user_id, "画像報告", "情報", "Image", None, "[Image Received]")

    # Reply with Phase 1 Quick Reply
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="葉の様子", text="葉の様子")),
        QuickReplyButton(action=MessageAction(label="根の状態", text="根の状態")),
        QuickReplyButton(action=MessageAction(label="ボックスの汚れ", text="ボックスの汚れ")),
        QuickReplyButton(action=MessageAction(label="その他", text="その他"))
    ])

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text="画像を受信しました。将来の学習のため、画像のカテゴリを選択してください。",
            quick_reply=quick_reply
        )
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
