"""
股票行情API模块
支持A股、港股、美股实时行情查询
"""

import requests
import re


def parse_stock_code(code: str) -> tuple:
    """
    解析股票代码，返回 (市场类型, 标准化代码)
    
    支持格式:
    - A股: 600519, sh600519, sz000001
    - 港股: hk00700, hk1810, 00700
    - 美股: usAAPL, AAPL, usGOOGL
    """
    code = code.strip().upper()
    
    # 港股
    if code.startswith('HK'):
        return ('HK', code[2:].zfill(5))
    
    # 美股
    if code.startswith('US'):
        return ('US', code[2:])
    
    # 上海A股
    if code.startswith('SH'):
        return ('SH', code[2:])
    
    # 深圳A股
    if code.startswith('SZ'):
        return ('SZ', code[2:])
    
    # 纯数字判断
    if code.isdigit():
        if len(code) == 5:
            # 5位数字默认港股
            return ('HK', code.zfill(5))
        elif len(code) == 6:
            if code.startswith('6'):
                return ('SH', code)
            else:
                return ('SZ', code)
    
    # 字母开头默认美股
    if code[0].isalpha():
        return ('US', code)
    
    return ('UNKNOWN', code)


def get_stock_realtime(code: str) -> dict:
    """
    获取股票实时行情
    
    Args:
        code: 股票代码，支持格式如 600519, hk00700, usAAPL
    
    Returns:
        包含股票信息的字典
    """
    market, symbol = parse_stock_code(code)
    
    if market == 'HK':
        return _get_hk_stock(symbol)
    elif market == 'US':
        return _get_us_stock(symbol)
    elif market in ('SH', 'SZ'):
        return _get_a_stock(market.lower() + symbol)
    else:
        return {'error': f'无法识别的股票代码: {code}'}


def _get_a_stock(full_code: str) -> dict:
    """获取A股实时行情"""
    url = f'http://hq.sinajs.cn/list={full_code}'
    headers = {
        'Referer': 'http://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gbk'
        data = response.text
        
        if 'FAILED' in data or '=""' in data:
            return {'error': '获取失败，请检查代码'}
        
        info = data.split('"')[1].split(',')
        if len(info) < 4:
            return {'error': '数据解析失败'}
        
        name = info[0]
        open_price = float(info[1]) if info[1] else 0
        yesterday_close = float(info[2]) if info[2] else 0
        current_price = float(info[3]) if info[3] else 0
        
        change = current_price - yesterday_close
        change_percent = (change / yesterday_close * 100) if yesterday_close > 0 else 0
        
        return {
            'code': full_code[2:],
            'name': name,
            'market': 'A',
            'current_price': current_price,
            'yesterday_close': yesterday_close,
            'open_price': open_price,
            'change': change,
            'change_percent': change_percent
        }
        
    except Exception as e:
        return {'error': f'请求失败: {e}'}


def _get_hk_stock(symbol: str) -> dict:
    """获取港股实时行情"""
    code = symbol.zfill(5)
    url = f'http://hq.sinajs.cn/list=hk{code}'
    headers = {
        'Referer': 'http://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gbk'
        data = response.text
        
        if 'FAILED' in data or '=""' in data:
            return {'error': '获取失败，请检查代码'}
        
        # 港股格式: 英文名,中文名,今开,昨收,最高,最低,最新价,...
        info = data.split('"')[1].split(',')
        if len(info) < 7:
            return {'error': '数据解析失败'}
        
        name = info[1]  # 中文名
        open_price = float(info[2]) if info[2] else 0
        yesterday_close = float(info[3]) if info[3] else 0
        current_price = float(info[6]) if info[6] else 0
        
        change = current_price - yesterday_close
        change_percent = (change / yesterday_close * 100) if yesterday_close > 0 else 0
        
        return {
            'code': code,
            'name': name,
            'market': 'HK',
            'current_price': current_price,
            'yesterday_close': yesterday_close,
            'open_price': open_price,
            'change': change,
            'change_percent': change_percent
        }
        
    except Exception as e:
        return {'error': f'请求失败: {e}'}


def _get_us_stock(symbol: str) -> dict:
    """获取美股实时行情"""
    url = f'http://hq.sinajs.cn/list=gb_{symbol.lower()}'
    headers = {
        'Referer': 'http://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gbk'
        data = response.text
        
        if 'FAILED' in data or '=""' in data:
            return {'error': '获取失败，请检查代码'}
        
        # 美股格式: 名称,当前价,涨跌额,涨跌幅%,时间,昨收,今开,...
        info = data.split('"')[1].split(',')
        if len(info) < 7:
            return {'error': '数据解析失败'}
        
        name = info[0]
        current_price = float(info[1]) if info[1] else 0
        change = float(info[2]) if info[2] else 0
        change_percent = float(info[3]) if info[3] else 0
        yesterday_close = float(info[5]) if info[5] else 0
        open_price = float(info[6]) if info[6] else 0
        
        return {
            'code': symbol.upper(),
            'name': name,
            'market': 'US',
            'current_price': current_price,
            'yesterday_close': yesterday_close,
            'open_price': open_price,
            'change': change,
            'change_percent': change_percent
        }
        
    except Exception as e:
        return {'error': f'请求失败: {e}'}
