# 火币交易所抢新币脚本
本脚本通过[火币API](https://www.htx.com/zh-cn/opend/)实现抢新币功能，抢币逻辑为用户配置好要抢的币种和倍数，在拿到第一分钟的开盘价后下一个 倍数 * 开盘价 的现货单，下单量为全部现货余额的整数。

# 简单使用
## 1.在[Release](https://github.com/DGxg9420/huobiBuyNewCoin/releases/latest)下载对应平台的可执行程序压缩包解压。

## 2.执行里面的可执行程序会自动生成config.yaml配置文件，在配置文件里输入你的[火币API](https://www.htx.com/zh-cn/opend/) Key。

"""yaml
ACCESS_KEY: YOUR_ACCESS_KEY
SECRET_KEY: YOUR_SECRET_KEY
"""

## 3.再次运行可执行程序输入必要的信息就可以开启抢新币了。
