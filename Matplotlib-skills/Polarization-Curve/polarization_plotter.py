#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Polarization Curve Plotter — 極化曲線繪圖 GUI（Tkinter + Matplotlib）

適用：燃料電池 (FC) 與水電解器 (EC) 的 I-V 極化曲線

功能：
  1. 分區上傳：多條極化曲線（CSV：任兩欄指定為 V / I）
  2. 數據處理：active area 換算（A → A/cm²）、正負號切換、功率 P=I×V 自動計算
  3. X/Y 軸角色可切換（電化學慣例 X=I,Y=V；或反轉）
  4. 可勾選疊圖：功率密度曲線（雙 Y 軸、單位可選 W/cm² / mW/cm²）
  5. 視覺微調：顏色、字型、字體大小、marker（種類/開關）、線型/線寬
  6. 排序：列表上下移動（決定繪圖順序與圖層）
  7. 圖例：拖曳位置
  8. 標註：新增線段與文字
  9. 輸出：儲存 PNG/SVG/PDF + DPI + 匯出合併 CSV

環境需求：
  pip install matplotlib pandas numpy

用法：
  python polarization_plotter.py
"""
import tkinter as tk
from tkinter import filedialog, colorchooser, messagebox, simpledialog, ttk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import pandas as pd
import numpy as np
import os

# 可選的效率理論電壓（暫未使用，保留供擴充）
THEORY_V = {'1.23 V (HHV)': 1.23, '1.48 V (LHV)': 1.48}


# ------------------------------------------------------------------
# 資料容器
# ------------------------------------------------------------------
class PolarizationData:
    """單條極化曲線"""
    def __init__(self, name, df, v_col, i_col,
                 color, current_unit='A/cm2', active_area=1.0,
                 negate=False, negate_v=False, marker_on=True, marker_style='o',
                 line_style='-', line_width=1.0, show_power=True,
                 power_unit='W/cm2', invert_xy=False):
        self.name = name
        self.df = df.copy()
        self.v_col = v_col
        self.i_col = i_col
        self.color = color
        self.current_unit = current_unit      # 'A', 'A/cm2', 'mA/cm2'
        self.active_area = active_area        # cm²
        self.negate = negate                  # 電流取絕對值
        self.negate_v = negate_v              # 電壓取絕對值
        self.marker_on = marker_on
        self.marker_style = marker_style
        self.line_style = line_style
        self.line_width = line_width
        self.show_power = show_power          # 是否顯示功率曲線
        self.power_unit = power_unit          # 'W/cm2', 'mW/cm2'
        self.invert_xy = invert_xy            # X/Y 軸角色

    def get_v(self):
        """電壓陣列（可選 ×(−1)）"""
        v = self.df[self.v_col].astype(float).values
        if self.negate_v:
            v = -v
        return v

    def get_i_density(self):
        """電流密度 A/cm²（已換算；negate = ×(−1)，使用者自行決定正負）"""
        i = self.df[self.i_col].astype(float).values
        if self.current_unit == 'A':
            i = i / self.active_area
        elif self.current_unit == 'mA/cm2':
            i = i / 1000.0
        # 'A/cm2' 直接使用
        if self.negate:
            i = -i   # 乘 −1（非絕對值）——使用者決定正負
        return i

    def get_power(self):
        """功率密度（依 power_unit）"""
        p = self.get_v() * self.get_i_density()   # W/cm²（若 I 為 A/cm²、V 為 V）
        if self.power_unit == 'mW/cm2':
            p = p * 1000.0
        return p

    def get_xy(self):
        """依 invert_xy 回傳 (x, y)
        invert_xy=False（預設）: X=I, Y=V（電化學慣例）
        invert_xy=True:          X=V, Y=I
        """
        if self.invert_xy:
            return self.get_v(), self.get_i_density()
        return self.get_i_density(), self.get_v()


# ------------------------------------------------------------------
# 主視窗
# ------------------------------------------------------------------
class PolarizationPlotterApp:
    DEFAULT_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    def __init__(self, root):
        self.root = root
        self.root.title("Polarization Curve Plotter — 極化曲線繪圖工具")
        self.root.geometry("1180x780")

        self.curves = []          # list[PolarizationData]
        self.annotations = []     # list[(type, ...)]
        self.show_power_global = True   # 全域功率曲線開關
        self.font_name = 'DejaVu Sans'
        self.font_size = 10
        self.title_size = 10
        self.tick_size = 9
        self.legend_dragging = False

        self._build_ui()
        self._new_figure()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        left = tk.Frame(self.root, width=330)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left.pack_propagate(False)

        # ===== 極化曲線列表 =====
        tk.Label(left, text="極化曲線 (Polarization Curves)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
        btn_row = tk.Frame(left)
        btn_row.pack(fill=tk.X)
        tk.Button(btn_row, text="＋ 新增曲線", command=self.add_curve).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row, text="✕ 刪除選取", command=self.remove_curve).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.listbox = tk.Listbox(left, height=8, exportselection=False)
        self.listbox.pack(fill=tk.X, pady=2)

        btn_row2 = tk.Frame(left)
        btn_row2.pack(fill=tk.X)
        tk.Button(btn_row2, text="↑ 上移", command=lambda: self.move_item(-1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row2, text="↓ 下移", command=lambda: self.move_item(1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row2, text="✎ 屬性", command=self.edit_props).pack(side=tk.LEFT, expand=True)

        # ===== 全域設定 =====
        tk.Label(left, text="全域設定", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        gf = tk.Frame(left)
        gf.pack(fill=tk.X)

        # X/Y 軸角色
        tk.Label(gf, text="軸角色:").grid(row=0, column=0, sticky="w")
        self.axis_var = tk.StringVar(value="X=I, Y=V (電化學慣例)")
        tk.OptionMenu(gf, self.axis_var,
                      "X=I, Y=V (電化學慣例)",
                      "X=V, Y=I (反轉)",
                      command=lambda _: self.redraw()).grid(row=0, column=1, sticky="ew")

        # 功率曲線全域開關
        tk.Label(gf, text="功率密度顯示:").grid(row=1, column=0, sticky="w")
        self.power_var = tk.BooleanVar(value=True)
        tk.Checkbutton(gf, text="(右 Y 軸)", variable=self.power_var,
                       command=self.redraw).grid(row=1, column=1, sticky="w")

        # 單位顯示
        tk.Label(gf, text="單位顯示:").grid(row=2, column=0, sticky="w")
        self.unit_display_var = tk.StringVar(value="A/cm²")
        tk.OptionMenu(gf, self.unit_display_var, 'A/cm²', 'mA/cm²', 'A',
                      command=lambda _: self.redraw()).grid(row=2, column=1, sticky="ew")

        # 字型
        tk.Label(gf, text="字型:").grid(row=3, column=0, sticky="w")
        self.font_var = tk.StringVar(value=self.font_name)
        fonts = ['DejaVu Sans', 'Arial', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(gf, self.font_var, *fonts, command=lambda _: self._apply_global()).grid(row=3, column=1, sticky="ew")

        # 字體大小（軸標題 / 刻度分開）
        tk.Label(gf, text="標題字體:").grid(row=4, column=0, sticky="w")
        self.title_size_var = tk.IntVar(value=self.title_size)
        ts_spin = tk.Spinbox(gf, from_=6, to=30, textvariable=self.title_size_var, width=5,
                             command=self._apply_global)
        ts_spin.grid(row=4, column=1, sticky="w")
        ts_spin.bind('<Return>', lambda e: self._apply_global())
        ts_spin.bind('<FocusOut>', lambda e: self._apply_global())

        tk.Label(gf, text="刻度字體:").grid(row=5, column=0, sticky="w")
        self.tick_size_var = tk.IntVar(value=self.tick_size)
        tk_spin = tk.Spinbox(gf, from_=6, to=30, textvariable=self.tick_size_var, width=5,
                             command=self._apply_global)
        tk_spin.grid(row=5, column=1, sticky="w")
        tk_spin.bind('<Return>', lambda e: self._apply_global())
        tk_spin.bind('<FocusOut>', lambda e: self._apply_global())

        # 功率密度單位
        tk.Label(gf, text="功率單位:").grid(row=6, column=0, sticky="w")
        self.power_unit_var = tk.StringVar(value="W/cm²")
        tk.OptionMenu(gf, self.power_unit_var, 'W/cm²', 'mW/cm²', 'W',
                      command=lambda _: self.redraw()).grid(row=6, column=1, sticky="ew")

        # ===== 軸設定 =====
        tk.Label(left, text="軸設定（空=自動）", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        axf = tk.Frame(left)
        axf.pack(fill=tk.X)

        def make_axis_row(parent, row, label, min_var, max_var, n_var, minor_var):
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
            parent.columnconfigure(1, weight=1)

        self.xmin_var = tk.StringVar(value="")
        self.xmax_var = tk.StringVar(value="")
        self.xn_var = tk.StringVar(value="")
        self.xminor_var = tk.BooleanVar(value=False)
        self.ymin_var = tk.StringVar(value="")
        self.ymax_var = tk.StringVar(value="")
        self.yn_var = tk.StringVar(value="")
        self.yminor_var = tk.BooleanVar(value=False)
        self.y2min_var = tk.StringVar(value="")
        self.y2max_var = tk.StringVar(value="")
        self.y2n_var = tk.StringVar(value="")
        self.y2minor_var = tk.BooleanVar(value=False)

        make_axis_row(axf, 0, "X:", self.xmin_var, self.xmax_var, self.xn_var, self.xminor_var)
        make_axis_row(axf, 1, "Y:", self.ymin_var, self.ymax_var, self.yn_var, self.yminor_var)
        make_axis_row(axf, 2, "Y₂:", self.y2min_var, self.y2max_var, self.y2n_var, self.y2minor_var)

        tk.Button(left, text="套用軸設定", command=self.redraw).pack(fill=tk.X, pady=(2, 0))

        gf.columnconfigure(1, weight=1)

        # ===== 標註 =====
        tk.Label(left, text="標註工具", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        btn_row3 = tk.Frame(left)
        btn_row3.pack(fill=tk.X)
        tk.Button(btn_row3, text="＋ 文字", command=self.add_text_annotation).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row3, text="＋ 線段", command=self.add_line_annotation).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row3, text="✕ 清除", command=self.clear_annotations).pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ===== 輸出 =====
        action_row = tk.Frame(left)
        action_row.pack(fill=tk.X, pady=(10, 2))
        tk.Button(action_row, text="🔄 重繪", command=self.redraw, bg="#e8f0fe").pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(action_row, text="💾 儲存圖", command=self.save_figure, bg="#e6f4e6").pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(action_row, text="📊 匯出CSV", command=self.export_csv, bg="#fff3e0").pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ===== 右側繪圖區 =====
        self.plot_frame = tk.Frame(self.root)
        self.plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _new_figure(self):
        for w in self.plot_frame.winfo_children():
            w.destroy()
        self.fig = plt.Figure(figsize=(7, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax2 = self.ax.twinx()  # 右 Y 軸（功率）
        self.ax2.spines['right'].set_visible(False)
        self.ax2.set_yticks([])
        self.ax2.set_ylabel('')
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        self.toolbar.update()
        self.canvas.mpl_connect('button_press_event', self._on_legend_press)
        self.canvas.mpl_connect('motion_notify_event', self._on_legend_drag)
        self.canvas.mpl_connect('button_release_event', self._on_legend_release)

    # ------------------------------------------------------------------
    # 上傳
    # ------------------------------------------------------------------
    def _pick_color(self, idx):
        return self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]

    def add_curve(self):
        files = filedialog.askopenfilenames(
            title="選擇極化曲線 CSV",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                df = pd.read_csv(f)
                if len(df.columns) < 2:
                    messagebox.showerror("格式錯誤", f"{os.path.basename(f)}\n至少需要 2 欄")
                    continue
                # 彈出欄位選擇視窗（含單位與 active area）
                name = os.path.splitext(os.path.basename(f))[0]
                info = self._ask_columns(df, name)
                if info is None:
                    continue
                v_col, i_col, unit, area = info
                self.curves.append(PolarizationData(
                    name, df, v_col, i_col, self._pick_color(len(self.curves)),
                    current_unit=unit, active_area=area))
                self._refresh_list()
            except Exception as e:
                messagebox.showerror("讀取失敗", f"{f}\n{e}")
        self.redraw()

    def _ask_columns(self, df, fname):
        """彈出視窗：選 V 欄 / I 欄 + 電流單位 + active area"""
        win = tk.Toplevel(self.root)
        win.title(f"數據設定: {fname}")
        win.geometry("420x260")
        win.transient(self.root)
        win.grab_set()

        cols = list(df.columns)
        result = {'v': None, 'i': None, 'unit': 'A/cm2', 'area': 1.0}

        tk.Label(win, text=f"檔案: {fname}", font=("Segoe UI", 9, "bold")).pack(pady=(8, 2))
        tk.Label(win, text="選擇電壓/電流欄位與電流單位").pack()

        rf = tk.Frame(win); rf.pack(pady=4)
        tk.Label(rf, text="電壓 (V):").pack(side=tk.LEFT)
        v_var = tk.StringVar(value=cols[0])
        tk.OptionMenu(rf, v_var, *cols).pack(side=tk.LEFT)

        cf = tk.Frame(win); cf.pack(pady=4)
        tk.Label(cf, text="電流 (I):").pack(side=tk.LEFT)
        i_var = tk.StringVar(value=cols[1] if len(cols) > 1 else cols[0])
        tk.OptionMenu(cf, i_var, *cols).pack(side=tk.LEFT)

        uf = tk.Frame(win); uf.pack(pady=4)
        tk.Label(uf, text="電流單位:").pack(side=tk.LEFT)
        unit_var = tk.StringVar(value='A/cm2')
        tk.OptionMenu(uf, unit_var, 'A', 'A/cm2', 'mA/cm2').pack(side=tk.LEFT)
        tk.Label(uf, text="   Active Area (cm²):").pack(side=tk.LEFT)
        area_var = tk.StringVar(value="1")
        area_entry = tk.Entry(uf, textvariable=area_var, width=6)
        area_entry.pack(side=tk.LEFT)

        def on_unit_change(*_):
            # 單位 = A 時 active area 才需要（否則停用）
            if unit_var.get() == 'A':
                area_entry.config(state='normal')
            else:
                area_entry.config(state='disabled')

        unit_var.trace_add('write', on_unit_change)
        on_unit_change()

        def ok():
            result['v'] = v_var.get()
            result['i'] = i_var.get()
            result['unit'] = unit_var.get()
            try:
                result['area'] = float(area_var.get()) if area_var.get() else 1.0
            except ValueError:
                result['area'] = 1.0
            win.destroy()

        def cancel():
            win.destroy()

        bf = tk.Frame(win); bf.pack(pady=10)
        tk.Button(bf, text="確定", command=ok, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="取消", command=cancel, width=10).pack(side=tk.LEFT, padx=5)

        win.wait_window()
        if result['v'] is None:
            return None
        return result['v'], result['i'], result['unit'], result['area']

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
        self._refresh_list()
        self.listbox.selection_set(new)
        self.redraw()

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, c in enumerate(self.curves):
            self.listbox.insert(tk.END, f"{i+1}. {c.name}")

    # ------------------------------------------------------------------
    # 屬性
    # ------------------------------------------------------------------
    def edit_props(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "請先在列表中選擇一條曲線")
            return
        self._edit_curve_props(sel[0])

    def _edit_curve_props(self, idx):
        c = self.curves[idx]
        win = tk.Toplevel(self.root)
        win.title(f"屬性: {c.name}")
        win.geometry("400x480")

        tk.Label(win, text=f"曲線: {c.name}（V: {c.v_col}, I: {c.i_col}）",
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

        # ×(−1) 切換
        nf = tk.Frame(win); nf.pack(fill=tk.X, padx=8)
        neg_var = tk.BooleanVar(value=c.negate)
        tk.Checkbutton(nf, text="電流 ×(−1)", variable=neg_var,
                       command=lambda: (setattr(c, 'negate', neg_var.get()), self.redraw())).pack(side=tk.LEFT)
        negv_var = tk.BooleanVar(value=c.negate_v)
        tk.Checkbutton(nf, text="電壓 ×(−1)", variable=negv_var,
                       command=lambda: (setattr(c, 'negate_v', negv_var.get()), self.redraw())).pack(side=tk.LEFT, padx=(8, 0))

        # 功率曲線（該曲線）——單位由主畫面「功率單位」控制
        pf = tk.Frame(win); pf.pack(fill=tk.X, padx=8)
        pw_var = tk.BooleanVar(value=c.show_power)
        tk.Checkbutton(pf, text="顯示功率曲線", variable=pw_var,
                       command=lambda: (setattr(c, 'show_power', pw_var.get()), self.redraw())).pack(side=tk.LEFT)

        # 線型/線寬
        lf = tk.Frame(win); lf.pack(fill=tk.X, padx=8)
        tk.Label(lf, text="線型:").pack(side=tk.LEFT)
        ls_var = tk.StringVar(value=c.line_style)
        tk.OptionMenu(lf, ls_var, '-', '--', '-.', ':',
                      command=lambda v: (setattr(c, 'line_style', v), self.redraw())).pack(side=tk.LEFT)
        tk.Label(lf, text="寬:").pack(side=tk.LEFT, padx=(8, 0))
        lw_var = tk.DoubleVar(value=c.line_width)
        tk.Spinbox(lf, from_=0.5, to=5, increment=0.1, textvariable=lw_var, width=4).pack(side=tk.LEFT)
        def set_lw():
            c.line_width = lw_var.get()
            self.redraw()
        tk.Button(lf, text="套用", command=set_lw).pack(side=tk.LEFT, padx=4)

        # marker
        mf = tk.Frame(win); mf.pack(fill=tk.X, padx=8)
        mk_var = tk.BooleanVar(value=c.marker_on)
        tk.Checkbutton(mf, text="顯示 marker", variable=mk_var,
                       command=lambda: (setattr(c, 'marker_on', mk_var.get()), self.redraw())).pack(side=tk.LEFT)
        ms_var = tk.StringVar(value=c.marker_style)
        markers = ['o', 's', '^', 'v', 'D', 'x', '+', '*', '|', 'None']
        tk.OptionMenu(mf, ms_var, *markers,
                      command=lambda v: (setattr(c, 'marker_style', v), self.redraw())).pack(side=tk.LEFT, padx=4)

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
    # 圖例拖曳
    # ------------------------------------------------------------------
    def _on_legend_press(self, event):
        if event.inaxes is None: return
        leg = self.ax.get_legend()
        if leg is None: return
        if leg.get_window_extent().contains(event.x, event.y):
            self.legend_dragging = True

    def _on_legend_drag(self, event):
        if not self.legend_dragging or event.inaxes is None: return
        leg = self.ax.get_legend()
        if leg is None: return
        leg.set_bbox_to_anchor((event.xdata, event.ydata), transform=self.ax.transData)
        self.canvas.draw_idle()

    def _on_legend_release(self, event):
        self.legend_dragging = False

    # ------------------------------------------------------------------
    # 繪圖
    # ------------------------------------------------------------------
    def redraw(self):
        self.ax.clear()
        self.ax2.clear()

        invert = self.axis_var.get().startswith("X=V")
        unit_txt = self.unit_display_var.get()   # A/cm² / mA/cm² / A
        xlabel = f'Current Density ({unit_txt})' if not invert else 'Voltage (V)'
        ylabel = 'Voltage (V)' if not invert else f'Current Density ({unit_txt})'

        # 顯示換算因子（內部一律 A/cm²，顯示時換算）
        if unit_txt == 'mA/cm²':
            disp_scale = 1000.0
        elif unit_txt == 'A':
            disp_scale = None   # 每條曲線依各自 active_area 換回
        else:
            disp_scale = 1.0

        # 收集功率數據（有顯示功率的曲線）
        power_plotted = False
        p_unit_txt = self.power_unit_var.get()   # 預設（防未定義引用）

        for c in self.curves:
            c.invert_xy = invert
            x, y = c.get_xy()
            # 顯示單位換算（只影響繪圖數值，內部計算不變）
            if disp_scale is None:
                x_disp = x * c.active_area   # 顯示 A（原始安培）
            else:
                x_disp = x * disp_scale
            marker = c.marker_style if c.marker_on and c.marker_style != 'None' else None
            self.ax.plot(x_disp, y, label=c.name, color=c.color,
                         linestyle=c.line_style, linewidth=c.line_width,
                         marker=marker, markersize=3)

            # 功率曲線（右 Y 軸）——功率顯示隨功率單位設定
            if c.show_power and self.power_var.get() and not invert:
                p = c.get_power()   # W/cm²（內部）
                pu = self.power_unit_var.get()
                if pu == 'mW/cm²':
                    p_disp = p * 1000.0
                elif pu == 'W':
                    p_disp = p * c.active_area
                else:
                    p_disp = p
                self.ax2.plot(x_disp, p_disp, color=c.color,
                              linestyle='--', linewidth=1.2, alpha=0.7,
                              label=f"{c.name} (P)")
                power_plotted = True

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
        self.ax.set_xlabel(xlabel, fontsize=self.title_size, fontweight='bold', fontname=self.font_name)
        self.ax.set_ylabel(ylabel, fontsize=self.title_size, fontweight='bold', fontname=self.font_name)
        self.ax.tick_params(labelsize=self.tick_size)

        # 軸範圍：預設 auto scale；使用者輸入自訂值時才固定
        if self.curves:
            self.ax.relim()
            self.ax.autoscale()
            # X 軸範圍
            try:
                if self.xmin_var.get() or self.xmax_var.get():
                    xmin = float(self.xmin_var.get()) if self.xmin_var.get() else None
                    xmax_u = float(self.xmax_var.get()) if self.xmax_var.get() else None
                    self.ax.set_xlim(xmin, xmax_u)
            except ValueError:
                pass
            # Y1 軸範圍
            try:
                if self.ymin_var.get() or self.ymax_var.get():
                    ymin = float(self.ymin_var.get()) if self.ymin_var.get() else None
                    ymax_u = float(self.ymax_var.get()) if self.ymax_var.get() else None
                    self.ax.set_ylim(ymin, ymax_u)
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
            # X 軸子刻度
            self.ax.minorticks_on() if self.xminor_var.get() else self.ax.minorticks_off()
            # Y1 軸刻度數量
            try:
                if self.yn_var.get():
                    n = int(self.yn_var.get())
                    if n > 1:
                        lo, hi = self.ax.get_ylim()
                        self.ax.set_yticks(np.linspace(lo, hi, n))
            except ValueError:
                pass
            # Y1 軸子刻度
            self.ax.minorticks_on() if self.yminor_var.get() else self.ax.minorticks_off()

        if power_plotted:
            # 恢復右軸顯示（含刻度與標題）
            self.ax2.spines['right'].set_visible(True)
            # 功率單位：主畫面設定
            p_unit_txt = self.power_unit_var.get()
            self.ax2.set_ylabel(f'Power Density ({p_unit_txt})', fontsize=self.title_size, fontweight='bold')
            self.ax2.tick_params(labelsize=self.tick_size)
            # 將 Y2 標題推到右軸外側（避免與 Y1 標題重疊）
            self.ax2.yaxis.set_label_coords(1.06, 0.5)
            # Y2 軸範圍
            try:
                if self.y2min_var.get() or self.y2max_var.get():
                    y2min = float(self.y2min_var.get()) if self.y2min_var.get() else None
                    y2max = float(self.y2max_var.get()) if self.y2max_var.get() else None
                    self.ax2.set_ylim(y2min, y2max)
            except ValueError:
                pass
            # Y2 軸刻度數量
            try:
                if self.y2n_var.get():
                    n = int(self.y2n_var.get())
                    if n > 1:
                        lo, hi = self.ax2.get_ylim()
                        self.ax2.set_yticks(np.linspace(lo, hi, n))
            except ValueError:
                pass
            # Y2 軸子刻度
            self.ax2.minorticks_on() if self.y2minor_var.get() else self.ax2.minorticks_off()
        else:
            # 無功率曲線時隱藏右軸
            self.ax2.spines['right'].set_visible(False)
            self.ax2.set_yticks([])
            self.ax2.set_ylabel('')
            self.ax2.minorticks_off()

        if self.curves:
            leg = self.ax.legend(loc='upper right', frameon=True, fontsize=self.tick_size)
            leg.set_draggable(True)

        # 統一設定刻度字體（在所有 set_xticks/子刻度之後執行，確保不被覆蓋）
        # 刻度與軸標題綁定相同字體（font_name）
        for lbl in self.ax.get_xticklabels() + self.ax.get_yticklabels():
            lbl.set_fontname(self.font_name)
        for lbl in self.ax2.get_xticklabels() + self.ax2.get_yticklabels():
            lbl.set_fontname(self.font_name)

        self.fig.tight_layout()
        if power_plotted:
            # 有功率曲線時，右側留空間給 Y2 標題（tight_layout 不會處理 twinx 標題）
            self.fig.subplots_adjust(right=0.85)
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
        self.fig.savefig(f, dpi=dpi, bbox_inches='tight')
        messagebox.showinfo("完成", f"已儲存: {f} (dpi={dpi})")

    def export_csv(self):
        """匯出合併 CSV：V, I_density, P, label"""
        if not self.curves:
            messagebox.showinfo("提示", "沒有曲線可匯出")
            return
        f = filedialog.asksaveasfilename(
            title="匯出 CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="polarization_data.csv")
        if not f:
            return
        rows = []
        for c in self.curves:
            v = c.get_v()
            i = c.get_i_density()
            p = c.get_power()
            for j in range(len(v)):
                rows.append({'V (V)': v[j], 'I_density (A/cm2)': i[j],
                             'P (W/cm2)': p[j], 'label': c.name})
        out = pd.DataFrame(rows)
        out.to_csv(f, index=False)
        messagebox.showinfo("完成", f"已匯出 {len(rows)} 筆數據 → {f}")


# ------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = PolarizationPlotterApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
