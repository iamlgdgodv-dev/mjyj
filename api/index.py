"""
基金估值API - 适配Vercel Serverless部署
直接复用 fund_realtime.py 和 stock_api.py 的逻辑
"""

import sys
import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 添加父目录到路径，以便导入现有模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fund_realtime import calculate_fund_change


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        # CORS
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
