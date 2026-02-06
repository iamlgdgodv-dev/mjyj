"""
基金估值API - Vercel Serverless
所有代码合并到单文件，避免模块导入问题
"""

import json
import re
import requests
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# ============ 股票行情API (来自 stock_api.py) ============

def parse_stock_code(code: str) -> tuple:
    code = code.strip().upper()
    if code.startswith('HK'):
        return ('HK', code[2:].zfill(5))
    if code.startswith('US'):
        return ('US', code[2:])
    if code.startswith('SH'):
        return ('SH', code[2:])
    if code.startswith('SZ'):
        return ('SZ', code[2:])
    if code.isdigit():
        if len(code) == 5:
            return ('HK', code.zfill(5))
        elif len(code) == 6:
            if code.startswith('6'):
                return ('SH', code)
            else:
                return ('SZ', code)
    if code[0].isalpha():
        return ('US', code)
    return ('UNKNOWN', code)


def get_stock_realtime(code: str) -> dict:
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
    url = f'http://hq.sinajs.cn/list={full_code}'
    headers = {'Referer': 'http://finance.sina.com.cn', 'User-Agent': 'Mozilla/5.0'}
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
        code = full_code[2:]
        is_etf = code.startswith('51') or code.startswith('56') or code.startswith('15') or code.startswith('159')
        return {
            'code': code, 'name': name, 'market': 'ETF' if is_etf else 'A',
            'current_price': current_price, 'yesterday_close': yesterday_close,
            'open_price': open_price, 'change': change, 'change_percent': change_percent
        }
    except Exception as e:
        return {'error': f'请求失败: {e}'}


