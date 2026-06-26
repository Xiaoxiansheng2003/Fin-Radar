#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
stock_fetcher.py - A 股实时数据抓取模块（多源容错）
====================================================
数据来源：东方财富网、新浪财经（备用）
自动降级：东方财富 → 新浪财经，确保服务可用性。
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

    # 新浪财经备用接口
    SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
    SINA_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn/",
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

    def _fetch_realtime_sina(self, stock_code: str) -> Dict[str, Any]:
        """
        新浪财经备用接口 - 当东方财富接口不可用时自动降级

        Args:
            stock_code: 股票代码

        Returns:
            Dict: 行情数据（字段名与东方财富接口保持一致）
        """
        market, code = self._parse_stock_code(stock_code)
        prefix = "sh" if market == 1 else "sz"
        sina_code = f"{prefix}{code}"

        try:
            resp = requests.get(
                f"{self.SINA_QUOTE_URL}{sina_code}",
                headers=self.SINA_HEADERS,
                timeout=10
            )
            resp.raise_for_status()

            # 解析新浪行情格式：var hq_str_sz300308="名称,今开,昨收,当前,最高,最低,..."
            match = re.search(r'"(.+)"', resp.text)
            if not match:
                return {"success": False, "error": "新浪接口返回数据为空"}

            data = match.group(1).split(",")
            if len(data) < 10:
                return {"success": False, "error": "新浪接口数据不完整"}

            name = data[0]
            open_price = float(data[1]) if data[1] else None
            prev_close = float(data[2]) if data[2] else None
            current = float(data[3]) if data[3] else None
            high = float(data[4]) if data[4] else None
            low = float(data[5]) if data[5] else None
            volume = float(data[8]) if data[8] else None  # 成交量（股）
            amount = float(data[9]) if data[9] else None  # 成交额

            change_pct = None
            change_amt = None
            if current and prev_close and prev_close > 0:
                change_pct = round((current - prev_close) / prev_close * 100, 2)
                change_amt = round(current - prev_close, 2)

            result = {
                "success": True,
                "source": "新浪财经（备用）",
                "code": code,
                "name": name,
                "price": current,
                "change_pct": change_pct,
                "change_amt": change_amt,
                "open": open_price,
                "high": high,
                "low": low,
                "prev_close": prev_close,
                "volume": round(volume / 100) if volume else None,  # 转为手
                "amount": amount,
                "turnover_rate": None,
                "amplitude": None,
                "volume_ratio": None,
                "pe_ttm": None,
                "pe_static": None,
                "pe_dynamic": None,
                "pb": None,
                "total_market_cap": None,
                "circulating_market_cap": None,
                "eps": None,
                "industry": "",
            }

            if amount:
                result["amount_yi"] = round(amount / 1e8, 2)

            return result

        except Exception as e:
            return {"success": False, "error": f"新浪备用接口也失败: {e}"}

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
            logger.warning(f"东方财富接口失败: {e}，尝试新浪备用接口...")
            return self._fetch_realtime_sina(stock_code)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.warning(f"东方财富数据解析失败: {e}，尝试新浪备用接口...")
            return self._fetch_realtime_sina(stock_code)

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
            logger.warning(f"东方财富公告接口失败: {e}")
            return {"success": False, "error": f"获取公告失败: {e}"}

    # 公告关键事件关键词分类表
    ANNOUNCEMENT_KEYWORDS = {
        "增减持": ["增持", "减持", "回购", "股东持股变动", "权益变动"],
        "诉讼仲裁": ["诉讼", "仲裁", "起诉", "被诉", "判决", "裁定"],
        "担保质押": ["担保", "质押", "抵押", "对外担保"],
        "关联交易": ["关联交易"],
        "业绩预告": ["业绩预告", "业绩预增", "业绩预减", "业绩预盈", "业绩预亏", "业绩快报"],
        "分红送转": ["分红", "派息", "送转", "利润分配"],
        "并购重组": ["收购", "重组", "并购", "合并", "资产注入"],
        "违规处罚": ["处罚", "违规", "警示函", "监管函", "立案"],
        "人事变动": ["董事", "高管", "辞职", "聘任", "换届"],
        "再融资": ["增发", "配股", "可转债", "定增", "融资"],
    }

    def analyze_announcements(self, stock_code: str, limit: int = 20) -> Dict[str, Any]:
        """
        抓取公告并进行关键事件分类

        Args:
            stock_code: 股票代码
            limit: 抓取条数

        Returns:
            Dict: 含事件分类的公告分析结果
        """
        raw = self.fetch_announcements(stock_code, limit=limit)
        if not raw.get("success"):
            return raw

        classified = []
        event_counts = {}

        for ann in raw.get("announcements", []):
            title = ann.get("title", "")
            matched_types = []
            for event_type, keywords in self.ANNOUNCEMENT_KEYWORDS.items():
                for kw in keywords:
                    if kw in title:
                        matched_types.append(event_type)
                        event_counts[event_type] = event_counts.get(event_type, 0) + 1
                        break

            classified.append({
                **ann,
                "event_types": matched_types if matched_types else ["其他"],
                "risk_flag": any(t in matched_types for t in ["诉讼仲裁", "违规处罚", "担保质押"]),
            })

        # 生成事件摘要
        summary_parts = []
        for etype, count in sorted(event_counts.items(), key=lambda x: -x[1]):
            summary_parts.append(f"{etype}({count})")

        risk_events = [a for a in classified if a.get("risk_flag")]

        return {
            "success": True,
            "source": "东方财富",
            "code": raw.get("code"),
            "total": len(classified),
            "event_summary": summary_parts,
            "risk_event_count": len(risk_events),
            "risk_events": risk_events,
            "announcements": classified,
        }

    def generate_credit_assessment(self, stock_code: str) -> Dict[str, Any]:
        """
        基于已有财务指标 + 行业数据生成信贷评估摘要

        Returns:
            Dict: 信贷评估结果（含信用评级、偿债能力、盈利质量、风险信号）
        """
        if not HAS_REQUESTS:
            return {"success": False, "error": "requests 库未安装"}

        # 并行获取数据
        quote = self.fetch_realtime_quote(stock_code)
        finance = self.fetch_financial_history(stock_code, periods=4)
        industry = self.fetch_industry_peers(stock_code)
        ann_analysis = self.analyze_announcements(stock_code, limit=15)

        if not quote.get("success"):
            return {"success": False, "error": f"获取行情失败: {quote.get('error')}"}

        signals = []
        score = 100  # 起始满分，扣分制

        # --- 偿债能力 ---
        reports = finance.get("reports", []) if finance.get("success") else []
        latest = reports[0] if reports else {}

        debt_ratio = latest.get("debt_ratio") or 0
        if debt_ratio > 70:
            signals.append({"dim": "偿债能力", "level": "高风险", "detail": f"资产负债率 {debt_ratio:.1f}%，超过 70% 警戒线"})
            score -= 25
        elif debt_ratio > 60:
            signals.append({"dim": "偿债能力", "level": "关注", "detail": f"资产负债率 {debt_ratio:.1f}%，偏高"})
            score -= 10

        # --- 盈利质量 ---
        net_margin = latest.get("net_margin")
        if net_margin is not None and net_margin < 0:
            signals.append({"dim": "盈利质量", "level": "高风险", "detail": f"净利率 {net_margin:.1f}%，为负值"})
            score -= 20

        roe = latest.get("roe")
        if roe is not None and roe < 0:
            signals.append({"dim": "盈利质量", "level": "高风险", "detail": f"ROE {roe:.1f}%，为负值"})
            score -= 15
        elif roe is not None and roe < 5:
            signals.append({"dim": "盈利质量", "level": "关注", "detail": f"ROE {roe:.1f}%，偏低"})
            score -= 5

        # --- 成长性 ---
        if len(reports) >= 2:
            rev_trend = [r.get("revenue") for r in reports if r.get("revenue")]
            if len(rev_trend) >= 2 and rev_trend[0] < rev_trend[-1]:
                signals.append({"dim": "成长性", "level": "关注", "detail": "近 4 期营收呈下降趋势"})
                score -= 10

            profit_trend = [r.get("net_profit") for r in reports if r.get("net_profit")]
            if len(profit_trend) >= 2 and profit_trend[0] < profit_trend[-1]:
                signals.append({"dim": "成长性", "level": "关注", "detail": "近 4 期净利润呈下降趋势"})
                score -= 10

        # --- 估值合理性 ---
        pe = quote.get("pe_dynamic")
        if pe and pe < 0:
            signals.append({"dim": "估值", "level": "关注", "detail": f"市盈率 {pe}，为负值（亏损）"})
            score -= 10
        elif pe and pe > 100:
            signals.append({"dim": "估值", "level": "关注", "detail": f"市盈率 {pe}，估值偏高"})
            score -= 5

        # --- 公告风险 ---
        if ann_analysis.get("success"):
            risk_count = ann_analysis.get("risk_event_count", 0)
            if risk_count >= 3:
                signals.append({"dim": "公告风险", "level": "高风险", "detail": f"近期有 {risk_count} 条风险类公告（诉讼/违规/担保）"})
                score -= 20
            elif risk_count >= 1:
                signals.append({"dim": "公告风险", "level": "关注", "detail": f"近期有 {risk_count} 条风险类公告"})
                score -= 5

        # --- 行业位置 ---
        if industry.get("success") and industry.get("current_rank"):
            rank = industry["current_rank"]
            total = industry.get("total_companies", 0)
            if total > 0 and rank > total * 0.8:
                signals.append({"dim": "行业地位", "level": "关注", "detail": f"行业市值排名 {rank}/{total}，处于后 20%"})
                score -= 5

        # 综合评级
        score = max(0, min(100, score))
        if score >= 80:
            credit_grade = "A"
            grade_desc = "信用良好"
        elif score >= 60:
            credit_grade = "B"
            grade_desc = "信用一般，需关注"
        elif score >= 40:
            credit_grade = "C"
            grade_desc = "信用较差，多项风险信号"
        else:
            credit_grade = "D"
            grade_desc = "信用风险较高"

        high_risks = [s for s in signals if s["level"] == "高风险"]

        return {
            "success": True,
            "code": quote.get("code"),
            "name": quote.get("name"),
            "industry": quote.get("industry"),
            "credit_grade": credit_grade,
            "credit_score": score,
            "grade_desc": grade_desc,
            "high_risk_count": len(high_risks),
            "signals": signals,
            "financial_snapshot": {
                "debt_ratio": debt_ratio,
                "roe": roe,
                "net_margin": net_margin,
                "revenue": latest.get("revenue"),
                "net_profit": latest.get("net_profit"),
            },
            "valuation": {
                "pe_dynamic": quote.get("pe_dynamic"),
                "pb": quote.get("pb"),
                "total_market_cap_yi": quote.get("total_market_cap_yi"),
            },
        }

    def analyze_peers_comparison(self, stock_code: str) -> Dict[str, Any]:
        """
        竞品深度对比：同行业 PE/PB/ROE 横向排名 + 优劣势分析

        Returns:
            Dict: 竞品对比分析结果
        """
        industry = self.fetch_industry_peers(stock_code)
        if not industry.get("success"):
            return {"success": False, "error": f"获取行业数据失败: {industry.get('error')}"}

        peers = industry.get("peers", [])
        current = industry.get("current_stock", {})
        if not peers:
            return {"success": True, "industry": industry.get("industry"), "peers": [], "note": "无同行数据"}

        # 计算各指标排名
        current_pe = current.get("pe_dynamic")
        current_pb = current.get("pb")
        current_cap = current.get("total_market_cap")

        # PE 排名（越低越好，排除负值）
        pe_valid = [(i, p) for i, p in enumerate(peers) if p.get("pe_dynamic") and p["pe_dynamic"] > 0]
        pe_valid.sort(key=lambda x: x[1]["pe_dynamic"])
        pe_rank = None
        for rank, (i, p) in enumerate(pe_valid, 1):
            if p.get("is_current"):
                pe_rank = rank
                break

        # PB 排名（越低越好）
        pb_valid = [(i, p) for i, p in enumerate(peers) if p.get("pb") and p["pb"] > 0]
        pb_valid.sort(key=lambda x: x[1]["pb"])
        pb_rank = None
        for rank, (i, p) in enumerate(pb_valid, 1):
            if p.get("is_current"):
                pb_rank = rank
                break

        # ROE 排名（越高越好）
        roe_valid = [(i, p) for i, p in enumerate(peers) if p.get("roe") and p["roe"] > 0]
        roe_valid.sort(key=lambda x: x[1]["roe"], reverse=True)
        roe_rank = None
        for rank, (i, p) in enumerate(roe_valid, 1):
            if p.get("is_current"):
                roe_rank = rank
                break

        # 市值排名
        cap_rank = industry.get("current_rank")

        # 优劣势分析
        strengths = []
        weaknesses = []
        total = len(peers)

        if pe_rank and pe_rank <= total * 0.3:
            strengths.append(f"估值偏低（PE 排名 {pe_rank}/{len(pe_valid)}）")
        elif pe_rank and pe_rank > total * 0.7:
            weaknesses.append(f"估值偏高（PE 排名 {pe_rank}/{len(pe_valid)}）")

        if pb_rank and pb_rank <= total * 0.3:
            strengths.append(f"PB 合理（排名 {pb_rank}/{len(pb_valid)}）")
        elif pb_rank and pb_rank > total * 0.7:
            weaknesses.append(f"PB 偏高（排名 {pb_rank}/{len(pb_valid)}）")

        if roe_rank and roe_rank <= total * 0.3:
            strengths.append(f"盈利能力强（ROE 排名 {roe_rank}/{len(roe_valid)}）")
        elif roe_rank and roe_rank > total * 0.7:
            weaknesses.append(f"盈利能力弱（ROE 排名 {roe_rank}/{len(roe_valid)}）")

        if cap_rank and cap_rank <= total * 0.3:
            strengths.append(f"行业龙头（市值排名 {cap_rank}/{total}）")

        return {
            "success": True,
            "source": "东方财富",
            "industry": industry.get("industry"),
            "total_peers": total,
            "rankings": {
                "market_cap": {"rank": cap_rank, "total": total, "note": "越高越好"},
                "pe_dynamic": {"rank": pe_rank, "total": len(pe_valid), "note": "越低越好（排除亏损）"},
                "pb": {"rank": pb_rank, "total": len(pb_valid), "note": "越低越好"},
                "roe": {"rank": roe_rank, "total": len(roe_valid), "note": "越高越好"},
            },
            "strengths": strengths,
            "weaknesses": weaknesses,
            "current_stock": current,
            "industry_avg_pe": industry.get("industry_avg_pe"),
            "industry_avg_pb": industry.get("industry_avg_pb"),
            "peers_top5": peers[:5],
        }

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
        lines.append("=" * 60)

        # 1. 实时行情
        quote = self.fetch_realtime_quote(stock_code)
        source = quote.get("source", "东方财富网") if quote.get("success") else "数据获取失败"
        lines.append(f"数据来源：{source}")
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

            lines.append(f"换手率: {quote.get('turnover_rate') or '-'}%  振幅: {quote.get('amplitude') or '-'}%  量比: {quote.get('volume_ratio') or '-'}")

            # 估值指标
            lines.append(f"\n【估值指标】")
            lines.append("-" * 40)
            lines.append(f"市盈率(动): {quote.get('pe_dynamic') or '-'}")
            lines.append(f"市盈率(TTM): {quote.get('pe_ttm') or '-'}")
            lines.append(f"市盈率(静): {quote.get('pe_static') or '-'}")
            lines.append(f"市净率: {quote.get('pb') or '-'}")
            lines.append(f"每股收益: {quote.get('eps') or '-'}")

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

        # 4. 近期公告（含事件分类）
        ann = self.analyze_announcements(stock_code, limit=10)
        if ann.get("success") and ann.get("announcements"):
            lines.append(f"\n【近期公告分析】")
            lines.append("-" * 40)
            if ann.get("event_summary"):
                lines.append(f"事件分布: {' / '.join(ann['event_summary'])}")
            if ann.get("risk_event_count", 0) > 0:
                lines.append(f"⚠️ 风险公告 {ann['risk_event_count']} 条:")
                for re_ in ann["risk_events"]:
                    lines.append(f"  🔴 [{re_['date']}] {re_['title']}")
            # 普通公告
            normal = [a for a in ann["announcements"] if not a.get("risk_flag")]
            if normal:
                lines.append(f"其他公告:")
                for a in normal[:5]:
                    lines.append(f"  [{a['date']}] {a['title']}")

        # 5. 竞品对比
        comp = self.analyze_peers_comparison(stock_code)
        if comp.get("success"):
            lines.append(f"\n【竞品对比 - {comp.get('industry', '')}】")
            lines.append("-" * 40)
            rankings = comp.get("rankings", {})
            for dim, info in rankings.items():
                name_map = {"market_cap": "市值", "pe_dynamic": "PE", "pb": "PB", "roe": "ROE"}
                if info.get("rank"):
                    lines.append(f"  {name_map.get(dim, dim)}: 第 {info['rank']}/{info['total']}（{info['note']}）")
            if comp.get("strengths"):
                lines.append(f"  ✅ 优势: {'; '.join(comp['strengths'])}")
            if comp.get("weaknesses"):
                lines.append(f"  ⚠️ 劣势: {'; '.join(comp['weaknesses'])}")

        # 6. 信贷评估摘要
        credit = self.generate_credit_assessment(stock_code)
        if credit.get("success"):
            lines.append(f"\n【信贷评估摘要】")
            lines.append("-" * 40)
            lines.append(f"信用评级: {credit['credit_grade']}（{credit['grade_desc']}）")
            lines.append(f"综合评分: {credit['credit_score']}/100")
            if credit.get("high_risk_count", 0) > 0:
                lines.append(f"⚠️ 高风险信号 {credit['high_risk_count']} 项:")
            for sig in credit.get("signals", []):
                icon = "🔴" if sig["level"] == "高风险" else "🟡" if sig["level"] == "关注" else "🟢"
                lines.append(f"  {icon} [{sig['dim']}] {sig['detail']}")

        lines.append("\n" + "=" * 60)
        lines.append("注意：以上数据来自东方财富网公开行情，仅供参考，不构成投资建议。")
        lines.append("=" * 60)

        return "\n".join(lines)
