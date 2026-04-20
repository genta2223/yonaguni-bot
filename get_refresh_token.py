import os
from google_auth_oauthlib.flow import InstalledAppFlow

# Drive and Sheets scopes
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets'
]

def main():
    if not os.path.exists('credentials.json'):
        print("\n" + "="*60)
        print("🚨 エラー: 'credentials.json' が見つかりません。")
        print("以下の手順で事前に OAuth 2.0 クライアント ID を作成してください：\n")
        print("1. Google Cloud Console (https://console.cloud.google.com/) にアクセス")
        print("2. 左側メニューから [APIとサービス] > [認証情報] を開く")
        print("3. 画面上部の [+ 認証情報を作成] > [OAuth クライアント ID] をクリック")
        print("4. アプリケーションの種類を「デスクトップ アプリ」にして作成")
        print("5. 完了画面で「JSON をダウンロード」をクリック")
        print("6. ダウンロードしたファイルの名前を「credentials.json」に変更し、")
        print("   この python スクリプトと同じフォルダ（Ecojima-Bot内）に配置してください。")
        print("="*60 + "\n")
        return

    print("ブラウザを開いてGoogleアカウント（genta2223@gmail.com）でログインしてください...")
    
    # Run the local server to get the refresh token
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n" + "✨"*30)
    print("✅ 認証大成功！以下の情報を Render の Environment Variables に登録してください。")
    print("✨"*30)
    print(f"GOOGLE_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("-" * 60)
    print("※ これでBotはあなたの2TBのDriveストレージへ画像を直接保存できるようになります！")

if __name__ == '__main__':
    main()
