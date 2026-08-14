#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Nyquist Plotter — EIS Nyquist 圖繪圖 GUI（Tkinter + Matplotlib）

功能：
  1. 解析 DRTxECM 匯出 CSV（ECM 參數表 + 頻率響應數據塊）自動擷取：
     - raw 數據（Z_raw_prime, Z_raw_double_prime）→ 純 marker
     - fitted 數據（Total_Fitted_Z_prime, Total_Fitted_Z_double_prime）→ 純實線
  2. 也支援標準 EIS CSV（f, Z', Z''）——上傳時手動指定欄位
  3. Nyquist 慣例：X = Z′ (Ω)，Y = −Z″ (Ω)（電弧朝上）
  4. X/Y 軸同比例鎖定（set_aspect('equal')，Nyquist 物理正確）——可切換
  5. 完整 GUI：多檔案列表、↑↓排序、屬性（顏色/線型/marker 種類）、圖例拖曳+鍵盤微調+雙擊設定、軸設定（範圍/刻度/子刻度/方向）

適用：EIS 阻抗譜分析（燃料電池、電解器、電池等）

依賴：pip install matplotlib pandas numpy
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
# 數據類
# ------------------------------------------------------------------
class NyquistData:
    """一組 EIS 數據（raw + fitted 兩條曲線）"""
    def __init__(self, name, df, z_col, zpp_col,
                 color, has_fitted=False,
                 marker_on=True, marker_style='o', marker_size=7,
                 line_style='-', line_width=2.0,
                 fitted_marker_style='o', fitted_line_style='-'):
        self.name = name
        self.df = df.copy()          # 原始 DataFrame
        self.z_col = z_col           # Z' 欄位
        self.zpp_col = zpp_col       # Z'' 欄位
        self.color = color
        self.has_fitted = has_fitted  # 是否有 fitted 數據
        self.marker_on = marker_on    # raw 用 marker（預設開）
        self.marker_style = marker_style
        self.marker_size = marker_size
        self.line_style = line_style  # raw 附加線型（預設 None → 純 marker）
        self.line_width = line_width
        self.fitted_marker_style = fitted_marker_style  # fitted marker（預設 None → 純線）
        self.fitted_line_style = fitted_line_style      # fitted 線型（預設實線）

    def _nyquist_y(self, zpp):
        """Nyquist Y 座標：自動偵測符號慣例
        - 若 Z'' 中位數 > 0（檔案已取負慣例）→ 直接使用
        - 若 Z'' 中位數 < 0（標準電化學慣例）→ 取負使電弧朝上
        """
        arr = np.asarray(zpp, dtype=float)
        if len(arr) == 0:
            return arr
        if np.median(arr) > 0:
            return arr
        return -arr

    def get_raw_xy(self):
        """raw Nyquist：X=Z', Y=−Z''（自動符號）"""
        z = self.df[self.z_col].astype(float).values
        zpp = self.df[self.zpp_col].astype(float).values
        return z, self._nyquist_y(zpp)

    def get_fitted_xy(self):
        """fitted Nyquist：X=Z', Y=−Z''（自動符號）"""
        if not self.has_fitted:
            return None
        fz = self.df['fitted_z_prime'].astype(float).values
        fzpp = self.df['fitted_z_double_prime'].astype(float).values
        return fz, self._nyquist_y(fzpp)


