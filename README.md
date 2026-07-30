# MinerU Paper Reading — 可重現安裝與使用

## 環境

- **Python**: 3.10（必要，3.11+ 有 transformers 相容問題）
- **OS**: Windows 10/11
- **GPU**: 可選（CPU 可用，較慢）

## 一鍵安裝

```bash
# 1. 建立 Python 3.10 獨立環境
uv python install 3.10
uv venv mineru_py310 -p 3.10

# 2. 安裝 MinerU 及所有依賴
uv pip install -p mineru_py310 "mineru[all]" "transformers>=4.44,<4.45"

# 3. 運行（必須清除 PYTHONPATH 避免污染）
# Windows CMD:
set PYTHONPATH=
mineru_py310\Scripts\mineru.exe -p paper.pdf -o output -b pipeline

# Git Bash:
PYTHONPATH= mineru_py310/Scripts/mineru.exe -p paper.pdf -o output -b pipeline
```

## 關鍵陷阱

| 問題 | 原因 | 解法 |
|------|------|------|
| `ModuleNotFoundError: torch/torchvision/...` | `mineru` 未含完整依賴 | 改用 `mineru[all]` |
| 載入 hermes venv 的套件 | `PYTHONPATH` 指向 hermes | `PYTHONPATH=` 清空後執行 |
| `tokenizers` ModelWrapper 錯誤 | venv 中 transformers 版本衝突 | Python 3.10 獨立環境 |
| `find_pruneable_heads_and_indices` | transformers ≥4.45 | 鎖定 `transformers>=4.44,<4.45` |

## 產出

MinerU 會為每個 PDF 建立 `<output>/<filename>/auto/` 目錄，包含：
- `<filename>.md` — 結構化 Markdown（含表格、LaTeX 公式）
- `<filename>_content_list.json` — 段落級內容清單
- `<filename>_model.json` — 版面分析結果

## 備用方案

若 MinerU 無法安裝，見 `skills/deepseek-ocr-pdf` skill — 用 DeepSeek API 直接 OCR 論文 PDF。
