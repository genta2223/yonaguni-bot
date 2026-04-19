import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
# Use the generated image path
IMAGE_PATH = "rich_menu_final_v4.png"

HEADERS = {
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

def setup_rich_menu():
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("Error: LINE_CHANNEL_ACCESS_TOKEN not found in .env")
        return

    # 1. Define Rich Menu
    rich_menu_body = {
        "size": {"width": 2500, "height": 1686}, 
        "selected": True,
        "name": "Yonaguni Hydroponics Final Menu v4",
        "chatBarText": "与那国水耕メニュー",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 1250, "height": 843},
                "action": {"type": "postback", "data": "action=planting_report", "displayText": "作付け報告（新規登録）を開始します"}
            },
            {
                "bounds": {"x": 1250, "y": 0, "width": 1250, "height": 843},
                "action": {"type": "postback", "data": "action=numeric_report", "displayText": "数値報告を開始します"}
            },
            {
                "bounds": {"x": 0, "y": 843, "width": 2500, "height": 843},
                "action": {"type": "postback", "data": "action=status_check", "displayText": "栽培状況を確認します"}
            }
        ]
    }

    # 2. Create rich menu
    res = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=HEADERS,
        data=json.dumps(rich_menu_body)
    )
    if res.status_code not in [200, 201]:
        print(f"Failed to create rich menu: {res.text}")
        return
    
    rich_menu_id = res.json()["richMenuId"]
    print(f"Created Rich Menu ID: {rich_menu_id}")

    # 3. Upload image
    with open(IMAGE_PATH, 'rb') as f:
        img_res = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
            headers={
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "image/png"
            },
            data=f
        )
    if img_res.status_code != 200:
        print(f"Failed to upload image: {img_res.text}")
        return
    print("Successfully uploaded Rich Menu image.")

    # 4. Set as default
    default_res = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
        headers=HEADERS
    )
    if default_res.status_code != 200:
        print(f"Failed to set default rich menu: {default_res.text}")
        return
    print("Successfully set as default rich menu!")

if __name__ == "__main__":
    setup_rich_menu()
