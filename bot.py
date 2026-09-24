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
        # Türkçe karakter kaldırıldı (Guvenli)
        self.wfile.write(b"BIST 100 1H Guvenli Scanner Bot is Running!")

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
TELEGRAM_TOKEN = "8853048772:AAEW22ekJlDBc3EK9pWTiC8plZVm_9RBwas"
CHAT_ID = "1131754179"

# BIST 100 Hisselerinin Tamamı (.IS uzantılı)
HISSELER = [
    "AEFES.IS", "AGHOL.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKFGY.IS", "AKFYE.IS", "AKSA.IS", "AKSEN.IS", "ALARK.IS",
    "ALBRK.IS", "ALFAS.IS", "ANSGR.IS", "ARCLK.IS", "ARDYZ.IS", "ASELS.IS", "ASTOR.IS", "BERA.IS", "BIENY.IS", "BIMAS.IS",
    "BIOEN.IS", "BOBET.IS", "BRSAN.IS", "BRYAT.IS", "BUCIM.IS", "CANTE.IS", "CCOLA.IS", "CIMSA.IS", "CWENE.IS", "DOAS.IS",
    "DOHOL.IS", "ECILC.IS", "ECZYT.IS", "EGEEN.IS", "EKGYO.IS", "ENJSA.IS", "ENKAI.IS", "EREGL.IS", "EUPWR.IS",
    "FROTO.IS", "GARAN.IS", "GESAN.IS", "GUBRF.IS", "HALKB.IS", "HEKTS.IS", "ISCTR.IS", "ISGYO.IS", "ISMEN.IS", "IZENR.IS",
    "KAYSE.IS", "KCAER.IS", "KCHOL.IS", "KLSER.IS", "KONTR.IS", "KORDS.IS", "KRDMD.IS", "KSTUR.IS",
    "LMKDC.IS", "MAALT.IS", "MAVI.IS", "MHRGY.IS", "MIATK.IS", "MGROS.IS", "MPARK.IS", "ODAS.IS", "OTKAR.IS", "OYYAT.IS",
    "OYAKC.IS", "PASEU.IS", "PETKM.IS", "PGSUS.IS", "PLTUR.IS", "PSGYO.IS", "REEDR.IS", "SAHOL.IS", "SASA.IS", "SDTTR.IS",
    "SISE.IS", "SKBNK.IS", "SMRTG.IS", "SOKM.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS", "TKFEN.IS", "TMSN.IS", "TOASO.IS",
    "TSKB.IS", "TTKOM.IS", "TTRAK.IS", "TUKAS.IS", "TUPRS.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YEOTK.IS",
    "YKBNK.IS", "YYLGD.IS", "ZOREN.IS"
]

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

def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ==================== Tarama Döngüsü ====================
def scan_markets():
    print("BIST 100 (1H Güvenlik Filtreli AL/SAT) Taraması Başlatılıyor...")

    for ticker in HISSELER:
        try:
            data_1h = yf.download(ticker, period="100d", interval="1h", progress=False)
            
            if data_1h.empty or len(data_1h) < 200:
                continue
                
            if isinstance(data_1h.columns, pd.MultiIndex):
                data_1h.columns = data_1h.columns.get_level_values(0)

            # İndikatör Hesaplamaları
            data_1h['Supertrend'], data_1h['ST_Direction'] = calculate_supertrend(data_1h)
            data_1h['RSI'] = calculate_rsi(data_1h)
            data_1h['Vol_SMA20'] = data_1h['Volume'].rolling(window=20).mean()
            data_1h['EMA200'] = data_1h['Close'].ewm(span=200, adjust=False).mean()

            last_1h = data_1h.iloc[-1]
            prev_1h = data_1h.iloc[-2]

            # Ortak Filtreler
            volume_confirmed = last_1h['Volume'] > last_1h['Vol_SMA20']
            
            # Gün içi aşırı primlenme kontrolü (%4.5 sınırı)
            low_price = last_1h['Low']
            close_price = last_1h['Close']
            price_change_from_low = ((close_price - low_price) / low_price) * 100
            not_overbought_today = price_change_from_low <= 4.5

            # 🟢 GÜVENLİ AL SİNYALİ
            st_buy_signal = (prev_1h['ST_Direction'] == -1) and (last_1h['ST_Direction'] == 1)
            ema200_buy_ok = last_1h['Close'] > last_1h['EMA200']
            rsi_buy_ok = 40 <= last_1h['RSI'] <= 60

            if st_buy_signal and volume_confirmed and ema200_buy_ok and rsi_buy_ok and not_overbought_today:
                entry_price = round(last_1h['Close'], 2)
                stop_loss = round(entry_price * 0.965, 2)
                take_profit = round(entry_price * 1.07, 2)

                message = (
                    f"🟢 *GÜVENLİ AL SİNYALİ (ALIM VARANTI)*\n\n"
                    f"📌 **Hisse:** `{ticker}`\n"
                    f"💰 **Sinyal/Giriş Fiyatı:** `{entry_price} TL`\n"
                    f"🎯 **Satış/Hedef Fiyat (+%7):** `{take_profit} TL`\n"
                    f"🛑 **Stop-Loss (-%3.5):** `{stop_loss} TL`\n\n"
                    f"📊 *Filtreler:* 1H Supertrend Kırılımı + EMA200 Trend Onayı + Hacim Onaylı + RSI ({round(last_1h['RSI'],1)})"
                )
                print(f"Güvenli AL Sinyali Bulundu: {ticker}")
                send_telegram_message(message)

            # 🔴 GÜVENLİ SAT SİNYALİ
            st_sell_signal = (prev_1h['ST_Direction'] == 1) and (last_1h['ST_Direction'] == -1)
            ema200_sell_ok = last_1h['Close'] < last_1h['EMA200']
            rsi_sell_ok = 32 <= last_1h['RSI'] <= 55

            if st_sell_signal and volume_confirmed and ema200_sell_ok and rsi_sell_ok:
                entry_price = round(last_1h['Close'], 2)
                stop_loss = round(entry_price * 1.035, 2)
                take_profit = round(entry_price * 0.93, 2)

                message = (
                    f"🔴 *GÜVENLİ SAT SİNYALİ (SATIM VARANTI)*\n\n"
                    f"📌 **Hisse:** `{ticker}`\n"
                    f"💰 **Sinyal/Giriş Fiyatı:** `{entry_price} TL`\n"
                    f"🎯 **Satış/Hedef Fiyat (-%7):** `{take_profit} TL`\n"
                    f"🛑 **Stop-Loss (+%3.5):** `{stop_loss} TL`\n\n"
                    f"📊 *Filtreler:* 1H Supertrend SAT Kırılımı + EMA200 Altı Düşüş Trendi + Hacim Onaylı + RSI ({round(last_1h['RSI'],1)})"
                )
                print(f"Güvenli SAT Sinyali Bulundu: {ticker}")
                send_telegram_message(message)

        except Exception as e:
            print(f"{ticker} işlenirken hata oluştu: {e}")

# ==================== Ana Çalıştırma Döngüsü ====================
if __name__ == "__main__":
    while True:
        scan_markets()
        time.sleep(3600)
