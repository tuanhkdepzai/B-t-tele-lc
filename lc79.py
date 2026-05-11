import requests
import time
import math
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================== CẤU HÌNH ====================
TOKEN = '8416284574:AAFVCRj9_tHRQqgwmyx5aKDKNSv_Xvnku1o'
ADMIN_ID = 7322903918
GROUP_ID = -1003978095472  # ID nhóm của bạn
API_URL = "https://wtx.tele68.com/v1/tx/lite-sessions?cp=R&cl=R&pf=web&at=ac66e2c04bff27faef086d365f9b6897"

# ==================== BIẾN TOÀN CỤC THUẬT TOÁN ====================
model_predictions = {
    'trend': {}, 'short': {}, 'mean': {}, 'switch': {}, 'bridge': {}
}

class PredictionEngine:
    def __init__(self):
        self.is_running = False
        self.last_sent_id = None
        self.history = [] # Lưu danh sách {session: id, result: 'Tài'/'Xỉu', score: point}

    # --- 1. Detect Streak and Break ---
    def detect_streak_and_break(self, history):
        if not history: return {'streak': 0, 'currentResult': None, 'breakProb': 0}
        streak = 1
        current_result = history[-1]['result']
        for i in range(len(history) - 2, -1, -1):
            if history[i]['result'] == current_result: streak += 1
            else: break
        
        last_15 = [h['result'] for h in history[-15:]]
        switches = sum(1 for i in range(1, len(last_15)) if last_15[i] != last_15[i-1])
        tai_c = last_15.count('Tài')
        xiu_c = last_15.count('Xỉu')
        imbalance = abs(tai_c - xiu_c) / (len(last_15) or 1)
        
        break_prob = 0
        if streak >= 8: break_prob = min(0.6 + switches/15 + imbalance*0.15, 0.9)
        elif streak >= 5: break_prob = min(0.35 + switches/10 + imbalance*0.25, 0.85)
        elif streak >= 3 and switches >= 7: break_prob = 0.3
        return {'streak': streak, 'currentResult': current_result, 'breakProb': break_prob}

    # --- 2. Evaluate Model Performance ---
    def evaluate_model_performance(self, model_name, lookback=10):
        if model_name not in model_predictions or len(self.history) < 2: return 1
        lookback = min(lookback, len(self.history) - 1)
        correct = 0
        for i in range(lookback):
            s_id = self.history[len(self.history) - (i + 2)]['session']
            pred = model_predictions[model_name].get(s_id, 0)
            actual = self.history[len(self.history) - (i + 1)]['result']
            if (pred == 1 and actual == 'Tài') or (pred == 2 and actual == 'Xỉu'):
                correct += 1
        ratio = 1 + (correct - lookback/2) / (lookback/2) if lookback > 0 else 1
        return max(0.5, min(1.5, ratio))

    # --- 3. Smart Bridge Break ---
    def smart_bridge_break(self, history):
        if len(history) < 3: return {'prediction': 0, 'breakProb': 0, 'reason': 'Ít dữ liệu'}
        db = self.detect_streak_and_break(history)
        last_20_res = [h['result'] for h in history[-20:]]
        last_20_scores = [h['score'] for h in history[-20:]]
        
        avg_score = sum(last_20_scores)/(len(last_20_scores) or 1)
        score_dev = sum(abs(s - avg_score) for s in last_20_scores)/(len(last_20_scores) or 1)
        
        final_prob = db['breakProb']
        if db['streak'] >= 6: 
            final_prob = min(final_prob + 0.15, 0.9)
            reason = f"[Bẻ Cầu] Chuỗi {db['streak']} dài"
        elif db['streak'] >= 4 and score_dev > 3:
            final_prob = min(final_prob + 0.1, 0.85)
            reason = "[Bẻ Cầu] Biến động điểm cao"
        else:
            final_prob = max(final_prob - 0.15, 0.15)
            reason = "Theo cầu"
            
        pred = (2 if db['currentResult'] == 'Tài' else 1) if final_prob > 0.65 else (1 if db['currentResult'] == 'Tài' else 2)
        return {'prediction': pred, 'breakProb': final_prob, 'reason': reason}

    # --- 4. Logic AI HTDD ---
    def ai_htdd_logic(self, history):
        if len(history) < 3: return {'prediction': random.choice(['Tài', 'Xỉu']), 'reason': 'Random'}
        last_5_res = [h['result'] for h in history[-5:]]
        avg_score = sum(h['score'] for h in history[-5:])/5
        
        if avg_score > 10: return {'prediction': 'Tài', 'reason': 'Điểm TB cao'}
        if avg_score < 8: return {'prediction': 'Xỉu', 'reason': 'Điểm TB thấp'}
        
        tai_c = last_5_res.count('Tài')
        xiu_c = last_5_res.count('Xỉu')
        return {'prediction': 'Xỉu' if tai_c > xiu_c else 'Tài', 'reason': 'Phân bổ 5 phiên'}

    # --- HÀM TỔNG HỢP DỰ ĐOÁN ---
    def generate_prediction(self):
        if not self.history: return "Không xác định", 0, "N/A"
        
        curr_session = self.history[-1]['session']
        # Giả định các model (Trend, Short, Mean, Switch) - bạn có thể viết chi tiết thêm
        # Ở đây tôi lấy cơ bản để đảm bảo code chạy
        trend_pred = 1 if self.history[-1]['result'] == 'Xỉu' else 2
        bridge_data = self.smart_bridge_break(self.history)
        ai_data = self.ai_htdd_logic(self.history)

        # Lưu vào bộ nhớ hiệu suất
        model_predictions['trend'][curr_session] = trend_pred
        model_predictions['bridge'][curr_session] = bridge_data['prediction']

        # Trọng số
        w_trend = 0.3 * self.evaluate_model_performance('trend')
        w_bridge = 0.4 * self.evaluate_model_performance('bridge')
        
        tai_score = (w_trend if trend_pred == 1 else 0) + (w_bridge if bridge_data['prediction'] == 1 else 0)
        xiu_score = (w_trend if trend_pred == 2 else 0) + (w_bridge if bridge_data['prediction'] == 2 else 0)
        
        if ai_data['prediction'] == 'Tài': tai_score += 0.2
        else: xiu_score += 0.2

        final_pred = "Tài" if tai_score > xiu_score else "Xỉu"
        confidence = min(99, int((max(tai_score, xiu_score) / (tai_score + xiu_score + 0.1)) * 100))
        
        return final_pred, confidence, f"{ai_data['reason']} | {bridge_data['reason']}"

