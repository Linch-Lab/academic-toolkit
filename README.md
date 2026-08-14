# Academic Toolkit

> 學術研究工具鏈 — 文獻解析 + 數據繪圖，開源分享給研究社群
> Academic research toolchain: paper parsing + data visualization

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

## 📦 內容 / Contents

| 工具 | 說明 | 目錄 |
|------|------|------|
| **MinerU Paper Reading** | 學術 PDF/DOCX 解析 → 結構化 Markdown（表格、LaTeX 公式、OCR）。Python 3.10 隔離環境、一鍵安裝 | [`MinerU-Paper-Reading/`](MinerU-Paper-Reading/) |
| **XRD Plotter** | XRD 數據繪圖 GUI（Tkinter）——實驗數據 + PDF 資料庫譜線對照，互動式微調與標註 | [`Matplotlib-skills/XRD/`](Matplotlib-skills/XRD/) |
| **Polarization Curve Plotter** | 極化曲線繪圖 GUI——FC/EC I-V 曲線、active area 換算、雙 Y 軸功率、單位切換 | [`Matplotlib-skills/Polarization-Curve/`](Matplotlib-skills/Polarization-Curve/) |
| **Nyquist Plotter** | EIS Nyquist 圖繪圖 GUI——解析 DRTxECM 匯出 CSV、raw marker / fitted 實線、X/Y 同比例鎖定 | [`Matplotlib-skills/Nyquist-plot/`](Matplotlib-skills/Nyquist-plot/) |
| **Pt CV Curve Plotter** | CV 曲線繪圖 + ECSA 計算 GUI——多圈自動切分、RHE 換算、陰/陽極吸附面積分 | [`Matplotlib-skills/Pt-CV-Curve/`](Matplotlib-skills/Pt-CV-Curve/) |

## 🚀 快速開始

### 文獻解析（MinerU）

```bash
# 1. 建立 Python 3.10 環境（必要）
uv python install 3.10
uv venv mineru_py310 -p 3.10

# 2. 安裝
uv pip install -p mineru_py310 "mineru[all]" "transformers>=4.44,<4.45"

# 3. 解析論文（Windows Git Bash）
PYTHONPATH= mineru_py310/Scripts/mineru.exe -p paper.pdf -o output -b pipeline
```

詳見 [`MinerU-Paper-Reading/README.md`](MinerU-Paper-Reading/README.md)

### XRD 繪圖

```bash
pip install matplotlib pandas numpy
python Matplotlib-skills/XRD/xrd_plotter.py
```

詳見 [`Matplotlib-skills/XRD/README.md`](Matplotlib-skills/XRD/README.md)

## 📖 誰適合用

- 研究生/學者：論文 PDF 解析、XRD 數據可視化
- 完全沒裝過 Python 的人：各工具 README 含從零安裝教學

## 🤝 貢獻

歡迎 fork 與 PR——新增學術工具 skill 請遵循既有結構（`<Tool-Name>/SKILL.md` + `README.md`）。

## 📄 授權

MIT License — 程式碼與文件均為 MIT（見 [LICENSE](LICENSE)）。

---

*Maintained by Linch-Lab (NCU 能源所)*
