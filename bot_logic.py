import re
from config import STANDARDS, TROUBLE_RESPONSES

def parse_and_diagnose(text):
    """
    Parses user text, identifies metrics or trouble keywords, 
    and returns a diagnostic string and log data dictionary.
    """
    text = text.lower()
    
    # Initialize data
    data = {
        "category": "不明",
        "status": "情報",
        "metric_type": "Unknown",
        "value": None,
        "humidity": None,
        "stage": None,
        "variety": "レタス"  # Default
    }

    # 0. Variety and Stage Parsing (Pre-parsing common attributes)
    stage_match = re.search(r'(\d+)\s*[段週]', text)
    if stage_match:
        data["stage"] = f"{stage_match.group(1)}段/週"
    
    # Simple variety detection
    varieties = ["レタス", "サラダ菜", "バジル", "大葉"]
    for v in varieties:
        if v in text:
            data["variety"] = v
            break

    # 1. Trouble Keywords
    for key, response in TROUBLE_RESPONSES.items():
        if key in text or key in text.replace(" ", ""):
            data.update({
                "category": "トラブル報告",
                "status": "異常",
                "metric_type": "Trouble",
                "value": key
            })
            return response, data

    # 2. Metric Parsing
    # pH
    match = re.search(r'ph[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("ph", val)
        data.update({"category": "数値報告", "status": status, "metric_type": "pH", "value": val})
        return msg, data

    # EC
    match = re.search(r'ec[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("ec", val)
        data.update({"category": "数値報告", "status": status, "metric_type": "EC", "value": val})
        return msg, data

    # Water Temp
    match = re.search(r'水温[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("water_temp", val)
        data.update({"category": "数値報告", "status": status, "metric_type": "Water Temp", "value": val})
        return msg, data

    # Room Temp
    match = re.search(r'室温[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        msg, status = check_standard("room_temp", val)
        data.update({"category": "数値報告", "status": status, "metric_type": "Room Temp", "value": val})
        return msg, data

    # Humidity
    match = re.search(r'湿度[:\s]*([\d\.]+)', text)
    if match:
        val = float(match.group(1))
        data.update({"category": "数値報告", "status": "情報", "metric_type": "Humidity", "value": val, "humidity": val})
        return f"湿度 {val}% を記録しました。", data

    # Image Labels from Quick Reply
    labels = ["葉の様子", "根の状態", "ボックスの汚れ", "その他"]
    for label in labels:
        if label in text:
            data.update({"category": "画像報告", "status": "情報", "metric_type": "Image Category", "value": label})
            return f"「{label}」として分類・保存しました。今後の生育パターンの分析に活用します。", data

    # Default fallback
    return "データを受信しました（解析に該当する報告・キーワードは見つかりませんでした）。", data

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
