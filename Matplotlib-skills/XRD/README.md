# XRD Plotter — XRD 數據繪圖工具

> 互動式 XRD 繪圖 GUI：實驗數據 + PDF 資料庫譜線對照、視覺微調、標註、高品質輸出。
> 完全免費、開源（MIT）、零額外依賴（只需 Python + 3 個套件）。

## ✨ 功能

| 功能 | 說明 |
|------|------|
| **分區上傳** | 實驗數據與資料庫譜線分開上傳、各自獨立、數量不限 |
| **數據處理** | 強度歸一化（min-max 0–1）+ 垂直 offset 微調（曲線分離）|
| **視覺微調** | 顏色（色盤選擇）、字型、字體大小、線型/線寬、marker（種類/開關）|
| **排序** | 列表 ↑↓ 上下移動——決定繪圖順序與圖層（誰蓋誰）|
| **圖例** | 可拖曳位置（圖上直接拖）|
| **標註** | 新增文字標註與線段標註（peak 標示、圖解說明）|
| **輸出** | 儲存 PNG / SVG / PDF，可選 DPI，自訂檔名與位置 |

## 📦 安裝（第一次使用）

> 以下為「完全沒裝過 Python」的人設計。已有 Python 的人跳過第 1 步。

### 1. 安裝 Python

1. 到 <https://www.python.org/downloads/> 下載 **Python 3.10 或更新版**（Windows 選 64-bit installer）
2. 安裝時 **務必勾選「Add Python to PATH」**（加入系統路徑）
3. 安裝完成後，開啟「命令提示字元」（cmd），輸入 `python --version` 確認顯示版本號

### 2. 安裝所需套件

在命令提示字元中輸入：

```bash
pip install matplotlib pandas numpy
```

等待安裝完成（約 1–2 分鐘）。

### 3. 執行

```bash
python xrd_plotter.py
```

或雙擊 `xrd_plotter.py`（若 Python 已關聯 .py 檔）。

## 🖱️ 使用教學

### 上傳數據

| 類型 | 按鈕 | CSV 需要欄位 | 範例 |
|------|------|------|------|
| **實驗數據** | 「＋ 新增實驗數據」 | `2Theta`（2θ 角度）+ `Intensity`（原始強度）| `XRD_Exp1_ConcentrationD_NiMesh.csv` |
| **資料庫譜線** | 「＋ 新增譜線」 | `2Theta` + `Intensity_Rel`（相對強度 0–100）| `Database_MoNi4_PDF-65-5480.csv` |

可一次選多個檔案（Ctrl 多選）。資料庫譜線會自動畫成垂直棒狀。

### 微調

1. **選取項目** → 點「✎ 屬性」→ 調整顏色/偏移/歸一化/線型/線寬/marker
2. **排序**：選取項目 → 「↑ 上移 / ↓ 下移」（最上面的畫在最上層）
3. **全域**：左下方字型/字體大小/X 軸範圍
4. **圖例**：直接用滑鼠在圖上拖動圖例框

### 標註

1. 「＋ 文字標註」→ 輸入 X、Y 位置與文字
2. 「＋ 線段標註」→ 輸入起點/終點座標（常用於標示 peak 位置）
3. 「✕ 清除標註」→ 移除全部標註

### 輸出

1. 調整完成後點「💾 儲存圖」
2. 選 DPI（發表用建議 **300**）
3. 選格式（PNG 最通用 / SVG 向量 / PDF）與儲存位置

## 📂 範例數據

本目錄 `examples/` 提供假數據（非真實數據）供測試：

```bash
python xrd_plotter.py
# 上傳 examples/XRD_Exp1_ConcentrationD_NiMesh.csv（實驗）
# 上傳 examples/Database_MoNi4_PDF-65-5480.csv（資料庫）
```

## ❓ 常見問題

| 問題 | 解法 |
|------|------|
| `python` 不是內部或外部命令 | Python 沒加 PATH——重新安裝並勾選「Add Python to PATH」|
| `ModuleNotFoundError: pandas` | 執行 `pip install pandas matplotlib numpy` |
| 檔案上傳後沒顯示 | 檢查 CSV 欄位名稱是否完全正確（`2Theta` 的 T 大寫）|
| 想要更多 marker 樣式 | 屬性視窗 marker 下拉有 `o s ^ v D x + * \| _` |

## 📄 授權

MIT License（見 repo 根目錄 LICENSE）。
