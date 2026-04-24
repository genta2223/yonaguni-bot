import os
import io
from PIL import Image, ImageOps
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage, ImageSendMessage,
    PostbackEvent, QuickReply, QuickReplyButton, MessageAction, PostbackAction
)
from bot_logic import (
    handle_interactive_step, get_quick_reply, calculate_days_and_phase,
    STATE_AWAITING_LOT, STATE_AWAITING_CATEGORY, STATE_AWAITING_STAGE,
    STATE_AWAITING_PH, STATE_AWAITING_ROOM_TEMP, STATE_AWAITING_HUMIDITY,
    STATE_AWAITING_PHOTO_UPLOAD, STATE_AWAITING_PLANT_VARIETY
)
from storage import save_log, save_new_lot, init_db, get_active_lots, upload_image_to_drive

load_dotenv()
init_db()
app = Flask(__name__, static_folder='static', static_url_path='/static')
os.makedirs(os.path.join("static", "images"), exist_ok=True)

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_GROUP_ID = os.getenv('LINE_GROUP_ID', 'C8b9dbb6dc99308366f28c0e136f67a55')
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', 'yonaguni-hydro-2026')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

USER_STATES = {}
USER_DATA = {}


# ---------------------------------------------------------------------------
# Image processing helper (S6: extracted for future Google Drive migration)
# ---------------------------------------------------------------------------
def process_and_store_image(message_id):
    """
    Downloads image from LINE, applies EXIF rotation, saves locally.
    Returns the public URL string, or an error description on failure.
    """
    try:
        message_content = line_bot_api.get_message_content(message_id)
        chunks = []
        for chunk in message_content.iter_content():
            chunks.append(chunk)
        image_bytes = b"".join(chunks)

        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        filename = f"{message_id}.jpg"
        
        # Save to memory instead of local disk
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=85)
        processed_image_bytes = img_byte_arr.getvalue()

        # Upload to Google Drive and get the public URL
        public_url = upload_image_to_drive(processed_image_bytes, filename)
        return public_url
    except Exception as e:
        print(f"Error processing image {message_id}: {e}")
        return f"処理エラー: {e}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@app.route("/force_menu", methods=['GET'])
def force_menu():
    if request.args.get("token") != ADMIN_TOKEN:
        abort(403)
    try:
        from scripts.setup_rich_menu import setup_rich_menu
        result = setup_rich_menu()
        return f"Menu Force Update Result: {result}", 200
    except Exception as e:
        import traceback
        return f"Error: {str(e)}\n{traceback.format_exc()}", 500


@app.route("/test_log", methods=['GET'])
def test_log():
    if request.args.get("token") != ADMIN_TOKEN:
        abort(403)
    try:
        result = save_log('dummy_id', 'TestUser', {'category': 'テスト', 'lot_name': 'TestLot'}, 'Direct log test', image_url='https://example.com/test_image.jpg')
        return f"Test log result: {result}", 200
    except Exception as e:
        import traceback
        return f"Log Error: {str(e)}\n{traceback.format_exc()}", 500


# ---------------------------------------------------------------------------
# Postback handler (rich menu buttons)
# ---------------------------------------------------------------------------
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
                days, _ = calculate_days_and_phase(str(l['種まき日']))
                lot_list.append(f"・{l['ロット名/品種']} ({days}日目)")
            reply = "【現在の稼働ロット】\n" + "\n".join(lot_list)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))


