"""
基金实时涨跌估算脚本
通过基金持仓和股票实时行情，估算基金当天涨跌
支持A股、港股持仓，支持ETF联接基金
"""

import argparse
import requests
import re
from datetime import datetime
from stock_api import get_stock_realtime, parse_stock_code


def get_fund_info(fund_code: str) -> dict:
    """获取基金基本信息，判断是否为ETF联接基金"""
    url = f'http://fundf10.eastmoney.com/jbgk_{fund_code}.html'
    headers = {
        'Referer': 'http://fundf10.eastmoney.com/',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        content = response.text
        
        # 提取基金名称
        name_match = re.search(r'<title>([^<]+)', content)
        fund_name = name_match.group(1).split('(')[0] if name_match else '未知基金'
        
        # 判断是否为ETF联接基金
        is_etf_feeder = 'ETF联接' in fund_name or 'ETF联接' in content[:5000]
        
        # 如果是ETF联接基金，获取持仓的ETF代码
        etf_code = None
        etf_name = None
        if is_etf_feeder:
            etf_info = get_etf_from_link_fund(fund_code)
            if 'error' not in etf_info:
                etf_code = etf_info.get('etf_code')
                etf_name = etf_info.get('etf_name')
        
        return {
            'fund_code': fund_code,
            'fund_name': fund_name,
            'is_etf_feeder': is_etf_feeder,
            'etf_code': etf_code,
            'etf_name': etf_name
        }
    except:
        return {
            'fund_code': fund_code,
            'fund_name': '未知基金',
            'is_etf_feeder': False,
            'etf_code': None,
            'etf_name': None
        }


def get_etf_from_link_fund(fund_code: str) -> dict:
    """获取ETF联接基金持仓的ETF代码"""
    url = f'http://fundmobapi.eastmoney.com/FundMNewApi/FundMNInverstPosition?FCODE={fund_code}&deviceid=1&plat=Iphone&product=EFund&version=6.2.5'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
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
        
        return {
            'fund_code': fund_code,
            'etf_code': etf_code,
            'etf_name': etf_name
        }
        
    except Exception as e:
        return {'error': f'获取ETF信息失败: {e}'}


def get_fund_holdings(fund_code: str, top: int = 10) -> dict:
    """获取基金持仓信息"""
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
        
        # 只取第一个季度的数据
        boxes = re.split(r"<div class='boxitem", html_content)
        if len(boxes) > 1:
            first_quarter_html = boxes[1]
        else:
            first_quarter_html = html_content
        
        quarter_match = re.search(r'(\d{4})年(\d)季度', first_quarter_html)
        if quarter_match:
            quarter = f'{quarter_match.group(1)}年第{quarter_match.group(2)}季度'
        else:
            quarter = '未知季度'
        
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
                    'rank': rank,
                    'stock_code': match.group(2),
                    'stock_name': match.group(3).strip(),
                    'ratio': float(match.group(4))
                })
        
        if not holdings:
            return {'error': '未找到持仓数据'}
        
        return {
            'fund_code': fund_code,
            'fund_name': fund_name,
            'quarter': quarter,
            'holdings': holdings
        }
        
    except Exception as e:
        return {'error': f'获取持仓失败: {e}'}


