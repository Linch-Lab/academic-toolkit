# Pt CV Curve Plotter — CV 曲線繪圖 + ECSA 計算工具

> Pt 電催化劑循環伏安（CV）曲線繪圖 + 電化學活性表面積（ECSA）計算 GUI。
> 開源（MIT）· 本目錄為 academic-toolkit 的一部分。

## ✨ 功能

| 功能 | 說明 |
|------|------|
| **多圈自動切分** | 依 V 極值循環切分封閉 CV 曲線（V_max→V_min→V_max = 一圈）|
| **圈選擇下拉** | 顯示圈 = 計算圈，下拉切換（顯示每圈 V 範圍）|
| **電位參考切換** | vs RHE / vs 參考電極——選擇後自動 E0 換算（sat. 0.1976 / 3.5M 0.205 / 3M 0.210 / 1M 0.235）|
| **電流單位切換** | A / mA / µA |
| **ECSA 計算彈窗** | 陰極吸附/陽極脫附勾選、積分區間與基準線輸入、內嵌小圖確認 |
| **完整 GUI** | 列表/↑↓排序/屬性/圖例互動/軸設定/標註/儲存 |

## ECSA 公式

```
Q_H = ∫(I − I_base) dV / scan_rate        [µC]
ECSA = Q_H / (Q_ref × m_Pt)               [m²/g Pt]
Q_ref = 210 µC/cm²（Pt 單層氫吸附電荷）
```

## 📦 安裝

```bash
pip install matplotlib pandas numpy scipy
```

## 🚀 使用

```bash
python pt_cv_plotter.py
```

### 載入 CV 數據
1. 「＋ 新增」→ 選 CSV → 彈窗指定 **電位 V 欄** 與 **電流 I 欄**
2. 自動切分多圈 → 列表顯示「名稱 (3圈)」
3. 選取數據 → 「圈選擇」下拉選圈（顯示圈 = 計算圈）

### ECSA 計算
1. 選取數據 → 按「ECSA」→ 彈窗
2. 填 Pt 載量 (mg/cm²)、幾何面積 (cm²)
3. 勾選陽極脫附/陰極吸附 → 各填積分區間與基準線兩端電位
4. 「預覽積分區」→ 內嵌小圖顯示積分區（紅=陽極、藍=陰極）
5. 「計算」→ 輸出 Q (µC) + ECSA (m²/g) + 平均

### 全域設定
- **電位參考**：vs RHE / vs 參考電極（電解質 E0 換算，圖與計算同步）
- **掃速**：mV/s（全域，ECSA 彈窗自動帶入）
- **電流單位**：A / mA / µA
- **曲線外觀**：marker 開關/大小/線粗、框粗、tick 粗/長
- **字型/字體/圖比例**（4:3 / 16:9 / 1:1 / 3:2）

## 📂 examples/
- `Pt_CV_3cycles_demo.csv` — 3 圈 Pt CV 示範數據（氫吸附/脫附峰 + 氧化物區）

## 參考

參考實作：[Linch-Lab/scientific-data-tools — Pt_ECSA_calculator](https://github.com/Linch-Lab/scientific-data-tools/tree/main/Pt_ECSA_calculator)
