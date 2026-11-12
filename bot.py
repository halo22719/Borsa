import os
import time
import logging
import requests
import pandas as pd
import yfinance as yf
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from datetime import datetime

# Yahoo Finance gereksiz log/warning çıktılarını gizleme
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ==================== Mini Web Sunucusu (Render Keep-Alive) ====================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BIST Akilli Bot Calisiyor!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"Web sunucusu {port} portunda baslatildi.")
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==================== Bot Ayarları ====================
TELEGRAM_TOKEN = "8853048772:AAEW22ekJlDBc3EK9pWTiC8plZVm_9RBwas"
CHAT_ID = "1131754179"

BIST_HISSELERI = [
    "AEFES.IS", "AGHOL.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKFGY.IS", "AKFYE.IS", "AKSA.IS", "AKSEN.IS", "ALARK.IS",
    "ALBRK.IS", "ALFAS.IS", "ANSGR.IS", "ARCLK.IS", "ARDYZ.IS", "ASELS.IS", "ASTOR.IS", "BERA.IS", "BIENY.IS", "BIMAS.IS",
    "BIOEN.IS", "BOBET.IS", "BRSAN.IS", "BRYAT.IS", "BUCIM.IS", "CANTE.IS", "CCOLA.IS", "CIMSA.IS", "CWENE.IS", "DOAS.IS",
    "DOHOL.IS", "ECILC.IS", "ECZYT.IS", "EGEEN.IS", "EKGYO.IS", "ENJSA.IS", "ENKAI.IS", "EREGL.IS", "EUPWR.IS", "FROTO.IS",
    "GARAN.IS", "GESAN.IS", "GUBRF.IS", "HALKB.IS", "HEKTS.IS", "ISCTR.IS", "ISGYO.IS", "ISMEN.IS", "IZENR.IS", "KAYSE.IS",
    "KCAER.IS", "KCHOL.IS", "KLSER.IS", "KONTR.IS", "KORDS.IS", "KRDMD.IS", "KSTUR.IS", "LMKDC.IS", "MAALT.IS", "MAVI.IS",
    "MHRGY.IS", "MIATK.IS", "MGROS.IS", "MPARK.IS", "ODAS.IS", "OTKAR.IS", "OYYAT.IS", "OYAKC.IS", "PASEU.IS", "PETKM.IS",
    "PGSUS.IS", "PLTUR.IS", "PSGYO.IS", "REEDR.IS", "SAHOL.IS", "SASA.IS", "SDTTR.IS", "SISE.IS", "SKBNK.IS", "SMRTG.IS",
    "SOKM.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS", "TKFEN.IS", "TMSN.IS", "TOASO.IS", "TSKB.IS", "TTKOM.IS", "TTRAK.IS",
    "TUKAS.IS", "TUPRS.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YEOTK.IS", "YKBNK.IS", "YYLGD.IS", "ZOREN.IS"
]

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

