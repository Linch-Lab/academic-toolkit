---
name: mineru-paper-reading
description: MinerU 論文 PDF/DOCX 解析——將學術文獻轉換為結構化 Markdown（含表格、LaTeX 公式、圖片描述）。Python 3.10 隔離環境，一鍵安裝。
version: 2.0.0
platforms: [windows]
---

# MinerU Paper Reading

## 概述

MinerU (opendatalab/MinerU) 將 PDF、DOCX、PPTX、XLSX 轉換為結構化 Markdown/JSON。Pipeline 後端支援 CPU/GPU，辨識表格（HTML→Markdown）、數學公式（LaTeX）、圖片描述、109 語言 OCR。

**GitHub**: https://github.com/opendatalab/MinerU

## 安裝（Python 3.10 隔離環境）

```bash
# 1. Python 3.10（必要，3.11+ 有 transformers 相容問題）
uv python install 3.10
uv venv mineru_py310 -p 3.10

# 2. 完整安裝
uv pip install -p mineru_py310 "mineru[all]" "transformers>=4.44,<4.45"

# 3. 清除 PYTHONPATH（防止其他 venv 污染）
# Windows CMD:  set PYTHONPATH=
# Git Bash:    PYTHONPATH=
```

## 使用

```bash
# 單篇論文
PYTHONPATH= mineru_py310/Scripts/mineru.exe -p paper.pdf -o output -b pipeline

# 批次
for pdf in ref/*.pdf; do
    PYTHONPATH= mineru_py310/Scripts/mineru.exe -p "$pdf" -o output -b pipeline
done
```

## 產出結構

```
output/{paper}/
└── auto/
    ├── {paper}.md                  # 結構化 Markdown（主產出）
    ├── {paper}_content_list.json   # 段落級內容清單
    └── {paper}_model.json          # 版面分析結果
```

## 關鍵陷阱

| 錯誤 | 原因 | 解法 |
|------|------|------|
| **任何 pip list 已有但 import 報錯** | `PYTHONPATH` 指向其他 venv（最常見：hermes-agent） | `PYTHONPATH=` 清空。診斷：`python -c "import sys; print([p for p in sys.path if 'hermes' in p])"` |
| traceback 出現其他 venv 路徑（如 `...hermes-agent\venv\Lib\...`） | 同上——PYTHONPATH 污染 | 同上。所有後續 import 都從錯誤環境載入 |
| `ModuleNotFoundError: torch/torchvision/shapely/ftfy/six/...` | 用了 `mineru` 而非 `mineru[all]` | `uv pip install -p mineru_py310 "mineru[all]"` |
| `tokenizers` ModelWrapper enum (line 249230) | transformers/tokenizers 版本衝突 | `"transformers>=4.44,<4.45"` |
| `find_pruneable_heads_and_indices` 消失 | transformers ≥4.45 | 同上 |
| `hgnet_v2` / `rt_detr` 模組缺失 | transformers <4.44 | 同上 |
| `dict object has no attribute 'to_dict'` | mineru-vl-utils 不相容 transformers 4.49+ | 同上 |
| CUDA OOM（6GB VRAM） | 大檔 PDF | 設 CUDA_VISIBLE_DEVICES、切 5-10 頁塊 |
| 首次執行慢（>5 min） | 模型下載 ~2GB | 僅首次，後續命中快取 |
| conda 不存在 | 本機無 conda | `uv venv -p 3.10` 替代 |

### 診斷 PYTHONPATH 污染

```bash
echo $PYTHONPATH
# 若出現 hermes-agent 路徑 → 污染源

PYTHONPATH= 你的python.exe -c "import mineru; print(mineru.__file__)"
# 正確：D:\mineru_py310\Lib\site-packages\mineru\...
# 污染：C:\Users\...\hermes\hermes-agent\venv\Lib\site-packages\mineru\...
```

## 完整工作流範例

```bash
# 1. 安裝（僅首次）
uv python install 3.10
uv venv mineru_py310 -p 3.10
uv pip install -p mineru_py310 "mineru[all]" "transformers>=4.44,<4.45"

# 2. 解析論文
PYTHONPATH= mineru_py310/Scripts/mineru.exe -p paper.pdf -o mineru_output -b pipeline

# 3. 讀取產出
cat mineru_output/paper/auto/paper.md
```

## 備用方案

若 MinerU 無法安裝，使用 `deepseek-ocr-pdf` skill（DeepSeek API OCR，免本機依賴）。

## 相關 Skills

- `deepseek-ocr-pdf` — API 替代方案
- `thesis-review` — 論文審查完整流程（引用此 skill 做解析）

## 參考資料

- `references/PPI-correlations.md` — 金屬泡沫 PPI 關聯式速查（Calmidi 2000, Fourie 2002, Boomsma 2001, Ghofrani 2024 四篇關鍵文獻的 d_p/K/C_F/A_v 量化數據）
