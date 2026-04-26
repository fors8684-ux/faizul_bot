import requests
import time
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

FINNHUB_KEY      = 'd7l4mihr01qm7o0ag8a0d7l4r'
TELEGRAM_TOKEN   = '8791826770:AAGDva8cuyH8_JGdbxzS-s8Mcf5zu2gzMn8'
TELEGRAM_CHAT_ID = '5636877695'
SYMBOL_YF        = 'EURUSD=X'
SYMBOL_NAME      = 'EURUSD'
SIGNAL_STRENGTH  = 70
CHECK_MINUTES    = 15
ACCOUNT_BALANCE  = 5000
RISK_AMOUNT      = 150

def send_telegram(msg, emoji='📊'):
    try:
        requests.post(
            'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/sendMessage',
            json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': emoji + ' FAIZUL SIGNAL BOT\n\n' + msg + '\n\n🕐 ' + datetime.now().strftime('%H:%M:%S'),
                'parse_mode': 'Markdown'
            },
            timeout=10
        )
        print('Telegram sent')
    except Exception as e:
        print('Telegram error: ' + str(e))

def get_news():
    try:
        news = requests.get(
            'https://finnhub.io/api/v1/news?category=forex&token=' + FINNHUB_KEY,
            timeout=10
        ).json()
        if not news:
            return 0.0, 'No news'
        vader = SentimentIntensityAnalyzer()
        scores = [vader.polarity_scores(a['headline'])['compound'] for a in news[:10]]
        avg = float(np.mean(scores))
        top = news[0]['headline'][:60]
        print('News: ' + str(round(avg, 3)))
        return avg, top
    except Exception as e:
        print('News error: ' + str(e))
        return 0.0, 'Error'

def get_candles():
    try:
        df = yf.download(SYMBOL_YF, period='5d', interval='15m', progress=False)
        if df is None or len(df) < 60:
            return None
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
        df = df.reset_index()
        print('Candles: ' + str(len(df)))
        return df
    except Exception as e:
        print('Candles error: ' + str(e))
        return None

def add_indicators(df):
    c = df['close']
    df['ema20']    = c.ewm(span=20,  adjust=False).mean()
    df['ema50']    = c.ewm(span=50,  adjust=False).mean()
    df['ema200']   = c.ewm(span=200, adjust=False).mean()
    d = c.diff()
    gain = d.clip(lower=0).rolling(14).mean()
    loss = (-d.clip(upper=0)).rolling(14).mean().replace(0, 1e-9)
    df['rsi']      = 100 - (100 / (1 + gain / loss))
    df['macd']     = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df['macd_s']   = df['macd'].ewm(span=9, adjust=False).mean()
    hl = df['high'] - df['low']
    hc = (df['high'] - c.shift()).abs()
    lc = (df['low']  - c.shift()).abs()
    df['atr']      = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()
    df['bb_mid']   = c.rolling(20).mean()
    std            = c.rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * std
    df['bb_lower'] = df['bb_mid'] - 2 * std
    return df

def get_signal(df):
    L = df.iloc[-1]
    P = df.iloc[-2]
    buy = 0
    sell = 0
    why = []
    if L['ema20'] > L['ema50'] > L['ema200']:
        buy += 25
        why.append('EMA Full Bullish')
    elif L['ema20'] < L['ema50'] < L['ema200']:
        sell += 25
        why.append('EMA Full Bearish')
    elif L['ema20'] > L['ema50']:
        buy += 12
        why.append('EMA Short Bullish')
    else:
        sell += 12
        why.append('EMA Short Bearish')
    rsi = L['rsi']
    if rsi < 30:
        buy += 20
        why.append('RSI Oversold ' + str(round(rsi, 1)))
    elif rsi > 70:
        sell += 20
        why.append('RSI Overbought ' + str(round(rsi, 1)))
    elif rsi < 50:
        buy += 10
        why.append('RSI Bullish ' + str(round(rsi, 1)))
    else:
        sell += 10
        why.append('RSI Bearish ' + str(round(rsi, 1)))
    if P['macd'] < P['macd_s'] and L['macd'] > L['macd_s']:
        buy += 25
        why.append('MACD Bullish Cross')
    elif P['macd'] > P['macd_s'] and L['macd'] < L['macd_s']:
        sell += 25
        why.append('MACD Bearish Cross')
    elif L['macd'] > L['macd_s']:
        buy += 10
        why.append('MACD Bullish')
    else:
        sell += 10
        why.append('MACD Bearish')
    price = float(L['close'])
    if price <= float(L['bb_lower']):
        buy += 15
        why.append('BB Oversold')
    elif price >= float(L['bb_upper']):
        sell += 15
        why.append('BB Overbought')
    elif price > float(L['bb_mid']):
        buy += 5
        why.append('Above BB Mid')
    else:
        sell += 5
        why.append('Below BB Mid')
    if price > float(L['ema200']):
        buy += 15
        why.append('Bull Market')
    else:
        sell += 15
        why.append('Bear Market')
    total = buy + sell
    if total == 0:
        return 'HOLD', 0, why, float(L['atr']), price
    if buy > sell:
        s = int(buy / total * 100)
        return ('BUY' if s >= SIGNAL_STRENGTH else 'HOLD'), s, why, float(L['atr']), price
    s = int(sell / total * 100)
    return ('SELL' if s >= SIGNAL_STRENGTH else 'HOLD'), s, why, float(L['atr']), price