# ==================== İndikatör Hesaplamaları ====================
def calculate_atr(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr

def calculate_supertrend(df, period=10, multiplier=3):
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    atr = calculate_atr(df, period=period)
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

def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['Close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['Close'].ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def clean_data(df):
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.loc[:, ~df.columns.duplicated()]
    return df

# ==================== BİST TARAMA DÖNGÜSÜ ====================
def scan_bist():
    while True:
        print("--- BIST 30M Akilli ATR Taramasi Baslatiliyor ---")
        scanned_count = 0
        signals_found = 0
        
        for ticker in BIST_HISSELERI:
            try:
                data_30m = yf.download(ticker, period="30d", interval="30m", progress=False)
                data_30m = clean_data(data_30m)
                
                if data_30m.empty or len(data_30m) < 50 or 'Close' not in data_30m.columns:
                    continue

                scanned_count += 1

                # İndikatörler
                data_30m['Supertrend'], data_30m['ST_Direction'] = calculate_supertrend(data_30m)
                data_30m['RSI'] = calculate_rsi(data_30m)
                data_30m['MACD'], data_30m['MACD_Signal'] = calculate_macd(data_30m)
                data_30m['ATR'] = calculate_atr(data_30m)
                data_30m['Vol_SMA20'] = data_30m['Volume'].rolling(window=20).mean()
                data_30m['EMA200'] = data_30m['Close'].ewm(span=200, adjust=False).mean()

                last = data_30m.iloc[-1]
                prev = data_30m.iloc[-2]

                support = round(data_30m['Low'].tail(20).min(), 2)
                resistance = round(data_30m['High'].tail(20).max(), 2)

                volume_confirmed = bool(last['Volume'] > last['Vol_SMA20'])
                close_price = float(last['Close'])
                low_price = float(last['Low'])
                atr_val = float(last['ATR'])
                rsi_val = float(last['RSI'])
                
                price_change_from_low = ((close_price - low_price) / low_price) * 100
                not_overbought_today = price_change_from_low <= 4.5

                # --- 🟢 AL SİNYALİ ŞARTLARI (Sertleştirilmiş RSI: 45 - 60) ---
                st_buy_signal = (prev['ST_Direction'] == -1) and (last['ST_Direction'] == 1)
                ema200_buy_ok = close_price > float(last['EMA200'])
                rsi_buy_ok = 45 <= rsi_val <= 60
                macd_buy_ok = float(last['MACD']) > float(last['MACD_Signal'])

                if st_buy_signal and volume_confirmed and ema200_buy_ok and rsi_buy_ok and macd_buy_ok and not_overbought_today:
                    signals_found += 1
                    entry_price = round(close_price, 2)
                    
                    # ATR Bazlı Akıllı Stop-Loss ve Hedef (Stop: 1.5 ATR, Hedef: 3.0 ATR)
                    stop_loss = round(entry_price - (1.5 * atr_val), 2)
                    take_profit = round(entry_price + (3.0 * atr_val), 2)
                    trailing_stop = round(entry_price - (1.0 * atr_val), 2)

                    message = (
                        f"🟢 *BİST 30M - AKILLI ATR AL SİNYALİ*\n\n"
                        f"📌 **Hisse:** `{ticker}`\n"
                        f"💰 **Giriş Fiyatı:** `{entry_price} TL`\n"
                        f"🎯 **ATR Hedef:** `{take_profit} TL`\n"
                        f"🛑 **ATR Stop-Loss:** `{stop_loss} TL`\n"
                        f"📈 **İz Süren Başlangıç:** `{trailing_stop} TL`\n\n"
                        f"🛡 **Destek:** `{support} TL` | ⚡ **Direnç:** `{resistance} TL`\n"
                        f"📊 *Filtreler:* Supertrend + EMA200 + MACD + RSI ({round(rsi_val,1)})"
                    )
                    send_telegram_message(message)

                # --- 🔴 SAT SİNYALİ ŞARTLARI (Sertleştirilmiş Dip Filtresi: RSI < 40 Engellendi!) ---
                st_sell_signal = (prev['ST_Direction'] == 1) and (last['ST_Direction'] == -1)
                ema200_sell_ok = close_price < float(last['EMA200'])
                # RSI 40'ın altındayken (aşırı satım/dip) SAT sinyali VERMEZ! Tepki alımı tuzağını önler.
                rsi_sell_ok = 40 <= rsi_val <= 65
                macd_sell_ok = float(last['MACD']) < float(last['MACD_Signal'])

                if st_sell_signal and volume_confirmed and ema200_sell_ok and rsi_sell_ok and macd_sell_ok:
                    signals_found += 1
                    entry_price = round(close_price, 2)
                    
                    # ATR Bazlı Satış/Short Stop ve Hedefleri
                    stop_loss = round(entry_price + (1.5 * atr_val), 2)
                    take_profit = round(entry_price - (3.0 * atr_val), 2)

                    message = (
                        f"🔴 *BİST 30M - AKILLI ATR SAT SİNYALİ*\n\n"
                        f"📌 **Hisse:** `{ticker}`\n"
                        f"💰 **Giriş Fiyatı:** `{entry_price} TL`\n"
                        f"🎯 **ATR Hedef (Düşüş):** `{take_profit} TL`\n"
                        f"🛑 **ATR Stop-Loss:** `{stop_loss} TL`\n\n"
                        f"🛡 **Destek:** `{support} TL` | ⚡ **Direnç:** `{resistance} TL`\n"
                        f"📊 *Filtreler:* Supertrend SAT + EMA200 Altı + MACD + RSI ({round(rsi_val,1)}) [Dip Filtreli]"
                    )
                    send_telegram_message(message)

            except Exception:
                pass
        
        # Periyodik Özet Raporu
        summary_msg = (
            f"📊 *BİST BOT - ATR ÖZET RAPORU*\n\n"
            f"🕒 Zaman: `{datetime.now().strftime('%d-%m-%Y %H:%M')}`\n"
            f"🔍 Taranan Hisse Adedi: `{scanned_count}`\n"
            f"🎯 Yakalanan Sinyal: `{signals_found}`\n"
            f"Status: Akıllı ATR ve Sert RSI Filtreleri Devrede."
        )
        send_telegram_message(summary_msg)

        # 30 Dakika Bekleme
        time.sleep(1800)

# ==================== Ana Çalıştırma ====================
if __name__ == "__main__":
    threading.Thread(target=scan_bist, daemon=True).start()

    while True:
        time.sleep(60)
