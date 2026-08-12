# Polarization Curve Plotter — 極化曲線繪圖工具

> 互動式 I-V 極化曲線繪圖 GUI：燃料電池 (FC) 與水電解器 (EC) 皆適用。
> 開源（MIT）· 本目錄為 academic-toolkit 的一部分。

## ✨ 功能

| 功能 | 說明 |
|------|------|
| **多曲線上傳** | 一條曲線一個 CSV，數量不限；上傳時手動指定電壓/電流欄位 |
| **Active Area 換算** | 輸入有效面積 (cm²)，原始電流 A → 電流密度 A/cm² |
| **單位轉換** | A / A/cm² / mA/cm² 三種電流單位自動換算 |
| **軸設定** | X / Y（左）/ Y₂（右，功率）三軸各自可設 min/max 範圍與刻度數量（空=自動）|
| **取絕對值切換** | 電流 |I| 與電壓 |V| 各自獨立「取絕對值」——處理儀器輸出負值的數據，圖維持第一象限 |
| **功率密度疊圖** | P = I×V 自動計算，雙 Y 軸顯示，單位可選 W/cm² / mW/cm² |
| **軸角色切換** | X=I,Y=V（電化學慣例）⇄ X=V,Y=I |
| **視覺微調** | 顏色、字型、字體大小、線型/線寬、marker（種類/開關）|
| **排序** | 列表 ↑↓ 上下移動——決定繪圖順序與圖層 |
| **圖例** | 自訂標籤 + 圖上直接拖曳位置 |
| **標註** | 文字標註、線段標註（peak 標示、圖解說明）|
| **輸出** | 儲存 PNG/SVG/PDF（可選 DPI）+ 匯出合併 CSV（V, I, P, label）|

## 📦 安裝（第一次使用）

> 以下為「完全沒裝過 Python」的人設計。已有 Python 的人跳過第 1 步。

### 1. 安裝 Python

1. 到 <https://www.python.org/downloads/> 下載 **Python 3.10 或更新版**
2. 安裝時 **務必勾選「Add Python to PATH」**
3. 命令提示字元輸入 `python --version` 確認

### 2. 安裝所需套件

```bash
pip install matplotlib pandas numpy
```

### 3. 執行

```bash
python polarization_plotter.py
```

## 🖱️ 使用教學

### 上傳數據

1. 點「＋ 新增曲線」→ 選擇 CSV（可多選）
2. 彈出視窗設定：
   - **電壓欄位**：哪欄是電壓 (V)
   - **電流欄位**：哪欄是電流 (I)
   - **電流單位**：`A`（原始安培，需輸入 Active Area）/ `A/cm²` / `mA/cm²`
   - **Active Area (cm²)**：原始 A 換算用（單位為 A 時才需要）
3. 新增後可在「✎ 屬性」中進一步設定：
   - **圖例標籤**：如 `T=180°C, sto=1`
   - **電流單位**：`A`（原始安培，需設 Active Area）/ `A/cm²` / `mA/cm²`
   - **Active Area**：如 `9`（cm²）
   - **取絕對值**：數據為負（儀器輸出）時勾選「電流 |I|」與/或「電壓 |V|」→ 翻正顯示、軸維持第一象限
   - **功率曲線**：勾選顯示 + 單位（W/cm² / mW/cm²）

### 全域設定

- **軸角色**：`X=I, Y=V`（電化學慣例）或 `X=V, Y=I`
- **顯示功率曲線**：勾選時所有勾了功率的曲線顯示在右 Y 軸（虛線）
- 字型 / 字體大小

### 輸出

- **💾 儲存圖**：PNG / SVG / PDF + DPI（發表用建議 300）
- **📊 匯出CSV**：全部曲線合併一個 CSV（`V, I_density, P, label`）——方便後續統計/其他軟體

## 📂 範例數據（examples/）

| 檔案 | 內容 | 上傳設定 |
|------|------|------|
| `FC_180C_sto1_rawA.csv` | 燃料電池 180°C sto1（原始 A）| V=Voltage_V, I=Current_A, 單位=A, 面積=9 |
| `FC_180C_sto3_rawA.csv` | 燃料電池 180°C sto3（原始 A）| 同上 |
| `AEMWE_60C.csv` | 水電解器 AEMWE（已是 A/cm²）| V=Cell_voltage, I=Current_density, 單位=A/cm² |

## ❓ 常見問題

| 問題 | 解法 |
|------|------|
| `python` 不是內部或外部命令 | Python 沒加 PATH——重裝並勾選「Add Python to PATH」|
| `ModuleNotFoundError: pandas` | `pip install matplotlib pandas numpy` |
| 上傳後圖是空的 | 檢查欄位選擇是否正確（V 欄選到文字欄會失敗）|
| 功率曲線沒顯示 | ① 該曲線屬性勾「顯示功率曲線」② 全域勾「顯示功率曲線」|
| EC 曲線看起來怪 | 電解器 V 隨 I 遞增是正常的；可關掉功率曲線 |

## 📄 授權

MIT License（見 repo 根目錄 LICENSE）。
