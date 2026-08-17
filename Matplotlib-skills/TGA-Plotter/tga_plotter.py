#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TGA Plotter — 熱重分析（TGA）數據繪圖 GUI（Tkinter + Matplotlib）

功能：
  1. 解析 NETZSCH 匯出格式（# metadata，自動讀初始重量）+ 通用 CSV
  2. 多檔案疊加（列表管理）
  3. Y 軸 4 種模式：
     A = Δm (mg) 原始質量變化
     B = Weight (%) = (W0 + Δm)/W0 × 100  剩餘重量百分比
     C = 失重 (%) = −Δm/W0 × 100 = 100 − B
     DTG = 導數 d(Weight%)/dX（%/°C 或 %/min）
  4. X 軸可選：溫度 (°C) / 時間
  5. 初始重量：自動讀 metadata + 屬性視窗可手動覆寫
  6. 完整 GUI：列表/↑↓排序/屬性/圖例互動/軸設定/標註/儲存

依賴：pip install matplotlib pandas numpy
"""

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, colorchooser

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


# ------------------------------------------------------------------
# TGA 檔案解析
# ------------------------------------------------------------------
def _read_text(path):
    """嘗試多編碼讀取（NETZSCH 中文 Windows 常是 GBK）"""
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'big5', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read(), 'utf-8'


def parse_tga_file(path):
    """解析 TGA 檔案（NETZSCH 或通用 CSV）
    回傳 (df, initial_weight_mg)
    """
    text, enc = _read_text(path)
    first_line = text.splitlines()[0] if text else ''
    if first_line.startswith('#'):
        # NETZSCH 格式
        meta_weight = None
        for l in text.splitlines():
            if l.startswith('#') and 'Weight:' in l:
                m = re.search(r'Weight:\s*([\d.]+)\s*(\w+)', l)
                if m:
                    val = float(m.group(1))
                    unit = m.group(2).lower()
                    if unit == 'mg':
                        meta_weight = val
                    elif unit == 'g':
                        meta_weight = val * 1000.0
                    elif unit in ('μg', 'ug', 'µg'):
                        meta_weight = val / 1000.0
        df = pd.read_csv(path, comment='#', sep=None, engine='python',
                         encoding=enc)
    else:
        df = pd.read_csv(path, encoding=enc)
        meta_weight = None
    # 清理欄位名（去掉單位括號）
    df.columns = [str(c).strip() for c in df.columns]
    return df, meta_weight


def detect_columns(df):
    """自動偵測欄位：回傳 dict(temp, time, weight) 可能的欄名清單"""
    cols = list(df.columns)
    temp_cols = [c for c in cols if re.search(r'temp|°c|℃|temperature', c, re.I)]
    time_cols = [c for c in cols if re.search(r'time|^t\b|時間', c, re.I)]
    weight_cols = [c for c in cols if re.search(r'weight|mass|delta|mg|重量|質量|weight loss|%', c, re.I)]
    return {'temp': temp_cols, 'time': time_cols, 'weight': weight_cols}


# ------------------------------------------------------------------
# 數據類
# ------------------------------------------------------------------
class TGAData:
    """一組 TGA 數據"""
    def __init__(self, name, df, x_col, weight_col, initial_weight,
                 color, marker_style='o', line_style='-'):
        self.name = name
        self.df = df.copy()
        self.x_col = x_col          # 目前選用的 X 欄（Temperature 或 Time）
        self.weight_col = weight_col
        self.initial_weight = initial_weight  # mg，None 表示未設定
        self.color = color
        self.marker_style = marker_style
        self.line_style = line_style
        # 可能的 X 欄（溫度/時間）
        self.temp_col = None
        self.time_col = None

    def raw_weight(self):
        """原始質量變化 Δm (mg)"""
        return self.df[self.weight_col].astype(float).values

    def weight_pct(self):
        """剩餘重量百分比（B 模式）"""
        raw = self.raw_weight()
        if self.initial_weight and self.initial_weight > 0:
            return (self.initial_weight + raw) / self.initial_weight * 100.0
        return raw  # 無初始重量 → 回傳原始值

    def loss_pct(self):
        """失重百分比（C 模式）"""
        return 100.0 - self.weight_pct()

    def x_values(self):
        return self.df[self.x_col].astype(float).values

    def get_xy(self, mode):
        """依 Y 軸模式回傳 (x, y)"""
        x = self.x_values()
        if mode == 'A':
            return x, self.raw_weight()
        elif mode == 'B':
            return x, self.weight_pct()
        elif mode == 'C':
            return x, self.loss_pct()
        elif mode == 'DTG':
            wp = self.weight_pct()
            dydx = np.gradient(wp, x)
            return x, dydx
        return x, self.raw_weight()


# ------------------------------------------------------------------
# 主視窗
# ------------------------------------------------------------------
class TGAPlotterApp:
    DEFAULT_COLORS = ['#0072B2', '#E69F00', '#56B4E9', '#009E73',
                      '#F0E442', '#CC79A7', '#D55E00']
    AUTO_MARKERS = ['o', 's', '^', 'v', 'D', 'x', '+', '*', 'p', 'h']
    Y_MODES = {
        'A': 'Δm (mg)',
        'B': 'Weight (%)',
        'C': '失重 (%)',
        'DTG': 'DTG (%/°C)',
    }

    def __init__(self, root):
        self.root = root
        self.root.title("TGA Plotter — 熱重分析")
        self.root.geometry("1280x800")

        self.curves = []
        self.annotations = []
        self.font_name = 'Arial'
        self.title_size = 18
        self.tick_size = 18
        self.title_bold = False
        self.legend_dragging = False
        self.legend_selected = False
        self._legend_sel_patches = []
        self._legend_pos_custom = False
        self._drag_anchor = None
        self._legend_cfg = {'fontsize': 12, 'fontname': 'Arial', 'frameon': False}

        self._build_ui()
        self._new_figure()
        self.redraw()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(main, width=340)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left.pack_propagate(False)

        # 數據列表
        tk.Label(left, text="TGA 數據", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, height=6)
        self.listbox.pack(fill=tk.X)
        self.listbox.bind('<<ListboxSelect>>', self._on_list_select)
        bf = tk.Frame(left)
        bf.pack(fill=tk.X, pady=2)
        tk.Button(bf, text="＋ 新增", command=self.add_curve, width=8).pack(side=tk.LEFT)
        tk.Button(bf, text="－ 刪除", command=self.remove_curve, width=8).pack(side=tk.LEFT)
        tk.Button(bf, text="↑", command=lambda: self.move_item(-1), width=3).pack(side=tk.LEFT)
        tk.Button(bf, text="↓", command=lambda: self.move_item(1), width=3).pack(side=tk.LEFT)
        tk.Button(bf, text="✎ 屬性", command=self.edit_props, width=8).pack(side=tk.LEFT)

        # 全域設定
        gf = tk.LabelFrame(left, text="全域設定")
        gf.pack(fill=tk.X, pady=(6, 0))

        def row(parent):
            f = tk.Frame(parent)
            f.pack(fill=tk.X, pady=1)
            return f

        # Y 軸模式 + X 軸
        r0 = row(gf)
        tk.Label(r0, text="Y 軸:").pack(side=tk.LEFT)
        self.ymode_var = tk.StringVar(value="B")
        ym_om = tk.OptionMenu(r0, self.ymode_var, 'A', 'B', 'C', 'DTG',
                              command=lambda _: self.redraw())
        ym_om.config(width=5)
        ym_om.pack(side=tk.LEFT)
        tk.Label(r0, text="X 軸:").pack(side=tk.LEFT, padx=(8, 0))
        self.xaxis_var = tk.StringVar(value="Temperature")
        self.xaxis_menu = tk.OptionMenu(r0, self.xaxis_var, "Temperature",
                                        command=lambda _: self.redraw())
        self.xaxis_menu.config(width=10)
        self.xaxis_menu.pack(side=tk.LEFT)

        # 曲線外觀（兩行）
        r3 = row(gf)
        tk.Label(r3, text="曲線外觀:").pack(side=tk.LEFT, anchor='n')
        ca_f = tk.Frame(r3)
        ca_f.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cf2 = tk.Frame(ca_f)
        cf2.pack(fill=tk.X)
        self.marker_global = tk.BooleanVar(value=True)
        tk.Checkbutton(cf2, text="marker", variable=self.marker_global,
                       command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf2, text="大小").pack(side=tk.LEFT, padx=(6, 0))
        self.marker_size_global = tk.DoubleVar(value=4.0)
        tk.Spinbox(cf2, from_=1, to=20, increment=0.5,
                   textvariable=self.marker_size_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf2, text="線粗").pack(side=tk.LEFT, padx=(6, 0))
        self.line_width_global = tk.DoubleVar(value=1.0)
        tk.Spinbox(cf2, from_=0.5, to=5, increment=0.1,
                   textvariable=self.line_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        cf3 = tk.Frame(ca_f)
        cf3.pack(fill=tk.X, pady=(2, 0))
        tk.Label(cf3, text="框粗").pack(side=tk.LEFT)
        self.spine_width_global = tk.DoubleVar(value=1.1)
        tk.Spinbox(cf3, from_=0.5, to=5, increment=0.1,
                   textvariable=self.spine_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf3, text="tick粗").pack(side=tk.LEFT, padx=(6, 0))
        self.tick_width_global = tk.DoubleVar(value=1.0)
        tk.Spinbox(cf3, from_=0.5, to=3, increment=0.5,
                   textvariable=self.tick_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf3, text="tick長").pack(side=tk.LEFT, padx=(6, 0))
        self.tick_len_global = tk.DoubleVar(value=1.5)
        tk.Spinbox(cf3, from_=0.5, to=3, increment=0.5,
                   textvariable=self.tick_len_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)

        # 字型
        r4 = row(gf)
        tk.Label(r4, text="字型:").pack(side=tk.LEFT)
        self.font_var = tk.StringVar(value='Arial')
        fonts = ['Arial', 'DejaVu Sans', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        font_om = tk.OptionMenu(r4, self.font_var, *fonts, command=lambda _: self._apply_global())
        font_om.config(width=12)
        font_om.pack(side=tk.LEFT)

        # 標題 + 刻度字體
        r5 = row(gf)
        tk.Label(r5, text="標題:").pack(side=tk.LEFT)
        self.title_size_var = tk.IntVar(value=18)
        ts_spin = tk.Spinbox(r5, from_=6, to=40, textvariable=self.title_size_var, width=4,
                             command=self._apply_global)
        ts_spin.pack(side=tk.LEFT)
        ts_spin.bind('<Return>', lambda e: self._apply_global())
        self.title_bold_var = tk.BooleanVar(value=False)
        tk.Checkbutton(r5, text="粗", variable=self.title_bold_var,
                       command=self._apply_global).pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(r5, text="刻度:").pack(side=tk.LEFT, padx=(8, 0))
        self.tick_size_var = tk.IntVar(value=18)
        tk_spin = tk.Spinbox(r5, from_=6, to=40, textvariable=self.tick_size_var, width=4,
                             command=self._apply_global)
        tk_spin.pack(side=tk.LEFT)

        # 圖比例
        r6 = row(gf)
        tk.Label(r6, text="圖比例:").pack(side=tk.LEFT)
        self.fig_ratio_var = tk.StringVar(value="4:3")
        fr_om = tk.OptionMenu(r6, self.fig_ratio_var, '4:3', '16:9', '1:1', '3:2',
                              command=lambda _: self.redraw())
        fr_om.config(width=5)
        fr_om.pack(side=tk.LEFT)

        # ===== 軸設定 =====
        tk.Label(left, text="軸設定（空=自動）", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        axf = tk.Frame(left)
        axf.pack(fill=tk.X)

        def make_axis_row(parent, row_i, label, min_var, max_var, n_var, minor_var, minor_n_var, dir_var):
            tk.Label(parent, text=label).grid(row=row_i, column=0, sticky="w", padx=(0, 2))
            f = tk.Frame(parent)
            f.grid(row=row_i, column=1, sticky="ew")
            tk.Entry(f, textvariable=min_var, width=5).pack(side=tk.LEFT)
            tk.Label(f, text="–").pack(side=tk.LEFT)
            tk.Entry(f, textvariable=max_var, width=5).pack(side=tk.LEFT)
            tk.Label(f, text="刻度數").pack(side=tk.LEFT, padx=(4, 0))
            tk.Entry(f, textvariable=n_var, width=3).pack(side=tk.LEFT)
            tk.Checkbutton(f, text="子", variable=minor_var,
                           command=self.redraw).pack(side=tk.LEFT, padx=(4, 0))
            tk.Label(f, text="子數").pack(side=tk.LEFT)
            tk.Entry(f, textvariable=minor_n_var, width=3).pack(side=tk.LEFT)
            tk.OptionMenu(f, dir_var, '外', '內',
                          command=lambda _: self.redraw()).pack(side=tk.LEFT, padx=(4, 0))
            parent.columnconfigure(1, weight=1)

        self.xmin_var = tk.StringVar(value="")
        self.xmax_var = tk.StringVar(value="")
        self.xn_var = tk.StringVar(value="")
        self.xminor_var = tk.BooleanVar(value=True)
        self.xminor_n_var = tk.StringVar(value="4")
        self.xdir_var = tk.StringVar(value="外")
        self.ymin_var = tk.StringVar(value="")
        self.ymax_var = tk.StringVar(value="")
        self.yn_var = tk.StringVar(value="")
        self.yminor_var = tk.BooleanVar(value=True)
        self.yminor_n_var = tk.StringVar(value="4")
        self.ydir_var = tk.StringVar(value="外")

        make_axis_row(axf, 0, "X:", self.xmin_var, self.xmax_var, self.xn_var, self.xminor_var, self.xminor_n_var, self.xdir_var)
        make_axis_row(axf, 1, "Y:", self.ymin_var, self.ymax_var, self.yn_var, self.yminor_var, self.yminor_n_var, self.ydir_var)
        tk.Button(left, text="套用軸設定", command=self.redraw).pack(fill=tk.X, pady=(2, 0))

        # 標註
        tk.Label(left, text="標註", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        abf = tk.Frame(left)
        abf.pack(fill=tk.X)
        tk.Button(abf, text="＋文字", command=self.add_text_annotation, width=8).pack(side=tk.LEFT)
        tk.Button(abf, text="＋線段", command=self.add_line_annotation, width=8).pack(side=tk.LEFT)
        tk.Button(abf, text="清除", command=self.clear_annotations, width=8).pack(side=tk.LEFT)

        # 輸出
        tk.Label(left, text="輸出", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        obf = tk.Frame(left)
        obf.pack(fill=tk.X)
        tk.Button(obf, text="儲存圖", command=self.save_figure, width=10).pack(side=tk.LEFT)

        self.plot_frame = tk.Frame(main, bg='white')
        self.plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Figure
    # ------------------------------------------------------------------
    def _new_figure(self):
        for w in self.plot_frame.winfo_children():
            w.destroy()
        ratio = getattr(self, 'fig_ratio_var', None)
        r = ratio.get() if ratio else '4:3'
        sizes = {'4:3': (7, 5.25), '16:9': (8, 4.5), '1:1': (6, 6), '3:2': (7.5, 5)}
        w, h = sizes.get(r, (7, 5.25))
        self.fig = plt.Figure(figsize=(w, h), dpi=100)
        self.ax = self.fig.add_subplot(111)
        spine_lw = getattr(self, 'spine_width_global', None)
        for sp in self.ax.spines.values():
            sp.set_linewidth(spine_lw.get() if spine_lw else 1.0)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        w_in, h_in = self.fig.get_size_inches()
        self.canvas.get_tk_widget().config(width=int(w_in * self.fig.dpi),
                                           height=int(h_in * self.fig.dpi))
        self.canvas.get_tk_widget().pack(padx=4, pady=4)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        self.toolbar.update()
        self.canvas.mpl_connect('button_press_event', self._on_legend_press)
        self.canvas.mpl_connect('motion_notify_event', self._on_legend_drag)
        self.canvas.mpl_connect('button_release_event', self._on_legend_release)

    # ------------------------------------------------------------------
    # 上傳
    # ------------------------------------------------------------------
    def _auto_style(self, idx):
        color = self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]
        marker = self.AUTO_MARKERS[idx % len(self.AUTO_MARKERS)]
        return color, marker

    def add_curve(self):
        files = filedialog.askopenfilenames(
            title="選擇 TGA 檔案",
            filetypes=[("TGA/CSV", "*.txt *.csv"), ("所有檔案", "*.*")])
        for f in files:
            try:
                df, meta_weight = parse_tga_file(f)
                if len(df.columns) < 2:
                    messagebox.showerror("格式錯誤", f"{os.path.basename(f)}\n至少需要 2 欄")
                    continue
                name = os.path.splitext(os.path.basename(f))[0]
                info = self._ask_columns(df, name, meta_weight)
                if info is None:
                    continue
                x_col, weight_col, init_w = info
                color, marker = self._auto_style(len(self.curves))
                c = TGAData(name, df, x_col, weight_col, init_w, color, marker_style=marker)
                # 設定 temp/time 欄
                detected = detect_columns(df)
                c.temp_col = detected['temp'][0] if detected['temp'] else x_col
                c.time_col = detected['time'][0] if detected['time'] else None
                self.curves.append(c)
                self._refresh_list()
                self._update_xaxis_menu()
            except Exception as e:
                messagebox.showerror("讀取失敗", f"{f}\n{e}")
        self.redraw()

    def _ask_columns(self, df, fname, meta_weight):
        win = tk.Toplevel(self.root)
        win.title(f"選擇欄位: {fname}")
        win.geometry("420x200")
        win.transient(self.root)
        win.grab_set()
        detected = detect_columns(df)
        cols = list(df.columns)
        tk.Label(win, text=f"檔案: {fname}\n選擇 X 軸與重量欄位:",
                 justify=tk.LEFT).pack(anchor="w", padx=10, pady=6)
        # X 欄（預設溫度）
        default_x = detected['temp'][0] if detected['temp'] else (detected['time'][0] if detected['time'] else cols[0])
        x_var = tk.StringVar(value=default_x)
        f1 = tk.Frame(win); f1.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f1, text="X 軸:").pack(side=tk.LEFT)
        tk.OptionMenu(f1, x_var, *cols).pack(side=tk.LEFT, padx=4)
        # 重量欄
        default_w = detected['weight'][0] if detected['weight'] else (cols[1] if len(cols) > 1 else cols[0])
        w_var = tk.StringVar(value=default_w)
        f2 = tk.Frame(win); f2.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f2, text="重量:").pack(side=tk.LEFT)
        tk.OptionMenu(f2, w_var, *cols).pack(side=tk.LEFT, padx=4)
        # 初始重量
        f3 = tk.Frame(win); f3.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f3, text="初始重量 (mg):").pack(side=tk.LEFT)
        init_var = tk.StringVar(value=f"{meta_weight}" if meta_weight else "")
        tk.Entry(f3, textvariable=init_var, width=10).pack(side=tk.LEFT, padx=4)
        if meta_weight:
            tk.Label(f3, text="(已自動讀取)").pack(side=tk.LEFT)
        else:
            tk.Label(f3, text="(手動輸入)").pack(side=tk.LEFT)
        result = {'v': None}
        def ok():
            try:
                iw = float(init_var.get()) if init_var.get() else None
            except ValueError:
                iw = None
            result['v'] = (x_var.get(), w_var.get(), iw)
            win.destroy()
        def cancel():
            win.destroy()
        bf = tk.Frame(win); bf.pack(pady=8)
        tk.Button(bf, text="確定", command=ok, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="取消", command=cancel, width=10).pack(side=tk.LEFT, padx=5)
        win.wait_window()
        return result['v']

    def remove_curve(self):
        sel = self.listbox.curselection()
        if sel:
            del self.curves[sel[0]]
            self._refresh_list()
            self.redraw()

    def move_item(self, direction):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        new = idx + direction
        if new < 0 or new >= len(self.curves):
            return
        self.curves[idx], self.curves[new] = self.curves[new], self.curves[idx]
        self._reassign_styles()
        self._refresh_list()
        self.listbox.selection_set(new)
        self.redraw()

    def _reassign_styles(self):
        for i, c in enumerate(self.curves):
            color, marker = self._auto_style(i)
            c.color = color
            c.marker_style = marker

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, c in enumerate(self.curves):
            w_txt = f"{c.initial_weight:.1f}mg" if c.initial_weight else "?"
            self.listbox.insert(tk.END, f"{i+1}. {c.name} ({w_txt})")

    def _on_list_select(self, _evt=None):
        pass

    def _update_xaxis_menu(self):
        """更新 X 軸下拉（依已載入數據是否有時間欄）"""
        has_time = any(c.time_col for c in self.curves)
        menu = self.xaxis_menu['menu']
        menu.delete(0, 'end')
        menu.add_command(label="Temperature", command=lambda: self._set_xaxis("Temperature"))
        if has_time:
            menu.add_command(label="Time", command=lambda: self._set_xaxis("Time"))
        self.xaxis_var.set("Temperature")

    def _set_xaxis(self, val):
        self.xaxis_var.set(val)
        # 切換各曲線的 x_col
        for c in self.curves:
            if val == "Time" and c.time_col:
                c.x_col = c.time_col
            elif val == "Temperature" and c.temp_col:
                c.x_col = c.temp_col
        self.redraw()

    # ------------------------------------------------------------------
    # 屬性
    # ------------------------------------------------------------------
    def edit_props(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "請先在列表中選擇一筆數據")
            return
        self._edit_curve_props(sel[0])

    def _edit_curve_props(self, idx):
        c = self.curves[idx]
        win = tk.Toplevel(self.root)
        win.title(f"屬性: {c.name}")
        win.geometry("400x300")
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text=f"數據: {c.name}", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=4)
        # 標籤
        tf = tk.Frame(win); tf.pack(fill=tk.X, padx=8)
        tk.Label(tf, text="圖例標籤:").pack(side=tk.LEFT)
        label_var = tk.StringVar(value=c.name)
        tk.Entry(tf, textvariable=label_var, width=22).pack(side=tk.LEFT)
        def set_label():
            c.name = label_var.get()
            self._refresh_list()
            self.redraw()
        tk.Button(tf, text="套用", command=set_label).pack(side=tk.LEFT, padx=4)
        # 初始重量（可手動覆寫）
        wf = tk.Frame(win); wf.pack(fill=tk.X, padx=8)
        tk.Label(wf, text="初始重量 (mg):").pack(side=tk.LEFT)
        init_var = tk.StringVar(value=f"{c.initial_weight}" if c.initial_weight else "")
        tk.Entry(wf, textvariable=init_var, width=10).pack(side=tk.LEFT, padx=4)
        def set_init():
            try:
                c.initial_weight = float(init_var.get()) if init_var.get() else None
            except ValueError:
                c.initial_weight = None
            self._refresh_list()
            self.redraw()
        tk.Button(wf, text="套用", command=set_init).pack(side=tk.LEFT, padx=4)
        # 顏色
        cf = tk.Frame(win); cf.pack(fill=tk.X, padx=8)
        tk.Label(cf, text="顏色:").pack(side=tk.LEFT)
        color_btn = tk.Button(cf, bg=c.color, width=4,
                              command=lambda: self._pick_color_btn(color_btn, c))
        color_btn.pack(side=tk.LEFT, padx=4)
        # marker 種類
        mf = tk.Frame(win); mf.pack(fill=tk.X, padx=8)
        tk.Label(mf, text="marker:").pack(side=tk.LEFT)
        ms_var = tk.StringVar(value=c.marker_style)
        markers = ['o', 's', '^', 'v', 'D', 'x', '+', '*', 'p', 'h', 'None']
        tk.OptionMenu(mf, ms_var, *markers,
                      command=lambda v: (setattr(c, 'marker_style', v), self.redraw())).pack(side=tk.LEFT, padx=4)
        # 線型
        lf = tk.Frame(win); lf.pack(fill=tk.X, padx=8)
        tk.Label(lf, text="線型:").pack(side=tk.LEFT)
        ls_var = tk.StringVar(value=c.line_style)
        tk.OptionMenu(lf, ls_var, '-', '--', '-.', ':',
                      command=lambda v: (setattr(c, 'line_style', v), self.redraw())).pack(side=tk.LEFT)

    def _pick_color_btn(self, btn, curve):
        rgb, _ = colorchooser.askcolor(color=curve.color, title="選擇顏色")
        if rgb:
            curve.color = '#%02x%02x%02x' % rgb
            btn.config(bg=curve.color)
            self.redraw()

    # ------------------------------------------------------------------
    # 全域
    # ------------------------------------------------------------------
    def _apply_global(self):
        try:
            self.font_name = self.font_var.get()
        except Exception:
            pass
        try:
            self.title_size = int(self.title_size_var.get())
        except (ValueError, tk.TclError):
            pass
        try:
            self.tick_size = int(self.tick_size_var.get())
        except (ValueError, tk.TclError):
            pass
        try:
            self.title_bold = bool(self.title_bold_var.get())
        except Exception:
            pass
        self.redraw()

    # ------------------------------------------------------------------
    # 標註
    # ------------------------------------------------------------------
    def add_text_annotation(self):
        x = simpledialog.askfloat("文字標註", "X 位置:", initialvalue=400.0)
        if x is None: return
        y = simpledialog.askfloat("文字標註", "Y 位置:", initialvalue=50.0)
        if y is None: return
        text = simpledialog.askstring("文字標註", "文字內容:")
        if not text: return
        self.annotations.append(('text', x, y, text, '#000000'))
        self.redraw()

    def add_line_annotation(self):
        x1 = simpledialog.askfloat("線段標註", "起點 X:", initialvalue=200.0)
        if x1 is None: return
        y1 = simpledialog.askfloat("線段標註", "起點 Y:", initialvalue=80.0)
        if y1 is None: return
        x2 = simpledialog.askfloat("線段標註", "終點 X:", initialvalue=600.0)
        if x2 is None: return
        y2 = simpledialog.askfloat("線段標註", "終點 Y:", initialvalue=80.0)
        if y2 is None: return
        self.annotations.append(('line', x1, y1, x2, y2, '#ff0000'))
        self.redraw()

    def clear_annotations(self):
        self.annotations.clear()
        self.redraw()

    # ------------------------------------------------------------------
    # 圖例互動
    # ------------------------------------------------------------------
    def _on_legend_press(self, event):
        if event.inaxes is None: return
        leg = self.ax.get_legend()
        if leg is None: return
        if leg.get_window_extent().contains(event.x, event.y):
            if event.dblclick:
                self._legend_settings()
                return
            self.legend_selected = True
            self._draw_legend_selection(leg)
            self.legend_dragging = True
            self._drag_last = (event.x, event.y)
            leg_win = leg.get_window_extent()
            inv = self.fig.transFigure.inverted()
            fx, fy = inv.transform((leg_win.x0, leg_win.y0))
            self._drag_anchor = (fx, fy)
            self.canvas.get_tk_widget().focus_set()
            self.canvas.get_tk_widget().bind('<KeyPress>', self._on_legend_key_tk)

    def _on_legend_key_tk(self, event):
        if not getattr(self, 'legend_selected', False):
            return
        leg = self.ax.get_legend()
        if leg is None: return
        step = 0.005
        ax, ay = self._drag_anchor
        if event.keysym == 'Left':
            ax -= step
        elif event.keysym == 'Right':
            ax += step
        elif event.keysym == 'Up':
            ay += step
        elif event.keysym == 'Down':
            ay -= step
        else:
            return
        leg.set_bbox_to_anchor((ax, ay), transform=self.fig.transFigure)
        self._drag_anchor = (ax, ay)
        self._legend_pos_custom = True
        self.canvas.draw_idle()

    def _draw_legend_selection(self, leg):
        for p in getattr(self, '_legend_sel_patches', []):
            try:
                p.remove()
            except Exception:
                pass
        self._legend_sel_patches = []
        bb = leg.get_window_extent()
        inv = self.fig.transFigure.inverted()
        (x0, y0) = inv.transform((bb.x0, bb.y0))
        (x1, y1) = inv.transform((bb.x1, bb.y1))
        rect = plt.Rectangle((x0, y0), x1-x0, y1-y0,
                             transform=self.fig.transFigure,
                             fill=False, edgecolor='red', linestyle='--', lw=1.5)
        rect._legend_sel = True
        self.fig.patches.append(rect)
        self._legend_sel_patches.append(rect)
        self.canvas.draw_idle()

    def _legend_settings(self):
        leg = self.ax.get_legend()
        if leg is None: return
        cfg = self._legend_cfg
        win = tk.Toplevel(self.root)
        win.title("圖例設定")
        win.geometry("320x220")
        win.transient(self.root)
        win.grab_set()
        ff = tk.Frame(win); ff.pack(fill=tk.X, padx=10, pady=6)
        frame_var = tk.BooleanVar(value=cfg['frameon'])
        tk.Checkbutton(ff, text="顯示外框", variable=frame_var).pack(side=tk.LEFT)
        sf = tk.Frame(win); sf.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(sf, text="字體大小:").pack(side=tk.LEFT)
        size_var = tk.IntVar(value=cfg['fontsize'])
        tk.Spinbox(sf, from_=6, to=40, textvariable=size_var, width=5).pack(side=tk.LEFT)
        ff2 = tk.Frame(win); ff2.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(ff2, text="字型:").pack(side=tk.LEFT)
        font_var = tk.StringVar(value=cfg['fontname'])
        fonts = ['Arial', 'DejaVu Sans', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(ff2, font_var, *fonts).pack(side=tk.LEFT)
        def apply_settings():
            cfg['fontsize'] = size_var.get()
            cfg['fontname'] = font_var.get()
            cfg['frameon'] = frame_var.get()
            if leg is not None:
                for t in leg.get_texts():
                    t.set_fontsize(cfg['fontsize'])
                    t.set_fontname(cfg['fontname'])
                leg.set_frame_on(cfg['frameon'])
            self.canvas.draw_idle()
            win.destroy()
        bf = tk.Frame(win); bf.pack(pady=10)
        tk.Button(bf, text="套用", command=apply_settings, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="取消", command=win.destroy, width=10).pack(side=tk.LEFT, padx=5)

    def _on_legend_drag(self, event):
        if not self.legend_dragging or event.inaxes is None: return
        leg = self.ax.get_legend()
        if leg is None: return
        last_x, last_y = self._drag_last
        dx = event.x - last_x
        dy = event.y - last_y
        self._drag_last = (event.x, event.y)
        ax, ay = self._drag_anchor
        fig_w = self.fig.bbox.width
        fig_h = self.fig.bbox.height
        if fig_w > 0 and fig_h > 0:
            new_anchor = (ax + dx / fig_w, ay + dy / fig_h)
            leg.set_bbox_to_anchor(new_anchor, transform=self.fig.transFigure)
            self._drag_anchor = new_anchor
            self._legend_pos_custom = True
        self.canvas.draw_idle()

    def _on_legend_release(self, event):
        self.legend_dragging = False
        for p in list(self._legend_sel_patches):
            try:
                p.remove()
            except Exception:
                pass
        self._legend_sel_patches = []
        keep = [p for p in self.fig.patches
                if not getattr(p, '_legend_sel', False)]
        self.fig.patches[:] = keep
        self.canvas.draw()

    # ------------------------------------------------------------------
    # 子刻度
    # ------------------------------------------------------------------
    def _apply_minor(self, axis='x'):
        from matplotlib.ticker import MultipleLocator, FixedLocator, NullLocator
        if axis == 'x':
            enabled = self.xminor_var.get()
            n_str = self.xminor_n_var.get()
            major_ticks = self.ax.get_xticks()
            lim_lo, lim_hi = self.ax.get_xlim()
        else:
            enabled = self.yminor_var.get()
            n_str = self.yminor_n_var.get()
            major_ticks = self.ax.get_yticks()
            lim_lo, lim_hi = self.ax.get_ylim()
        if not enabled:
            if axis == 'x':
                self.ax.xaxis.set_minor_locator(NullLocator())
            else:
                self.ax.yaxis.set_minor_locator(NullLocator())
            return
        try:
            n = int(n_str) if n_str else 4
            n = max(1, min(n, 20))
        except ValueError:
            n = 4
        if len(major_ticks) >= 2:
            major_step = abs(major_ticks[1] - major_ticks[0])
            if major_step > 0:
                step = major_step / (n + 1)
                minor_positions = []
                for mt in major_ticks:
                    for k in range(1, n + 1):
                        p = mt + k * step
                        if lim_lo - 1e-9 <= p <= lim_hi + 1e-9:
                            minor_positions.append(p)
                if axis == 'x':
                    self.ax.xaxis.set_minor_locator(FixedLocator(minor_positions))
                else:
                    self.ax.yaxis.set_minor_locator(FixedLocator(minor_positions))
                return
        lo, hi = lim_lo, lim_hi
        if hi > lo:
            if axis == 'x':
                self.ax.xaxis.set_minor_locator(MultipleLocator((hi - lo) / 50.0))
            else:
                self.ax.yaxis.set_minor_locator(MultipleLocator((hi - lo) / 50.0))

    # ------------------------------------------------------------------
    # 繪圖
    # ------------------------------------------------------------------
    def redraw(self):
        sizes = {'4:3': (7, 5.25), '16:9': (8, 4.5), '1:1': (6, 6), '3:2': (7.5, 5)}
        r = self.fig_ratio_var.get() if hasattr(self, 'fig_ratio_var') else '4:3'
        target = sizes.get(r, (7, 5.25))
        if self.fig.get_size_inches()[0] != target[0] or self.fig.get_size_inches()[1] != target[1]:
            self._new_figure()
        self.ax.clear()
        self._legend_sel_patches = [
            p for p in self._legend_sel_patches if p in self.fig.patches]
        for p in self._legend_sel_patches:
            try:
                p.remove()
            except Exception:
                pass
        self._legend_sel_patches = []
        self.fig.patches[:] = [p for p in self.fig.patches
                               if not getattr(p, '_legend_sel', False)]
        spine_lw = self.spine_width_global.get()
        for sp in self.ax.spines.values():
            sp.set_linewidth(spine_lw)

        ymode = self.ymode_var.get()
        for c in self.curves:
            x, y = c.get_xy(ymode)
            marker = c.marker_style if (self.marker_global.get()
                                        and c.marker_style != 'None') else None
            self.ax.plot(x, y, label=c.name,
                         color=c.color, linestyle=c.line_style,
                         marker=marker, markersize=self.marker_size_global.get(),
                         linewidth=self.line_width_global.get())

        # 標註
        for a in self.annotations:
            if a[0] == 'text':
                _, x, y, text, color = a
                self.ax.annotate(text, (x, y), color=color,
                                 fontsize=self.title_size - 1, fontname=self.font_name)
            elif a[0] == 'line':
                _, x1, y1, x2, y2, color = a
                self.ax.plot([x1, x2], [y1, y2], color=color, lw=1.5)

        # 版面
        fw = 'bold' if self.title_bold else 'normal'
        xlabel = "Temperature (°C)" if self.xaxis_var.get() == "Temperature" else "Time (s)"
        ylabel = self.Y_MODES.get(ymode, 'Weight (%)')
        self.ax.set_xlabel(xlabel, fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        self.ax.set_ylabel(ylabel, fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        self.ax.tick_params(labelsize=self.tick_size)
        xdir = 'in' if self.xdir_var.get() == '內' else 'out'
        ydir = 'in' if self.ydir_var.get() == '內' else 'out'
        tw = self.tick_width_global.get()
        tl = self.tick_len_global.get()
        self.ax.tick_params(axis='x', which='both', direction=xdir, width=tw, length=3.5*tl)
        self.ax.tick_params(axis='y', which='both', direction=ydir, width=tw, length=3.5*tl)
        self.ax.tick_params(axis='x', which='minor', length=2.1*tl)
        self.ax.tick_params(axis='y', which='minor', length=2.1*tl)

        # 軸範圍
        if self.curves:
            self.ax.relim()
            self.ax.autoscale()
            try:
                if self.xmin_var.get() or self.xmax_var.get():
                    xmin = float(self.xmin_var.get()) if self.xmin_var.get() else None
                    xmax = float(self.xmax_var.get()) if self.xmax_var.get() else None
                    self.ax.set_xlim(xmin, xmax)
            except ValueError:
                pass
            try:
                if self.ymin_var.get() or self.ymax_var.get():
                    ymin = float(self.ymin_var.get()) if self.ymin_var.get() else None
                    ymax = float(self.ymax_var.get()) if self.ymax_var.get() else None
                    self.ax.set_ylim(ymin, ymax)
            except ValueError:
                pass
            try:
                if self.xn_var.get():
                    n = int(self.xn_var.get())
                    if n > 1:
                        lo, hi = self.ax.get_xlim()
                        self.ax.set_xticks(np.linspace(lo, hi, n))
            except ValueError:
                pass
            self._apply_minor('x')
            try:
                if self.yn_var.get():
                    n = int(self.yn_var.get())
                    if n > 1:
                        lo, hi = self.ax.get_ylim()
                        self.ax.set_yticks(np.linspace(lo, hi, n))
            except ValueError:
                pass
            self._apply_minor('y')

        # 圖例
        if self.curves:
            cfg = self._legend_cfg
            leg = self.ax.legend(loc='upper right',
                                 frameon=cfg['frameon'],
                                 fontsize=cfg['fontsize'],
                                 prop={'family': cfg['fontname'],
                                       'size': cfg['fontsize']})
            handles = getattr(leg, 'legend_handles', None) or getattr(leg, 'legendHandles', None)
            if handles:
                for i, c in enumerate(self.curves):
                    try:
                        handle = handles[i]
                        handle.set_linestyle(c.line_style)
                        handle.set_linewidth(self.line_width_global.get())
                        marker = c.marker_style if (self.marker_global.get()
                                                    and c.marker_style != 'None') else None
                        handle.set_marker(marker)
                        handle.set_markersize(self.marker_size_global.get())
                    except Exception:
                        pass
            if getattr(self, '_legend_pos_custom', False) and self._drag_anchor is not None:
                leg.set_bbox_to_anchor(self._drag_anchor, transform=self.fig.transFigure)
            leg.set_draggable(True)
            self._legend = leg

        for lbl in self.ax.get_xticklabels() + self.ax.get_yticklabels():
            lbl.set_fontname(self.font_name)

        self.fig.tight_layout()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # 輸出
    # ------------------------------------------------------------------
    def save_figure(self):
        dpi = simpledialog.askinteger("儲存", "DPI（建議 300）:", initialvalue=300, minvalue=50, maxvalue=1200)
        if dpi is None:
            dpi = 300
        f = filedialog.asksaveasfilename(
            title="儲存圖檔", defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("SVG", "*.svg"), ("PDF", "*.pdf")])
        if not f:
            return
        try:
            self.fig.savefig(f, dpi=dpi, bbox_inches='tight')
            messagebox.showinfo("完成", f"已儲存:\n{f}")
        except Exception as e:
            messagebox.showerror("儲存失敗", str(e))


def main():
    root = tk.Tk()
    app = TGAPlotterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
