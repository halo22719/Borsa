import os
import time
import requests
import pandas as pd
import yfinance as yf
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ==================== Mini Web Sunucusu (Render Keep-Alive) ====================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BIST 4H Scanner Bot is Running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"Web sunucusu {port} portunda başlatıldı.")
    server.serve_forever()

# Web sunucusunu arka planda çalıştır
threading.Thread(target=run_web_server, daemon=True).start()

# ==================== Bot Ayarları ====================
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Telegram Bot Token'ını girin
CHAT_ID = "YOUR_CHAT_ID"                    # Telegram Chat ID'nizi girin

# Tarama Yapılacak Hisse Listesi (.IS uzantılı)
HISSELER = ["THYAO.IS", "GARAN.IS", "AKBNK.IS", "EREGL.IS", "SASA.IS", "ASELS.IS"]

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}")

# ==================== İndikatör Hesaplamaları ====================
def calculate_supertrend(df, period=10, multiplier=3):
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # ATR Hesaplama
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (high + low) / 2
    basic_upperband = hl2 + (multiplier * atr)
    basic_lowerband = hl2 - (multiplier * atr)
    
    final_upperband = basic_upperband.copy()
    final_lowerband = basic_lowerband.copy()
    
    for i in range(1, len(df)):
        if basic_upperband.iloc[i] < final_upperband.iloc[i-1] or close.iloc[i-1] > final_upperband.iloc[i-1]:
            final_upperband.iloc[i] = basic_upperband.iloc[i]
        else:
            final_upperband.iloc[i] = final_upperband.iloc[i-1]
            
        if basic_lowerband.iloc[i] > final_lowerband.iloc[i-1] or close.iloc[i-1] < final_lowerband.iloc[i-1]:
            final_lowerband.iloc[i] = basic_lowerband.iloc[i]
        else:
            final_lowerband.iloc[i] = final_lowerband.iloc[i-1]
            
    supertrend = pd.Series(index=df.index, dtype='float64')
    direction = pd.Series(1, index=df.index)
    
    for i in range(1, len(df)):
        if close.iloc[i] > final_upperband.iloc[i-1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lowerband.iloc[i-1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i-1]
            
        supertrend.iloc[i] = final_lowerband.iloc[i] if direction.iloc[i] == 1 else final_upperband.iloc[i]
        
    return supertrend, direction

def calculate_ott(df, pperiod=2, percent=1.4):
    close = df['Close']
    mavg = close.ewm(span=pperiod, adjust=False).mean()
    fark = mavg * (percent / 100)
    
    long_stop = mavg - fark
    short_stop = mavg + fark
    
    ott = pd.Series(index=df.index, dtype='float64')
    
    for i in range(1, len(df)):
        if mavg.iloc[i] > long_stop.iloc[i-1]:
            long_stop.iloc[i] = max(long_stop.iloc[i], long_stop.iloc[i-1])
        if mavg.iloc[i] < short_stop.iloc[i-1]:
            short_stop.iloc[i] = min(short_stop.iloc[i], short_stop.iloc[i-1])
            
        if mavg.iloc[i] > short_stop.iloc[i-1]:
            ott.iloc[i] = long_stop.iloc[i]
        elif mavg.iloc[i] < long_stop.iloc[i-1]:
            ott.iloc[i] = short_stop.iloc[i]
        else:
            ott.iloc[i] = ott.iloc[i-1] if not pd.isna(ott.iloc[i-1]) else long_stop.iloc[i]
            
    return ott, mavg

# ==================== Tarama Döngüsü ====================
def scan_markets():
    print("4 Saatlik BIST Taraması Başlatılıyor...")
    
    for ticker in HISSELER:
        try:
            # 1 Saatlik veriyi çekip 4 saatlik mumlara dönüştürüyoruz (Resampling)
            data = yf.download(ticker, period="60d", interval="1h", progress=False)
            
            if data.empty or len(data) < 50:
                continue
                
            # MultiIndex sütun yapısını düzeltme (gerekirse)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            # 4 Saatlik periyoda çevirme
            df_4h = data.resample('4h').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()

            # İndikatörleri Hesapla
            df_4h['Supertrend'], df_4h['ST_Direction'] = calculate_supertrend(df_4h)
            df_4h['OTT'], df_4h['MA'] = calculate_ott(df_4h)
            df_4h['EMA50'] = df_4h['Close'].ewm(span=50, adjust=False).mean()

            # Son Tamamlanan ve Bir Önceki Mum Verisi
            last_row = df_4h.iloc[-1]
            prev_row = df_4h.iloc[-2]

            # Koşullar: Supertrend AL'a geçti mi + OTT Trend Onayı Var mı + EMA50 Üzerinde mi
            st_buy_signal = (prev_row['ST_Direction'] == -1) and (last_row['ST_Direction'] == 1)
            ott_bullish = last_row['MA'] > last_row['OTT']
            trend_above_ema = last_row['Close'] > last_row['EMA50']

            if st_buy_signal and ott_bullish and trend_above_ema:
                entry_price = round(last_row['Close'], 2)
                stop_loss = round(entry_price * 0.965, 2)   # %3.5 Stop-Loss
                take_profit = round(entry_price * 1.07, 2)   # %7 Take-Profit

                message = (
                    f"🚀 *BİST 4 SAATLİK AL SİNYALİ*\n\n"
                    f"📌 **Hisse:** `{ticker}`\n"
                    f"💰 **Giriş Fiyatı:** `{entry_price} TL`\n"
                    f"🛑 **Stop-Loss (%3.5):** `{stop_loss} TL`\n"
                    f"🎯 **Hedef (Take-Profit %7):** `{take_profit} TL`\n\n"
                    f"📊 *Filtreler:* Supertrend AL + OTT Boğa + EMA50 Üzerinde"
                )
                print(f"Sinyal Bulundu: {ticker}")
                send_telegram_message(message)
                
        except Exception as e:
            print(f"{ticker} işlenirken hata oluştu: {e}")

# ==================== Ana Çalıştırma Döngüsü ====================
if __name__ == "__main__":
    while True:
        scan_markets()
        # 4 saatlik grafiklerde her saat başı tarama yapmak yeterlidir (3600 saniye)
        time.sleep(3600)
