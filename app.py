from flask import Flask, request, jsonify, Response
from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.exceptions import InvalidSignatureError
import os
import requests
import logging
import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)


CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CWA_API_KEY = os.getenv("CWA_API_KEY")


configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(CHANNEL_SECRET)

# 啟用 Debug 記錄
logging.basicConfig(level=logging.DEBUG)

# 對話歷史儲存
HISTORY_FILE = "chat_history.json"
chat_history = {}

# 台灣縣市對照表
TAIWAN_LOCATIONS = {
    '台北': '臺北市', '臺北': '臺北市', '台北市': '臺北市',
    '台中': '臺中市', '臺中': '臺中市', '台中市': '臺中市',
    '台南': '臺南市', '臺南': '臺南市', '台南市': '臺南市',
    '台東': '臺東縣', '臺東': '臺東縣', '台東縣': '臺東縣',
    '新北': '新北市', '新北市': '新北市',
    '桃園': '桃園市', '桃園市': '桃園市',
    '高雄': '高雄市', '高雄市': '高雄市',
    '基隆': '基隆市', '基隆市': '基隆市',
    '新竹': '新竹市', '新竹市': '新竹市', '新竹縣': '新竹縣',
    '苗栗': '苗栗縣', '苗栗縣': '苗栗縣',
    '彰化': '彰化縣', '彰化縣': '彰化縣',
    '南投': '南投縣', '南投縣': '南投縣',
    '雲林': '雲林縣', '雲林縣': '雲林縣',
    '嘉義': '嘉義市', '嘉義市': '嘉義市', '嘉義縣': '嘉義縣',
    '屏東': '屏東縣', '屏東縣': '屏東縣',
    '宜蘭': '宜蘭縣', '宜蘭縣': '宜蘭縣',
    '花蓮': '花蓮縣', '花蓮縣': '花蓮縣',
    '澎湖': '澎湖縣', '澎湖縣': '澎湖縣',
    '金門': '金門縣', '金門縣': '金門縣',
    '連江': '連江縣', '連江縣': '連江縣', '馬祖': '連江縣'
}

def load_history():
    global chat_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                chat_history = json.load(f)
    except Exception as e:
        logging.error(f"載入歷史對話失敗: {str(e)}")
        chat_history = {}

def save_history():
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"儲存歷史對話失敗: {str(e)}")

load_history()

@app.route("/")
def index():
    return "LINE Bot with Weather and AI Service"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    
    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    
    for event in events:
        if event.type == "message" and event.message.type == "text":
            handle_message(event)
    
    return "OK"

def get_weather(location_input):
    """天氣查詢功能保持不變"""
    try:
        location_name = TAIWAN_LOCATIONS.get(location_input, location_input)
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001?Authorization={CWA_API_KEY}&format=JSON"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('success') != 'true':
            return "氣象資料服務異常，請稍後再試"
        
        matched_locations = [
            loc for loc in data['records']['location'] 
            if loc['locationName'] == location_name
        ]
        
        if not matched_locations:
            return f"找不到 {location_input} 的天氣資訊，請嘗試輸入完整縣市名稱 (如: 台北市)"
        
        location = matched_locations[0]
        elements = {e['elementName']: e for e in location['weatherElement']}
        latest_time = elements['Wx']['time'][0]
        return (
            f"【{location['locationName']} 最新天氣】\n"
            f"⏰ {latest_time['startTime']} ~ {latest_time['endTime']}\n"
            f"🌤 天氣: {latest_time['parameter']['parameterName']}\n"
            f"🌧 降雨機率: {elements['PoP']['time'][0]['parameter']['parameterName']}%\n"
            f"🌡 溫度: {elements['MinT']['time'][0]['parameter']['parameterName']}~"
            f"{elements['MaxT']['time'][0]['parameter']['parameterName']}°C\n"
            f"💧 舒適度: {elements['CI']['time'][0]['parameter']['parameterName']}"
        )
        
    except requests.exceptions.RequestException as e:
        logging.error(f"天氣API請求失敗: {str(e)}")
        return "天氣服務暫時不可用，請稍後再試"
    except Exception as e:
        logging.error(f"天氣資料解析錯誤: {str(e)}")
        return "天氣資料處理異常"

def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    
    if user_id not in chat_history:
        chat_history[user_id] = []
    
    chat_history[user_id].append({
        "type": "user",
        "text": user_text,
        "timestamp": datetime.now().isoformat()
    })
    
    if user_text.startswith("天氣 "):
        location = user_text[3:].strip()
        reply_text = get_weather(location) if location else "請輸入查詢地點，例如：天氣 台北"
    else:
        reply_text = generate_text_with_gemini(user_text)
    
    chat_history[user_id].append({
        "type": "bot",
        "text": reply_text,
        "timestamp": datetime.now().isoformat()
    })
    
    save_history()
    
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
    except Exception as e:
        logging.error(f"發送訊息失敗: {str(e)}")

def generate_text_with_gemini(prompt):
    """使用最新 Gemini 1.5 Flash 模型"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 200
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if 'candidates' in result and result['candidates']:
            candidate = result['candidates'][0]
            if 'content' in candidate and 'parts' in candidate['content']:
                return candidate['content']['parts'][0]['text']
        
        return "我無法理解這個問題，請換個方式詢問"
    except requests.exceptions.RequestException as e:
        logging.error(f"Gemini API 請求失敗: {str(e)}")
        return "AI 服務暫時不可用 (網路錯誤)"
    except Exception as e:
        logging.error(f"Gemini 回應解析錯誤: {str(e)}")
        return "AI 服務暫時異常"

if __name__ == "__main__":
    app.run(port=58073)