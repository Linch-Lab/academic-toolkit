#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pt CV Curve Plotter — Pt 電催化 CV 曲線繪圖 + ECSA 計算 GUI（Tkinter + Matplotlib）

功能：
  1. CV 數據載入（手動指定 V/I 欄位），自動切分多圈封閉曲線
  2. 圈選擇下拉：顯示圈 = 計算圈
  3. X 軸電位參考切換：vs RHE / vs 參考電極（電解質 E0 換算）
  4. Y 軸電流單位切換（A / mA / µA）
  5. ECSA 計算彈窗：陰極吸附/陽極脫附勾選、積分區間與基準線輸入、
     內嵌小圖確認、輸出 ECSA (m²/g Pt)
  6. 完整 GUI：列表/屬性/圖例互動/軸設定/儲存

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

from pt_cv_core import split_cycles, calc_ecsa, Q_REF_PT

# ------------------------------------------------------------------
# 數據類
# ------------------------------------------------------------------
class CVData:
    """一組 CV 數據（含多圈）"""
    def __init__(self, name, df, v_col, i_col, color,
                 marker_style='o', line_style='-'):
        self.name = name
        self.df = df.copy()
        self.v_col = v_col
        self.i_col = i_col
        self.color = color
        self.marker_style = marker_style
        self.line_style = line_style
        # 自動切分多圈
        self.cycles = split_cycles(df[v_col].values, df[i_col].values)
        self.selected_cycle = 0   # 顯示/計算圈索引

    def get_cycle(self, idx=None):
        idx = self.selected_cycle if idx is None else idx
        if idx < len(self.cycles):
            return self.cycles[idx]
        return self.cycles[0]

    @property
    def n_cycles(self):
        return len(self.cycles)


