#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pt CV Curve Plotter — Pt 電催化 CV 曲線繪圖 + ECSA 計算 GUI（Tkinter + Matplotlib）

功能：
  1. CV 數據載入（手動指定 V/I 欄位），自動切分多圈封閉曲線（V 極值循環）
  2. 圈選擇下拉：顯示圈 = 計算圈
  3. X 軸電位參考切換：vs RHE / vs 參考電極（電解質 E0 換算）
  4. Y 軸電流單位切換（A / mA / µA）
  5. ECSA 計算彈窗：陰極吸附/陽極脫附勾選、積分區間與基準線輸入、
     內嵌小圖確認、輸出 ECSA (m²/g Pt)
  6. 完整 GUI：列表/屬性/圖例互動/軸設定/儲存

ECSA 公式：
  Q_H = ∫(I - I_base) dV / scan_rate
  ECSA = Q_H / (Q_ref × m_Pt)    [m²/g Pt]
  Q_ref = 210 µC/cm² (Pt 單層氫吸附電荷)

依賴：pip install matplotlib pandas numpy scipy
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, colorchooser

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# ------------------------------------------------------------------
# 常數
# ------------------------------------------------------------------
Q_REF_PT = 210.0        # µC/cm² Pt 單層
F_CONST = 96485.0       # C/mol
E0_REF_DICT = {          # 電解質 → RHE 參考電位 (V)
    "sat.": 0.1976,
    "3.5M": 0.205,
    "3M": 0.210,
    "1M": 0.235,
}

# ------------------------------------------------------------------
# 多圈切分
# ------------------------------------------------------------------
def split_cycles(V, I, tol=0.02):
    """依 V 極值切分多圈 CV 封閉曲線
    以數據表第一點為起點：每圈 = 完整循環（起點 → V 往返 → 回到起點電位）
    圈邊界：V 極值（局部最大/最小）——每 2 個極值 = 1 圈
    回傳 list of (V_arr, I_arr)
    """
    V = np.asarray(V, dtype=float)
    I = np.asarray(I, dtype=float)
    cycles = []
    # 找局部極值點（方向反轉）——忽略 dV=0 的接縫點
    dV = np.diff(V)
    reversals = []
    prev_dir = None
    for i in range(len(dV)):
        d = np.sign(dV[i])
        if d == 0:
            continue   # 接縫/平台——跳過但不中斷
        if prev_dir is not None and d != prev_dir:
            reversals.append(i)
        prev_dir = d
    # 極值點 = 反轉點+1（峰）
    extrema = [r + 1 for r in reversals]
    if len(extrema) < 2:
        # 無法切分——整段當一圈
        return [(V, I)]
    # 分類極值：V_max（局部極大）與 V_min（局部極小）
    # 每個極值與前一個比較（第一個與 V[0] 比較）
    types = []
    for i, e in enumerate(extrema):
        prev_v = V[extrema[i-1]] if i > 0 else V[0]
        types.append('max' if V[e] > prev_v else 'min')

    # 半圈切割：起點 + 極值交替 = 半圈邊界
    # 每 2 個半圈 = 1 圈（完整往返）；起點/尾端殘段併入相鄰圈
    segs = [0] + extrema + [len(V) - 1]
    # 合併：每對相鄰半圈成圈（segs[k] → segs[k+2]）
    for k in range(0, len(segs) - 2, 2):
        s, e = segs[k], segs[k+2]
        if e - s > 3:
            cycles.append((V[s:e+1], I[s:e+1]))
    if not cycles:
        cycles = [(V, I)]
    return cycles


# ------------------------------------------------------------------
# ECSA 計算（參考 Pt_ECSA_calculator 方法）
# ------------------------------------------------------------------
def get_linear_intersection(x1, y1, x2, y2, base_y1, base_y2):
    """曲線線段與基準線的交點（Case B/C 穿越）"""
    if x2 == x1:
        return x1, y1
    m1 = (y2 - y1) / (x2 - x1)
    m2 = (base_y2 - base_y1) / (x2 - x1)
    if m1 == m2:
        return x1, y1
    x_cross = (base_y1 - y1 + x1 * (m1 - m2)) / (m1 - m2)
    y_cross = m1 * (x_cross - x1) + y1
    return x_cross, y_cross