# ---------------------------------------------------------------------------
# Text message handler (state machine driver)
# ---------------------------------------------------------------------------
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()

    if event.source.type != 'user':
        return  # Ignore group messages for guided flow

    if user_text in ["キャンセル", "中止", "やめる"]:
        USER_STATES.pop(user_id, None)
        USER_DATA.pop(user_id, None)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="入力をキャンセルしました。最初からやり直してください。"))
        return

    # Handle rich menu text commands
    if user_text == "作付け報告（新規登録）を開始します":
        USER_STATES.pop(user_id, None)
        USER_DATA.pop(user_id, None)
        USER_STATES[user_id] = STATE_AWAITING_PLANT_VARIETY
        USER_DATA[user_id] = {"mode": "planting"}
        reply_text = "【与那国水耕栽培】作付け報告（新規登録）を開始します。\nまずは【野菜の種類】を選択してください。"
        quick_reply = get_quick_reply(["レタス", "水菜", "ルッコラ"])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text, quick_reply=quick_reply))
        return

    elif user_text == "数値報告を開始します":
        USER_STATES.pop(user_id, None)
        USER_DATA.pop(user_id, None)
        active_lots = get_active_lots()
        if not active_lots:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="現在稼働中のロットがありません。"))
            return
        USER_STATES[user_id] = STATE_AWAITING_LOT
        USER_DATA[user_id] = {"mode": "numerical"}
        reply_text = "【与那国水耕栽培】数値報告を開始します。まずは【対象ロット】を選択してください。"
        quick_reply = get_quick_reply([l['ロット名/品種'] for l in active_lots])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text, quick_reply=quick_reply))
        return

    elif user_text == "栽培状況を確認します":
        USER_STATES.pop(user_id, None)
        USER_DATA.pop(user_id, None)
        active_lots = get_active_lots()
        if not active_lots:
            reply = "現在稼働中のロットはありません。"
        else:
            lot_list = []
            for l in active_lots:
                days, _ = calculate_days_and_phase(str(l['種まき日']))
                lot_list.append(f"・{l['ロット名/品種']} ({days}日目)")
            reply = "【現在の稼働ロット】\n" + "\n".join(lot_list)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if user_id in USER_STATES:
        state = USER_STATES[user_id]
        active_lots = get_active_lots()
        msg, next_state, data_update, qr = handle_interactive_step(user_id, state, user_text, active_lots)

        if user_id not in USER_DATA:
            USER_DATA[user_id] = {}
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
            try:
                profile = line_bot_api.get_profile(user_id)
                user_name = profile.display_name
            except Exception as e:
                print(f"Profile fetch failed: {e}")
                user_name = "管理者"

            lot_name = save_new_lot(user_name, final_data.get("variety"), final_data.get("seeding_date"), final_data.get("qty"), final_data.get("image_url", ""), final_data.get("memo", ""))
            USER_STATES.pop(user_id, None)

            reply = f"作付け登録を完了しました！新しいロット【{lot_name}】を作成しました。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

            if LINE_GROUP_ID:
                summary = f"🌱 【新規作付け報告】\n報告者：{user_name}\n野菜：{final_data.get('variety')}\n種まき日：{final_data.get('seeding_date')}\n予定数量：{final_data.get('qty')}"
                if final_data.get("memo") and final_data.get("memo") != "なし":
                    summary += f"\nメモ：{final_data.get('memo')}"
                if final_data.get("image_url") and final_data.get("image_url") != "なし":
                     summary += f"\n写真：{final_data.get('image_url')}"
                try:
                    line_bot_api.push_message(LINE_GROUP_ID, TextSendMessage(text=summary))
                except Exception as e:
                    print(f"Group push failed: {e}")
            return

        if next_state == "DONE":
            final_data = USER_DATA.pop(user_id, {})
            try:
                profile = line_bot_api.get_profile(user_id)
                user_name = profile.display_name
            except Exception as e:
                print(f"Profile fetch failed: {e}")
                user_name = "管理者"
            
            try:
                save_log(user_id, user_name, final_data, final_data.get("memo", ""), image_url=final_data.get("image_url", "スキップ"))
                reply = f"報告を完了しました。記録ありがとうございました！\n（カテゴリ：{final_data.get('category')}）"
                USER_STATES.pop(user_id, None)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
                send_group_summary(user_name, final_data)
            except Exception as e:
                reply = f"⚠️スプレッドシートへの保存に失敗しました。エラーログを確認してください。\n({str(e)})"
                USER_STATES.pop(user_id, None)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        if next_state:
            USER_STATES[user_id] = next_state
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg, quick_reply=qr))
        else:
            USER_STATES.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))