bot_engine = PredictionEngine()

async def run_tool(context: ContextTypes.DEFAULT_TYPE):
    if not bot_engine.is_running: return
    try:
        response = requests.get(API_URL, timeout=10).json()
        data_list = response.get('list', [])
        if not data_list: return
        
        newest = data_list[0]
        if newest['id'] == bot_engine.last_sent_id: return
        
        # Cập nhật History từ API (Chuyển format cho đúng thuật toán)
        bot_engine.history = []
        for item in reversed(data_list[:20]):
            bot_engine.history.append({
                'session': item['id'],
                'result': 'Tài' if item['resultTruyenThong'] == 'TAI' else 'Xỉu',
                'score': item['point']
            })
            
        bot_engine.last_sent_id = newest['id']
        pred, conf, reason = bot_engine.generate_prediction()
        
        msg = (
            f"Phiên hiện tại: {newest['id']}\n"
            f"Kết quả: {newest['resultTruyenThong']}\n"
            f"Xúc xắc: {newest['dices']}\n"
            f"______________________\n"
            f"Phiên kế tiếp: {newest['id'] + 1}\n"
            f"Dự đoán: {pred}\n"
            f"Tỉ lệ: {conf}%\n"
            f"Phân tích: {reason}"
        )
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg)
        await context.bot.send_message(chat_id=GROUP_ID, text=msg)
    except Exception as e:
        print(f"Lỗi: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        bot_engine.is_running = True
        await update.message.reply_text("🚀 Bot Thuật Toán đã khởi động!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        bot_engine.is_running = False
        await update.message.reply_text("🛑 Bot đã dừng.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.job_queue.run_repeating(run_tool, interval=20, first=1)
    app.run_polling()