def _get_hk_stock(symbol: str) -> dict:
    code = symbol.zfill(5)
    url = f'http://hq.sinajs.cn/list=hk{code}'
    headers = {'Referer': 'http://finance.sina.com.cn', 'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gbk'
        data = response.text
        if 'FAILED' in data or '=""' in data:
            return {'error': '获取失败，请检查代码'}
        info = data.split('"')[1].split(',')
        if len(info) < 7:
            return {'error': '数据解析失败'}
        name = info[1]
        open_price = float(info[2]) if info[2] else 0
        yesterday_close = float(info[3]) if info[3] else 0
        current_price = float(info[6]) if info[6] else 0
        change = current_price - yesterday_close
        change_percent = (change / yesterday_close * 100) if yesterday_close > 0 else 0
        return {
            'code': code, 'name': name, 'market': 'HK',
            'current_price': current_price, 'yesterday_close': yesterday_close,
            'open_price': open_price, 'change': change, 'change_percent': change_percent
        }
    except Exception as e:
        return {'error': f'请求失败: {e}'}


def _get_us_stock(symbol: str) -> dict:
    url = f'http://hq.sinajs.cn/list=gb_{symbol.lower()}'
    headers = {'Referer': 'http://finance.sina.com.cn', 'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gbk'
        data = response.text
        if 'FAILED' in data or '=""' in data:
            return {'error': '获取失败，请检查代码'}
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
            'code': symbol.upper(), 'name': name, 'market': 'US',
            'current_price': current_price, 'yesterday_close': yesterday_close,
            'open_price': open_price, 'change': change, 'change_percent': change_percent
        }
    except Exception as e:
        return {'error': f'请求失败: {e}'}


# ============ 基金相关 (来自 fund_realtime.py) ============

def get_fund_info(fund_code: str) -> dict:
    url = f'http://fundf10.eastmoney.com/jbgk_{fund_code}.html'
    headers = {
        'Referer': 'http://fundf10.eastmoney.com/',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        content = response.text
        name_match = re.search(r'<title>([^<]+)', content)
        fund_name = name_match.group(1).split('(')[0] if name_match else '未知基金'
        is_etf_feeder = 'ETF联接' in fund_name or 'ETF联接' in content[:5000]
        etf_code = None
        etf_name = None
        if is_etf_feeder:
            etf_info = get_etf_from_link_fund(fund_code)
            if 'error' not in etf_info:
                etf_code = etf_info.get('etf_code')
                etf_name = etf_info.get('etf_name')
        return {
            'fund_code': fund_code, 'fund_name': fund_name,
            'is_etf_feeder': is_etf_feeder, 'etf_code': etf_code, 'etf_name': etf_name
        }
    except:
        return {
            'fund_code': fund_code, 'fund_name': '未知基金',
            'is_etf_feeder': False, 'etf_code': None, 'etf_name': None
        }


def get_etf_from_link_fund(fund_code: str) -> dict:
    url = f'http://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition?FCODE={fund_code}&deviceid=1&plat=Iphone&product=EFund&version=6.2.5'
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if not data.get('Success'):
            return {'error': f"查询失败: {data.get('ErrMsg', '未知错误')}"}
        datas = data.get('Datas', {})
        etf_code = datas.get('ETFCODE')
        etf_name = datas.get('ETFSHORTNAME')
        if not etf_code:
            return {'error': f'基金 {fund_code} 不是ETF联接基金或暂无ETF持仓信息'}
        return {'fund_code': fund_code, 'etf_code': etf_code, 'etf_name': etf_name}
    except Exception as e:
        return {'error': f'获取ETF信息失败: {e}'}


def get_fund_holdings(fund_code: str, top: int = 10) -> dict:
    topline = 100 if top <= 0 else top
    url = f'http://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={fund_code}&topline={topline}'
    headers = {
        'Referer': 'http://fundf10.eastmoney.com/',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        content = response.text
        if not content or 'content' not in content:
            return {'error': f'无法获取基金 {fund_code} 的数据'}
        name_match = re.search(r"title='([^']+)'", content)
        fund_name = name_match.group(1) if name_match else '未知基金'
        data_match = re.search(r'content:"(.+)"', content)
        if not data_match:
            return {'error': '持仓数据解析失败'}
        html_content = data_match.group(1)
        boxes = re.split(r"<div class='boxitem", html_content)
        first_quarter_html = boxes[1] if len(boxes) > 1 else html_content
        quarter_match = re.search(r'(\d{4})年(\d)季度', first_quarter_html)
        quarter = f'{quarter_match.group(1)}年第{quarter_match.group(2)}季度' if quarter_match else '未知季度'
        holdings = []
        row_pattern = re.compile(
            r'<tr><td>(\d+)</td>'
            r"<td><a[^>]*>(\d+)</a></td>"
            r"<td[^>]*><a[^>]*>([^<]+)</a></td>"
            r".*?<td[^>]*>(\d+\.?\d*)%</td>",
            re.DOTALL
        )
        for match in row_pattern.finditer(first_quarter_html):
            rank = int(match.group(1))
            if top <= 0 or rank <= top:
                holdings.append({
                    'rank': rank, 'stock_code': match.group(2),
                    'stock_name': match.group(3).strip(), 'ratio': float(match.group(4))
                })
        if not holdings:
            return {'error': '未找到持仓数据'}
        return {
            'fund_code': fund_code, 'fund_name': fund_name,
            'quarter': quarter, 'holdings': holdings
        }
    except Exception as e:
        return {'error': f'获取持仓失败: {e}'}


def guess_market(stock_code: str, stock_name: str) -> str:
    if len(stock_code) == 5:
        return f'hk{stock_code}'
    if len(stock_code) == 6:
        if stock_code.startswith('00') and not stock_code.startswith(('000', '002', '003')):
            return f'hk{stock_code}'
        if stock_code.startswith('6'):
            return f'sh{stock_code}'
        return f'sz{stock_code}'
    return stock_code


def calculate_fund_change(fund_code: str, top: int = 10, manual_etf: str = None) -> dict:
    fund_info = get_fund_info(fund_code)
    etf_code = manual_etf or fund_info.get('etf_code')
    etf_name = fund_info.get('etf_name', '')
    
    if (fund_info['is_etf_feeder'] or manual_etf) and etf_code:
        if etf_code.startswith('51') or etf_code.startswith('56'):
            etf_full = f'sh{etf_code}'
        else:
            etf_full = f'sz{etf_code}'
        etf_info = get_stock_realtime(etf_full)
        if 'error' not in etf_info:
            return {
                'fund_code': fund_code, 'fund_name': fund_info['fund_name'],
                'quarter': '实时', 'is_etf_feeder': True,
                'etf_code': etf_code, 'etf_name': etf_name or etf_info.get('name', ''),
                'stock_details': [{
                    'stock_code': etf_code, 'stock_name': etf_name or etf_info.get('name', 'ETF'),
                    'ratio': 95.0, 'change_percent': etf_info['change_percent'],
                    'weighted_change': etf_info['change_percent'] * 0.95,
                    'status': 'ok', 'market': 'ETF'
                }],
                'total_ratio': 95.0,
                'estimated_change': etf_info['change_percent'] * 0.95,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    holdings_info = get_fund_holdings(fund_code, top)
    if 'error' in holdings_info:
        return holdings_info
    
    holdings = holdings_info['holdings']
    total_holding_ratio = sum(h['ratio'] for h in holdings)
    if total_holding_ratio < 5:
        return {'error': f"该基金股票持仓比例过低({total_holding_ratio:.2f}%)，可能是ETF联接基金、债券基金或货币基金，暂不支持估算"}
    
    stock_details = []
    total_weighted_change = 0.0
    total_ratio = 0.0
    
    for h in holdings:
        code = guess_market(h['stock_code'], h['stock_name'])
        stock_info = get_stock_realtime(code)
        if 'error' in stock_info and code.startswith('hk'):
            stock_info = get_stock_realtime(h['stock_code'])
        if 'error' not in stock_info:
            weighted_change = h['ratio'] * stock_info['change_percent'] / 100
            total_weighted_change += weighted_change
            total_ratio += h['ratio']
            stock_details.append({
                'stock_code': h['stock_code'], 'stock_name': h['stock_name'],
                'ratio': h['ratio'], 'change_percent': stock_info['change_percent'],
                'weighted_change': weighted_change, 'status': 'ok',
                'market': stock_info.get('market', 'A')
            })
        else:
            stock_details.append({
                'stock_code': h['stock_code'], 'stock_name': h['stock_name'],
                'ratio': h['ratio'], 'change_percent': 0, 'weighted_change': 0,
                'status': 'error', 'market': '?'
            })
    
    return {
        'fund_code': fund_code, 'fund_name': holdings_info['fund_name'],
        'quarter': holdings_info['quarter'], 'is_etf_feeder': False,
        'stock_details': stock_details, 'total_ratio': total_ratio,
        'estimated_change': total_weighted_change,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


# ============ Vercel Handler ============

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        code = params.get('code', [''])[0]
        
        if not code or not code.isdigit() or len(code) != 6:
            result = {'error': '请提供有效的6位基金代码，如 ?code=110011'}
        else:
            try:
                result = calculate_fund_change(code)
            except Exception as e:
                result = {'error': str(e)}
        
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
