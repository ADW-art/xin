"""
Notebook Service — Markdown to .ipynb converter

Pure Python, zero external API dependencies.
Uses nbformat to produce valid Jupyter notebook JSON.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)


def markdown_to_notebook(markdown_content: str, title: str = "Notebook") -> dict:
    """Parse markdown with code blocks into .ipynb notebook dict.

    Rules:
    - ```python blocks → code cells
    - Everything else → markdown cells
    - Consecutive text blocks merged into one markdown cell
    """
    cells: list[dict] = []

    # Split on fenced code blocks: ```python ... ``` or ``` ... ```
    pattern = re.compile(r'```(?:python|python3|py)?\s*\n(.*?)```', re.DOTALL)
    parts = pattern.split(markdown_content)

    # parts[0] = text before first code block
    # parts[1] = first code content
    # parts[2] = text between first and second code block
    # parts[3] = second code content, etc.

    for i, part in enumerate(parts):
        if not part.strip():
            continue
        if i % 2 == 1:
            # Code cell (odd indices are code content)
            cells.append({
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [line + "\n" for line in part.split("\n")],
            })
        else:
            # Markdown cell (even indices are text)
            cells.append({
                "cell_type": "markdown",
                "metadata": {},
                "source": [line + "\n" for line in part.split("\n")],
            })

    # If no code blocks found, make the whole thing a single markdown cell
    if not any(c["cell_type"] == "code" for c in cells):
        cells = [{
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + "\n" for line in markdown_content.split("\n")],
        }]

    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.9.0",
            },
        },
        "cells": cells,
    }

    return notebook


def content_to_notebook_bytes(content: str, title: str = "Notebook") -> bytes:
    """Full pipeline: markdown → .ipynb JSON → UTF-8 bytes."""
    notebook = markdown_to_notebook(content, title)
    return json.dumps(notebook, ensure_ascii=False, indent=1).encode("utf-8")
