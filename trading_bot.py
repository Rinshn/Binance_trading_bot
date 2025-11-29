import argparse
import logging
import time
import math
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException


API_KEY = 'YOUR_API_KEY'
API_SECRET = 'YOUR_API_SECRET'

class BasicBot:
    def __init__(self, api_key, api_secret, testnet=True):
        """
        Initialize the trading bot
        """
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # File Handling
        file_handler = logging.FileHandler('trading_bot.log')
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Console Handler 
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(file_formatter)
        self.logger.addHandler(console_handler)

        self.logger.info("Bot initialized with testnet=%s", testnet)
        
        # Cache for symbol precision
        self.qty_precision = 3
        self.price_precision = 2
        self.min_notional = 5.0

    def setup_symbol_info(self, symbol):

        try:
            info = self.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    self.qty_precision = s['quantityPrecision']
                    self.price_precision = s['pricePrecision']
                    
                    # Get Min Notional(minimum trade value in usdt)
                    for f in s['filters']:
                        if f['filterType'] == 'MIN_NOTIONAL':
                            self.min_notional = float(f['notional'])
                            
                    self.logger.info(f"Setup complete for {symbol}: QtyPrec={self.qty_precision}, PricePrec={self.price_precision}, MinNotional={self.min_notional}")
                    return
        except BinanceAPIException as e:
            self.logger.error(f"Error fetching symbol info: {e}")

    def get_current_price(self, symbol):
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except BinanceAPIException as e:
            self.logger.error(f"Error fetching price: {e}")
            raise

    def get_futures_balance(self, asset='USDT'):
        try:
            account = self.client.futures_account()
            for balance in account['assets']:
                if balance['asset'] == asset:
                    return float(balance['availableBalance'])
            return 0.0
        except BinanceAPIException as e:
            self.logger.error(f"Error fetching balance: {e}")
            raise

    def place_order(self, symbol, side, quantity, order_type='MARKET', price=None):
        try:
            #  FIX: Round Quantity to accepted precision 
            # If user enters 0.0012 but precision is 3, this becomes 0.001
            adjusted_qty = round(quantity, self.qty_precision)
            
            # Validations
            if adjusted_qty <= 0:
                self.logger.error(f"Quantity {quantity} rounded to 0. Increase quantity.")
                return None

            current_price = self.get_current_price(symbol)
            notional = adjusted_qty * (price if price else current_price)

            if notional < self.min_notional:
                self.logger.warning(f"Order Value {notional:.2f} < Min {self.min_notional}. Trade ignored.")
                return None

            # Prepare Params
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': adjusted_qty,
            }
            
            # Add price only for limit orders
            if order_type == 'LIMIT':
                if price is None:
                    self.logger.error("Limit order requires price.")
                    return None
                # Fix Price Precision
                params['price'] = "{:.{}f}".format(price, self.price_precision)
                params['timeInForce'] = 'GTC'

            self.logger.info(f"Placing Order: {params}")
            
            # Execution
            order = self.client.futures_create_order(**params)
            self.logger.info(f"SUCCESS: {side} order {order['orderId']} filled/placed.")
            return order

        except BinanceAPIException as e:
            self.logger.error(f"Binance API Error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"General Error: {e}")
            return None

    def trading_bot(self, symbol, buy_threshold, sell_threshold, quantity, order_type='MARKET', poll_interval=3):
        
        # 1. Setup Symbol Rules
        self.setup_symbol_info(symbol)
        
        in_position = False
        print(f"Bot running on {symbol}. CTRL+C to stop.")
        
        try:
            while True:
                price = self.get_current_price(symbol)
                print(f"Price: {price:.2f} | Target Buy: {buy_threshold} | Target Sell: {sell_threshold}")

                # Simple Logic: Buy Low, Sell High
                if not in_position and price <= buy_threshold:
                    print(">> Buy Threshold Hit!")
                    buy_price = buy_threshold if order_type == 'LIMIT' else None
                    order = self.place_order(symbol, 'BUY', quantity, order_type, buy_price)
                    if order:
                        in_position = True

                elif in_position and price >= sell_threshold:
                    print(">> Sell Threshold Hit!")
                    sell_price = sell_threshold if order_type == 'LIMIT' else None
                    order = self.place_order(symbol, 'SELL', quantity, order_type, sell_price)
                    if order:
                        in_position = False

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\nBot stopped by user.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', type=str, default='BTCUSDT')
    parser.add_argument('--buy-threshold', type=float, default=90900.0)
    parser.add_argument('--sell-threshold', type=float, default=91000.0)
    parser.add_argument('--quantity', type=float, default=0.0012)
    parser.add_argument('--order-type', type=str, default='MARKET', choices=['MARKET', 'LIMIT'])
    parser.add_argument('--poll-interval', type=int, default=3)
    parser.add_argument('--leverage', type=int, default=1)

    args = parser.parse_args()

    bot = BasicBot(API_KEY, API_SECRET, testnet=True)
    
    # Setup leverage 
    try:
        bot.client.futures_change_leverage(symbol=args.symbol, leverage=args.leverage)
    except:
        pass

    bot.trading_bot(
        symbol=args.symbol,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        quantity=args.quantity,
        order_type=args.order_type,
        poll_interval=args.poll_interval
    )

if __name__ == "__main__":
    main()