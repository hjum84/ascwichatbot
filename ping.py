import requests
import time

# 배포된 서버의 URL
SERVER_URL = "https://bcc3.onrender.com/"

while True:
    try:
        response = requests.get(SERVER_URL)
        print(f"Pinged {SERVER_URL} - Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error pinging {SERVER_URL}: {e}")

    # 10분마다 Ping 요청을 보냅니다
    time.sleep(600)
