import csv
import os
from datetime import datetime

LOG_FILE = "logs.csv"

def init_db():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "User ID", "Category", "Status", "Metric Type", "Value", "Raw Message"])

def save_log(user_id, category, status, metric_type, value, raw_message):
    init_db()
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            user_id,
            category,
            status,
            metric_type,
            value,
            raw_message
        ])
