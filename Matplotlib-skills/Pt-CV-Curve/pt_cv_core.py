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
    邏輯：追蹤 V 的極值（局部最大/最小），完成 V_max→V_min→V_max = 一圈
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
    # 每個極值對（V_max→V_min 或 V_min→V_max）為半圈；兩對 = 一圈
    # 找第一個 V_max（局部極大）作圈起點——從所有極值搜尋（含第 0 個）
    start = 0
    for i in range(len(extrema)):
        prev_v = V[extrema[i-1]] if i > 0 else -np.inf
        next_v = V[extrema[i+1]] if i < len(extrema)-1 else -np.inf
        if V[extrema[i]] > prev_v and V[extrema[i]] > next_v:
            start = i
            break
    # 圈切分：idxs = [起點] + 全部極值 + [數據尾]，每 2 個極值區間成圈
    # 起點前的半圈（數據起點到第一個極值）併入第一圈
    idxs = [0] + extrema + [len(V) - 1]
    for k in range(0, len(idxs) - 2, 2):
        s, e = idxs[k], idxs[k+2]
        if e - s > 3:
            cycles.append((V[s:e+1], I[s:e+1]))
    if not cycles:
        cycles = [(V, I)]
    return cycles


# ------------------------------------------------------------------
# ECSA 計算
# ------------------------------------------------------------------
def calc_ecsa(V_curve, I_curve, V_lo, V_hi, base_v1, base_v2,
              scan_rate, m_pt, area_geom=1.0, q_ref=Q_REF_PT):
    """計算 ECSA
    V_curve, I_curve: 該半圈的 V/I 數據（已含 RHE 換算）
    V_lo, V_hi: 積分區間（H-UPD 區）
    base_v1, base_v2: 雙電層基準線兩端電位
    scan_rate: V/s
    m_pt: mg/cm²
    area_geom: 幾何面積 cm²（載量已含面積則 1）
    回傳 dict(area_charge_uC, ecsa_m2g, fill_V, fill_I_top, fill_I_bot, baseline_V, baseline_I)
    """
    V = np.asarray(V_curve, dtype=float)
    I = np.asarray(I_curve, dtype=float)
    # 篩選積分區間 [V_lo, V_hi]
    mask = (V >= V_lo) & (V <= V_hi)
    if mask.sum() < 3:
        return None
    Vm = V[mask]
    Im = I[mask]
    # 基準線：兩端點 (base_v1, I@base_v1) 與 (base_v2, I@base_v2)
    # 在積分區間內找最接近 base_v1/base_v2 的點
    i1 = np.argmin(np.abs(Vm - base_v1))
    i2 = np.argmin(np.abs(Vm - base_v2))
    if i1 == i2:
        return None
    # 基準線斜率的線性插值（全區間）
    base_slope = (Im[i2] - Im[i1]) / (Vm[i2] - Vm[i1]) if Vm[i2] != Vm[i1] else 0.0
    base_intercept = Im[i1] - base_slope * Vm[i1]
    I_base = base_slope * Vm + base_intercept
    # 梯形積分（曲線 − 基準線）——取絕對值（方向由掃描決定）
    charge = np.trapezoid(np.abs(Im - I_base), Vm)   # A·V = C·(V/s)... 除以掃速得 C
    charge_coul = charge / scan_rate                  # C（電荷）
    charge_uC = charge_coul * 1e6                      # µC
    # ECSA：Q / (Q_ref × m_Pt) → cm² Pt → m²/g
    # Q_ref µC/cm²；m_Pt mg/cm²
    # ECSA_cm2 = Q_uC / Q_ref_uC_per_cm2 = cm² Pt
    # 歸一化幾何面積：ECSA_geo = cm² Pt / cm² geo
    ecsa_cm2 = charge_uC / q_ref
    ecsa_cm2_per_cm2 = ecsa_cm2 / area_geom if area_geom > 0 else ecsa_cm2
    # m²/g：cm² Pt / (m_Pt mg/cm² × area_geom cm²) × (1 g/1000 mg) × (1 m²/10000 cm²)
    m_pt_total_g = m_pt * area_geom / 1000.0          # g
    if m_pt_total_g > 0:
        ecsa_m2g = ecsa_cm2 / m_pt_total_g / 10000.0
    else:
        ecsa_m2g = 0.0
    return {
        'charge_uC': charge_uC,
        'charge_uC_per_cm2': charge_uC / area_geom if area_geom > 0 else charge_uC,
        'ecsa_cm2': ecsa_cm2,
        'ecsa_cm2_per_cm2': ecsa_cm2_per_cm2,
        'ecsa_m2g': ecsa_m2g,
        'fill_V': Vm, 'fill_I_top': Im, 'fill_I_bot': I_base,
        'baseline_V': Vm, 'baseline_I': I_base,
    }
