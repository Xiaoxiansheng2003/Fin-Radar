"""
config/prompt_template.py
==========================
财务指标提取的 Prompt 模板（供扩展开发参考）
"""

# 主提取 Prompt - 用于从财报文本中提取关键财务指标
EXTRACT_METRICS_PROMPT = """你是一个专业的财务分析师。请从以下财报文本中提取关键财务指标，并以严格的JSON格式返回。

## 需要提取的指标：
1. **营业收入** (revenue): 单位为元，如果是亿元请转换
2. **归母净利润** (net_profit): 归属于母公司股东的净利润，单位为元
3. **资产负债率** (debt_ratio): 百分比数值，例如 65.5 表示 65.5%
4. **经营现金流净额** (operating_cash_flow): 单位为元
5. **研发投入占比** (rd_ratio): 研发费用占营收比例，百分比数值
6. **营业收入同比增长率** (revenue_yoy): 百分比数值
7. **归母净利润同比增长率** (net_profit_yoy): 百分比数值

## 输出格式要求：
```json
{
  "company_name": "公司名称",
  "report_period": "报告期，如 2023年报/2024Q1",
  "extracted_at": "提取时间",
  "metrics": {
    "revenue": {"value": 1234567890, "unit": "元", "raw_text": "原始文本"},
    "net_profit": {"value": 123456789, "unit": "元", "raw_text": "原始文本"},
    "debt_ratio": {"value": 65.5, "unit": "%", "raw_text": "原始文本"},
    "operating_cash_flow": {"value": 123456789, "unit": "元", "raw_text": "原始文本"},
    "rd_ratio": {"value": 5.2, "unit": "%", "raw_text": "原始文本"},
    "revenue_yoy": {"value": 15.3, "unit": "%", "raw_text": "原始文本"},
    "net_profit_yoy": {"value": -10.2, "unit": "%", "raw_text": "原始文本"}
  },
  "extraction_confidence": "high/medium/low"
}
```

## 注意事项：
- 如果某项指标在文本中未找到，请将 value 设为 null，raw_text 设为 "未提及"
- 百分比统一转换为数值，例如 15.3% 转换为 15.3
- 金额统一转换为元，如果是亿元需乘以 100000000
- 只返回 JSON，不要有任何其他文字

## 财报文本内容：
{text}
"""


# 风险评估 Prompt - 用于分析提取的指标并生成风险提示
RISK_ANALYSIS_PROMPT = """你是一个专业的财务风险分析师。请根据以下财务指标数据，分析潜在的财务风险并给出风险提示。

## 财务指标数据：
{metrics_json}

## 需要评估的风险维度：
1. **负债风险**：资产负债率是否过高（>70%为高风险，60-70%为中等风险）
2. **盈利风险**：净利润是否出现大幅下跌（同比下跌>30%为高风险，下跌15-30%为中等风险）
3. **现金流风险**：经营现金流是否为负（负值为高风险）
4. **研发投入风险**：研发投入占比是否过低（<3%为风险提示）
5. **增长风险**：营收是否出现下滑（同比下跌>10%为风险）

## 输出格式要求：
```json
{
  "risk_level": "high/medium/low",
  "risk_score": 75,
  "risk_summary": "总体风险评估摘要",
  "risk_details": [
    {
      "risk_type": "负债风险",
      "status": "high/medium/low/normal",
      "description": "具体风险描述",
      "suggestion": "建议措施"
    }
  ],
  "key_findings": ["关键发现1", "关键发现2"]
}
```

## 注意事项：
- 只返回 JSON，不要有任何其他文字
- risk_score 为 0-100 的整数，越高风险越大
- 如果某项指标为 null，跳过该维度的评估
"""


# 纯文本提取 Prompt - 当 PDF 解析失败时使用文本输入
TEXT_EXTRACTION_PROMPT = """请从以下文本中提取财务指标信息。这可能是用户直接输入的财报摘要或关键数据。

{text}

请按照与上述相同的 JSON 格式返回结果。"""


# 错误降级 Prompt - 用于处理解析异常
FALLBACK_PROMPT = """以下文本可能格式不规范或包含噪声，请尽力从中提取任何可识别的财务数据：

{text}

如果无法提取任何有效数据，请返回：
```json
{
  "company_name": "未知",
  "report_period": "未知",
  "metrics": {},
  "extraction_confidence": "failed",
  "error": "无法从文本中提取有效财务数据"
}
```
"""
