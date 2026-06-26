---
name: Fin-Radar
description: 金融雷达 - 财报智能解析与风险预警系统，基于本地规则引擎从财报文本中提取关键财务指标并进行风险评估
version: 1.1.0
author: Xiaoxiansheng2003
tags: finance, risk-analysis, financial-report, local-analysis
category: 金融分析
license: MIT
---

# Fin-Radar - 金融雷达｜财报智能解析与风险预警系统

## 📋 功能概述

**Fin-Radar** 是一款财报智能分析工具，支持从公司财报中提取关键财务数据并进行风险评估，同时可查询 A 股实时行情。

### 核心能力
1. **文档解析**：支持 PDF 文件和文本输入
2. **指标提取**：基于规则引擎自动识别关键财务指标
3. **风险评估**：多维度财务风险分析
4. **实时行情**：A 股个股实时行情、估值指标、行业对比（数据来源：东方财富网）
5. **结构化输出**：JSON 格式数据和风险报告

### 技术特点
- ✅ **财报分析纯本地运行**：PDF/文本解析数据不离开本地
- ✅ **隐私安全**：敏感财务数据不会上传到任何服务器
- ✅ **行情数据来源透明**：实时行情仅从东方财富网公开接口获取
- ✅ **财报功能零网络依赖**：离线环境也可正常使用

---

## 🚀 快速开始

### 环境要求
- Python 3.10+
- 依赖：pdfplumber, PyPDF2, requests

### 安装依赖
```bash
pip install -r requirements.txt
```

---

## 📖 使用方法

### 方式一：处理 PDF 文件
```bash
python scripts/helper.py --pdf /path/to/report.pdf
```

### 方式二：处理文本输入
```bash
python scripts/helper.py --text "公司2023年营业收入100亿元..."
```

### 方式三：处理文本文件
```bash
python scripts/helper.py --file /path/to/report.txt
```

### 方式四：输出 JSON 格式
```bash
python scripts/helper.py --file report.txt --json
```

### 方式五：查询 A 股实时行情
```bash
# 查询个股行情、估值指标、行业对比
python scripts/helper.py --stock 600519

# 输出 JSON 格式
python scripts/helper.py --stock 600519 --json
```

---

## 📊 支持的财务指标

| 指标名称 | 字段标识 | 单位 | 说明 |
|---------|---------|------|------|
| 营业收入 | revenue | 元 | 公司主营业务收入 |
| 归母净利润 | net_profit | 元 | 归属于母公司股东的净利润 |
| 资产负债率 | debt_ratio | % | 总负债/总资产 |
| 经营现金流 | operating_cash_flow | 元 | 经营活动产生的现金流量净额 |
| 研发投入占比 | rd_ratio | % | 研发费用/营业收入 |
| 营收同比增长率 | revenue_yoy | % | 营业收入同比变化 |
| 净利润同比增长率 | net_profit_yoy | % | 净利润同比变化 |

### 实时行情指标（--stock 模式）

| 指标名称 | 字段标识 | 说明 |
|---------|---------|------|
| 最新股价 | price | 实时价格 |
| 市盈率(动) | pe_dynamic | 动态市盈率 |
| 市盈率(TTM) | pe_ttm | 滚动市盈率 |
| 市净率 | pb | PB 比率 |
| 总市值 | total_market_cap | 单位：元 |
| 流通市值 | circulating_market_cap | 单位：元 |
| 换手率 | turnover_rate | % |
| 行业排名 | industry_rank | 按市值排名 |
| 行业平均 PE | industry_avg_pe | 同行业对比 |

---

## ⚠️ 风险评估维度

### 风险等级划分
- 🔴 **高风险**：负债率 >70%、净利润下滑 >30%、经营现金流为负
- 🟡 **中风险**：负债率 60-70%、净利润下滑 15-30%
- 🟢 **低风险**：各项指标处于正常范围

### 评分机制
- 负债率风险：25 分（高风险）/ 15 分（中风险）
- 盈利风险：25 分（高风险）/ 15 分（中风险）/ 5 分（低风险）
- 现金流风险：20 分（高风险）
- 增长风险：15 分（高风险）/ 10 分（中风险）
- 研发风险：5 分（中风险）

总分 0-100，≥50 为高风险，25-49 为中风险，<25 为低风险

---

## 🔧 技术实现

### 本地规则引擎
财报分析部分采用纯本地规则引擎，通过正则表达式和模式匹配提取财务指标：
- 财报解析不依赖任何外部 API
- 财报分析在本地完成，数据不会离开用户设备

### PDF 解析策略
```
优先级 1: pdfplumber（功能强大，支持复杂 PDF）
    ↓ 失败
优先级 2: PyPDF2（轻量级，兼容性好）
    ↓ 失败
降级方案: 提示用户输入文本内容
```

### 安全合规
- ✅ **不存储敏感数据**：上传的 PDF 仅在内存中临时处理
- ✅ **不上传数据**：财报分析在本地完成，无网络请求
- ✅ **数据脱敏**：测试用例使用模拟数据
- ✅ **合法使用**：遵守相关法律法规

---

## 📝 输出格式

### JSON 输出示例
```json
{
  "success": true,
  "metrics": {
    "company_name": "示例公司",
    "revenue": 8560000000,
    "net_profit": 820000000,
    "debt_ratio": 62.8,
    "operating_cash_flow": 530000000,
    "rd_ratio": 5.6,
    "revenue_yoy": 12.3,
    "net_profit_yoy": -15.6
  },
  "risk_assessment": {
    "risk_level": "medium",
    "risk_score": 30,
    "risk_summary": "发现部分风险指标，需持续关注",
    "risk_details": [...]
  }
}
```

---

## ⚠️ 注意事项

1. **PDF 格式支持**：扫描版 PDF（图片格式）暂不支持，需使用 OCR 工具预处理
2. **指标提取精度**：规则引擎对格式不规范的文本可能存在漏提
3. **适用场景**：适用于标准格式的财报文本分析
4. **行情查询**：--stock 功能需联网，数据来自东方财富网公开接口，仅供参考，不构成投资建议

---

## 📄 许可证

MIT License

---

## 🙏 致谢

- pdfplumber 开发团队（MIT 许可证）
- PyPDF2 开发团队（BSD 许可证）