# ---------------------------------------------------------------------------
# Image handler
# ---------------------------------------------------------------------------
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    if USER_STATES.get(user_id) == STATE_AWAITING_PHOTO_UPLOAD:
        final_data = USER_DATA.pop(user_id, {})

        public_url = process_and_store_image(event.message.id)
        final_data["image_url"] = public_url

        try:
            profile = line_bot_api.get_profile(user_id)
            user_name = profile.display_name
        except Exception as e:
            print(f"Profile fetch failed: {e}")
            user_name = "管理者"

        try:
            if public_url.startswith("処理エラー"):
                raise Exception(public_url)
                
            save_log(user_id, user_name, final_data, final_data.get("memo", ""), image_url=public_url)
            USER_STATES.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="写真を保存し、すべての報告を完了しました！"))
            send_group_summary(user_name, final_data, has_photo=True, image_url=public_url)
        except Exception as e:
            reply_text = f"⚠️スプレッドシートやDriveへの保存に失敗しました。エラーログを確認してください。\n({str(e)})"
            USER_STATES.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    elif USER_STATES.get(user_id) == "AWAITING_PLANT_PHOTO":
        final_data = USER_DATA.pop(user_id, {})
        public_url = process_and_store_image(event.message.id)
        final_data["image_url"] = public_url

        try:
            profile = line_bot_api.get_profile(user_id)
            user_name = profile.display_name
        except Exception as e:
            print(f"Profile fetch failed: {e}")
            user_name = "管理者"

        try:
            if public_url.startswith("処理エラー"):
                raise Exception(public_url)
                
            lot_name = save_new_lot(user_name, final_data.get("variety"), final_data.get("seeding_date"), final_data.get("qty"), public_url, final_data.get("memo", ""))

            USER_STATES.pop(user_id, None)
            reply_text = f"作付け登録を完了し、写真を保存しました！新しいロット【{lot_name}】を作成しました。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            
            if LINE_GROUP_ID:
                summary = f"🌱 【新規作付け報告】\n報告者：{user_name}\nロット：{lot_name}\n種まき日：{final_data.get('seeding_date')}\n予定数量：{final_data.get('qty')}"
                if final_data.get("memo") and final_data.get("memo") != "なし":
                    summary += f"\nメモ：{final_data.get('memo')}"
                summary += f"\n写真：{public_url}"
                try:
                    line_bot_api.push_message(LINE_GROUP_ID, [
                        TextSendMessage(text=summary),
                        ImageSendMessage(original_content_url=public_url, preview_image_url=public_url)
                    ])
                except Exception as e:
                    print(f"Group summary push failed: {e}")
                    line_bot_api.push_message(LINE_GROUP_ID, TextSendMessage(text=summary))

        except Exception as e:
            reply_text = f"⚠️スプレッドシートやDriveへの保存に失敗しました。エラーログを確認してください。\n({str(e)})"
            USER_STATES.pop(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    elif user_id in USER_STATES:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="数値の入力が完了していません。まずは数値を入力してください。"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="現在、写真を受け付けるステータスではありません。\n（1回の報告につき写真は1枚のみです。新しく報告を開始する場合はメニューから選択してください）"))


# ---------------------------------------------------------------------------
# Group notification
# ---------------------------------------------------------------------------
def send_group_summary(user_name, data, has_photo=False, image_url=None):
    if not LINE_GROUP_ID:
        return
    category = data.get('category', '一般')
    header = "🌱 発芽報告" if category == "種から発芽" else "【与那国水耕栽培 報告】"
    metrics = f"pH: {data.get('ph','-')} / EC: {data.get('ec','-')}\n室温: {data.get('room_temp','-')}℃ / 湿度: {data.get('humidity','-')}%"
    
    memo_text = f"\nメモ：{data.get('memo')}" if data.get('memo') and data.get('memo') != "なし" else ""
    photo_label = image_url if has_photo and image_url and not image_url.startswith("処理エラー") else "なし"
    summary = f"{header}\n報告者：{user_name}\nロット：{data.get('lot_name')}\n{metrics}{memo_text}\n写真：{photo_label}"

    messages = [TextSendMessage(text=summary)]

    # Attach the actual photo if available
    if has_photo and image_url and not image_url.startswith("処理エラー"):
        try:
            messages.append(ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            ))
        except Exception as e:
            print(f"ImageSendMessage creation failed: {e}")

    try:
        line_bot_api.push_message(LINE_GROUP_ID, messages)
    except Exception as e:
        print(f"Group summary push failed: {e}")
        # Fallback: try sending text only if image caused the failure
        if len(messages) > 1:
            try:
                line_bot_api.push_message(LINE_GROUP_ID, messages[0])
            except Exception as e2:
                print(f"Group text-only fallback also failed: {e2}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
