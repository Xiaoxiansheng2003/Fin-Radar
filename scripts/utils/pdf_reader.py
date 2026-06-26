"""
utils/pdf_reader.py
====================
PDF 文档读取和预处理工具类
支持 PyPDF2 和 pdfplumber 两种解析引擎，提供优雅降级机制
"""

import os
import re
import logging
from typing import Optional, Dict, Any
from pathlib import Path

# 配置日志
logger = logging.getLogger(__name__)


class PDFReadError(Exception):
    """PDF 读取异常基类"""
    pass


class PDFNotFoundError(PDFReadError):
    """文件不存在异常"""
    pass


class PDFCorruptedError(PDFReadError):
    """文件损坏异常"""
    pass


class PDFEmptyError(PDFReadError):
    """文件内容为空异常"""
    pass


class PDFReader:
    """
    PDF 文档读取器
    
    支持多种 PDF 解析引擎，自动降级处理：
    1. 优先使用 pdfplumber（更强大）
    2. 降级使用 PyPDF2（更轻量）
    3. 最终降级提示用户输入文本
    """
    
    def __init__(self, max_pages: int = 100):
        """
        初始化 PDF 读取器
        
        Args:
            max_pages: 最大读取页数限制，防止内存溢出
        """
        self.max_pages = max_pages
        self._pdfplumber_available = self._check_pdfplumber()
        self._pypdf2_available = self._check_pypdf2()
        
        logger.info(f"PDFReader 初始化完成: pdfplumber={self._pdfplumber_available}, "
                    f"PyPDF2={self._pypdf2_available}")
    
    def _check_pdfplumber(self) -> bool:
        """检查 pdfplumber 是否可用"""
        try:
            import pdfplumber
            return True
        except ImportError:
            logger.warning("pdfplumber 未安装，将使用 PyPDF2 作为备选")
            return False
    
    def _check_pypdf2(self) -> bool:
        """检查 PyPDF2 是否可用"""
        try:
            from PyPDF2 import PdfReader
            return True
        except ImportError:
            logger.warning("PyPDF2 未安装")
            return False
    
    def validate_file(self, file_path: str) -> Path:
        """
        验证 PDF 文件是否有效
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            Path: 验证后的文件路径对象
            
        Raises:
            PDFNotFoundError: 文件不存在
            PDFCorruptedError: 文件损坏或不是 PDF
        """
        path = Path(file_path)
        
        # 检查文件是否存在
        if not path.exists():
            raise PDFNotFoundError(f"文件不存在: {file_path}")
        
        # 检查是否是文件（非目录）
        if not path.is_file():
            raise PDFNotFoundError(f"路径不是文件: {file_path}")
        
        # 检查文件扩展名
        if path.suffix.lower() != '.pdf':
            logger.warning(f"文件扩展名不是 .pdf: {path.suffix}")
        
        # 检查文件大小
        file_size = path.stat().st_size
        if file_size == 0:
            raise PDFCorruptedError(f"文件为空: {file_path}")
        
        if file_size > 100 * 1024 * 1024:  # 100MB 限制
            logger.warning(f"文件过大 ({file_size / 1024 / 1024:.2f}MB)，可能导致处理缓慢")
        
        return path
    
    def read_with_pdfplumber(self, file_path: Path) -> str:
        """
        使用 pdfplumber 读取 PDF
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            str: 提取的文本内容
            
        Raises:
            PDFCorruptedError: 文件损坏
            PDFEmptyError: 内容为空
        """
        if not self._pdfplumber_available:
            raise ImportError("pdfplumber 未安装")
        
        import pdfplumber
        
        text_parts = []
        try:
            with pdfplumber.open(file_path) as pdf:
                pages = pdf.pages[:self.max_pages]
                
                for i, page in enumerate(pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                    except Exception as e:
                        logger.warning(f"第 {i+1} 页提取失败: {e}")
                        continue
                
                if not text_parts:
                    raise PDFEmptyError("PDF 中未提取到任何文本内容")
                
                return "\n\n".join(text_parts)
                
        except PDFEmptyError:
            raise
        except Exception as e:
            raise PDFCorruptedError(f"PDF 文件损坏或格式不支持: {e}")
    
    def read_with_pypdf2(self, file_path: Path) -> str:
        """
        使用 PyPDF2 读取 PDF
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            str: 提取的文本内容
            
        Raises:
            PDFCorruptedError: 文件损坏
            PDFEmptyError: 内容为空
        """
        if not self._pypdf2_available:
            raise ImportError("PyPDF2 未安装")
        
        from PyPDF2 import PdfReader
        
        text_parts = []
        try:
            reader = PdfReader(file_path)
            pages = reader.pages[:self.max_pages]
            
            for i, page in enumerate(pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception as e:
                    logger.warning(f"第 {i+1} 页提取失败: {e}")
                    continue
            
            if not text_parts:
                raise PDFEmptyError("PDF 中未提取到任何文本内容")
            
            return "\n\n".join(text_parts)
            
        except PDFEmptyError:
            raise
        except Exception as e:
            raise PDFCorruptedError(f"PDF 文件损坏或格式不支持: {e}")
    
    def preprocess_text(self, text: str) -> str:
        """
        预处理提取的文本
        
        Args:
            text: 原始提取文本
            
        Returns:
            str: 清洗后的文本
        """
        if not text:
            return ""
        
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text)
        
        # 去除特殊字符但保留中文、英文、数字、标点
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\.\,\;\:\!\?\%\+\-\*\/\(\)\[\]\{\}\"\'\-\—\…\、\。\，\；\：\！\？]', '', text)
        
        # 规范化数字格式
        text = re.sub(r'(\d+)\s*%', r'\1%', text)
        
        # 去除重复换行
        text = re.sub(r'\n\s*\n', '\n', text)
        
        return text.strip()
    
    def read_pdf(self, file_path: str) -> Dict[str, Any]:
        """
        读取 PDF 文件（主方法）
        
        优先使用 pdfplumber，失败后降级使用 PyPDF2
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            Dict: 包含以下字段：
                - success: 是否成功
                - text: 提取的文本内容
                - engine: 使用的解析引擎
                - error: 错误信息（如果失败）
                - file_path: 文件路径
                - page_count: 读取的页数
        """
        result = {
            "success": False,
            "text": "",
            "engine": "none",
            "error": None,
            "file_path": file_path,
            "page_count": 0
        }
        
        try:
            # 验证文件
            path = self.validate_file(file_path)
            
            # 尝试 pdfplumber
            if self._pdfplumber_available:
                try:
                    text = self.read_with_pdfplumber(path)
                    text = self.preprocess_text(text)
                    
                    result["success"] = True
                    result["text"] = text
                    result["engine"] = "pdfplumber"
                    result["page_count"] = min(len(text.split('\f')) + 1, self.max_pages)
                    
                    logger.info(f"pdfplumber 解析成功: {len(text)} 字符")
                    return result
                    
                except Exception as e:
                    logger.warning(f"pdfplumber 解析失败，尝试 PyPDF2: {e}")
            
            # 降级到 PyPDF2
            if self._pypdf2_available:
                try:
                    text = self.read_with_pypdf2(path)
                    text = self.preprocess_text(text)
                    
                    result["success"] = True
                    result["text"] = text
                    result["engine"] = "pypdf2"
                    
                    logger.info(f"PyPDF2 解析成功: {len(text)} 字符")
                    return result
                    
                except Exception as e:
                    logger.warning(f"PyPDF2 解析失败: {e}")
            
            # 所有引擎都失败
            result["error"] = "PDF 解析引擎不可用或解析失败"
            
        except PDFNotFoundError as e:
            result["error"] = f"文件不存在: {e}"
        except PDFCorruptedError as e:
            result["error"] = f"文件损坏: {e}"
        except PDFEmptyError as e:
            result["error"] = f"内容为空: {e}"
        except Exception as e:
            result["error"] = f"未知错误: {e}"
        
        return result
    
    def cleanup(self):
        """清理资源（安全删除临时文件等）"""
        # 当前实现不创建临时文件，预留接口
        logger.debug("PDFReader 资源清理完成")


def read_pdf_safe(file_path: str) -> str:
    """
    安全读取 PDF 的便捷函数
    
    Args:
        file_path: PDF 文件路径
        
    Returns:
        str: 提取的文本内容，失败返回空字符串
    """
    reader = PDFReader()
    result = reader.read_pdf(file_path)
    
    if result["success"]:
        return result["text"]
    else:
        logger.error(f"PDF 读取失败: {result['error']}")
        return ""


if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
    else:
        print("用法: python pdf_reader.py <pdf文件路径>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.INFO)
    
    reader = PDFReader()
    result = reader.read_pdf(test_file)
    
    if result["success"]:
        print(f"解析引擎: {result['engine']}")
        print(f"提取字符数: {len(result['text'])}")
        print("\n--- 提取内容预览 ---")
        print(result['text'][:1000])
    else:
        print(f"解析失败: {result['error']}")