# ------------------------------------------------------------------
# 主視窗
# ------------------------------------------------------------------
class NyquistPlotterApp:
    # Okabe-Ito 色盲友善配色（科學標準，7 色）
    DEFAULT_COLORS = ['#0072B2', '#E69F00', '#56B4E9', '#009E73',
                      '#F0E442', '#CC79A7', '#D55E00']
    # 自動配色/配 marker：依序循環不重複（7 色 × 10 marker = 70 組合）
    AUTO_MARKERS = ['o', 's', '^', 'v', 'D', 'x', '+', '*', 'p', 'h']

    def __init__(self, root):
        self.root = root
        self.root.title("Nyquist Plotter — EIS Nyquist 圖")
        self.root.geometry("1280x800")

        self.curves = []          # list[NyquistData]
        self.annotations = []     # list[(type, ...)]
        self.font_name = 'Arial'
        self.title_size = 18
        self.tick_size = 18
        self.title_bold = False
        self.legend_dragging = False
        self.legend_selected = False
        self._legend_sel_patches = []
        self._legend_pos_custom = False
        self._drag_anchor = None
        self.aspect_equal = True   # X/Y 同比例鎖定（預設開）

        self._build_ui()
        self._new_figure()
        self.redraw()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True)

        # 左側控制
        left = tk.Frame(main, width=320)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left.pack_propagate(False)

        # 數據列表
        tk.Label(left, text="EIS 數據", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, height=8)
        self.listbox.pack(fill=tk.X)
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

        # 同比例鎖定
        tk.Label(gf, text="軸同比例:").grid(row=0, column=0, sticky="w")
        self.aspect_var = tk.BooleanVar(value=True)
        tk.Checkbutton(gf, text="(Nyquist 慣例)", variable=self.aspect_var,
                       command=self.redraw).grid(row=0, column=1, sticky="w")

        # 曲線外觀（全域統一）——上下兩行放同一容器
        tk.Label(gf, text="曲線外觀:").grid(row=1, column=0, sticky="nw")
        ca_f = tk.Frame(gf)
        ca_f.grid(row=1, column=1, sticky="ew")
        # 第 1 行
        cf2 = tk.Frame(ca_f)
        cf2.pack(fill=tk.X)
        self.marker_global = tk.BooleanVar(value=True)
        tk.Checkbutton(cf2, text="marker", variable=self.marker_global,
                       command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf2, text="大小").pack(side=tk.LEFT, padx=(6, 0))
        self.marker_size_global = tk.DoubleVar(value=7.0)
        tk.Spinbox(cf2, from_=1, to=20, increment=0.5,
                   textvariable=self.marker_size_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf2, text="線粗").pack(side=tk.LEFT, padx=(6, 0))
        self.line_width_global = tk.DoubleVar(value=2.0)
        tk.Spinbox(cf2, from_=0.5, to=5, increment=0.1,
                   textvariable=self.line_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        # 第 2 行（框粗/tick粗/tick長）
        cf3 = tk.Frame(ca_f)
        cf3.pack(fill=tk.X, pady=(2, 0))
        tk.Label(cf3, text="框粗").pack(side=tk.LEFT, padx=(0, 0))
        self.spine_width_global = tk.DoubleVar(value=1.0)
        tk.Spinbox(cf3, from_=0.5, to=5, increment=0.1,
                   textvariable=self.spine_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf3, text="tick粗").pack(side=tk.LEFT, padx=(6, 0))
        self.tick_width_global = tk.DoubleVar(value=1.0)
        tk.Spinbox(cf3, from_=0.5, to=3, increment=0.5,
                   textvariable=self.tick_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf3, text="tick長").pack(side=tk.LEFT, padx=(6, 0))
        self.tick_len_global = tk.DoubleVar(value=1.0)
        tk.Spinbox(cf3, from_=0.5, to=3, increment=0.5,
                   textvariable=self.tick_len_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)

        # 字型
        tk.Label(gf, text="字型:").grid(row=2, column=0, sticky="w")
        self.font_var = tk.StringVar(value='Arial')
        fonts = ['Arial', 'DejaVu Sans', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(gf, self.font_var, *fonts, command=lambda _: self._apply_global()).grid(row=2, column=1, sticky="ew")

        # 字體大小（標題 + 刻度同列）
        tk.Label(gf, text="標題字體:").grid(row=3, column=0, sticky="w")
        fs_f = tk.Frame(gf)
        fs_f.grid(row=3, column=1, sticky="ew")
        self.title_size_var = tk.IntVar(value=18)
        ts_spin = tk.Spinbox(fs_f, from_=6, to=40, textvariable=self.title_size_var, width=4,
                             command=self._apply_global)
        ts_spin.pack(side=tk.LEFT)
        ts_spin.bind('<Return>', lambda e: self._apply_global())
        ts_spin.bind('<FocusOut>', lambda e: self._apply_global())
        self.title_bold_var = tk.BooleanVar(value=False)
        tk.Checkbutton(fs_f, text="粗體", variable=self.title_bold_var,
                       command=self._apply_global).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(fs_f, text="刻度:").pack(side=tk.LEFT, padx=(8, 0))
        self.tick_size_var = tk.IntVar(value=18)
        tk_spin = tk.Spinbox(fs_f, from_=6, to=40, textvariable=self.tick_size_var, width=4,
                             command=self._apply_global)
        tk_spin.pack(side=tk.LEFT)
        tk_spin.bind('<Return>', lambda e: self._apply_global())
        tk_spin.bind('<FocusOut>', lambda e: self._apply_global())

        # 圖比例
        tk.Label(gf, text="圖比例:").grid(row=4, column=0, sticky="w")
        self.fig_ratio_var = tk.StringVar(value="4:3")
        tk.OptionMenu(gf, self.fig_ratio_var, '4:3', '16:9', '1:1', '3:2',
                      command=lambda _: self.redraw()).grid(row=4, column=1, sticky="ew")

        # ===== 軸設定 =====
        tk.Label(left, text="軸設定（空=自動）", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        axf = tk.Frame(left)
        axf.pack(fill=tk.X)

        def make_axis_row(parent, row, label, min_var, max_var, n_var, minor_var, minor_n_var, dir_var):
            tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 2))
            f = tk.Frame(parent)
            f.grid(row=row, column=1, sticky="ew")
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
        tk.Button(obf, text="匯出 CSV", command=self.export_csv, width=10).pack(side=tk.LEFT)

        # 右側繪圖區
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
        # 圖框線粗
        lw = getattr(self, 'spine_width_global', None)
        spine_lw = lw.get() if lw else 1.0
        for sp in self.ax.spines.values():
            sp.set_linewidth(spine_lw)
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
    # EIS 檔案解析
    # ------------------------------------------------------------------
    @staticmethod
    def parse_drtxecm_csv(path):
        """解析 DRTxECM 匯出 CSV——回傳 (df, has_fitted) 或 None
        格式：開頭 ECM 參數表，遇 'Merged Frequency Response' 後讀數據塊
        """
        try:
            with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
                lines = f.readlines()
        except Exception:
            with open(path, 'r', errors='replace') as f:
                lines = f.readlines()

        # 找數據塊 header 行（含 'Frequency' 且含 'Z_raw'）
        header_idx = None
        for i, ln in enumerate(lines):
            if 'Frequency' in ln and 'Z_raw' in ln:
                header_idx = i
                break
        if header_idx is None:
            return None

        # 解析 header 欄位
        header = [c.strip() for c in lines[header_idx].strip().split(',')]
        data_lines = []
        for ln in lines[header_idx + 1:]:
            ln = ln.strip()
            if not ln or ln.startswith('---'):
                continue
            data_lines.append(ln)

        import io
        df = pd.read_csv(io.StringIO('\n'.join(data_lines)), header=None,
                         names=header, skipinitialspace=True)
        # 欄位清理（去掉單位括號與空格）
        df.columns = [c.split('(')[0].strip().replace(' ', '_') for c in df.columns]
        # 確認必要欄位
        has_fitted = 'Total_Fitted_Z_prime' in df.columns
        return df, has_fitted

    # ------------------------------------------------------------------
    # 上傳
    # ------------------------------------------------------------------
    def _auto_style(self, idx):
        color = self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]
        marker = self.AUTO_MARKERS[idx % len(self.AUTO_MARKERS)]
        return color, marker

    def add_curve(self):
        files = filedialog.askopenfilenames(
            title="選擇 EIS CSV",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                parsed = self.parse_drtxecm_csv(f)
                name = os.path.splitext(os.path.basename(f))[0]
                if parsed is not None:
                    df, has_fitted = parsed
                    z_col = 'Z_raw_prime' if 'Z_raw_prime' in df.columns else df.columns[1]
                    zpp_col = 'Z_raw_double_prime' if 'Z_raw_double_prime' in df.columns else df.columns[2]
                    color, marker = self._auto_style(len(self.curves))
                    c = NyquistData(name, df, z_col, zpp_col, color,
                                    has_fitted=has_fitted, marker_style=marker)
                    # fitted 欄位名稱
                    if has_fitted:
                        c.df['fitted_z_prime'] = df['Total_Fitted_Z_prime'].astype(float)
                        c.df['fitted_z_double_prime'] = df['Total_Fitted_Z_double_prime'].astype(float)
                    self.curves.append(c)
                else:
                    # 標準 EIS CSV——彈窗選欄位
                    df = pd.read_csv(f)
                    info = self._ask_columns(df, name)
                    if info is None:
                        continue
                    z_col, zpp_col = info
                    color, marker = self._auto_style(len(self.curves))
                    self.curves.append(NyquistData(
                        name, df, z_col, zpp_col, color,
                        has_fitted=False, marker_style=marker))
                self._refresh_list()
            except Exception as e:
                messagebox.showerror("讀取失敗", f"{f}\n{e}")
        self.redraw()

    def _ask_columns(self, df, fname):
        """標準 CSV：彈窗選 Z' 欄與 Z'' 欄"""
        win = tk.Toplevel(self.root)
        win.title(f"選擇欄位: {fname}")
        win.geometry("380x180")
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=f"檔案: {fname}\n選擇 Z′（實部）與 Z″（虛部）欄位:",
                 justify=tk.LEFT).pack(anchor="w", padx=10, pady=6)

        cols = list(df.columns)
        z_var = tk.StringVar(value=cols[0] if cols else "")
        zpp_var = tk.StringVar(value=cols[1] if len(cols) > 1 else (cols[0] if cols else ""))

        f1 = tk.Frame(win); f1.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f1, text="Z′ 欄位:").pack(side=tk.LEFT)
        tk.OptionMenu(f1, z_var, *cols).pack(side=tk.LEFT, padx=4)
        f2 = tk.Frame(win); f2.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f2, text="Z″ 欄位:").pack(side=tk.LEFT)
        tk.OptionMenu(f2, zpp_var, *cols).pack(side=tk.LEFT, padx=4)

        result = {'v': None}
        def ok():
            result['v'] = (z_var.get(), zpp_var.get())
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
            tag = " (R+F)" if c.has_fitted else ""
            self.listbox.insert(tk.END, f"{i+1}. {c.name}{tag}")

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
        win.geometry("420x400")
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=f"數據: {c.name}（Z′: {c.z_col}, Z″: {c.zpp_col}）",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=4)

        # 自訂標籤
        tf = tk.Frame(win); tf.pack(fill=tk.X, padx=8)
        tk.Label(tf, text="圖例標籤:").pack(side=tk.LEFT)
        label_var = tk.StringVar(value=c.name)
        tk.Entry(tf, textvariable=label_var, width=22).pack(side=tk.LEFT)
        def set_label():
            c.name = label_var.get()
            self._refresh_list()
            self.redraw()
        tk.Button(tf, text="套用", command=set_label).pack(side=tk.LEFT, padx=4)

        # 顏色
        cf = tk.Frame(win); cf.pack(fill=tk.X, padx=8)
        tk.Label(cf, text="顏色:").pack(side=tk.LEFT)
        color_btn = tk.Button(cf, bg=c.color, width=4,
                              command=lambda: self._pick_color_btn(color_btn, c))
        color_btn.pack(side=tk.LEFT, padx=4)

        # raw marker 種類（區分數據用）
        mf = tk.Frame(win); mf.pack(fill=tk.X, padx=8)
        tk.Label(mf, text="raw marker:").pack(side=tk.LEFT)
        ms_var = tk.StringVar(value=c.marker_style)
        markers = ['o', 's', '^', 'v', 'D', 'x', '+', '*', 'p', 'h', 'None']
        tk.OptionMenu(mf, ms_var, *markers,
                      command=lambda v: (setattr(c, 'marker_style', v), self.redraw())).pack(side=tk.LEFT, padx=4)

        # fitted 線型
        lf = tk.Frame(win); lf.pack(fill=tk.X, padx=8)
        tk.Label(lf, text="fitted 線型:").pack(side=tk.LEFT)
        fl_var = tk.StringVar(value=c.fitted_line_style)
        tk.OptionMenu(lf, fl_var, '-', '--', '-.', ':',
                      command=lambda v: (setattr(c, 'fitted_line_style', v), self.redraw())).pack(side=tk.LEFT)

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
        x = simpledialog.askfloat("文字標註", "X 位置:", initialvalue=0.5)
        if x is None: return
        y = simpledialog.askfloat("文字標註", "Y 位置:", initialvalue=0.7)
        if y is None: return
        text = simpledialog.askstring("文字標註", "文字內容:")
        if not text: return
        self.annotations.append(('text', x, y, text, '#000000'))
        self.redraw()

    def add_line_annotation(self):
        x1 = simpledialog.askfloat("線段標註", "起點 X:", initialvalue=0.3)
        if x1 is None: return
        y1 = simpledialog.askfloat("線段標註", "起點 Y:", initialvalue=0.8)
        if y1 is None: return
        x2 = simpledialog.askfloat("線段標註", "終點 X:", initialvalue=0.5)
        if x2 is None: return
        y2 = simpledialog.askfloat("線段標註", "終點 Y:", initialvalue=0.8)
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
        win = tk.Toplevel(self.root)
        win.title("圖例設定")
        win.geometry("320x220")
        win.transient(self.root)
        win.grab_set()
        ff = tk.Frame(win); ff.pack(fill=tk.X, padx=10, pady=6)
        frame_var = tk.BooleanVar(value=leg.get_frame_on())
        tk.Checkbutton(ff, text="顯示外框", variable=frame_var,
                       command=lambda: (leg.set_frame_on(frame_var.get()),
                                        self.canvas.draw_idle())).pack(side=tk.LEFT)
        sf = tk.Frame(win); sf.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(sf, text="字體大小:").pack(side=tk.LEFT)
        size_var = tk.IntVar(value=int(leg.get_texts()[0].get_fontsize()) if leg.get_texts() else 14)
        tk.Spinbox(sf, from_=6, to=40, textvariable=size_var, width=5).pack(side=tk.LEFT)
        ff2 = tk.Frame(win); ff2.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(ff2, text="字型:").pack(side=tk.LEFT)
        font_var = tk.StringVar(value=leg.get_texts()[0].get_fontname() if leg.get_texts() else 'Arial')
        fonts = ['Arial', 'DejaVu Sans', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(ff2, font_var, *fonts).pack(side=tk.LEFT)
        def apply_settings():
            for t in leg.get_texts():
                t.set_fontsize(size_var.get())
                t.set_fontname(font_var.get())
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
        from matplotlib.ticker import MultipleLocator
        if axis == 'x':
            ax = self.ax
            enabled = self.xminor_var.get()
            n_str = self.xminor_n_var.get()
            set_loc = ax.xaxis.set_minor_locator
            major_ticks = ax.get_xticks()
        else:
            ax = self.ax
            enabled = self.yminor_var.get()
            n_str = self.yminor_n_var.get()
            set_loc = ax.yaxis.set_minor_locator
            major_ticks = ax.get_yticks()
        if not enabled:
            ax.minorticks_off()
            return
        try:
            n = int(n_str) if n_str else 4
            n = max(1, min(n, 20))
        except ValueError:
            n = 4
        ax.minorticks_on()
        if len(major_ticks) >= 2:
            major_step = abs(major_ticks[1] - major_ticks[0])
            if major_step > 0:
                set_loc(MultipleLocator(major_step / (n + 1)))
                return
        lo, hi = ax.get_xlim() if axis == 'x' else ax.get_ylim()
        if hi > lo:
            set_loc(MultipleLocator((hi - lo) / 50.0))

    # ------------------------------------------------------------------
    # 繪圖
    # ------------------------------------------------------------------
    def redraw(self):
        # 圖比例變更時重建 figure
        sizes = {'4:3': (7, 5.25), '16:9': (8, 4.5), '1:1': (6, 6), '3:2': (7.5, 5)}
        r = self.fig_ratio_var.get() if hasattr(self, 'fig_ratio_var') else '4:3'
        target = sizes.get(r, (7, 5.25))
        if self.fig.get_size_inches()[0] != target[0] or self.fig.get_size_inches()[1] != target[1]:
            self._new_figure()
        self.ax.clear()
        # 清除殘留的圖例選取框
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
        # 圖框線粗
        spine_lw = self.spine_width_global.get()
        for sp in self.ax.spines.values():
            sp.set_linewidth(spine_lw)

        # 繪製各數據
        for c in self.curves:
            z, neg_zpp = c.get_raw_xy()
            # raw：預設純 marker（無線）
            marker = c.marker_style if (self.marker_global.get()
                                        and c.marker_style != 'None') else None
            self.ax.plot(z, neg_zpp, label=f"{c.name} (raw)",
                         color=c.color, linestyle='None',
                         marker=marker, markersize=self.marker_size_global.get(),
                         linewidth=self.line_width_global.get())
            # fitted：預設純實線（無 marker）
            if c.has_fitted:
                fz, fneg = c.get_fitted_xy()
                self.ax.plot(fz, fneg, label=f"{c.name} (fit)",
                             color=c.color, linestyle=c.fitted_line_style,
                             linewidth=self.line_width_global.get(), alpha=0.8)

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
        self.ax.set_xlabel("Z′ (Ω)", fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        self.ax.set_ylabel("−Z″ (Ω)", fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        self.ax.tick_params(labelsize=self.tick_size)
        # tick 方向 + 粗細/長度
        xdir = 'in' if self.xdir_var.get() == '內' else 'out'
        ydir = 'in' if self.ydir_var.get() == '內' else 'out'
        tw = self.tick_width_global.get()
        tl = self.tick_len_global.get()
        self.ax.tick_params(axis='x', which='both', direction=xdir,
                            width=tw, length=3.5*tl)
        self.ax.tick_params(axis='y', which='both', direction=ydir,
                            width=tw, length=3.5*tl)
        self.ax.tick_params(axis='x', which='minor', length=2.1*tl)
        self.ax.tick_params(axis='y', which='minor', length=2.1*tl)

        # 軸範圍：預設 auto scale
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
            # X 軸刻度數量
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
            # X/Y 同比例鎖定（Nyquist 慣例）
            if self.aspect_var.get():
                self.ax.set_aspect('equal', adjustable='box')
            else:
                self.ax.set_aspect('auto')

        # 圖例
        if self.curves:
            leg = self.ax.legend(loc='upper right', frameon=True,
                                 fontsize=14, prop={'family': 'Arial'})
            if getattr(self, '_legend_pos_custom', False) and self._drag_anchor is not None:
                leg.set_bbox_to_anchor(self._drag_anchor, transform=self.fig.transFigure)
            leg.set_draggable(True)
            self._legend = leg

        # 刻度字體
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

    def export_csv(self):
        """匯出合併 CSV（f, Z'_raw, -Z''_raw, Z'_fit, -Z''_fit, label）"""
        if not self.curves:
            messagebox.showinfo("提示", "無數據可匯出")
            return
        f = filedialog.asksaveasfilename(
            title="匯出 CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not f:
            return
        rows = []
        for c in self.curves:
            z, nz = c.get_raw_xy()
            freq = c.df['Frequency'].astype(float).values if 'Frequency' in c.df.columns else np.arange(len(z))
            for i in range(len(z)):
                row = {'label': c.name, 'freq': freq[i],
                       'Z_raw_prime': z[i], 'neg_Z_raw_double_prime': nz[i]}
                if c.has_fitted:
                    fz, fnz = c.get_fitted_xy()
                    row['Z_fit_prime'] = fz[i] if i < len(fz) else np.nan
                    row['neg_Z_fit_double_prime'] = fnz[i] if i < len(fnz) else np.nan
                rows.append(row)
        out = pd.DataFrame(rows)
        out.to_csv(f, index=False)
        messagebox.showinfo("完成", f"已匯出:\n{f}")


def main():
    root = tk.Tk()
    app = NyquistPlotterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
