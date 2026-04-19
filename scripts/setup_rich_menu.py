import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
# Use the generated image path
IMAGE_PATH = r"C:\Users\genta\.gemini\antigravity\brain\25ab8214-db12-46b5-a087-6cb1562f0fc1\rich_menu_yonaguni_1776589733888.png"

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
        "name": "Yonaguni Hydroponics Menu",
        "chatBarText": "メニューを開く",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 1250, "height": 843},
                "action": {"type": "message", "text": "数値報告"}
            },
            {
                "bounds": {"x": 1250, "y": 0, "width": 1250, "height": 843},
                "action": {"type": "camera", "label": "写真報告"}
            },
            {
                "bounds": {"x": 0, "y": 843, "width": 1250, "height": 843},
                "action": {"type": "message", "text": "栽培状況確認"}
            },
            {
                "bounds": {"x": 1250, "y": 843, "width": 1250, "height": 843},
                "action": {"type": "uri", "uri": "https://docs.google.com/spreadsheets/d/1hV0EgMDl0lE6DdD5hlstK4Bnc_CuP5r18fKNnO_8aYw/edit"}
            }
        ]
    }

    # 2. Create rich menu
    res = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=HEADERS,
        data=json.dumps(rich_menu_body)
    )
    if res.status_code != 201:
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
