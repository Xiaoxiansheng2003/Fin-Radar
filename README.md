# Fin-Radar v1.2.0 - 金融雷达

财报智能解析与风险预警系统 — 从财报 PDF/文本中提取关键财务指标，进行风险评估，查询 A 股实时行情，并提供信贷评估和竞品对比分析。

## 功能

- **财报解析**：支持 PDF 文件和纯文本输入
- **指标提取**：自动识别营业收入、净利润、资产负债率等 7 项核心指标
- **风险评估**：基于负债、盈利、现金流、增长、研发 5 个维度自动评分
- **实时行情**：通过股票代码查询股价、市盈率、市净率、行业对比等
- **公告分析**：公告关键事件自动分类（增减持/诉讼/担保/违规等 10 类），风险公告标记
- **信贷评估**：基于财务指标 + 行业数据 + 公告风险的综合信用评级（A/B/C/D）
- **竞品对比**：同行业 PE/PB/ROE 横向排名及优劣势分析
- **结构化输出**：支持可读报告和 JSON 两种格式

## 安装

```bash
pip install -r requirements.txt
```

依赖：pdfplumber、PyPDF2、requests

## 使用

```bash
# 分析 PDF 财报
python scripts/helper.py --pdf report.pdf

# 分析文本
python scripts/helper.py --text "公司2023年营业收入100亿元..."

# 分析文本文件
python scripts/helper.py --file examples/sample_report.txt

# 输出 JSON 格式
python scripts/helper.py --file examples/sample_report.txt --json

# 查询 A 股实时行情（需联网，数据来源：东方财富网）
python scripts/helper.py --stock 600519
python scripts/helper.py --stock 000001 --json
```

## 示例

`examples/` 目录提供了几组示例：

| 文件 | 场景 |
|------|------|
| `sample_report.txt` | 普通财报文本 |
| `high_risk_sample.txt` | 高风险（负债率高、利润下滑） |
| `low_risk_sample.txt` | 低风险（各项指标正常） |

```bash
python scripts/helper.py --file examples/sample_report.txt
```

## 输出示例

```
============================================================
Fin-Radar 财务指标分析报告
============================================================

公司名称: 示例科技股份有限公司
报告期间: 2023年度报告

【核心财务指标】
----------------------------------------
营业收入: 85.60 亿元
归母净利润: 8.20 亿元
资产负债率: 62.8%

【风险评估】
----------------------------------------
风险等级: MEDIUM
风险评分: 30/100
风险摘要: 发现部分风险指标，需持续关注
```

## 项目结构

```
Fin-Radar/
├── README.md                 本文件
├── LICENSE                   MIT 许可证
├── requirements.txt          Python 依赖
├── scripts/
│   ├── helper.py             主程序入口
│   ├── utils/
│   │   ├── pdf_reader.py     PDF 解析
│   │   └── stock_fetcher.py  行情数据抓取（东方财富网）
│   └── config/
│       └── prompt_template.py
├── examples/                 示例文件
├── templates/                输出模板
└── docs/
    ├── reference.md          技术参考文档
    └── SKILL.md              SkillHub 发布说明
```

## 数据来源

| 功能 | 数据来源 | 联网 |
|------|----------|------|
| 财报分析（--pdf/--text/--file） | 本地规则引擎 | ❌ 不需要 |
| 实时行情（--stock） | 东方财富网公开接口 | ✅ 需要 |

行情数据仅供参考，不构成投资建议。

## 注意事项

1. 扫描版 PDF（纯图片）暂不支持，需先用 OCR 工具转为文字
2. 规则引擎对格式不规范的文本可能存在漏提
3. 财报分析功能完全离线运行，不上传任何数据
4. `--stock` 行情功能需联网

## 许可证

[MIT License](LICENSE)

## 作者

[Xiaoxiansheng2003](https://github.com/Xiaoxiansheng2003)
