import pandas as pd
from binance.client import Client
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
load_dotenv()
import ccxt 
import time
import warnings
warnings.filterwarnings('ignore')
import schedule

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = Client(api_key=api_key, api_secret=api_secret)

binance = ccxt.binance(config={
    'apiKey': api_key, 
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

symbol = 'DOGEUSDT'
interval = '30m'
leverage = 5

def post_leverage():
    resp = binance.fapiprivate_post_leverage({
        'symbol': symbol,
        'leverage': leverage,
    })
    time.sleep(0.5)
    return resp

def get_ohlc():
    end_time = datetime.now()
    start_time = end_time - timedelta(days=14)

    start_timestamp = int(start_time.timestamp() * 1000)
    end_timestamp = int(end_time.timestamp() * 1000)

    klines = client.get_historical_klines(symbol, interval, start_timestamp, end_timestamp)

    ohlc_data = []
    for kline in klines:
        timestamp = datetime.fromtimestamp(kline[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
        open_price = float(kline[1])
        high_price = float(kline[2])
        low_price = float(kline[3])
        close_price = float(kline[4])
        volume = float(kline[5])
        ohlc_data.append([timestamp, open_price, high_price, low_price, close_price, volume])

    ohlc_df = pd.DataFrame(ohlc_data, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])

    ohlc_df['Timestamp'] = pd.to_datetime(ohlc_df['Timestamp'])

    time.sleep(0.5)

    return ohlc_df

def get_current_price(df):
    df = df.tail(1)
    current_price = float(df['Close'])

    return current_price

def calculate_atr(df):
    df['High-Low'] = df['High'] - df['Low']
    df['High-PreviousClose'] = abs(df['High'] - df['Close'].shift(1))
    df['Low-PreviousClose'] = abs(df['Low'] - df['Close'].shift(1))
    df['TrueRange'] = df[['High-Low', 'High-PreviousClose', 'Low-PreviousClose']].max(axis=1)

    period = 14
    df['ATR'] = df['TrueRange'].rolling(period).mean()

    df.drop(['High-Low', 'High-PreviousClose', 'Low-PreviousClose', 'TrueRange'], axis=1, inplace=True)
    
    return df

def calculate_rsi(df):
    df['Change'] = df['Close'].diff()

    upward_change = df['Change'][df['Change'] > 0].mean()
    downward_change = -df['Change'][df['Change'] < 0].mean()

    rsi = 100 - (100 / (1 + (upward_change / downward_change)))
    
    return rsi

def calculate_atr_trailing_stop(df):
    atr_trailing_stop = pd.Series(index=df.index)

    for i in range(1, len(df)):
        n_loss = df.iloc[i]['ATR'] * 2
        close = df.iloc[i]['Close']
        prev_close = df.iloc[i - 1]['Close']
        prev_atr_trailing_stop = atr_trailing_stop.iloc[i - 1]

        if close > prev_atr_trailing_stop and prev_close > prev_atr_trailing_stop:
            atr_trailing_stop.iloc[i] = max(prev_atr_trailing_stop, close - n_loss)
        elif close < prev_atr_trailing_stop and prev_close < prev_atr_trailing_stop:
            atr_trailing_stop.iloc[i] = min(prev_atr_trailing_stop, close + n_loss)
        elif close > prev_atr_trailing_stop:
            atr_trailing_stop.iloc[i] = close - n_loss
        else:
            atr_trailing_stop.iloc[i] = close + n_loss

    df['ATR_Trailing_Stop'] = atr_trailing_stop

    df = df.tail(20)

    return df

def if_crossover(df):
    #  0 : initial value, no crossover 
    #  1 : upward crossover
    # -1 : downward crossover

    df = df.tail(2)
    
    prev_close = df.iloc[0]['Close']
    close = df.iloc[1]['Close']
    
    prev_atr_trailing_stop = df.iloc[0]['ATR_Trailing_Stop']
    atr_trailing_stop = df.iloc[1]['ATR_Trailing_Stop']

    if close > atr_trailing_stop and prev_close < prev_atr_trailing_stop:
        crossover = 1
    elif atr_trailing_stop > close and prev_atr_trailing_stop < close:
        crossover = -1
    else:
        crossover = 0

    return crossover

def position_decision(df, crossover, rsi):
    #  0 : Hold 
    #  1 : Enter Long  Position, Close Short Position
    # -1 : Enter Short Position, Close Long Position
    #  2 : Close Long  Positon
    # -2 : Close Short Position
    df = df.tail(1)
    close = df.iloc[0]['Close']
    atr_trailing_stop = df.iloc[0]['ATR_Trailing_Stop']

    if close > atr_trailing_stop and crossover == 1 and rsi > 55:
        position = 1
    elif close > atr_trailing_stop and crossover == 1 and rsi < 45:
        position = 1
    elif close < atr_trailing_stop and crossover == -1 and rsi > 55:
        position = -1
    elif close < atr_trailing_stop and crossover == -1 and rsi < 45:
        position = -1
    elif close < atr_trailing_stop and crossover == -1 and 45 <= rsi <= 55:
        position = 2
    elif close > atr_trailing_stop and crossover == 1 and 45 <= rsi <= 55:
        position = -2
    else:
        position = 0

    return position

def chart_analysis(): 
        ohlc_df = get_ohlc()
        
        ohlc_df = calculate_atr(ohlc_df)
        ohlc_df = calculate_atr_trailing_stop(ohlc_df) # Data Frame
        rsi = calculate_rsi(ohlc_df) # Most Recent Value
        
        crossover = if_crossover(ohlc_df)
        #  0 : Initial Value, No Crossover 
        #  1 : Upward Crossover
        # -1 : Downward Crossover

        decision = position_decision(ohlc_df, crossover, rsi)
        #  0 : Hold 
        #  1 : Enter Long  Position, Close Short Position
        # -1 : Enter Short Position, Close Long Position
        #  2 : Close Long  Positon
        # -2 : Close Short Position

        print(ohlc_df.tail(1))
        print("\n")
        print("RSI :",rsi)

        return decision, ohlc_df

def get_balance():
    balance = binance.fetch_balance(params={"type": "future"})
    free_balance = balance['free']
    usdt = free_balance['USDT']
    time.sleep(0.5)
    return usdt

def calculate_amount(usdt, current_price):
    if usdt > current_price:
        amount = usdt / current_price / 3
        amount = int(amount) - 1
        return amount
    elif usdt < current_price:
        # 여기 나중에 다시 계산해야됨
        amount = 0
        return amount
    else:
        amount = 0
        return amount

def before_trade(ohlc_df):
        current_price = get_current_price(ohlc_df)
        time.sleep(0.5)

        usdt = get_balance() # My Account
        
        amount = calculate_amount(usdt, current_price)

        time.sleep(0.5)

        if_position, prev_amount = my_position()
        time.sleep(0.5)

        return if_position, prev_amount, amount

def my_position():
    #  if_position Value
    #  0 : Initial Value, Have No Position
    #  1 : Prev Positon is Long
    # -1 : Prev Position is Short

    balance = binance.fetch_balance()
    positions = balance['info']['positions']

    for position in positions:
        if position["symbol"] == symbol:
            if float(position['positionAmt']) != 0:
                prev_amount = float(position['positionAmt'])
                if prev_amount > 0 : 
                    if_position = 1
                else :
                    if_position = -1
                    prev_amount = abs(prev_amount)
            else:
                if_position = 0
                prev_amount = 0

            return if_position, prev_amount

def buy(amount):
    binance.create_market_buy_order(
        symbol=symbol,
        amount=amount,
    )
    time.sleep(0.5)

def sell(amount):
    binance.create_market_sell_order(
        symbol=symbol,
        amount=amount,
    )
    time.sleep(0.5)

def if_trade(decision, ohlc_df):
    if decision == 0:
        return
    
    if_position, prev_amount, amount = before_trade(ohlc_df)

    #  decision Value
    #  0 : Hold 
    #  1 : Enter Long  Position, Close Short Position (If I have)
    # -1 : Enter Short Position, Close Long Position  (If I have)
    #  2 : Close Long  Positon   (If I have)
    # -2 : Close Short Position  (If I have)

    #  if_position Value
    #  0 : Initial Value, Have No Position
    #  1 : Prev Positon is Long
    # -1 : Prev Position is Short

    # decision == 1
    if decision == 1 and if_position == -1:
        buy(prev_amount)
        buy(amount)

    elif decision == 1 and if_position != -1 and if_position != 1:
        buy(amount)

    elif decision == 1 and if_position == 1:
        return

    # decision == -1
    elif decision == -1 and if_position == 1:
        sell(prev_amount)
        sell(amount)

    elif decision == -1 and if_position != 1 and if_position != -1:
        sell(amount)

    elif decision == -1 and if_position == -1 :
        return

    # decision == 2
    elif decision == 2 and if_position == 1:
        sell(amount)

    # decision == -2
    elif decision == -2 and if_position == -1:
        buy(amount)
    
    else:
        return

def every_30_min():
        time.sleep(10)
        decision, ohlc_df = chart_analysis()
        time.sleep(0.5)
        if_trade(decision, ohlc_df)

def schedule_tasks(my_function):
    schedule.every().hour.at(":00").do(my_function)
    schedule.every().hour.at(":30").do(my_function)

if __name__ == "__main__":
    resp = post_leverage() # Once

    schedule_tasks(every_30_min)  # 초기 스케줄 등록

    while True:
        schedule.run_pending()
        time.sleep(1)