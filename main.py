# -*- coding: utf-8 -*-
"""
Created on 2024/10/13 23:34
@project: huobiBuyNewCoin
---------
@summary: 火币平台抢新币脚本
---------
@author: ssson
---------
@email: ssson966@gmail.com
"""
import re
import os
import hmac
import yaml
import hashlib
import base64
import urllib.parse
import requests
from datetime import datetime, date, timezone
from decimal import Decimal, getcontext
from traceback import format_exc
from time import sleep, time

# 设置全局精度，例如 50 位小数
getcontext().prec = 50


class HuobiAPIClient:
    def __init__(self, access_key, secret_key, logger, base_url="https://api-aws.huobi.pro"):
        self.access_key = access_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.logger = logger
        self.account_id = self.__init_account_id()
    
    @staticmethod
    def warpFunc(func):
        def innerFunc(*arg, **kwargs):
            try:
                return func(*arg, **kwargs)
            except Exception as ec:
                stack = format_exc()
                arg[0].logger.error(f"ec is: {ec}\nstack is: {stack}")
                return None
        return innerFunc
    
    def generate_signature(self, method, domain, path, params):
        """
        生成用于签名的字符串，并返回 Base64 编码的 HmacSHA256 签名。
        """
        # 1. 规范请求方法（GET/POST）和换行符
        method = method.upper() + "\n"
        
        # 2. 规范域名（小写）和换行符
        domain = domain.lower() + "\n"
        
        # 3. 规范路径和换行符
        path = path + "\n"
        
        # 4. 对参数进行 URL 编码并排序
        sorted_params = sorted(params.items())
        encoded_params = urllib.parse.urlencode(sorted_params, quote_via=urllib.parse.quote)
        
        # 5. 拼接请求字符串
        to_sign = method + domain + path + encoded_params
        
        # 6. 生成签名
        hmac_obj = hmac.new(self.secret_key.encode('utf-8'), to_sign.encode('utf-8'), hashlib.sha256)
        signature = base64.b64encode(hmac_obj.digest()).decode('utf-8')
        
        return signature
    
    def send_request(self, method, path, params=None):
        """
        发送请求并自动添加签名。
        """
        # 构造最终的请求 URL
        url = self.base_url + path
        
        if params is None:
            params = {}
        public_params = {
            "AccessKeyId": self.access_key,
            "SignatureMethod": "HmacSHA256",
            "SignatureVersion": "2",
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        # 发送请求
        if method.upper() == "GET":
            # 添加公共请求参数
            params.update(public_params)
            # 生成签名
            domain = urllib.parse.urlparse(self.base_url).hostname
            signature = self.generate_signature(method, domain, path, params)
            # 将签名加入到请求参数中
            params["Signature"] = signature
            response = requests.get(url, params=params)
        elif method.upper() == "POST":
            # 生成签名
            domain = urllib.parse.urlparse(self.base_url).hostname
            signature = self.generate_signature(method, domain, path, public_params)
            # 将签名加入到请求参数中
            public_params["Signature"] = signature
            response = requests.post(url, params=public_params, json=params)
        else:
            raise ValueError("Unsupported HTTP method")
        
        # 返回响应结果
        return response
    
    @warpFunc
    def __init_account_id(self):
        resp = self.send_request("GET", "/v1/account/accounts")
        if resp.status_code == 200:
            return resp.json()['data'][0]["id"]
        else:
            return None
        
    @warpFunc
    def get_balance_usdt(self):
        resp = self.send_request("GET", f"/v1/account/accounts/{self.account_id}/balance")
        if resp.status_code == 200:
            balance_list = resp.json()['data']['list']
            for balance in balance_list:
                if balance["currency"] == "usdt" and balance["type"] == "trade":
                    usdt_balance = balance["available"]
                    self.logger.info(f"{self.account_id}账户可用余额为：{usdt_balance}")
                    return usdt_balance
        else:
            return None
    
    @warpFunc
    def get_trade_info(self, coinType="puffer"):
        resp = self.send_request("GET", "/v2/settings/common/symbols")
        if resp.status_code == 200:
            symbols_list = resp.json()['data']
            for symbol in symbols_list:
                if symbol["sc"] == f"{coinType}usdt":
                    self.logger.info(f"交易对{coinType}usdt信息：{symbol}")
                    return symbol
    
    @warpFunc
    def get_k_line_info(self, symbol: str, period: str, size: int = 1):
        para = {
            "symbol": symbol,
            "period": period,
            "size": size,
        }
        resp = self.send_request("GET", "/market/history/kline", params=para)
        if resp.status_code == 200:
            if resp.json()['status'] == "ok":
                info = resp.json()['data'][0]
                self.logger.info(f"获取到了{symbol}的{period}最近一条k线数据: {info}")
                return info
            else:
                return None
            
    @staticmethod
    def str_to_timestamp_ms(s):
        t = datetime.combine(date.today(), datetime.strptime(s, "%H:%M:%S").time())
        return int(t.timestamp() * 1000)
    
    @warpFunc
    def take_order_spot_api(self, symbol: str, amount: str, price: str, ctype: str = "buy-limit", **kwargs):
        para = {
            "account-id": self.account_id,
            "symbol": symbol,
            "type": ctype,
            "amount": amount,
            "price": price,
        }
        try:
            resp = self.send_request("POST", "/v1/order/orders/place", params=para)
            if resp.status_code == 200:
                result = resp.json()
                if result['status'] == "ok":
                    self.logger.info(f"成功下现货订单：{result['data']}")
                elif result.get('err-code'):
                    # 开盘价格保护,睡眠后进行重试
                    if result.get('err-code') == "forbidden-trade-for-open-protect":
                        err_msg = result.get('err-msg')
                        priceProtectionCloseTime = re.search(r"\d{2}:\d{2}:\d{2}", err_msg)
                        if priceProtectionCloseTime:
                            priceProtectionCloseTime = priceProtectionCloseTime.group()
                            priceProtectionCloseTimeStamp = self.str_to_timestamp_ms(priceProtectionCloseTime)
                            now_time = int(time() * 1000)
                            waitTime = priceProtectionCloseTimeStamp - now_time + 10  # 加10毫秒的误差，防止仍在开盘保护前下单
                            self.logger.warning(f"开盘价格保护，将在在{waitTime}毫秒后重试")
                            sleep(abs(waitTime) / 1000)
                            self.take_order_spot_api(symbol, amount, price, ctype)
                    # 下单价格高于开盘前下单限制价格
                    elif result.get('err-code') == "order-price-greater-than-limit":
                        # 下单价格下调百分之10，再次尝试下单
                        lessPrice = Decimal(price) * Decimal("0.9")
                        self.logger.warning(f"下单价格下调百分之10，再次尝试下单：{lessPrice}")
                        self.take_order_spot_api(symbol, amount, str(lessPrice), ctype)
                    elif result.get('err-code') == "order-price-less-than-limit":
                        # 下单价格上调百分之10，再次尝试下单
                        morePrice = Decimal(price) * Decimal("1.1")
                        self.logger.warning(f"下单价格上调百分之10，再次尝试下单：{morePrice}")
                        self.take_order_spot_api(symbol, amount, str(morePrice), ctype)
                    else:
                        self.logger.warning(f"下单失败：{result.get('err-msg')}，错误码：{result.get('err-code')}， 将继续重试下单。")
                        self.take_order_spot_api(symbol, amount, price, ctype)
                else:
                    self.logger.warning(f"下单失败, 未知错误：{result.json()}")
        except Exception as e:
            retry = kwargs.get("retry", 0)
            self.logger.error(f"下单失败, 未知错误, 将进行第{retry}次重试：{e}")
            if retry < 3:
                self.take_order_spot_api(symbol, amount, price, ctype, retry=retry + 1)
            else:
                self.logger.error(f"下单失败，重试次数过多：{e}")
                
    @warpFunc
    def get_order_info(self, order_id: str):
        resp = self.send_request("GET", f"/v1/order/orders/{order_id}")
        if resp.status_code == 200:
            self.logger.info(resp.json())
    
    @warpFunc
    def cancel_order(self, order_id: str):
        resp = self.send_request("POST", f"/v1/order/orders/{order_id}/submitcancel")
        if resp.status_code == 200:
            self.logger.info(resp.json())
            
    @warpFunc
    def grab_new_coins(self, coinType: str, multiple: float, test: bool = False):
        # 余额
        balance = int(float(client.get_balance_usdt()))
        trade_info = client.get_trade_info(coinType=coinType)
        # 交易数量精度
        precision_tap = trade_info["tap"]
        # 交易价格精度
        precision_tpp = trade_info["tpp"]
        # 交易总精度
        precision_ttp = trade_info["ttp"]
        self.logger.info(f"{coinType} 交易数量精度 is: {precision_tap}, 交易价格精度 is: {precision_tpp}, 交易总精度 is: {precision_ttp}")
        # 一直循环直到拿到开盘价格
        while True:
            now_time = int(time() * 1000)
            self.logger.info(f"开始获取数据时间戳：{now_time}")
            kLineInfo = client.get_k_line_info(symbol=f"{coinType}usdt", period="1min")
            self.logger.info(f"获取k线数据耗时：{int(time() * 1000 - now_time)} ms")
            if kLineInfo:
                openPrice = "{:.{}f}".format(kLineInfo["open"], precision_tpp)
                self.logger.info(f'{coinType} openPrice is: {openPrice}')
                multiple = "{:.2f}".format(multiple)
                # 根据倍数和开盘价计算买入价
                # 测试模式用负的倍数
                if test:
                    buy_price = Decimal(openPrice) / Decimal(multiple)
                else:
                    buy_price = Decimal(openPrice) * Decimal(multiple)
                # 修改购买价格位数为交易价格精度
                buy_price = buy_price.quantize(Decimal("0.{}".format("0" * precision_tpp)))
                self.logger.info(f"buy_price is: {buy_price}")
                balance = "{:.{}f}".format(balance, precision_ttp)
                self.logger.info(f"use buy balance is: {balance}")
                buy_amount = Decimal(balance) / buy_price
                buy_amount = buy_amount.quantize(Decimal('0.{}'.format("0" * precision_tap)))
                self.logger.info(f"buy_amount is: {buy_amount}")
                client.take_order_spot_api(symbol=f"{coinType}usdt", amount=str(buy_amount), price=str(buy_price))
                break
            
        
if __name__ == "__main__":
    import logging
    from logging.handlers import RotatingFileHandler
    
    logging.basicConfig(
        level=logging.INFO,
        encoding='utf-8',
        datefmt='%Y-%m-%d %H:%M:%S',
        format='$asctime - $name - [$module line:$lineno]- $levelname - $message',
        style="$"
    )
    file_log_format = logging.Formatter(
        fmt='$asctime - $name - [$module $funcName line:$lineno]- $levelname - $message',
        datefmt='%Y-%m-%d %H:%M:%S',
        style="$"
    )
    # 创建日志记录器，指明日志保存的路径，每个日志文件的最大值，保存的日志文件个数上限
    file_log_handle = RotatingFileHandler("appLog.log", maxBytes=1024 * 1024 * 10, backupCount=1, encoding='utf-8')
    # 设置格式
    file_log_handle.setFormatter(file_log_format)
    # 终端日志格式
    console_log_format = logging.Formatter(
        fmt="$name - $levelname - $message",
        style="$"
    )
    # 创建终端处理器
    console_handle = logging.StreamHandler()
    # 设置终端格式
    console_handle.setFormatter(console_log_format)
    # 获取日志对象
    appLogger = logging.getLogger("appLog")
    # 获取日志对象并且禁止日志传播给root logger
    appLogger.propagate = False
    # 为全局的日志工具对象添加日志记录器
    appLogger.addHandler(file_log_handle)
    # 为终端设置处理对象
    appLogger.addHandler(console_handle)
    
    if not os.path.exists("config.yaml"):
        init_config = {
            "ACCESS_KEY": "your_access_key",
            "SECRET_KEY": "your_secret_key"
        }
        # 写入key配置
        with open("config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(init_config, f)
        input("请先在config.yaml中填写ACCESS_KEY和SECRET_KEY，按回车键继续...")
    else:
        # 读取key配置
        with open("config.yaml", "r") as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
    
        ACCESS_KEY = config["ACCESS_KEY"]
        SECRET_KEY = config["SECRET_KEY"]
    
        coinType = input("请输入要抢新币的币种，例如(puffer)：").strip()
        multiple = float(input("请输入以开盘价几倍抢币，例如(2.5)：").strip())
        testMode = input("是否为测试模式，是请输入1，否请输入0，默认为0：").strip()
        testMode = bool(int(testMode if testMode else "0"))
        appLogger.info(f"抢新币种为：{coinType},倍数为：{multiple},测试模式为：{testMode}")
        # 创建 API 客户端实例
        client = HuobiAPIClient(ACCESS_KEY, SECRET_KEY, appLogger)
        client.grab_new_coins(coinType=coinType, multiple=multiple, test=testMode)
    