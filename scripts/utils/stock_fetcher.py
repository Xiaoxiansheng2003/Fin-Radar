#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
stock_fetcher.py - 东方财富 A 股实时数据抓取模块
================================================
数据来源：东方财富网公开行情页面及公开 API
仅用于获取公开的金融行情数据，不涉及任何大模型服务。
"""

import re
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


class StockFetcher:
    """
    A 股行情数据抓取器（数据来源：东方财富网）

    支持获取：实时行情、估值指标、行业对比、历史财务、近期公告
    所有数据均来自东方财富公开页面，不涉及任何付费或大模型服务。
    """

    # 东方财富公开 API 地址
    BASE_QUOTE_URL = "http://push2.eastmoney.com/api/qt/stock/get"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    def __init__(self):
        if not HAS_REQUESTS:
            logger.warning("requests 库未安装，请执行: pip install requests")

    @staticmethod
    def _parse_stock_code(code: str) -> tuple:
        """
        解析股票代码，返回 (market, code)
        market: 1=上海, 0=深圳/创业板/北交所
        """
        code = code.strip().upper()

        # 去掉可能的前缀
        for prefix in ["SH", "SZ", "BJ"]:
            if code.startswith(prefix):
                code = code[len(prefix):]

        code = code.zfill(6)

        if code.startswith("6") or code.startswith("9"):
            return (1, code)  # 上海
        elif code.startswith("0") or code.startswith("3") or code.startswith("2"):
            return (0, code)  # 深圳
        elif code.startswith("4") or code.startswith("8"):
            return (0, code)  # 北交所
        else:
            return (1, code)  # 默认上海

    def fetch_realtime_quote(self, stock_code: str) -> Dict[str, Any]:
        """
        获取个股实时行情 + 估值指标

        返回字段：股价、涨跌幅、市盈率(动)、市净率、总市值、流通市值、
                 换手率、量比、振幅、每股收益、每股净资产等

        Args:
            stock_code: 股票代码（如 "600519"、"000001"、"SH600519"）

        Returns:
            Dict: 实时行情数据
        """
        if not HAS_REQUESTS:
            return {"success": False, "error": "requests 库未安装"}

        market, code = self._parse_stock_code(stock_code)
        secid = f"{market}.{code}"

        # 请求所有需要的字段
        fields = ",".join([
            "f43",   # 最新价
            "f44",   # 最高
            "f45",   # 最低
            "f46",   # 开盘
            "f47",   # 成交量（手）
            "f48",   # 成交额
            "f50",   # 量比
            "f55",   # 每股收益
            "f57",   # 代码
            "f58",   # 名称
            "f60",   # 昨收
            "f100",  # 行业
            "f116",  # 总市值
            "f117",  # 流通市值
            "f162",  # 市盈率(动)
            "f163",  # 市盈率(TTM)
            "f167",  # 市净率
            "f168",  # 换手率
            "f169",  # 涨跌额
            "f170",  # 涨跌幅
            "f171",  # 振幅
            "f173",  # 市盈率(静)
        ])

        params = {
            "secid": secid,
            "fields": fields,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fltt": 2,
        }

        try:
            resp = requests.get(
                self.BASE_QUOTE_URL,
                params=params,
                headers=self.HEADERS,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()

            if not data.get("data"):
                return {"success": False, "error": f"未找到股票 {stock_code} 的数据"}

            d = data["data"]

            result = {
                "success": True,
                "source": "东方财富",
                "code": d.get("f57", code),
                "name": d.get("f58", ""),
                "price": d.get("f43"),
                "change_pct": d.get("f170"),
                "change_amt": d.get("f169"),
                "open": d.get("f46"),
                "high": d.get("f44"),
                "low": d.get("f45"),
                "prev_close": d.get("f60"),
                "volume": d.get("f47"),
                "amount": d.get("f48"),
                "turnover_rate": d.get("f168"),
                "amplitude": d.get("f171"),
                "volume_ratio": d.get("f50"),
                "pe_ttm": d.get("f163"),
                "pe_static": d.get("f173"),
                "pe_dynamic": d.get("f162"),
                "pb": d.get("f167"),
                "total_market_cap": d.get("f116"),
                "circulating_market_cap": d.get("f117"),
                "eps": d.get("f55"),
                "industry": d.get("f100", ""),
            }

            # 单位转换：总市值/流通市值/成交额（元 → 亿元）
            for field in ["total_market_cap", "circulating_market_cap", "amount"]:
                if result[field] and isinstance(result[field], (int, float)):
                    result[f"{field}_yi"] = round(result[field] / 1e8, 2)

            return result

        except requests.RequestException as e:
            return {"success": False, "error": f"请求失败: {e}"}
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return {"success": False, "error": f"数据解析失败: {e}"}

    def fetch_financial_history(self, stock_code: str, periods: int = 4) -> Dict[str, Any]:
        """
        获取近几期财报核心数据（来源：东方财富财务摘要）

        Args:
            stock_code: 股票代码
            periods: 获取最近几期，默认 4 期（约 1 年）

        Returns:
            Dict: 历史财务数据
        """
        if not HAS_REQUESTS:
            return {"success": False, "error": "requests 库未安装"}

        market, code = self._parse_stock_code(stock_code)

        url = "https://emweb.securities.eastmoney.com/pc_hsf10/FinanceAnalysis/FinanceAnalysisAjax"

        params = {
            "companyType": 4,
            "reportDateType": 0,
            "reportType": 1,
            "code": f"{'SH' if market == 1 else 'SZ'}{code}",
        }

        try:
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("zygb"):
                return {"success": False, "error": "未找到财务数据"}

            reports = []
            items = data["zygb"].get("data", [])[:periods]

            for item in items:
                report = {
                    "report_date": item.get("REPORT_DATE", ""),
                    "revenue": item.get("TOTAL_OPERATE_INCOME"),
                    "net_profit": item.get("PARENT_NETPROFIT"),
                    "net_profit_deducted": item.get("DEDUCT_PARENT_NETPROFIT"),
                    "total_assets": item.get("TOTAL_ASSETS"),
                    "net_assets": item.get("TOTAL_EQUITY"),
                    "eps": item.get("BASIC_EPS"),
                    "roe": item.get("WEIGHTAVG_ROE"),
                    "gross_margin": item.get("SALES_GROSS_PROFIT_RATE"),
                    "net_margin": item.get("SALES_NET_PROFIT_RATE"),
                    "debt_ratio": item.get("DEBT_ASSET_RATIO"),
                    "revenue_yoy": item.get("TOTAL_OPERATE_INCOME_RATIO"),
                    "net_profit_yoy": item.get("PARENT_NETPROFIT_RATIO"),
                }
                reports.append(report)

            return {
                "success": True,
                "source": "东方财富",
                "code": code,
                "reports": reports
            }

        except Exception as e:
            return {"success": False, "error": f"获取财务数据失败: {e}"}

    def fetch_industry_peers(self, stock_code: str) -> Dict[str, Any]:
        """
        获取同行业公司对比（PE/PB/市值排名）

        Args:
            stock_code: 股票代码

        Returns:
            Dict: 行业对比数据
        """
        if not HAS_REQUESTS:
            return {"success": False, "error": "requests 库未安装"}

        quote = self.fetch_realtime_quote(stock_code)
        if not quote.get("success"):
            return {"success": False, "error": f"获取股票信息失败: {quote.get('error')}"}

        industry = quote.get("industry", "")
        if not industry:
            return {"success": False, "error": "未找到该股票的行业分类"}

        market, code = self._parse_stock_code(stock_code)

        url = "http://push2.eastmoney.com/api/qt/clist/get"

        # 获取所有行业列表
        params_map = {
            "pn": 1, "pz": 500, "po": 1, "np": 1,
            "fltt": 2, "invt": 2,
            "fs": "m:90+t:2",
            "fields": "f12,f14",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        }

        try:
            resp = requests.get(url, params=params_map, headers=self.HEADERS, timeout=10)
            industries = resp.json().get("data", {}).get("diff", [])

            industry_code = None
            for ind in industries:
                if ind.get("f14") == industry:
                    industry_code = ind.get("f12")
                    break

            if not industry_code:
                return {
                    "success": True,
                    "source": "东方财富",
                    "industry": industry,
                    "peers": [],
                    "note": "未找到行业板块代码"
                }

            # 获取该行业成分股
            params_peers = {
                "pn": 1, "pz": 20, "po": 1, "np": 1,
                "fltt": 2, "invt": 2,
                "fs": f"b:{industry_code}+f:!50",
                "fields": "f2,f3,f9,f12,f14,f20,f23,f115",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            }

            resp = requests.get(url, params=params_peers, headers=self.HEADERS, timeout=10)
            peers_data = resp.json().get("data", {}).get("diff", [])

            peers = []
            for p in peers_data:
                peers.append({
                    "code": p.get("f12", ""),
                    "name": p.get("f14", ""),
                    "price": p.get("f2"),
                    "change_pct": p.get("f3"),
                    "pe_dynamic": p.get("f9"),
                    "total_market_cap": p.get("f20"),
                    "pb": p.get("f23"),
                    "roe": p.get("f115"),
                })

            peers.sort(key=lambda x: x.get("total_market_cap") or 0, reverse=True)

            current_rank = None
            for i, p in enumerate(peers):
                if p["code"] == code:
                    current_rank = i + 1
                    p["is_current"] = True
                    break

            valid_pe = [p["pe_dynamic"] for p in peers if p.get("pe_dynamic") and p["pe_dynamic"] > 0]
            valid_pb = [p["pb"] for p in peers if p.get("pb") and p["pb"] > 0]

            industry_avg_pe = round(sum(valid_pe) / len(valid_pe), 2) if valid_pe else None
            industry_avg_pb = round(sum(valid_pb) / len(valid_pb), 2) if valid_pb else None

            return {
                "success": True,
                "source": "东方财富",
                "industry": industry,
                "industry_avg_pe": industry_avg_pe,
                "industry_avg_pb": industry_avg_pb,
                "current_rank": current_rank,
                "total_companies": len(peers),
                "peers": peers[:20],
                "current_stock": {
                    "pe_dynamic": quote.get("pe_dynamic"),
                    "pb": quote.get("pb"),
                    "total_market_cap": quote.get("total_market_cap"),
                }
            }

        except Exception as e:
            return {"success": False, "error": f"获取行业对比失败: {e}"}

    def fetch_announcements(self, stock_code: str, limit: int = 10) -> Dict[str, Any]:
        """
        获取公司近期公告

        Args:
            stock_code: 股票代码
            limit: 返回条数，默认 10

        Returns:
            Dict: 公告列表
        """
        if not HAS_REQUESTS:
            return {"success": False, "error": "requests 库未安装"}

        market, code = self._parse_stock_code(stock_code)

        url = "https://np-anotice-stock.eastmoney.com/api/security/ann"

        params = {
            "sr": -1,
            "page_size": limit,
            "page_index": 1,
            "ann_type": "A",
            "client_source": "web",
            "stock_list": code,
            "f_node": "0",
            "s_node": "0",
        }

        try:
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            announcements = []
            for item in data.get("data", {}).get("list", []):
                columns = item.get("columns", [])
                ann_type = columns[0].get("column_name", "") if columns else ""
                announcements.append({
                    "title": item.get("title", ""),
                    "date": (item.get("notice_date") or "")[:10],
                    "type": ann_type,
                    "url": f"https://data.eastmoney.com/notices/detail/{code}/{item.get('art_code', '')}.html",
                })

            return {
                "success": True,
                "source": "东方财富",
                "code": code,
                "count": len(announcements),
                "announcements": announcements,
            }

        except Exception as e:
            return {"success": False, "error": f"获取公告失败: {e}"}

    def generate_market_report(self, stock_code: str) -> str:
        """
        生成完整的市场数据报告（文本格式）

        Args:
            stock_code: 股票代码

        Returns:
            str: 格式化的报告文本
        """
        lines = []
        lines.append("=" * 60)
        lines.append("Fin-Radar 市场数据报告")
        lines.append("数据来源：东方财富网（公开行情数据）")
        lines.append("=" * 60)

        # 1. 实时行情
        quote = self.fetch_realtime_quote(stock_code)
        if quote.get("success"):
            lines.append(f"\n【实时行情】")
            lines.append("-" * 40)
            lines.append(f"股票: {quote['name']} ({quote['code']})")
            lines.append(f"行业: {quote.get('industry', '未知')}")
            lines.append(f"最新价: {quote.get('price', '-')}")

            change_pct = quote.get("change_pct")
            if change_pct is not None:
                trend = "↑" if change_pct > 0 else "↓" if change_pct < 0 else "→"
                lines.append(f"涨跌幅: {trend} {change_pct}%")

            lines.append(f"今开: {quote.get('open', '-')}  最高: {quote.get('high', '-')}  最低: {quote.get('low', '-')}")
            lines.append(f"昨收: {quote.get('prev_close', '-')}")
            lines.append(f"成交量: {quote.get('volume', '-')} 手")

            if quote.get("amount_yi"):
                lines.append(f"成交额: {quote['amount_yi']} 亿元")

            lines.append(f"换手率: {quote.get('turnover_rate', '-')}%  振幅: {quote.get('amplitude', '-')}%  量比: {quote.get('volume_ratio', '-')}")

            # 估值指标
            lines.append(f"\n【估值指标】")
            lines.append("-" * 40)
            lines.append(f"市盈率(动): {quote.get('pe_dynamic', '-')}")
            lines.append(f"市盈率(TTM): {quote.get('pe_ttm', '-')}")
            lines.append(f"市盈率(静): {quote.get('pe_static', '-')}")
            lines.append(f"市净率: {quote.get('pb', '-')}")
            lines.append(f"每股收益: {quote.get('eps', '-')}")

            if quote.get("total_market_cap_yi"):
                lines.append(f"总市值: {quote['total_market_cap_yi']} 亿元")
            if quote.get("circulating_market_cap_yi"):
                lines.append(f"流通市值: {quote['circulating_market_cap_yi']} 亿元")
        else:
            lines.append(f"\n实时行情获取失败: {quote.get('error')}")

        # 2. 历史财务
        finance = self.fetch_financial_history(stock_code, periods=4)
        if finance.get("success") and finance.get("reports"):
            lines.append(f"\n【近 4 期财报核心数据】")
            lines.append("-" * 40)
            for rpt in finance["reports"]:
                date = rpt.get("report_date", "")[:10]
                rev = rpt.get("revenue")
                profit = rpt.get("net_profit")
                roe = rpt.get("roe")
                debt = rpt.get("debt_ratio")

                rev_str = f"{rev/1e8:.2f}亿" if rev else "-"
                profit_str = f"{profit/1e8:.2f}亿" if profit else "-"
                roe_str = f"{roe:.2f}%" if roe is not None else "-"
                debt_str = f"{debt:.2f}%" if debt is not None else "-"

                lines.append(f"  {date}  营收:{rev_str}  净利润:{profit_str}  ROE:{roe_str}  负债率:{debt_str}")

        # 3. 行业对比
        industry = self.fetch_industry_peers(stock_code)
        if industry.get("success"):
            lines.append(f"\n【行业对比 - {industry.get('industry', '')}】")
            lines.append("-" * 40)

            if industry.get("industry_avg_pe"):
                lines.append(f"行业平均 PE: {industry['industry_avg_pe']}")
            if industry.get("industry_avg_pb"):
                lines.append(f"行业平均 PB: {industry['industry_avg_pb']}")
            if industry.get("current_rank"):
                lines.append(f"当前股票行业市值排名: 第 {industry['current_rank']}/{industry.get('total_companies', '?')}")

            if industry.get("peers"):
                lines.append(f"\n行业市值 Top 5:")
                for i, p in enumerate(industry["peers"][:5]):
                    marker = " ★" if p.get("is_current") else ""
                    cap_yi = f"{p['total_market_cap']/1e8:.0f}亿" if p.get("total_market_cap") else "-"
                    lines.append(f"  {i+1}. {p['name']}({p['code']})  市值:{cap_yi}  PE:{p.get('pe_dynamic', '-')}  PB:{p.get('pb', '-')}{marker}")

        # 4. 近期公告
        ann = self.fetch_announcements(stock_code, limit=5)
        if ann.get("success") and ann.get("announcements"):
            lines.append(f"\n【近期公告】")
            lines.append("-" * 40)
            for a in ann["announcements"]:
                lines.append(f"  [{a['date']}] {a['title']}")

        lines.append("\n" + "=" * 60)
        lines.append("注意：以上数据来自东方财富网公开行情，仅供参考，不构成投资建议。")
        lines.append("=" * 60)

        return "\n".join(lines)