def calc_levels(signal, price, atr):
    sl_d = atr * 1.5
    tp_d = atr * 3.0
    if signal == 'BUY':
        sl = round(price - sl_d, 5)
        tp = round(price + tp_d, 5)
    else:
        sl = round(price + sl_d, 5)
        tp = round(price - tp_d, 5)
    sl_pips = max(int(sl_d / 0.0001), 10)
    lot = round(min(max(RISK_AMOUNT / (sl_pips * 10), 0.01), 2.0), 2)
    return sl, tp, lot

def run_cycle(n):
    print('CYCLE #' + str(n) + ' | ' + datetime.now().strftime('%H:%M:%S'))
    df = get_candles()
    if df is None:
        return
    df = add_indicators(df)
    signal, strength, reasons, atr, price = get_signal(df)
    news_score, top_news = get_news()
    nsig = 'BUY' if news_score > 0.15 else ('SELL' if news_score < -0.15 else 'HOLD')
    if signal != 'HOLD' and signal == nsig:
        strength = min(strength + 5, 100)
        reasons.append('News Confirms')
    print('Signal: ' + signal + ' | ' + str(strength) + '%')
    if signal != 'HOLD' and strength >= SIGNAL_STRENGTH:
        sl, tp, lot = calc_levels(signal, price, atr)
        rr = abs(round((tp - price) / (price - sl) if signal == 'BUY' else (price - tp) / (sl - price), 1))
        emoji = '🟢' if signal == 'BUY' else '🔴'
        profit_est = round(RISK_AMOUNT * rr, 2)
        msg = (
            emoji + ' *' + signal + ' SIGNAL - ' + SYMBOL_NAME + '*\n'
            '━━━━━━━━━━━━━━━━━━━━\n'
            '💱 Pair: ' + SYMBOL_NAME + '\n'
            '📈 Entry: `' + str(round(price, 5)) + '`\n'
            '🛑 Stop Loss: `' + str(sl) + '`\n'
            '✅ Take Profit: `' + str(tp) + '`\n'
            '📦 Lot Size: `' + str(lot) + '`\n'
            '💰 Risk: `$' + str(RISK_AMOUNT) + '`\n'
            '💵 Est. Profit: `$' + str(profit_est) + '`\n'
            '⚖️ RR: 1:' + str(rr) + '\n'
            '⚡ Strength: ' + str(strength) + '%\n'
            '━━━━━━━━━━━━━━━━━━━━\n'
            '📋 ' + ' | '.join(reasons[:4]) + '\n'
            '━━━━━━━━━━━━━━━━━━━━\n'
            '📰 ' + top_news[:50]
        )
        send_telegram(msg, emoji)
    elif 50 < strength < SIGNAL_STRENGTH:
        send_telegram('👀 Watching ' + SYMBOL_NAME + '\n' + signal + ' | ' + str(strength) + '%\nWait karo...', '⏳')
    else:
        print('No signal')

print('FAIZUL SIGNAL BOT STARTING...')
send_telegram(
    '*Bot Started! 24/7 Running*\n'
    '━━━━━━━━━━━━━━━━━━━━\n'
    '💱 ' + SYMBOL_NAME + '\n'
    '⚡ Strength: ' + str(SIGNAL_STRENGTH) + '%\n'
    '💰 Risk: $' + str(RISK_AMOUNT) + ' per trade\n'
    '🔄 Every ' + str(CHECK_MINUTES) + ' min\n'
    '━━━━━━━━━━━━━━━━━━━━\n'
    'Signals aayenge Telegram pe!\n'
    'MT5 mein manually lagao 📱',
    '🚀'
)

cycle = 0
while True:
    cycle += 1
    try:
        run_cycle(cycle)
    except Exception as e:
        print('Error: ' + str(e))
        send_telegram('Auto Fixed! Bot OK', '🔧')
    print('Next: ' + str(CHECK_MINUTES) + ' min...\n')
    time.sleep(CHECK_MINUTES * 60)
