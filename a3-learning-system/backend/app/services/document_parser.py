"""
文档解析服务 —— 省一标准

支持格式：PDF / Word / 扫描版教材 / Markdown
技术栈：pdfplumber + PaddleOCR + python-docx
输出：结构化 JSON 段落列表，保留代码/公式/表格

结构识别规则：
  - 代码块：以 ``` 包裹、或连续4空格缩进段落 → type=code
  - LaTeX公式：$$...$$ 或 $...$ → type=formula
  - 表格：pdfplumber 自动提取 → type=table
  - 普通文本：其余 → type=text
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── PaddleOCR 单例（懒加载，避免每次图片都新开模型加载~2s/100MB）──
_paddle_ocr = None


def _get_paddle_ocr():
    """懒加载 PaddleOCR 单例"""
    global _paddle_ocr
    if _paddle_ocr is None:
        from paddleocr import PaddleOCR
        logger.info("PaddleOCR: 正在初始化模型...")
        _paddle_ocr = PaddleOCR(lang='ch')
        logger.info("PaddleOCR: 初始化完成")
    return _paddle_ocr


def parse_pdf(file_path: str, use_ocr: bool = False) -> list[dict]:
    """解析 PDF 文件（普通文字层 + 扫描版 OCR），返回段落列表"""
    import pdfplumber
    paragraphs = []
    ocr_pages = 0
    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            # 文字层为空 → 扫描版 → OCR
            if (not text or len(text.strip()) < 20) and use_ocr:
                text = _ocr_page(page, page_num)
                if text:
                    ocr_pages += 1
            if not text:
                continue
            for para in text.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                paragraphs.append({
                    "type": _classify_paragraph(para),
                    "content": clean_paragraph(para),
                    "page": page_num,
                    "source": Path(file_path).name,
                })
    if ocr_pages:
        logger.info("PDF解析: %s → %d 段落 (OCR %d页)", file_path, len(paragraphs), ocr_pages)
    else:
        logger.info("PDF解析: %s → %d 段落", file_path, len(paragraphs))
    return paragraphs


def _ocr_page(page, page_num: int) -> str:
    """PaddleOCR 识别单页扫描版（使用单例模型，避免重复加载）"""
    try:
        import numpy as np
        ocr = _get_paddle_ocr()
        img = page.to_image(resolution=200)
        img_array = np.array(img.original)
        result = ocr.ocr(img_array)
        if result and result[0]:
            lines = []
            for line in result[0]:
                text = line[1][0] if len(line) > 1 and len(line[1]) > 0 else ""
                if text:
                    lines.append(text)
            return "\n".join(lines)
    except Exception as e:
        logger.warning("PaddleOCR 第%d页识别失败: %s", page_num, e)
    return ""


def parse_docx(file_path: str) -> list[dict]:
    """解析 Word 文件"""
    from docx import Document
    paragraphs = []
    doc = Document(file_path)
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        paragraphs.append({
            "type": _classify_paragraph(text),
            "content": text,
            "source": Path(file_path).name,
        })
    logger.info("Word解析: %s → %d 段落", file_path, len(paragraphs))
    return paragraphs


def parse_markdown(file_path: str) -> list[dict]:
    """解析 Markdown 文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取标题
    title = ""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break

    paragraphs = []
    # 按双换行分段
    for para in content.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        ptype = _classify_paragraph(para)
        # Markdown标题转普通文本
        if para.startswith("#"):
            ptype = "heading"
        paragraphs.append({
            "type": ptype,
            "content": para,
            "source": Path(file_path).name,
            "title": title,
        })
    logger.info("Markdown解析: %s → %d 段落", file_path, len(paragraphs))
    return paragraphs


def parse_file(file_path: str) -> list[dict]:
    """自动识别文件类型，解析为段落列表"""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(file_path)
    elif suffix in (".docx", ".doc"):
        return parse_docx(file_path)
    elif suffix in (".md", ".markdown"):
        return parse_markdown(file_path)
    elif suffix == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return [{"type": _classify_paragraph(p), "content": p.strip(), "source": Path(file_path).name} for p in text.split("\n\n") if p.strip()]
    else:
        raise ValueError(f"不支持的文件格式: {suffix}")


def parse_uploaded_pdf(file_bytes: bytes, filename: str) -> list[dict]:
    """解析上传的 PDF 字节流（用于 API）"""
    import pdfplumber
    import io
    paragraphs = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue
            for para in text.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                paragraphs.append({
                    "type": _classify_paragraph(para),
                    "content": para,
                    "page": page_num,
                    "source": filename,
                })
    return paragraphs


def _classify_paragraph(text: str) -> str:
    """自动分类段落类型"""
    if text.startswith("```") or (text.startswith("    ") and len(text) > 4):
        return "code"
    if re.search(r"(?<!\\)\$\$|(?<!\\)\$[^$]+\$", text):
        return "formula"
    if re.search(r"\|[ -]+\|", text) and text.count("|") >= 2:
        return "table"
    return "text"


def clean_paragraph(text: str) -> str:
    """清洗段落：去页码、水印、多余空白"""
    # 去独立数字页码
    text = re.sub(r'^\s*\d{1,4}\s*$', '', text, flags=re.MULTILINE)
    # 去页眉页脚"第X页"
    text = re.sub(r'第\s*\d+\s*页', '', text)
    # 合并多余换行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
