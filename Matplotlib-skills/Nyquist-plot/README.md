# Nyquist Plotter — EIS Nyquist 圖繪圖工具

> 互動式 EIS Nyquist 圖繪圖 GUI：解析 DRTxECM 匯出 CSV，raw 與 fitted 數據對照。
> 開源（MIT）· 本目錄為 academic-toolkit 的一部分。

## ✨ 功能

| 功能 | 說明 |
|------|------|
| **DRTxECM 格式解析** | 自動偵測「ECM 參數表 + 頻率響應數據塊」結構，擷取 raw 與 fitted 數據 |
| **標準 EIS CSV** | 無 DRTxECM 欄位時，上傳彈窗手動指定 Z′ / Z″ 欄位 |
| **Nyquist 慣例** | X = Z′ (Ω)、Y = −Z″ (Ω)（電弧朝上）；自動偵測檔案符號慣例 |
| **raw 預設純 marker** | 實驗數據用 marker 顯示（無連線） |
| **fitted 預設純實線** | 擬合數據用實線顯示（無 marker） |
| **X/Y 同比例鎖定** | `set_aspect('equal')`（Nyquist 物理正確），可勾選關閉 |
| **完整 GUI** | 多檔案列表、↑↓排序、✎屬性、圖例拖曳+鍵盤微調+雙擊設定、軸設定（範圍/刻度/子刻度/方向）、標註、儲存 PNG/SVG/PDF、匯出 CSV |

## 📦 安裝

```bash
pip install matplotlib pandas numpy
```

## 🚀 使用

```bash
python nyquist_plotter.py
```

### 載入 DRTxECM 匯出 CSV
1. 點「＋ 新增」→ 選擇 CSV（可多選）
2. 自動解析：偵測 `Merged Frequency Response` 數據塊
   - **raw** → 純 marker（`Z_raw_prime`, `Z_raw_double_prime`）
   - **fitted** → 純實線（`Total_Fitted_Z_prime`, `Total_Fitted_Z_double_prime`）
3. 列表顯示 `名稱 (R+F)` = 有 raw + fitted

### 載入標準 EIS CSV
- 無 DRTxECM 欄位時彈窗 → 手動選 **Z′ 欄位** 與 **Z″ 欄位**

### 全域設定
- **軸同比例**：☑ 鎖定（Nyquist 慣例，X/Y 同單位 Ω）
- **曲線外觀**：marker 開關/大小/線粗、框粗、tick 粗/長（主:子 = 1:0.6）
- **字型/標題字體/刻度字體/圖比例**（4:3 / 16:9 / 1:1 / 3:2）

### 軸設定
```
X: [min]–[max] [刻度數] ☑子 [子數] [外/內]
Y: [min]–[max] [刻度數] ☑子 [子數] [外/內]
```

### 圖例互動
- **單擊**：選取（紅框）→ 方向鍵微調位置
- **雙擊**：設定視窗（外框/字體大小/字型）
- **拖曳**：移動位置（redraw 後保留）

## 📂 examples/
- `EIS_SC_SC-fitting.csv` — DRTxECM 匯出範例（80 頻率點，raw + fitted）

## Nyquist 慣例說明

Nyquist 圖 X = 實部 Z′、Y = 虛部 −Z″（標準電化學慣例，電容性阻抗 Z″<0 → −Z″>0 電弧朝上）。
本工具**自動偵測檔案符號**：若檔案的 Z″ 已是正值（如 DRTxECM 匯出），直接使用；否則取負。
