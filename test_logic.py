from bot_logic import parse_and_diagnose
from storage import save_log

def test():
    # Test 1: pH High
    user_text = "pH 6.5"
    resp, data = parse_and_diagnose(user_text)
    print(f"Input: {user_text}")
    print(f"Response: {resp}")
    if data: save_log("test_user_1", data[0], data[1], user_text)
    print("---")
    
    # Test 2: EC Low
    user_text = "EC 1.0"
    resp, data = parse_and_diagnose(user_text)
    print(f"Input: {user_text}")
    print(f"Response: {resp}")
    if data: save_log("test_user_2", data[0], data[1], user_text)
    print("---")
    
    # Test 3: Trouble
    user_text = "昨夜、停電がありました。"
    resp, data = parse_and_diagnose(user_text)
    print(f"Input: {user_text}")
    print(f"Response: {resp}")
    if data: save_log("test_user_3", data[0], data[1], user_text)
    print("---")
    
    # Test 4: Normal
    user_text = "水温 20"
    resp, data = parse_and_diagnose(user_text)
    print(f"Input: {user_text}")
    print(f"Response: {resp}")
    if data: save_log("test_user_4", data[0], data[1], user_text)
    print("---")

if __name__ == '__main__':
    test()