# ------------------------------------------------------------------
# 主視窗
# ------------------------------------------------------------------
class PtCVPlotterApp:
    DEFAULT_COLORS = ['#0072B2', '#E69F00', '#56B4E9', '#009E73',
                      '#F0E442', '#CC79A7', '#D55E00']
    AUTO_MARKERS = ['o', 's', '^', 'v', 'D', 'x', '+', '*', 'p', 'h']
    CURRENT_UNITS = {'A': 1.0, 'mA': 1e-3, 'µA': 1e-6}

    def __init__(self, root):
        self.root = root
        self.root.title("Pt CV Curve Plotter — CV 曲線 + ECSA")
        self.root.geometry("1280x800")

        self.curves = []          # list[CVData]
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
        self._legend_cfg = {'fontsize': 12, 'fontname': 'Arial', 'frameon': True}
        self.electrolyte = 'sat.'    # 電解質（E0 換算）
        self.ref_mode = 'vs RHE'     # vs RHE / vs 參考電極

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
        tk.Label(left, text="CV 數據", font=("Segoe UI", 10, "bold")).pack(anchor="w")
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
        tk.Button(bf, text="ECSA", command=self.open_ecsa, width=8).pack(side=tk.LEFT)

        # 圈選擇
        cf = tk.Frame(left)
        cf.pack(fill=tk.X, pady=(4, 0))
        tk.Label(cf, text="圈選擇:").pack(side=tk.LEFT)
        self.cycle_var = tk.StringVar(value="圈 1")
        self.cycle_menu = tk.OptionMenu(cf, self.cycle_var, "圈 1", command=self._on_cycle_change)
        self.cycle_menu.pack(side=tk.LEFT, padx=4)

        # 全域設定——全部用 pack 框架（避免 grid 欄位累加超寬）
        gf = tk.LabelFrame(left, text="全域設定")
        gf.pack(fill=tk.X, pady=(6, 0))

        def row(parent):
            f = tk.Frame(parent)
            f.pack(fill=tk.X, pady=1)
            return f

        # 電位換算區（參考電極 / KCl 濃度 / pH / 溫度 / 顯示參考）
        r0 = row(gf)
        tk.Label(r0, text="參考電極:").pack(side=tk.LEFT)
        self.elec_var = tk.StringVar(value="Ag/AgCl")
        elec_om = tk.OptionMenu(r0, self.elec_var,
                                'vs RHE', 'vs SHE', 'SCE',
                                'Ag/AgCl', 'Hg/HgO',
                                command=lambda _: self.redraw())
        elec_om.config(width=8)
        elec_om.pack(side=tk.LEFT)

        # KCl 濃度（僅 Ag/AgCl 有效）
        r0b = row(gf)
        tk.Label(r0b, text="KCl 濃度:").pack(side=tk.LEFT)
        self.kcl_var = tk.StringVar(value="sat.")
        kcl_om = tk.OptionMenu(r0b, self.kcl_var, 'sat.', '3.5M', '3M', '1M',
                               command=lambda _: self.redraw())
        kcl_om.config(width=4)
        kcl_om.pack(side=tk.LEFT)
        tk.Label(r0b, text="(Ag/AgCl)").pack(side=tk.LEFT, padx=(4, 0))

        # pH + 溫度
        r1 = row(gf)
        tk.Label(r1, text="pH:").pack(side=tk.LEFT)
        self.ph_var = tk.StringVar(value="0")
        tk.Entry(r1, textvariable=self.ph_var, width=5).pack(side=tk.LEFT)
        tk.Label(r1, text="溫度:").pack(side=tk.LEFT, padx=(8, 0))
        self.temp_var = tk.StringVar(value="25")
        tk.Entry(r1, textvariable=self.temp_var, width=5).pack(side=tk.LEFT)
        tk.Label(r1, text="°C").pack(side=tk.LEFT)

        # 顯示參考
        r1b = row(gf)
        tk.Label(r1b, text="顯示參考:").pack(side=tk.LEFT)
        self.ref_var = tk.StringVar(value="vs RHE")
        ref_om = tk.OptionMenu(r1b, self.ref_var, 'vs RHE', '原始',
                               command=lambda _: self.redraw())
        ref_om.config(width=8)
        ref_om.pack(side=tk.LEFT)

        # 掃速
        r1c = row(gf)
        tk.Label(r1c, text="掃速:").pack(side=tk.LEFT)
        self.scan_var = tk.StringVar(value="50")
        tk.Entry(r1c, textvariable=self.scan_var, width=6).pack(side=tk.LEFT)
        tk.Label(r1c, text="mV/s").pack(side=tk.LEFT)

        # 電流單位
        r2 = row(gf)
        tk.Label(r2, text="電流單位:").pack(side=tk.LEFT)
        self.iunit_var = tk.StringVar(value="A")
        iu_om = tk.OptionMenu(r2, self.iunit_var, 'A', 'mA', 'µA',
                              command=lambda _: self.redraw())
        iu_om.config(width=3)
        iu_om.pack(side=tk.LEFT)

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
        tk.Label(cf3, text="框粗").pack(side=tk.LEFT, padx=(0, 0))
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
    # 上傳
    # ------------------------------------------------------------------
    def _auto_style(self, idx):
        color = self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]
        marker = self.AUTO_MARKERS[idx % len(self.AUTO_MARKERS)]
        return color, marker

    def add_curve(self):
        files = filedialog.askopenfilenames(
            title="選擇 CV CSV",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                df = pd.read_csv(f)
                if len(df.columns) < 2:
                    messagebox.showerror("格式錯誤", f"{os.path.basename(f)}\n至少需要 2 欄")
                    continue
                name = os.path.splitext(os.path.basename(f))[0]
                info = self._ask_columns(df, name)
                if info is None:
                    continue
                v_col, i_col = info
                color, marker = self._auto_style(len(self.curves))
                c = CVData(name, df, v_col, i_col, color, marker_style=marker)
                self.curves.append(c)
                self._refresh_list()
                self._update_cycle_menu()
            except Exception as e:
                messagebox.showerror("讀取失敗", f"{f}\n{e}")
        self.redraw()

    def _ask_columns(self, df, fname):
        win = tk.Toplevel(self.root)
        win.title(f"選擇欄位: {fname}")
        win.geometry("380x160")
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text=f"檔案: {fname}\n選擇電位（V）與電流（I）欄位:",
                 justify=tk.LEFT).pack(anchor="w", padx=10, pady=6)
        cols = list(df.columns)
        v_var = tk.StringVar(value=cols[0] if cols else "")
        i_var = tk.StringVar(value=cols[1] if len(cols) > 1 else (cols[0] if cols else ""))
        f1 = tk.Frame(win); f1.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f1, text="電位 V:").pack(side=tk.LEFT)
        tk.OptionMenu(f1, v_var, *cols).pack(side=tk.LEFT, padx=4)
        f2 = tk.Frame(win); f2.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f2, text="電流 I:").pack(side=tk.LEFT)
        tk.OptionMenu(f2, i_var, *cols).pack(side=tk.LEFT, padx=4)
        result = {'v': None}
        def ok():
            result['v'] = (v_var.get(), i_var.get())
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
            self._update_cycle_menu()
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
            self.listbox.insert(tk.END, f"{i+1}. {c.name} ({c.n_cycles}圈)")

    def _on_list_select(self, _evt=None):
        """列表點選 → 更新圈下拉"""
        self._update_cycle_menu()

    def _update_cycle_menu(self):
        """更新圈選擇下拉（依當前選取數據）"""
        sel = self.listbox.curselection()
        if not sel:
            return
        c = self.curves[sel[0]]
        menu = self.cycle_menu['menu']
        menu.delete(0, 'end')
        for i in range(c.n_cycles):
            Vc, _ = c.get_cycle(i)
            menu.add_command(label=f"圈 {i+1} ({Vc.min():.2f}~{Vc.max():.2f}V)",
                             command=lambda v=i: self._set_cycle(v))
        self.cycle_var.set(f"圈 {c.selected_cycle+1}")

    def _set_cycle(self, idx):
        sel = self.listbox.curselection()
        if sel:
            c = self.curves[sel[0]]
            c.selected_cycle = idx
            self.cycle_var.set(f"圈 {idx+1}")
            self.redraw()

    def _on_cycle_change(self, _val):
        """OptionMenu 下拉觸發（與 _set_cycle 重複時忽略——menu 已用 _set_cycle）"""
        pass

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
        win.geometry("400x260")
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text=f"數據: {c.name}（V: {c.v_col}, I: {c.i_col}）",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=4)
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

    # 參考電極 E0 表（vs SHE）
    ELEC_E0 = {
        'vs RHE': 0.0,
        'vs SHE': 0.0,
        'SCE': 0.241,
        'Ag/AgCl': None,   # 依 KCl 濃度
        'Hg/HgO': 0.098,
    }
    KCL_E0 = {   # Ag/AgCl 依 KCl 濃度 (vs SHE)
        'sat.': 0.197,
        '3.5M': 0.205,
        '3M': 0.210,
        '1M': 0.235,
    }

    def _get_elec_e0(self):
        """參考電極 E0（vs SHE，V）"""
        elec = self.elec_var.get()
        if elec == 'Ag/AgCl':
            return self.KCL_E0.get(self.kcl_var.get(), 0.197)
        return self.ELEC_E0.get(elec, 0.0)

    def _get_ph(self):
        try:
            return float(self.ph_var.get()) if self.ph_var.get() else 0.0
        except ValueError:
            return 0.0

    def _get_temp(self):
        try:
            return float(self.temp_var.get()) if self.temp_var.get() else 25.0
        except ValueError:
            return 25.0

    def _nernst_slope(self):
        """Nernst 溫度修正斜率：0.05916 V/dec at 25°C → ×T/298.15"""
        T = self._get_temp() + 273.15
        return 0.05916 * T / 298.15

    def _ref_conversion(self, V):
        """電位換算：
        顯示 vs RHE：E_RHE = E_raw + E0_electrode + slope×pH
        顯示 原始：不換算
        """
        if self.ref_var.get() == '原始':
            return np.asarray(V, dtype=float)
        e0 = self._get_elec_e0()
        ph = self._get_ph()
        slope = self._nernst_slope()
        return np.asarray(V, dtype=float) + e0 + slope * ph

    def _i_scale(self):
        """電流單位縮放：內部統一 A"""
        return self.CURRENT_UNITS.get(self.iunit_var.get(), 1.0)

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
    # 圖例互動（沿用 Nyquist）
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
        from matplotlib.ticker import MultipleLocator
        if axis == 'x':
            enabled = self.xminor_var.get()
            n_str = self.xminor_n_var.get()
            set_loc = self.ax.xaxis.set_minor_locator
            major_ticks = self.ax.get_xticks()
        else:
            enabled = self.yminor_var.get()
            n_str = self.yminor_n_var.get()
            set_loc = self.ax.yaxis.set_minor_locator
            major_ticks = self.ax.get_yticks()
        if not enabled:
            self.ax.minorticks_off()
            return
        try:
            n = int(n_str) if n_str else 4
            n = max(1, min(n, 20))
        except ValueError:
            n = 4
        self.ax.minorticks_on()
        if len(major_ticks) >= 2:
            major_step = abs(major_ticks[1] - major_ticks[0])
            if major_step > 0:
                set_loc(MultipleLocator(major_step / (n + 1)))
                return
        lo, hi = self.ax.get_xlim() if axis == 'x' else self.ax.get_ylim()
        if hi > lo:
            set_loc(MultipleLocator((hi - lo) / 50.0))

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

        # RHE 換算 + 電流單位
        i_scale = self._i_scale()

        for c in self.curves:
            Vc, Ic = c.get_cycle()
            V_disp = self._ref_conversion(Vc)
            I_disp = Ic / i_scale    # 內部 A → 顯示單位（A/mA/µA）
            marker = c.marker_style if (self.marker_global.get()
                                        and c.marker_style != 'None') else None
            self.ax.plot(V_disp, I_disp, label=c.name,
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
        ref_txt = self.ref_var.get()
        self.ax.set_xlabel(f"Potential ({ref_txt})", fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        iunit = self.iunit_var.get()
        self.ax.set_ylabel(f"Current ({iunit})", fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
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
                                 prop={'family': cfg['fontname']})
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
    # ECSA 計算彈窗
    # ------------------------------------------------------------------
    def open_ecsa(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "請先選擇一筆數據")
            return
        c = self.curves[sel[0]]
        Vc, Ic = c.get_cycle()
        # 分離正掃/反掃
        dV = np.diff(Vc)
        fwd_mask = np.concatenate([[True], dV > 0])   # 正掃（V 上升）
        rev_mask = np.concatenate([[True], dV < 0])   # 反掃（V 下降）

        win = tk.Toplevel(self.root)
        win.title(f"ECSA 計算 — {c.name}")
        win.geometry("520x640")
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=f"數據: {c.name}  圈 {c.selected_cycle+1}\n"
                 f"掃速: {self.scan_var.get()} mV/s",
                 font=("Segoe UI", 9, "bold"), justify=tk.LEFT).pack(anchor="w", padx=10, pady=4)

        # 載量與面積
        lf = tk.Frame(win); lf.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(lf, text="Pt 載量 (mg/cm²):").pack(side=tk.LEFT)
        m_pt_var = tk.StringVar(value="0.1")
        tk.Entry(lf, textvariable=m_pt_var, width=8).pack(side=tk.LEFT, padx=4)
        tk.Label(lf, text="幾何面積 (cm²):").pack(side=tk.LEFT)
        area_var = tk.StringVar(value="1")
        tk.Entry(lf, textvariable=area_var, width=6).pack(side=tk.LEFT, padx=4)

        # 陰極/陽極勾選
        ckf = tk.Frame(win); ckf.pack(fill=tk.X, padx=10, pady=2)
        anodic_var = tk.BooleanVar(value=True)
        cathodic_var = tk.BooleanVar(value=True)
        tk.Checkbutton(ckf, text="陽極脫附 (anodic)", variable=anodic_var).pack(side=tk.LEFT, padx=(0, 12))
        tk.Checkbutton(ckf, text="陰極吸附 (cathodic)", variable=cathodic_var).pack(side=tk.LEFT)

        # 陽極輸入
        tk.Label(win, text="─ 陽極脫附區（正掃）─", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 0))
        af = tk.Frame(win); af.pack(fill=tk.X, padx=10)
        tk.Label(af, text="積分區間").pack(side=tk.LEFT)
        a_lo = tk.StringVar(value="0.05"); a_hi = tk.StringVar(value="0.4")
        tk.Entry(af, textvariable=a_lo, width=6).pack(side=tk.LEFT, padx=2)
        tk.Label(af, text="~").pack(side=tk.LEFT)
        tk.Entry(af, textvariable=a_hi, width=6).pack(side=tk.LEFT, padx=2)
        tk.Label(af, text="基準線").pack(side=tk.LEFT, padx=(10, 0))
        a_b1 = tk.StringVar(value="0.05"); a_b2 = tk.StringVar(value="0.4")
        tk.Entry(af, textvariable=a_b1, width=6).pack(side=tk.LEFT, padx=2)
        tk.Label(af, text="~").pack(side=tk.LEFT)
        tk.Entry(af, textvariable=a_b2, width=6).pack(side=tk.LEFT, padx=2)

        # 陰極輸入
        tk.Label(win, text="─ 陰極吸附區（反掃）─", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 0))
        kf = tk.Frame(win); kf.pack(fill=tk.X, padx=10)
        tk.Label(kf, text="積分區間").pack(side=tk.LEFT)
        c_lo = tk.StringVar(value="0.05"); c_hi = tk.StringVar(value="0.4")
        tk.Entry(kf, textvariable=c_lo, width=6).pack(side=tk.LEFT, padx=2)
        tk.Label(kf, text="~").pack(side=tk.LEFT)
        tk.Entry(kf, textvariable=c_hi, width=6).pack(side=tk.LEFT, padx=2)
        tk.Label(kf, text="基準線").pack(side=tk.LEFT, padx=(10, 0))
        c_b1 = tk.StringVar(value="0.05"); c_b2 = tk.StringVar(value="0.4")
        tk.Entry(kf, textvariable=c_b1, width=6).pack(side=tk.LEFT, padx=2)
        tk.Label(kf, text="~").pack(side=tk.LEFT)
        tk.Entry(kf, textvariable=c_b2, width=6).pack(side=tk.LEFT, padx=2)

        # 內嵌小圖
        tk.Label(win, text="─ 積分區視覺確認 ─", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 0))
        fig_small = plt.Figure(figsize=(5, 2.2), dpi=90)
        ax_small = fig_small.add_subplot(111)
        canvas_small = FigureCanvasTkAgg(fig_small, master=win)
        canvas_small.get_tk_widget().pack(padx=10, pady=4)

        # 結果區
        result_var = tk.StringVar(value="尚未計算")
        tk.Label(win, textvariable=result_var, justify=tk.LEFT,
                 font=("Consolas", 9)).pack(anchor="w", padx=10, pady=4)

        def draw_preview():
            """內嵌小圖：顯示曲線 + 積分區（依 RHE 換算）"""
            ax_small.clear()
            V_disp = self._ref_conversion(Vc)
            I_disp = Ic / self._i_scale()
            ax_small.plot(V_disp, I_disp, color=c.color, lw=1.0)
            # 標註積分區
            try:
                lo, hi = float(a_lo.get()), float(a_hi.get())
                if anodic_var.get():
                    ax_small.axvspan(lo, hi, color='red', alpha=0.15)
            except ValueError:
                pass
            try:
                lo, hi = float(c_lo.get()), float(c_hi.get())
                if cathodic_var.get():
                    ax_small.axvspan(lo, hi, color='blue', alpha=0.15)
            except ValueError:
                pass
            ref_txt = self.ref_var.get()
            ax_small.set_xlabel(f"Potential ({ref_txt})", fontsize=8)
            ax_small.set_ylabel(f"Current ({self.iunit_var.get()})", fontsize=8)
            ax_small.tick_params(labelsize=7)
            fig_small.tight_layout()
            canvas_small.draw()

        def do_calc():
            try:
                scan_rate = float(self.scan_var.get()) / 1000.0   # mV/s → V/s
                m_pt = float(m_pt_var.get())
                area_geo = float(area_var.get())
            except ValueError:
                messagebox.showerror("錯誤", "掃速/載量/面積需為數字")
                return
            # 正掃/反掃數據（RHE 換算後——與圖顯示一致）
            V_all_conv = self._ref_conversion(Vc)
            V_f = V_all_conv[fwd_mask]
            I_f = Ic[fwd_mask]
            V_r = V_all_conv[rev_mask]
            I_r = Ic[rev_mask]

            lines = []
            results = []
            # 陽極（正掃）
            if anodic_var.get():
                r = calc_ecsa(V_f, I_f, float(a_lo.get()), float(a_hi.get()),
                              float(a_b1.get()), float(a_b2.get()),
                              scan_rate, m_pt, area_geo)
                if r:
                    lines.append(f"陽極脫附: Q={r['charge_uC']:.1f} µC, "
                                 f"ECSA={r['ecsa_m2g']:.2f} m²/g")
                    results.append(r['ecsa_m2g'])
            # 陰極（反掃）
            if cathodic_var.get():
                r = calc_ecsa(V_r, I_r, float(c_lo.get()), float(c_hi.get()),
                              float(c_b1.get()), float(c_b2.get()),
                              scan_rate, m_pt, area_geo)
                if r:
                    lines.append(f"陰極吸附: Q={r['charge_uC']:.1f} µC, "
                                 f"ECSA={r['ecsa_m2g']:.2f} m²/g")
                    results.append(r['ecsa_m2g'])
            if results:
                avg = sum(results) / len(results)
                lines.append(f"平均 ECSA = {avg:.2f} m²/g Pt")
            result_var.set("\n".join(lines) if lines else "無有效結果")

        bf = tk.Frame(win); bf.pack(pady=6)
        tk.Button(bf, text="預覽積分區", command=draw_preview, width=12).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="計算", command=do_calc, width=10).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="關閉", command=win.destroy, width=10).pack(side=tk.LEFT, padx=4)

        draw_preview()

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
    app = PtCVPlotterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
