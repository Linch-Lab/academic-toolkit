# Three-Electrode Polarization — 三電極極化曲線繪圖工具

> 三電極量測（工作電極 vs 參考電極）的極化曲線繪圖 GUI：
> 參考電位換算、Tafel 圖、過電位 η、iR 補償。開源（MIT）· academic-toolkit 一部分。

## ✨ 功能

| 功能 | 說明 |
|------|------|
| **多檔案疊加** | 列表管理，多條 LSV/半電池曲線比較 |
| **參考電位換算** | 來源電極 → RHE（SCE/Ag/AgCl/Hg/HgO/SHE/RHE，含 KCl/pH/溫度 Nernst）|
| **vs RHE / Raw** | 顯示換算後或原始電位 |
| **線性 / Tafel** | Y 軸電流密度或 log\|j\| |
| **過電位 η** | η = V − E0（全域勾選，E0 每檔獨立）|
| **iR 補償** | V − i×R（全域勾選，R 每檔獨立）|
| **X/Y 軸切換** | X=V,Y=I ↔ X=I,Y=V |
| **單位** | A/cm² / mA/cm² / µA/cm² / A |

## 參考電位換算公式

```
E_RHE = E_raw + E0(來源電極) + slope×pH
slope = 0.05916 × (T+273.15)/298.15
```

| 來源電極 | E0 (vs SHE) |
|---------|:--:|
| vs RHE / vs SHE | 0 |
| SCE | 0.241 |
| Ag/AgCl | 依 KCl（sat 0.197 / 3.5M 0.205 / 3M 0.210 / 1M 0.235）|
| Hg/HgO | 0.098 |

## 過電位 η 與 iR 補償

- **η** = V − E0：E0 為平衡電位（如 OER 1.23 V vs RHE），屬性視窗每檔輸入
- **iR** = V − i×R：R 為未補償電阻（Ω），i 用總電流（j × 面積）

## 📦 安裝

```bash
pip install matplotlib pandas numpy
```

## 🚀 使用

```bash
python three_electrode_plotter.py
```

1. 「+ Add Curve」載入 CSV（欄位：電位 V + 電流 A）
2. 全域設定選來源電極 + pH/溫度 → 自動換算 vs RHE
3. 切換 Y Mode 看 Tafel 圖；勾 η/iR 看過電位/補償曲線

## 📂 examples/
- `OER_LSV_demo.csv` — 三電極 OER LSV 範例（vs Ag/AgCl，假數據）
