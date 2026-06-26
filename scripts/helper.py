#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fin-Radar - 金融雷达 主程序
==================================

功能：财务文档解析与风险洞察
- 从财报 PDF 或文本中提取关键财务指标
- 进行财务风险评估和预警
- 查询 A 股实时行情和估值指标
- 返回结构化 JSON 输出

作者：Xiaoxiansheng2003
"""

import os
import sys
import json
import re
import argparse
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

# 尝试导入股票数据抓取模块
try:
    from utils.stock_fetcher import StockFetcher
except ImportError:
    StockFetcher = None
import io

# 设置标准输出编码为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class FinancialMetricExtractor:
    """
    财务指标提取器
    
    支持两种模式：
    1. 本地规则引擎模式（默认，无需 API）
    2. 大模型 API 模式（可选，精度更高）
    """
    def format_amount(self, value: float) -> str:
        """格式化金额显示"""
        if value < 1000:
            return f"{value:.2f} 亿元"
        else:
            return f"{value/100000000:.2f} 亿元"

    
    # 关键财务指标定义
    METRICS_SCHEMA = {
        "company_name": {"type": "string", "description": "公司名称"},
        "report_period": {"type": "string", "description": "报告期"},
        "revenue": {"type": "number", "unit": "元", "description": "营业收入"},
        "net_profit": {"type": "number", "unit": "元", "description": "归母净利润"},
        "debt_ratio": {"type": "number", "unit": "%", "description": "资产负债率"},
        "operating_cash_flow": {"type": "number", "unit": "元", "description": "经营现金流净额"},
        "rd_ratio": {"type": "number", "unit": "%", "description": "研发投入占比"},
        "revenue_yoy": {"type": "number", "unit": "%", "description": "营收同比增长率"},
        "net_profit_yoy": {"type": "number", "unit": "%", "description": "净利润同比增长率"}
    }
    
    # 风险阈值配置
    RISK_THRESHOLDS = {
        "debt_ratio": {"high": 70, "medium": 60, "description": "资产负债率"},
        "net_profit_yoy": {"high": -30, "medium": -15, "description": "净利润同比"},
        "operating_cash_flow": {"high": 0, "medium": None, "description": "经营现金流"},
        "rd_ratio": {"high": 3, "medium": 5, "description": "研发投入占比"},
        "revenue_yoy": {"high": -10, "medium": 0, "description": "营收同比"}
    }
    
    def __init__(self):
        """
        初始化提取器
        
        采用纯本地规则引擎，无需外部 API 调用
        """
        
        # 导入 PDF 读取器
        try:
            from utils.pdf_reader import PDFReader
            self.pdf_reader = PDFReader()
        except ImportError:
            logger.warning("PDF 读取器导入失败，将仅支持文本输入")
            self.pdf_reader = None
        

    
    def extract_number(self, text: str) -> Optional[float]:
        """
        从文本中提取数字
        
        Args:
            text: 包含数字的文本
            
        Returns:
            float: 提取的数字，失败返回 None
        """
        if not text:
            return None
        
        # 移除逗号和空格
        text = text.replace(',', '').replace(' ', '')
        
        # 匹配数字模式
        # 先尝试匹配带单位的数字（如 52.3亿元、15.2万亿）
        patterns_with_unit = [
            r'([-+]?\d+\.?\d*)\s*亿',  # 亿元
            r'([-+]?\d+\.?\d*)\s*万',  # 万元
        ]
        
        for pattern in patterns_with_unit:
            match = re.search(pattern, text)
            if match:
                num_str = match.group(1)
                try:
                    num = float(num_str)
                    if '亿' in pattern:
                        return num * 100000000
                    elif '万' in pattern:
                        return num * 10000
                except:
                    pass
        
        # 匹配普通数字
        pattern = r'[-+]?\d+\.?\d*'
        match = re.search(pattern, text)
        if match:
            num_str = match.group()
            try:
                return float(num_str)
            except:
                pass
        
        return None
    
    def extract_percentage(self, text: str) -> Optional[float]:
        """
        从文本中提取百分比
        
        Args:
            text: 包含百分比的文本
            
        Returns:
            float: 百分比数值，失败返回 None
        """
        if not text:
            return None
        
        # 匹配百分比模式
        patterns = [
            r'[-+]?\d+\.?\d*%',
            r'[-+]?\d+\.?\d*％',
            r'[-+]?\d+\.?\d*\s*个百分点',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                num_str = match.group()
                # 移除百分号和单位
                num_str = num_str.replace('%', '').replace('％', '').replace('个百分点', '').strip()
                try:
                    return float(num_str)
                except:
                    pass
        
        return None
    
    def extract_metrics_by_rules(self, text: str) -> Dict[str, Any]:
        """
        使用规则引擎提取财务指标
        
        Args:
            text: 财报文本
            
        Returns:
            Dict: 提取的财务指标
        """
        metrics = {}
        
        # 公司名称提取
        company_patterns = [
            r'(?:公司名称|股票简称|证券简称)[：:]\s*(.+?)(?:\s|$)',
            r'(.+?)(?:股份有限|集团|控股)',
            r'^([^\n]{2,20}(?:公司|集团|股份))',
        ]
        for pattern in company_patterns:
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                metrics['company_name'] = match.group(1).strip()
                break
        
        # 报告期提取
        period_patterns = [
            r'(20\d{2})\s*年(?:年度|年报|半年报|第[一二三四]季度|Q[1-4])',
            r'(20\d{2})年',
            r'(20\d{2})[/-](\d{1,2})',
        ]
        for pattern in period_patterns:
            match = re.search(pattern, text)
            if match:
                metrics['report_period'] = match.group(0)
                break
        
        # 营业收入提取
        revenue_patterns = [
            r'(?:营业收入|营业总收入|营收)[：:为是]?\s*([^\n]{5,50}(?:元|万元|亿元))',
            r'实现营业收入\s*([^\n]{5,50}(?:元|万元|亿元))',
            r'营业收入\s*(?:为|达到|实现)\s*([^\n]{5,50}(?:元|万元|亿元))',
        ]
        for pattern in revenue_patterns:
            match = re.search(pattern, text)
            if match:
                value = self.extract_number(match.group(1))
                if value:
                    metrics['revenue'] = value
                    metrics['revenue_text'] = match.group(1).strip()
                    break
        
        # 归母净利润提取
        profit_patterns = [
            r'(?:归母净利润|归属于母公司股东的净利润|归属于上市公司股东的净利润)[：:为是]?\s*([^\n]{5,50}(?:元|万元|亿元))',
            r'(?:净利润|归母净利)[：:为是]?\s*([^\n]{5,50}(?:元|万元|亿元))',
        ]
        for pattern in profit_patterns:
            match = re.search(pattern, text)
            if match:
                value = self.extract_number(match.group(1))
                if value:
                    metrics['net_profit'] = value
                    metrics['net_profit_text'] = match.group(1).strip()
                    break
        
        # 资产负债率提取
        debt_patterns = [
            r'(?:资产负债率|负债率)[：:为是]?\s*([^\n]{3,20}%?)',
            r'资产负债[：:为是]?\s*([^\n]{3,20}%?)',
        ]
        for pattern in debt_patterns:
            match = re.search(pattern, text)
            if match:
                value = self.extract_percentage(match.group(1))
                if value is None:
                    value = self.extract_number(match.group(1))
                if value:
                    metrics['debt_ratio'] = value
                    metrics['debt_ratio_text'] = match.group(1).strip()
                    break
        
        # 经营现金流提取
        cash_patterns = [
            r'(?:经营活动产生的现金流量净额|经营现金流|经营活动现金流)[：:为是]?\s*([^\n]{5,50}(?:元|万元|亿元))',
            r'经营性现金流[：:为是]?\s*([^\n]{5,50}(?:元|万元|亿元))',
        ]
        for pattern in cash_patterns:
            match = re.search(pattern, text)
            if match:
                value = self.extract_number(match.group(1))
                if value:
                    metrics['operating_cash_flow'] = value
                    metrics['operating_cash_flow_text'] = match.group(1).strip()
                    break
        
        # 研发投入占比提取
        rd_patterns = [
            r'(?:研发费用|研发投入)[占营比收入]*[：:为是]?\s*([^\n]{3,20}%?)',
            r'研发投入占比[：:为是]?\s*([^\n]{3,20}%?)',
        ]
        for pattern in rd_patterns:
            match = re.search(pattern, text)
            if match:
                value = self.extract_percentage(match.group(1))
                if value is None:
                    value = self.extract_number(match.group(1))
                if value:
                    metrics['rd_ratio'] = value
                    metrics['rd_ratio_text'] = match.group(1).strip()
                    break
        
        # 营收同比增长率提取
        revenue_yoy_patterns = [
            r'营业收入同比[增长下降变动]*[：:为是]?\s*([^\n]{3,20}%?)',
            r'营收同比[增长下降变动]*[：:为是]?\s*([^\n]{3,20}%?)',
            r'营业收入[增下长降]*[速幅]?\s*([^\n]{3,20}%)',
        ]
        for pattern in revenue_yoy_patterns:
            match = re.search(pattern, text)
            if match:
                value = self.extract_percentage(match.group(1))
                if value is None:
                    value = self.extract_number(match.group(1))
                if value:
                    # 判断是增长还是下降
                    if '下降' in match.group(0) or '减少' in match.group(0) or '降' in match.group(0):
                        value = -abs(value)
                    metrics['revenue_yoy'] = value
                    metrics['revenue_yoy_text'] = match.group(1).strip()
                    break
        
        # 净利润同比增长率提取
        profit_yoy_patterns = [
            r'(?:归母净利润|净利润)同比[增长下降变动]*[：:为是]?\s*([^\n]{3,20}%?)',
            r'净利润[增下长降]*[速幅]?\s*([^\n]{3,20}%)',
        ]
        for pattern in profit_yoy_patterns:
            match = re.search(pattern, text)
            if match:
                value = self.extract_percentage(match.group(1))
                if value is None:
                    value = self.extract_number(match.group(1))
                if value:
                    if '下降' in match.group(0) or '减少' in match.group(0) or '降' in match.group(0):
                        value = -abs(value)
                    metrics['net_profit_yoy'] = value
                    metrics['net_profit_yoy_text'] = match.group(1).strip()
                    break
        
        return metrics
    
    def assess_risk(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估财务风险
        
        Args:
            metrics: 财务指标数据
            
        Returns:
            Dict: 风险评估结果
        """
        risk_details = []
        risk_score = 0
        
        # 负债率风险
        if 'debt_ratio' in metrics:
            debt_ratio = metrics['debt_ratio']
            if debt_ratio > 70:
                risk_details.append({
                    "risk_type": "负债风险",
                    "status": "high",
                    "description": f"资产负债率 {debt_ratio}% 过高，超过70%警戒线",
                    "suggestion": "建议关注公司偿债能力，评估债务违约风险"
                })
                risk_score += 25
            elif debt_ratio > 60:
                risk_details.append({
                    "risk_type": "负债风险",
                    "status": "medium",
                    "description": f"资产负债率 {debt_ratio}% 偏高",
                    "suggestion": "建议持续关注负债变化趋势"
                })
                risk_score += 15
            else:
                risk_details.append({
                    "risk_type": "负债风险",
                    "status": "low",
                    "description": f"资产负债率 {debt_ratio}% 处于正常水平",
                    "suggestion": "无需特别关注"
                })
        
        # 净利润下滑风险
        if 'net_profit_yoy' in metrics:
            profit_yoy = metrics['net_profit_yoy']
            if profit_yoy < -30:
                risk_details.append({
                    "risk_type": "盈利风险",
                    "status": "high",
                    "description": f"净利润同比下滑 {abs(profit_yoy)}%，出现断崖式下跌",
                    "suggestion": "建议深入分析下滑原因，关注主营业务盈利能力"
                })
                risk_score += 25
            elif profit_yoy < -15:
                risk_details.append({
                    "risk_type": "盈利风险",
                    "status": "medium",
                    "description": f"净利润同比下滑 {abs(profit_yoy)}%",
                    "suggestion": "建议关注公司盈利能力变化趋势"
                })
                risk_score += 15
            elif profit_yoy < 0:
                risk_details.append({
                    "risk_type": "盈利风险",
                    "status": "low",
                    "description": f"净利润同比小幅下滑 {abs(profit_yoy)}%",
                    "suggestion": "建议持续观察"
                })
                risk_score += 5
        
        # 经营现金流风险
        if 'operating_cash_flow' in metrics:
            cash_flow = metrics['operating_cash_flow']
            if cash_flow < 0:
                risk_details.append({
                    "risk_type": "现金流风险",
                    "status": "high",
                    "description": f"经营现金流为负 ({cash_flow/100000000:.2f}亿)，存在资金链风险",
                    "suggestion": "建议关注公司现金流状况和融资能力"
                })
                risk_score += 20
            else:
                risk_details.append({
                    "risk_type": "现金流风险",
                    "status": "low",
                    "description": "经营现金流为正",
                    "suggestion": "现金流状况良好"
                })
        
        # 营收下滑风险
        if 'revenue_yoy' in metrics:
            revenue_yoy = metrics['revenue_yoy']
            if revenue_yoy < -10:
                risk_details.append({
                    "risk_type": "增长风险",
                    "status": "high",
                    "description": f"营业收入同比下滑 {abs(revenue_yoy)}%，业务萎缩",
                    "suggestion": "建议分析行业环境和公司竞争力"
                })
                risk_score += 15
            elif revenue_yoy < 0:
                risk_details.append({
                    "risk_type": "增长风险",
                    "status": "medium",
                    "description": f"营业收入同比下滑 {abs(revenue_yoy)}%",
                    "suggestion": "建议关注业务发展趋势"
                })
                risk_score += 10
        
        # 研发投入风险
        if 'rd_ratio' in metrics:
            rd_ratio = metrics['rd_ratio']
            if rd_ratio < 3:
                risk_details.append({
                    "risk_type": "研发投入风险",
                    "status": "medium",
                    "description": f"研发投入占比 {rd_ratio}% 较低",
                    "suggestion": "建议关注公司技术创新能力"
                })
                risk_score += 5
        
        # 计算总风险等级
        risk_score = min(risk_score, 100)
        if risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # 生成风险摘要
        high_risks = [r for r in risk_details if r['status'] == 'high']
        if high_risks:
            risk_summary = f"发现 {len(high_risks)} 项高风险指标：{'、'.join([r['risk_type'] for r in high_risks])}"
        elif risk_details:
            risk_summary = "发现部分风险指标，需持续关注"
        else:
            risk_summary = "各项指标正常，财务状况良好"
        
        return {
            "risk_level": risk_level,
            "risk_score": risk_score,
            "risk_summary": risk_summary,
            "risk_details": risk_details,
            "assessed_at": datetime.now().isoformat()
        }
    
    def process_text(self, text: str) -> Dict[str, Any]:
        """
        处理文本输入
        
        Args:
            text: 财报文本
            
        Returns:
            Dict: 完整的处理结果
        """
        # 提取指标
        metrics = self.extract_metrics_by_rules(text)
        
        # 评估风险
        risk_assessment = self.assess_risk(metrics)
        
        return {
            "success": True,
            "metrics": metrics,
            "risk_assessment": risk_assessment,
            "processed_at": datetime.now().isoformat(),
            "input_type": "text"
        }
    
    def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        处理 PDF 文件
        
        Args:
            pdf_path: PDF 文件路径
            
        Returns:
            Dict: 完整的处理结果
        """
        if not self.pdf_reader:
            return {
                "success": False,
                "error": "PDF 读取器不可用，请安装 pdfplumber 或 PyPDF2",
                "metrics": {},
                "risk_assessment": {}
            }
        
        # 读取 PDF
        result = self.pdf_reader.read_pdf(pdf_path)
        
        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "metrics": {},
                "risk_assessment": {},
                "input_type": "pdf"
            }
        
        # 提取指标
        metrics = self.extract_metrics_by_rules(result["text"])
        
        # 评估风险
        risk_assessment = self.assess_risk(metrics)
        
        return {
            "success": True,
            "metrics": metrics,
            "risk_assessment": risk_assessment,
            "pdf_info": {
                "engine": result["engine"],
                "text_length": len(result["text"])
            },
            "processed_at": datetime.now().isoformat(),
            "input_type": "pdf"
        }
    
    def generate_report(self, result: Dict[str, Any]) -> str:
        """
        生成可读的报告
        
        Args:
            result: 处理结果
            
        Returns:
            str: 格式化的报告文本
        """
        if not result.get("success"):
            return f"处理失败: {result.get('error', '未知错误')}"
        
        metrics = result.get("metrics", {})
        risk = result.get("risk_assessment", {})
        
        report = []
        report.append("=" * 60)
        report.append("Fin-Radar 财务指标分析报告")
        report.append("=" * 60)
        
        # 基本信息
        if metrics.get("company_name"):
            report.append(f"\n公司名称: {metrics['company_name']}")
        if metrics.get("report_period"):
            report.append(f"报告期间: {metrics['report_period']}")
        
        # 核心指标
        report.append("\n【核心财务指标】")
        report.append("-" * 40)
        
        if metrics.get("revenue"):
            # 如果数值已经是亿元级别（<1000），直接显示；否则转换
            rev = metrics['revenue']
            if rev < 1000:
                report.append(f"营业收入: {rev:.2f} 亿元")
            else:
                report.append(f"营业收入: {rev/100000000:.2f} 亿元")
        
        if metrics.get("net_profit"):
            profit_str = f"{metrics['net_profit']/100000000:.2f} 亿元"
            if metrics['net_profit'] < 0:
                profit_str = f"-{abs(metrics['net_profit'])/100000000:.2f} 亿元"
            report.append(f"归母净利润: {profit_str}")
        
        if metrics.get("debt_ratio"):
            report.append(f"资产负债率: {metrics['debt_ratio']}%")
        
        if metrics.get("operating_cash_flow"):
            cash_str = f"{metrics['operating_cash_flow']/100000000:.2f} 亿元"
            if metrics['operating_cash_flow'] < 0:
                cash_str = f"-{abs(metrics['operating_cash_flow'])/100000000:.2f} 亿元"
            report.append(f"经营现金流: {cash_str}")
        
        if metrics.get("rd_ratio"):
            report.append(f"研发投入占比: {metrics['rd_ratio']}%")
        
        # 同比变化
        report.append("\n【同比变化】")
        report.append("-" * 40)
        
        if metrics.get("revenue_yoy"):
            yoy = metrics['revenue_yoy']
            trend = "↑" if yoy > 0 else "↓"
            report.append(f"营收同比: {trend} {abs(yoy)}%")
        
        if metrics.get("net_profit_yoy"):
            yoy = metrics['net_profit_yoy']
            trend = "↑" if yoy > 0 else "↓"
            report.append(f"净利润同比: {trend} {abs(yoy)}%")
        
        # 风险评估
        report.append("\n【风险评估】")
        report.append("-" * 40)
        report.append(f"风险等级: {risk.get('risk_level', '未知').upper()}")
        report.append(f"风险评分: {risk.get('risk_score', 0)}/100")
        report.append(f"风险摘要: {risk.get('risk_summary', '无')}")
        
        if risk.get("risk_details"):
            report.append("\n风险详情:")
            for detail in risk["risk_details"]:
                status_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(detail["status"], "⚪")
                report.append(f"  {status_icon} {detail['risk_type']}: {detail['description']}")
                if detail.get("suggestion"):
                    report.append(f"     建议: {detail['suggestion']}")
        
        report.append("\n" + "=" * 60)
        report.append(f"生成时间: {result.get('processed_at', datetime.now().isoformat())}")
        
        return "\n".join(report)


def main():
    """
    主函数 - 命令行入口
    """
    parser = argparse.ArgumentParser(
        description="金融智能 Skill - 财务文档解析与风险洞察",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 处理 PDF 文件
  python skill.py --pdf report.pdf
  
  # 处理文本
  python skill.py --text "公司2023年营业收入100亿元..."
  
  # 输出 JSON 格式
  python skill.py --pdf report.pdf --json
  

        """
    )
    
    parser.add_argument("--pdf", type=str, help="PDF 文件路径")
    parser.add_argument("--text", type=str, help="直接输入财报文本")
    parser.add_argument("--file", type=str, help="文本文件路径")
    parser.add_argument("--stock", type=str, help="股票代码，获取实时行情和估值指标（如 600519、000001）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式")
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    # 检查输入
    if not args.pdf and not args.text and not args.file:
        parser.print_help()
        print("\n错误: 请提供 --pdf、--text 或 --file 参数")
        sys.exit(1)
    
    # 初始化提取器
    extractor = FinancialMetricExtractor()
    
    # 处理输入
    result = None
    
    try:
        # 股票行情查询
        if args.stock:
            if StockFetcher is None:
                print("错误: requests 库未安装，请执行: pip install requests")
                sys.exit(1)
            
            fetcher = StockFetcher()
            if args.json:
                # JSON 输出
                quote = fetcher.fetch_realtime_quote(args.stock)
                finance = fetcher.fetch_financial_history(args.stock)
                industry = fetcher.fetch_industry_peers(args.stock)
                ann = fetcher.fetch_announcements(args.stock, limit=5)
                result = {
                    "quote": quote,
                    "financial_history": finance,
                    "industry_comparison": industry,
                    "announcements": ann,
                }
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                # 文本报告
                report = fetcher.generate_market_report(args.stock)
                print(report)
            sys.exit(0)
        
        elif args.pdf:
            if not os.path.exists(args.pdf):
                print(f"错误: 文件不存在: {args.pdf}")
                sys.exit(1)
            result = extractor.process_pdf(args.pdf)
            
        elif args.text:
            result = extractor.process_text(args.text)
            
        elif args.file:
            if not os.path.exists(args.file):
                print(f"错误: 文件不存在: {args.file}")
                sys.exit(1)
            with open(args.file, 'r', encoding='utf-8') as f:
                text = f.read()
            result = extractor.process_text(text)
        
        # 输出结果
        if result:
            if args.json:
                # JSON 输出
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                # 可读报告输出
                report = extractor.generate_report(result)
                print(report)
                
                # 同时输出 JSON（如果需要）
                if args.verbose:
                    print("\n\n--- JSON 原始数据 ---")
                    print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("错误: 无法处理输入")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n操作已取消")
        sys.exit(0)
    except Exception as e:
        logger.error(f"处理失败: {e}", exc_info=args.verbose)
        print(f"处理失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