def calculate_precise_area(V_arr, I_curve, I_base, direction='up'):
    """曲線與基準線之間的精確面積（Case A/B/C）
    direction='up'：積分曲線在基準線上方（陽極脫附，diff>0）
    direction='down'：積分曲線在基準線下方（陰極吸附，diff<0）
    """
    total_area = 0.0
    V_fill, I_fill_top, I_fill_bot = [], [], []
    for i in range(len(V_arr) - 1):
        x1, x2 = V_arr[i], V_arr[i+1]
        y1, y2 = I_curve[i], I_curve[i+1]
        b1, b2 = I_base[i], I_base[i+1]
        diff1 = y1 - b1
        diff2 = y2 - b2
        if direction == 'down':
            # 陰極：取負 diff（曲線在基準線下方）
            diff1, diff2 = -diff1, -diff2
        if diff1 >= 0 and diff2 >= 0:   # Case A: 全在基準線上
            width = abs(x2 - x1)          # 支援 V 遞減（陰極反掃）
            avg_height = (diff1 + diff2) / 2.0
            total_area += width * avg_height
            V_fill.extend([x1, x2])
            if direction == 'down':
                # 陰極：曲線在基準線下方——top=基準線、bot=曲線（保持 top>bot 數值）
                I_fill_top.extend([b1, b2])
                I_fill_bot.extend([y1, y2])
            else:
                I_fill_top.extend([y1, y2])
                I_fill_bot.extend([b1, b2])
        elif diff1 < 0 and diff2 > 0:   # Case B: 向上穿越
            x_cross, y_cross = get_linear_intersection(x1, y1, x2, y2, b1, b2)
            total_area += 0.5 * abs(x2 - x_cross) * diff2
            V_fill.extend([x_cross, x2])
            if direction == 'down':
                I_fill_top.extend([y_cross, b2])
                I_fill_bot.extend([y_cross, y2])
            else:
                I_fill_top.extend([y_cross, y2])
                I_fill_bot.extend([y_cross, b2])
        elif diff1 > 0 and diff2 < 0:   # Case C: 向下穿越
            x_cross, y_cross = get_linear_intersection(x1, y1, x2, y2, b1, b2)
            total_area += 0.5 * abs(x_cross - x1) * diff1
            V_fill.extend([x1, x_cross])
            if direction == 'down':
                I_fill_top.extend([b1, y_cross])
                I_fill_bot.extend([y1, y_cross])
            else:
                I_fill_top.extend([y1, y_cross])
                I_fill_bot.extend([b1, y_cross])
    return total_area, V_fill, I_fill_top, I_fill_bot


def calc_ecsa(V_curve, I_curve, dl_start, dl_end, h_start, h_end,
              scan_rate, m_pt, area_geom=1.0, q_ref=Q_REF_PT, direction='up'):
    """計算 ECSA（參考 Pt_ECSA_calculator 方法）
    V_curve, I_curve: 陽極（正掃）或陰極（反掃）半圈的 V/I 數據（已含 RHE 換算）
    dl_start, dl_end: 雙電層擬合區（基準線，線性回歸）
    h_start, h_end: 積分區間（H-UPD 區）
    scan_rate: V/s；m_pt: mg/cm²；area_geom: cm²
    direction: 'up'（陽極，曲線在基準線上）/'down'（陰極，曲線在基準線下）
    回傳 dict
    """
    V = np.asarray(V_curve, dtype=float)
    I = np.asarray(I_curve, dtype=float)
    if len(V) < 3:
        return None
    # 1. 雙電層區線性回歸（基準線）
    mask_dl = (V >= dl_start) & (V <= dl_end)
    if mask_dl.sum() < 2:
        return None
    slope, intercept = np.polyfit(V[mask_dl], I[mask_dl], 1)
    if direction == 'down':
        # 陰極：基準線 = 與陽極平行（同 slope），穿過陰極 DL 區最高點
        # 陰極反掃（V 遞減），DL 區為 0.4~0.7V；找該區最高點
        mask_cat = (V >= dl_start) & (V <= dl_end)
        if mask_cat.sum() > 0:
            max_idx = np.argmax(I[mask_cat])
            V_max_cat = V[mask_cat][max_idx]
            I_max_cat = I[mask_cat][max_idx]
            intercept = I_max_cat - slope * V_max_cat   # 平行線截距
        else:
            return None
    # 2. 積分區
    mask_int = (V >= h_start) & (V <= h_end)
    if mask_int.sum() < 2:
        return None
    V_int = V[mask_int]
    I_curve_int = I[mask_int]
    I_base_int = slope * V_int + intercept
    # 3. 精確面積
    area_AV, V_fill, I_fill_top, I_fill_bot = calculate_precise_area(
        V_int, I_curve_int, I_base_int, direction=direction)
    # 4. 物理計算
    charge_uC = (area_AV / scan_rate) * 1e6   # area (A·V) / (V/s) = C → µC
    ecsa_cm2 = charge_uC / q_ref
    ecsa_cm2_per_cm2 = ecsa_cm2 / area_geom if area_geom > 0 else ecsa_cm2
    total_mass_g = (m_pt * area_geom) / 1000.0
    ms_ecsa = (ecsa_cm2 / 10000.0) / total_mass_g if total_mass_g > 0 else 0.0
    return {
        'charge_uC': charge_uC,
        'charge_uC_per_cm2': charge_uC / area_geom if area_geom > 0 else charge_uC,
        'ecsa_cm2': ecsa_cm2,
        'ecsa_cm2_per_cm2': ecsa_cm2_per_cm2,
        'ecsa_m2g': ms_ecsa,
        'baseline_slope': slope,
        'baseline_intercept': intercept,
        'fill_V': np.asarray(V_fill, dtype=float),
        'fill_I_top': np.asarray(I_fill_top, dtype=float),
        'fill_I_bot': np.asarray(I_fill_bot, dtype=float),
        'baseline_V': V, 'baseline_I': slope * V + intercept,
    }
