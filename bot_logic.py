import re
from config import STANDARDS, TROUBLE_RESPONSES

def parse_and_diagnose(text):
    """
    Parses user text, identifies metrics or trouble keywords, 
    and returns a diagnostic string and log data tuple: 
    (category, status, metric_type, value).
    """
    text = text.lower()
    
    # 1. Trouble Keywords
    for key, response in TROUBLE_RESPONSES.items():
        if key in text or key in text.replace(" ", ""):
            return response, ("トラブル報告", "異常", "Trouble", key)

    # 2. Metric Parsing
    # We look for simple patterns: "[ph/ec/水温/室温] [value]"
    match = re.search(r'ph[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("ph", val)
        return msg, ("数値報告", status, "pH", val)

    match = re.search(r'ec[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("ec", val)
        return msg, ("数値報告", status, "EC", val)

    match = re.search(r'水温[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("water_temp", val)
        return msg, ("数値報告", status, "Water Temp", val)

    match = re.search(r'室温[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("room_temp", val)
        return msg, ("数値報告", status, "Room Temp", val)

    # Image Labels from Quick Reply
    labels = ["葉の様子", "根の状態", "ボックスの汚れ", "その他"]
    for label in labels:
        if label in text:
            return f"「{label}」として分類・保存しました。今後の生育パターンの分析に活用します。", ("画像報告", "情報", "Image Category", label)

    # Default fallback
    return "データを受信しました（解析に該当する報告・キーワードは見つかりませんでした）。", ("不明", "情報", "Unknown", None)

def check_standard(metric_key, val):
    std = STANDARDS.get(metric_key)
    if not std:
        return f"{metric_key} の基準値設定が見つかりません", "異常"

    lbl_map = {
        "ph": "pH",
        "ec": "EC",
        "water_temp": "水温",
        "room_temp": "室温"
    }
    label = lbl_map.get(metric_key, metric_key)
    min_val = std["min"]
    max_val = std["max"]

    if val < min_val:
        return f"基準値({min_val}-{max_val})を下回っています。{std['low_action']}", "異常"
    elif val > max_val:
        return f"基準値({min_val}-{max_val})を超えています。{std['high_action']}", "異常"
    else:
        return f"{label}は基準値内({min_val}-{max_val})です。この状態を維持してください。", "正常"

def handle_image():
    """ Placeholder response for the phase 1 image handling. """
    return "画像を確認しました。葉の色（クロロシス等）、根の張り、藻の発生状況、および栽培パイプ等の汚れ（ナノゾーン効果）をチェックしています。異常があれば後ほど通知します。"
