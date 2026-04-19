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
    STATE_AWAITING_STAGE, STATE_AWAITING_VARIETY, STATE_AWAITING_LOT,
    STATE_AWAITING_PHOTO_LOT, STATE_AWAITING_PHOTO_CATEGORY, STATE_AWAITING_PHOTO_UPLOAD,
    STATE_AWAITING_PH
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
            row_info = save_log(user_id, user_name, final_data, f"[Guided] {final_data}")
            USER_STATES.pop(user_id, None)
            
            # Enhancing the reply to user
            category = final_data.get('category', '')
            cat_msg = f"（カテゴリ：{category}）" if category else ""
            reply_text = f"{response_msg}\n{cat_msg}スプレッドシートの {row_info} に記録しました！"
            
            # Send reply to user
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            
            # 2. Push summary to Group
            if LINE_GROUP_ID:
                lot_name = final_data.get('lot_name', '不明')
                days = final_data.get('days', '?')
                week = (int(days) - 1) // 7 + 1
                category = final_data.get('category', '一般')
                
                # Special header for sprout reports
                header = "🌱 発芽報告" if category == "種から発芽" else "【与那国水耕栽培 報告】"
                    status_text = (f"段数: {final_data.get('stage')}\n"
                                   f"pH: {final_data.get('ph')}  EC: {final_data.get('ec')}\n"
                                   f"水温: {final_data.get('water_temp')}℃")
                else: # Phase 1 (Wk 1-3)
                    status_text = f"経過日数: {days}日目（順調です）"

                summary = (f"【与那国水耕栽培 報告】\n"
                           f"報告者：{user_name}さん\n"
                           f"野菜：{lot_name}（第{week}週目）\n"
                           f"状態：\n{status_text}\n"
                           f"写真：[画像報告を確認してください]") # Image links logic is complex, keeping it descriptive
                
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

    # 3. Trigger Numerical/Photo Report Flows
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

    if "写真報告" in user_text:
        active_lots = get_active_lots()
        if not active_lots:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ロットが登録されていません。"))
            return
        USER_STATES[user_id] = STATE_AWAITING_PHOTO_LOT
        USER_DATA[user_id] = {}
        reply_text = "【写真報告】を開始します。どのロットの写真ですか？"
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
    
    # Check if we are in the middle of a photo flow
    if user_id in USER_STATES and USER_STATES[user_id] == STATE_AWAITING_PHOTO_UPLOAD:
        # Received Expected Image
        if user_id not in USER_DATA: USER_DATA[user_id] = {}
        # We store the image ID or URL here
        # For now, we use message_id as placeholder URL
        USER_DATA[user_id]["image_url"] = message_id
        
        # Determine next step based on Phase
        data = USER_DATA[user_id]
        phase = data.get("phase", 1)
        
        if phase == 1:
            # Finish for Phase 1
            # We fulfill the logic by calling a fake interactive step or just manually finishing
            response_msg = "画像を保存しました。第1週〜3週（苗期）のため、これで報告を終了します。ありがとうございました！"
            
            # Perform DONE logic (similar to TextMessage)
            try:
                profile = line_bot_api.get_profile(user_id)
                user_name = profile.display_name
            except Exception:
                user_name = "管理者"
            
            final_data = USER_DATA.pop(user_id, {})
            row_info = save_log(user_id, user_name, final_data, f"[Photo Flow] {final_data}", image_url=message_id)
            USER_STATES.pop(user_id, None)
            
            category = final_data.get('category', '種から発芽')
            reply_text = f"{response_msg}\n（カテゴリ：{category}）スプレッドシートの {row_info} に記録しました！"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            
            # Push to Group
            if LINE_GROUP_ID:
                lot_name = final_data.get('lot_name', '不明')
                days = final_data.get('days', '?')
                week = (int(days) - 1) // 7 + 1
                header = "🌱 発芽報告" if category == "種から発芽" else "【与那国水耕栽培 報告】"
                summary = (f"{header}\n"
                           f"報告者：{user_name}さん\n"
                           f"野菜：{lot_name}（第{week}週目）\n"
                           f"状態：\n経過日数: {days}日目（{category}）\n"
                           f"写真：[画像を確認してください]")
                try:
                    line_bot_api.push_message(LINE_GROUP_ID, TextSendMessage(text=summary))
                except Exception as e:
                    print(f"Error pushing to group: {e}")
        else:
            # Phase 2: Move to Numerical Entry
            USER_STATES[user_id] = STATE_AWAITING_PH
            reply_text = "画像を受信しました。続けて栽培環境の数値を入力してください。まずは【pH】はいくつですか？"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return

    # Cold Upload (Not in a flow)
    try:
        profile = line_bot_api.get_profile(user_id)
        user_name = profile.display_name
    except Exception:
        user_name = "Unknown User"
    
    # Ask for Lot if cold upload
    active_lots = get_active_lots()
    if active_lots:
        USER_STATES[user_id] = STATE_AWAITING_PHOTO_LOT
        USER_DATA[user_id] = {"pending_image_url": message_id} # Save image id temporarily
        reply = "画像を受信しました。どのロットの写真ですか？（選択すると詳細な詳細記録が可能です）"
        quick_reply = get_quick_reply([l['ロット名/品種'] for l in active_lots])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply, quick_reply=quick_reply))
    else:
        save_log(user_id, user_name, {"category": "画像報告"}, "[Static Upload]", image_url=message_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="画像を保存しました。（ロット未選択）"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
