import os
import time
import json
import logging
import threading
import http.server
import socketserver
import datetime
import pytz
import pandas as pd
import yfinance as yf
import requests

# ================== WEB SERVER (RENDER UYKU ÖNLEMESİ) ================== 
def run_web_server():
    class SimpleHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Borsa Botu Aktif ve Calisiyor!")
            
    port = int(os.getenv("PORT", 10000))
    with socketserver.TCPServer(("", port), SimpleHandler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ================== GENEL AYARLAR VE LOGGING ================== 
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Telegram Entegrasyon Bilgileri
TELEGRAM_TOKEN = "8853048772:AAEW2ekJlDBc3EK9pWTiC8pLZVm_9RBwas"
TELEGRAM_CHAT_ID = "1131754179"
PORTFOLIO_FILE = "portfolio.json"

# Takip Edilen Hisseler Listesi (BIST)
SYMBOLS = [
    "AKBNK.IS", "ALARK.IS", "ASELS.IS", "ASTOR.IS", "BIMAS.IS",
    "BRSAN.IS", "DOAS.IS", "EKGYO.IS", "ENKAI.IS", "EREGL.IS",
    "FROTO.IS", "GARAN.IS", "HEKTS.IS", "ISCTR.IS", "KCHOL.IS",
    "KONTR.IS", "KRDMD.IS", "ODAS.IS", "OYAKC.IS", "PETKM.IS",
    "PGSUS.IS", "REEDR.IS", "SAHOL.IS", "SISE.IS", "TCELL.IS",
    "THYAO.IS", "TOASO.IS", "TUPRS.IS", "ULKER.IS", "YKBNK.IS"
]

# ================== YARDIMCI FONKSİYONLAR ================== 
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logging.error(f"Telegram mesajı gönderilemedi: {response.text}")
    except Exception as e:
        logging.error(f"Telegram bağlantı hatası: {e}")

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_portfolio(portfolio):
    try:
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(portfolio, f, indent=4)
    except Exception as e:
        logging.error(f"Portföy kaydedilemedi: {e}")

# ================== SUPERTREND HESAPLAMA ================== 
def calculate_supertrend(df, period=10, multiplier=3):
    """
    Supertrend indikatörünü hesaplar.
    """
    hl2 = (df['High'] + df['Low']) / 2
    
    # True Range (TR) Hesaplama
    df['TR1'] = abs(df['High'] - df['Low'])
    df['TR2'] = abs(df['High'] - df['Close'].shift(1))
    df['TR3'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['TR1', 'TR2', 'TR3']].max(axis=1)
    
    # Average True Range (ATR)
    df['ATR'] = df['TR'].rolling(window=period).mean()
    
    # Temel Üst ve Alt Bantlar
    df['UpperBasic'] = hl2 + (multiplier * df['ATR'])
    df['LowerBasic'] = hl2 - (multiplier * df['ATR'])
    
    df['UpperBand'] = 0.0
    df['LowerBand'] = 0.0
    df['Supertrend'] = True
    
    # Bantların ve Supertrend yönünün döngü ile tespiti
    for i in range(period, len(df)):
        # Üst bant hesaplama
        if df['UpperBasic'].iloc[i] < df['UpperBand'].iloc[i-1] or df['Close'].iloc[i-1] > df['UpperBand'].iloc[i-1]:
            df.loc[df.index[i], 'UpperBand'] = df['UpperBasic'].iloc[i]
        else:
            df.loc[df.index[i], 'UpperBand'] = df['UpperBand'].iloc[i-1]
            
        # Alt bant hesaplama
        if df['LowerBasic'].iloc[i] > df['LowerBand'].iloc[i-1] or df['Close'].iloc[i-1] < df['LowerBand'].iloc[i-1]:
            df.loc[df.index[i], 'LowerBand'] = df['LowerBasic'].iloc[i]
        else:
            df.loc[df.index[i], 'LowerBand'] = df['LowerBand'].iloc[i-1]
            
        # Trend Yönü Kararı
        if i == period:
            df.loc[df.index[i], 'Supertrend'] = True if df['Close'].iloc[i] > df['UpperBand'].iloc[i] else False
        else:
            if df['Supertrend'].iloc[i-1] == False and df['Close'].iloc[i] > df['UpperBand'].iloc[i]:
                df.loc[df.index[i], 'Supertrend'] = True
            elif df['Supertrend'].iloc[i-1] == True and df['Close'].iloc[i] < df['LowerBand'].iloc[i]:
                df.loc[df.index[i], 'Supertrend'] = False
            else:
                df.loc[df.index[i], 'Supertrend'] = df['Supertrend'].iloc[i-1]
                
    return df

# ================== PİYASA ANALİZ MOTORU ================== 
def check_signals():
    portfolio = load_portfolio()
    
    for symbol in SYMBOLS:
        try:
            # 30 Dakikalık veriler çekiliyor
            df = yf.download(symbol, period="5d", interval="30m", progress=False)
            if df.empty or len(df) < 25:
                continue
            
            # Çoklu sütun yapılarını düzeltme (yfinance güncellemeleri için önlem)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Supertrend Hesapla (10 periyot, 3 çarpan)
            df = calculate_supertrend(df, period=10, multiplier=3)
            
            current_price = float(df['Close'].iloc[-1])
            prev_trend = df['Supertrend'].iloc[-2]
            curr_trend = df['Supertrend'].iloc[-1]
            
            # AL SİNYALI (Supertrend Alıcılı tarafa döndü: False -> True)
            if not prev_trend and curr_trend:
                if symbol not in portfolio:
                    portfolio[symbol] = {
                        "buy_price": current_price,
                        "stop_loss": current_price * 0.98,  # %2 Stop
                        "take_profit": current_price * 1.04 # %4 Kâr Al
                    }
                    save_portfolio(portfolio)
                    
                    msg = (
                        f"🟢 *AL SINYALI (Supertrend)*\n"
                        f"Hisse: `{symbol}`\n"
                        f"Fiyat: `{current_price:.2f} TL`\n"
                        f"Strateji: Trend Yukarı Döndü 🚀"
                    )
                    send_telegram(msg)
            
            # SAT SİNYALI / RİSK YÖNETİMİ (Supertrend Satıcılı tarafa döndü VEYA Stop/Kâr Seviyesi)
            elif symbol in portfolio:
                buy_data = portfolio[symbol]
                buy_price = buy_data["buy_price"]
                stop_loss = buy_data["stop_loss"]
                take_profit = buy_data["take_profit"]
                
                sell_reason = ""
                if curr_trend and not prev_trend: # Trend aşağı döndü
                    sell_reason = "Supertrend Aşağı Kesti 📉"
                elif current_price <= stop_loss:
                    sell_reason = "Stop-Loss (Zarar Kes) Seviyesi! 🛑"
                elif current_price >= take_profit:
                    sell_reason = "Take-Profit (Kâr Al) Hedefine Ulaşıldı! 🎯"
                
                if sell_reason:
                    profit_loss_pct = ((current_price - buy_price) / buy_price) * 100
                    msg = (
                        f"🔴 *SAT / KAPATMA SİNYALI*\n"
                        f"Hisse: `{symbol}`\n"
                        f"Alış Fiyatı: `{buy_price:.2f} TL`\n"
                        f"Satış/Güncel Fiyat: `{current_price:.2f} TL`\n"
                        f"Getiri: `%{profit_loss_pct:.2f}`\n"
                        f"Gerekçe: {sell_reason}"
                    )
                    send_telegram(msg)
                    del portfolio[symbol]
                    save_portfolio(portfolio)
                    
        except Exception as e:
            logging.error(f"{symbol} analizi sırasında hata oluştu: {e}")
        
        time.sleep(1) # Hisse başı bekleme

# ================== ANA ÇALIŞMA DÖNGÜSÜ ================== 
def main():
    send_telegram("🤖 *Borsa İstanbul Supertrend Botu Başarıyla Başlatıldı!*")
    istanbul_tz = pytz.timezone("Europe/Istanbul")
    
    while True:
        try:
            now = datetime.datetime.now(istanbul_tz)
            # BIST Çalışma Saatleri Kontrolü (Hafta içi 09:30 - 18:15 arası)
            is_weekday = now.weekday() < 5
            is_market_hours = (now.hour == 9 and now.minute >= 30) or (10 <= now.hour < 18) or (now.hour == 18 and now.minute <= 15)
            
            if is_weekday and is_market_hours:
                logging.info("Piyasa açık, Supertrend sinyalleri taranıyor...")
                check_signals()
            else:
                logging.info("Piyasa kapalı veya seans dışı saatlerdeyiz. Bekleniyor...")
                
        except Exception as e:
            logging.error(f"Ana döngü hatası: {e}")
            
        # 5 dakikada bir döngüyü tekrarla
        time.sleep(300)

if __name__ == "__main__":
    main()
