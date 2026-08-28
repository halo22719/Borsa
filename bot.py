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

# ==================== WEB SERVER (RENDER UYKU ÖNLENMESİ) ====================
def run_web_server():
    handler = http.server.SimpleHTTPRequestHandler
    port = int(os.getenv("PORT", 10000))
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==================== GENEL AYARLAR VE LOGGING ====================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Telegram Entegrasyon Bilgileri
TELEGRAM_TOKEN = "8853048772:AAEW22ekJlDBc3EK9pWTiC8plZVm_9RBwas"
TELEGRAM_CHAT_ID = "1131754179"
PORTFOLIO_FILE = "portfolio.json"

# BIST 30 Hisselerinin Tamamı (30 Hisse)
SYMBOLS = [
    "AKBNK.IS", "ALARK.IS", "ASELS.IS", "ASTOR.IS", "BIMAS.IS",
    "BRSAN.IS", "DOAS.IS",  "EKGYO.IS", "ENKAI.IS", "EREGL.IS",
    "FROTO.IS", "GARAN.IS", "HEKTS.IS", "ISCTR.IS", "KCHOL.IS",
    "KONTR.IS", "KRDMD.IS", "ODAS.IS",  "OYAKC.IS",
    "PETKM.IS", "PGSUS.IS", "SAHOL.IS", "SISE.IS",  "TCELL.IS",
    "THYAO.IS", "TOASO.IS", "TUPRS.IS", "ULKER.IS", "YKBNK.IS"
]

# ==================== YARDIMCI FONKSİYONLAR ====================
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram token veya Chat ID tanımlı değil!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Telegram mesajı gönderilemedi: {e}")

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Portföy okuma hatası: {e}")
    return {}

def save_portfolio(portfolio):
    try:
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(portfolio, f, indent=4)
    except Exception as e:
        logging.error(f"Portföy kaydetme hatası: {e}")

# ==================== TEKNİK ANALİZ VE STRATEJİ ====================
def check_signals(symbol, portfolio):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="30m")
        
        if df.empty or len(df) < 22:
            return

        # MultiIndex sütun temizliği
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs(symbol, level=1, axis=1)

        # İndikatörler (SMA 5 ve SMA 22)
        df["SMA5"] = df["Close"].rolling(window=5).mean()
        df["SMA22"] = df["Close"].rolling(window=22).mean()

        current_price = float(df["Close"].iloc[-1])
        prev_sma5 = float(df["SMA5"].iloc[-2])
        curr_sma5 = float(df["SMA5"].iloc[-1])
        prev_sma22 = float(df["SMA22"].iloc[-2])
        curr_sma22 = float(df["SMA22"].iloc[-1])

        clean_symbol = symbol.replace(".IS", "")

        # 1. PORTFÖYDEKİ HİSSELER İÇİN SATIŞ / STOP-LOSS KONTROLÜ
        if clean_symbol in portfolio:
            entry_price = portfolio[clean_symbol]["entry_price"]
            stop_loss = entry_price * 0.98    # %2 Stop-Loss
            take_profit = entry_price * 1.04  # %4 Take-Profit

            # Stop-Loss veya Take-Profit Tetiklendi mi?
            if current_price <= stop_loss:
                send_telegram(f"🚨 *STOP-LOSS KESİLDİ*\n\nHisse: #{clean_symbol}\nAlış: {entry_price:.2f} TL\nSatış: {current_price:.2f} TL\nZarar: %{((current_price/entry_price)-1)*100:.2f}")
                del portfolio[clean_symbol]
                save_portfolio(portfolio)
                return

            elif current_price >= take_profit:
                send_telegram(f"🎯 *TAKE-PROFIT HEDEFİNE ULAŞILDI*\n\nHisse: #{clean_symbol}\nAlış: {entry_price:.2f} TL\nSatış: {current_price:.2f} TL\nKâr: %{((current_price/entry_price)-1)*100:.2f}")
                del portfolio[clean_symbol]
                save_portfolio(portfolio)
                return

            # SMA Satış Kesişimi (SMA5, SMA22'yi aşağı kırdıysa)
            elif prev_sma5 >= prev_sma22 and curr_sma5 < curr_sma22:
                send_telegram(f"📉 *SAT SİNYALİ (SMA Kesişimi)*\n\nHisse: #{clean_symbol}\nFiyat: {current_price:.2f} TL")
                del portfolio[clean_symbol]
                save_portfolio(portfolio)
                return

        # 2. ALIM SİNYALİ KONTROLÜ (SMA5, SMA22'yi yukarı kırdıysa)
        else:
            if prev_sma5 <= prev_sma22 and curr_sma5 > curr_sma22:
                portfolio[clean_symbol] = {
                    "entry_price": current_price,
                    "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                save_portfolio(portfolio)
                send_telegram(f"🚀 *AL SİNYALİ*\n\nHisse: #{clean_symbol}\nFiyat: {current_price:.2f} TL\nStop: {current_price*0.98:.2f} TL\nHedef: {current_price*1.04:.2f} TL")

    except Exception as e:
        logging.error(f"{symbol} analiz hatası: {e}")

# ==================== ANA DÖNGÜ VE SEANS SAATİ KONTROLÜ ====================
def main():
    send_telegram("🤖 *Borsa İstanbul Botu Başarıyla Başlatıldı!*")
    tz = pytz.timezone("Europe/Istanbul")
    
    while True:
        try:
            now = datetime.datetime.now(tz)
            
            # Pazartesi(0) - Cuma(4) ve Seans Saatleri (10:00 - 18:10 TSİ)
            is_weekday = now.weekday() < 5
            is_market_hours = (10 <= now.hour < 18) or (now.hour == 18 and now.minute <= 10)

            if is_weekday and is_market_hours:
                portfolio = load_portfolio()
                for symbol in SYMBOLS:
                    check_signals(symbol, portfolio)
                # Seans sırasında her 5 dakikada bir kontrol eder
                time.sleep(300)
            else:
                # Seans dışındaysa 15 dakikada bir kontrol eder
                time.sleep(900)
                
        except Exception as e:
            logging.error(f"Ana döngü hatası: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