def guess_market(stock_code: str, stock_name: str) -> str:
    """根据股票代码猜测市场类型"""
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
    """计算基金实时涨跌"""
    
    # 先检查是否为ETF联接基金
    fund_info = get_fund_info(fund_code)
    
    # 手动指定ETF代码优先
    etf_code = manual_etf or fund_info.get('etf_code')
    etf_name = fund_info.get('etf_name', '')
    
    if (fund_info['is_etf_feeder'] or manual_etf) and etf_code:
        # ETF联接基金，直接查ETF涨跌
        if etf_code.startswith('51') or etf_code.startswith('56'):
            etf_full = f'sh{etf_code}'
        else:
            etf_full = f'sz{etf_code}'
        
        etf_info = get_stock_realtime(etf_full)
        
        if 'error' not in etf_info:
            return {
                'fund_code': fund_code,
                'fund_name': fund_info['fund_name'],
                'quarter': '实时',
                'is_etf_feeder': True,
                'etf_code': etf_code,
                'etf_name': etf_name or etf_info.get('name', ''),
                'stock_details': [{
                    'stock_code': etf_code,
                    'stock_name': etf_name or etf_info.get('name', 'ETF'),
                    'ratio': 95.0,
                    'change_percent': etf_info['change_percent'],
                    'weighted_change': etf_info['change_percent'] * 0.95,
                    'status': 'ok',
                    'market': 'ETF'
                }],
                'total_ratio': 95.0,
                'estimated_change': etf_info['change_percent'] * 0.95,
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    # 普通基金，按持仓计算
    holdings_info = get_fund_holdings(fund_code, top)
    if 'error' in holdings_info:
        return holdings_info
    
    holdings = holdings_info['holdings']
    
    # 检查持仓比例是否过低
    total_holding_ratio = sum(h['ratio'] for h in holdings)
    if total_holding_ratio < 5:
        return {
            'error': f"该基金股票持仓比例过低({total_holding_ratio:.2f}%)，可能是ETF联接基金、债券基金或货币基金，暂不支持估算"
        }
    
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
                'stock_code': h['stock_code'],
                'stock_name': h['stock_name'],
                'ratio': h['ratio'],
                'change_percent': stock_info['change_percent'],
                'weighted_change': weighted_change,
                'status': 'ok',
                'market': stock_info.get('market', 'A')
            })
        else:
            stock_details.append({
                'stock_code': h['stock_code'],
                'stock_name': h['stock_name'],
                'ratio': h['ratio'],
                'change_percent': 0,
                'weighted_change': 0,
                'status': 'error',
                'market': '?'
            })
    
    return {
        'fund_code': fund_code,
        'fund_name': holdings_info['fund_name'],
        'quarter': holdings_info['quarter'],
        'is_etf_feeder': False,
        'stock_details': stock_details,
        'total_ratio': total_ratio,
        'estimated_change': total_weighted_change,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def display_result(info: dict):
    """显示结果"""
    if 'error' in info:
        print(f"❌ {info['error']}")
        return
    
    print(f"\n{'='*80}")
    print(f"基金: {info['fund_name']} ({info['fund_code']})")
    
    if info.get('is_etf_feeder'):
        print(f"类型: ETF联接基金 -> 跟踪ETF: {info.get('etf_name', '')} ({info.get('etf_code', '')})")
    else:
        print(f"持仓报告期: {info['quarter']}")
    
    print(f"查询时间: {info['update_time']}")
    print(f"{'='*80}")
    print(f"{'股票代码':<10} {'股票名称':<12} {'市场':<6} {'占净值比':<10} {'今日涨跌':<12} {'贡献涨跌':<10}")
    print(f"{'-'*80}")
    
    for s in info['stock_details']:
        status = '' if s['status'] == 'ok' else ' ⚠️'
        market = s.get('market', '?')
        sign = '+' if s['change_percent'] > 0 else ''
        wsign = '+' if s['weighted_change'] > 0 else ''
        print(f"{s['stock_code']:<10} {s['stock_name']:<12} {market:<6} {s['ratio']:<10.2f}% {sign}{s['change_percent']:<11.2f}% {wsign}{s['weighted_change']:<9.4f}%{status}")
    
    print(f"{'-'*80}")
    
    sign = '+' if info['estimated_change'] > 0 else ''
    trend = '📈' if info['estimated_change'] > 0 else ('📉' if info['estimated_change'] < 0 else '➡️')
    
    print(f"持仓占比: {info['total_ratio']:.2f}%")
    print(f"基金估算涨跌: {sign}{info['estimated_change']:.4f}%  {trend}")
    print(f"{'='*80}")
    
    if info.get('is_etf_feeder'):
        print("⚠️ 注意: ETF联接基金按95%仓位估算，实际涨跌以基金公司公布为准\n")
    else:
        print("⚠️ 注意: 此为根据持仓估算，实际涨跌以基金公司公布为准\n")


def main():
    parser = argparse.ArgumentParser(description='📊 基金实时涨跌估算')
    parser.add_argument('code', help='基金代码 (如: 110011)')
    parser.add_argument('-t', '--top', type=int, default=0, help='只计算前N大持仓 (默认全部)')
    parser.add_argument('-e', '--etf', help='手动指定ETF代码 (用于ETF联接基金)')
    
    args = parser.parse_args()
    
    code = args.code.strip()
    if not code.isdigit() or len(code) != 6:
        print("❌ 请输入6位数字的基金代码")
        return
    
    print("正在查询持仓和股票行情...")
    info = calculate_fund_change(code, args.top, args.etf)
    display_result(info)


if __name__ == '__main__':
    main()
