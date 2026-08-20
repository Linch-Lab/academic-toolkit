#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Three-Electrode Polarization — half-cell I-V curve GUI (Tkinter + Matplotlib)

For: three-electrode (working vs reference electrode) polarization curves
     (LSV / half-cell / RDE measurements)

Features:
  1. Multi-file overlay (list managed)
  2. Potential reference conversion: source electrode → RHE (or Raw)
     (SCE / Ag/AgCl by KCl / Hg/HgO / vs SHE / vs RHE; Nernst pH + temp)
  3. Y mode: linear current density or Tafel log|j|
  4. Overpotential η (V − E0) + iR correction (V − i×R) — global toggles
  5. X/Y axis role switchable
  6. Current units: A/cm² / mA/cm² / µA/cm² / A
  7. Visual: color, font, size, marker, linestyle/linewidth
  8. Sort, legend drag, annotations, axis settings, save + export CSV

Requirements:
  pip install matplotlib pandas numpy

Usage:
  python three_electrode_plotter.py
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


# ------------------------------------------------------------------
# Data container
# ------------------------------------------------------------------
class ThreeElectrodeData:
    """A three-electrode polarization curve (working vs reference electrode)"""
    def __init__(self, name, df, v_col, i_col,
                 color, current_unit='mA/cm2', active_area=1.0,
                 negate=False, negate_v=False, marker_on=True, marker_style='o',
                 marker_size=3, line_style='-', line_width=1.0,
                 e0=0.0, r=0.0, invert_xy=False):
        self.name = name
        self.df = df.copy()
        self.v_col = v_col
        self.i_col = i_col
        self.color = color
        self.current_unit = current_unit      # 'A', 'A/cm2', 'mA/cm2', 'uA/cm2'
        self.active_area = active_area        # cm²
        self.negate = negate                  # Current ×(-1)
        self.negate_v = negate_v              # Voltage ×(-1)
        self.marker_on = marker_on
        self.marker_style = marker_style
        self.marker_size = marker_size
        self.line_style = line_style
        self.line_width = line_width
        self.e0 = e0                          # equilibrium potential (V) for η
        self.r = r                            # resistance (Ω) for iR correction
        self.invert_xy = invert_xy            # X/Y axis role

    def get_v(self):
        """Voltage array (optional ×(-1))"""
        v = self.df[self.v_col].astype(float).values
        if self.negate_v:
            v = -v
        return v

    def get_i_density(self):
        """Current density A/cm² (converted)"""
        i = self.df[self.i_col].astype(float).values
        if self.current_unit == 'A':
            i = i / self.active_area
        elif self.current_unit == 'mA/cm2':
            i = i / 1000.0
        elif self.current_unit == 'uA/cm2':
            i = i / 1e6
        # 'A/cm2' used directly
        if self.negate:
            i = -i   # times -1 (not abs) -- user decides sign
        return i

    def get_current_A(self):
        """Total current (A) for iR correction = j × area"""
        return self.get_i_density() * self.active_area

    def get_xy(self):
        """Return (x, y) per invert_xy
        invert_xy=False (default): X=V, Y=I density (electrochem convention)
        invert_xy=True:          X=I density, Y=V
        """
        if self.invert_xy:
            return self.get_i_density(), self.get_v()
        return self.get_v(), self.get_i_density()


# ------------------------------------------------------------------
# Main window
# ------------------------------------------------------------------
class ThreeElectrodePlotterApp:
    # Okabe-Ito colorblind-safe palette (7 colors)
    DEFAULT_COLORS = ['#0072B2', '#E69F00', '#56B4E9', '#009E73',
                      '#F0E442', '#CC79A7', '#D55E00']

    def __init__(self, root):
        self.root = root
        self.root.title("Three-Electrode Polarization")
        self.root.geometry("1180x780")

        self.curves = []          # list[ThreeElectrodeData]
        self.annotations = []     # list[(type, ...)]
        self.font_name = 'Arial'        # default font
        self.font_size = 18
        self.title_size = 18            # default title size 18
        self.tick_size = 18             # default tick size 18
        self.title_bold = False         # axis title bold toggle, default normal
        self.legend_dragging = False
        self.legend_selected = False    # legend selection state
        self._legend_sel_patches = []   # selection-box patches
        self._legend_pos_custom = False  # whether legend position was customized
        self._drag_anchor = None

        self._build_ui()
        self._new_figure()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        left = tk.Frame(self.root, width=360)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left.pack_propagate(False)

        # ===== Polarization list =====
        tk.Label(left, text="Polarization Curves", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
        btn_row = tk.Frame(left)
        btn_row.pack(fill=tk.X)
        tk.Button(btn_row, text="+ Add Curve", command=self.add_curve).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row, text="✕ Remove", command=self.remove_curve).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.listbox = tk.Listbox(left, height=8, exportselection=False)
        self.listbox.pack(fill=tk.X, pady=2)

        btn_row2 = tk.Frame(left)
        btn_row2.pack(fill=tk.X)
        tk.Button(btn_row2, text="↑ Up", command=lambda: self.move_item(-1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row2, text="↓ Down", command=lambda: self.move_item(1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row2, text="✎ Properties", command=self.edit_props).pack(side=tk.LEFT, expand=True)

        # ===== Global Settings =====
        tk.Label(left, text="Global Settings", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        gf = tk.Frame(left)
        gf.pack(fill=tk.X)

        # X/Y axis role
        tk.Label(gf, text="Axis Role:").grid(row=0, column=0, sticky="w")
        self.axis_var = tk.StringVar(value="X=V, Y=I (electrochem convention)")
        tk.OptionMenu(gf, self.axis_var,
                      "X=V, Y=I (electrochem convention)",
                      "X=I, Y=V (inverted)",
                      command=lambda _: self.redraw()).grid(row=0, column=1, sticky="ew")

        # potential reference (source electrode + display ref)
        tk.Label(gf, text="Potential Ref:").grid(row=1, column=0, sticky="w")
        ref_f = tk.Frame(gf)
        ref_f.grid(row=1, column=1, sticky="ew")
        self.elec_var = tk.StringVar(value="vs RHE")
        tk.OptionMenu(ref_f, self.elec_var, 'vs RHE', 'vs SHE', 'SCE', 'Ag/AgCl', 'Hg/HgO',
                      command=lambda _: self.redraw()).pack(side=tk.LEFT)
        tk.Label(ref_f, text="Display:").pack(side=tk.LEFT, padx=(8, 0))
        self.ref_var = tk.StringVar(value="vs RHE")
        tk.OptionMenu(ref_f, self.ref_var, 'vs RHE', 'Raw',
                      command=lambda _: self.redraw()).pack(side=tk.LEFT)

        # KCl concentration + pH + temperature
        tk.Label(gf, text="KCl/pH/T:").grid(row=2, column=0, sticky="w")
        kpt_f = tk.Frame(gf)
        kpt_f.grid(row=2, column=1, sticky="ew")
        self.kcl_var = tk.StringVar(value="sat.")
        tk.OptionMenu(kpt_f, self.kcl_var, 'sat.', '3.5M', '3M', '1M',
                      command=lambda _: self.redraw()).pack(side=tk.LEFT)
        tk.Label(kpt_f, text="pH").pack(side=tk.LEFT, padx=(6, 0))
        self.ph_var = tk.StringVar(value="0")
        ph_e = tk.Entry(kpt_f, textvariable=self.ph_var, width=4)
        ph_e.pack(side=tk.LEFT)
        ph_e.bind('<Return>', lambda e: self.redraw())
        tk.Label(kpt_f, text="T°C").pack(side=tk.LEFT, padx=(6, 0))
        self.temp_var = tk.StringVar(value="25")
        temp_e = tk.Entry(kpt_f, textvariable=self.temp_var, width=4)
        temp_e.pack(side=tk.LEFT)
        temp_e.bind('<Return>', lambda e: self.redraw())

        # Y mode (linear / Tafel) + η / iR toggles
        tk.Label(gf, text="Y Mode:").grid(row=3, column=0, sticky="w")
        ym_f = tk.Frame(gf)
        ym_f.grid(row=3, column=1, sticky="ew")
        self.ymode_var = tk.StringVar(value="linear")
        tk.OptionMenu(ym_f, self.ymode_var, 'linear', 'Tafel log|j|',
                      command=lambda _: self.redraw()).pack(side=tk.LEFT)
        self.eta_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ym_f, text="η", variable=self.eta_var,
                       command=self.redraw).pack(side=tk.LEFT, padx=(8, 0))
        self.ir_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ym_f, text="iR", variable=self.ir_var,
                       command=self.redraw).pack(side=tk.LEFT, padx=(4, 0))

        # curve style (global, 2 rows in container)
        tk.Label(gf, text="Curve Style:").grid(row=4, column=0, sticky="nw")
        ca_f = tk.Frame(gf)
        ca_f.grid(row=4, column=1, sticky="ew")
        # row 1
        cf2 = tk.Frame(ca_f)
        cf2.pack(fill=tk.X)
        self.marker_global = tk.BooleanVar(value=True)
        tk.Checkbutton(cf2, text="marker", variable=self.marker_global,
                       command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf2, text="size").pack(side=tk.LEFT, padx=(6, 0))
        self.marker_size_global = tk.DoubleVar(value=7.0)   # default 7
        tk.Spinbox(cf2, from_=1, to=20, increment=0.5,
                   textvariable=self.marker_size_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf2, text="lw").pack(side=tk.LEFT, padx=(6, 0))
        self.line_width_global = tk.DoubleVar(value=2.0)    # default 2
        tk.Spinbox(cf2, from_=0.5, to=5, increment=0.1,
                   textvariable=self.line_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        # row 2 (spine/tick width/length)
        cf3 = tk.Frame(ca_f)
        cf3.pack(fill=tk.X, pady=(2, 0))
        tk.Label(cf3, text="spine").pack(side=tk.LEFT, padx=(0, 0))
        self.spine_width_global = tk.DoubleVar(value=1.0)   # default 1
        tk.Spinbox(cf3, from_=0.5, to=5, increment=0.1,
                   textvariable=self.spine_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf3, text="tick w").pack(side=tk.LEFT, padx=(6, 0))
        self.tick_width_global = tk.DoubleVar(value=1.0)    # default 1
        tk.Spinbox(cf3, from_=0.5, to=3, increment=0.5,
                   textvariable=self.tick_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf3, text="tick len").pack(side=tk.LEFT, padx=(6, 0))
        self.tick_len_global = tk.DoubleVar(value=1.0)      # default 1 (ratio)
        tk.Spinbox(cf3, from_=0.5, to=3, increment=0.5,
                   textvariable=self.tick_len_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)

        # unit display
        tk.Label(gf, text="Unit Display:").grid(row=5, column=0, sticky="w")
        uf = tk.Frame(gf)
        uf.grid(row=5, column=1, sticky="ew")
        self.unit_display_var = tk.StringVar(value="mA/cm²")   # default mA/cm²
        tk.OptionMenu(uf, self.unit_display_var, 'A/cm²', 'mA/cm²', 'µA/cm²', 'A',
                      command=lambda _: self.redraw()).pack(side=tk.LEFT)

        # font
        tk.Label(gf, text="Font:").grid(row=6, column=0, sticky="w")
        self.font_var = tk.StringVar(value='Arial')   # default Arial
        fonts = ['Arial', 'DejaVu Sans', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(gf, self.font_var, *fonts, command=lambda _: self._apply_global()).grid(row=6, column=1, sticky="ew")

        # font size (title + tick)
        tk.Label(gf, text="Title Size:").grid(row=7, column=0, sticky="w")
        fs_f = tk.Frame(gf)
        fs_f.grid(row=7, column=1, sticky="ew")
        self.title_size_var = tk.IntVar(value=18)   # default 18
        ts_spin = tk.Spinbox(fs_f, from_=6, to=40, textvariable=self.title_size_var, width=4,
                             command=self._apply_global)
        ts_spin.pack(side=tk.LEFT)
        ts_spin.bind('<Return>', lambda e: self._apply_global())
        ts_spin.bind('<FocusOut>', lambda e: self._apply_global())
        # bold checkbox
        self.title_bold_var = tk.BooleanVar(value=False)
        tk.Checkbutton(fs_f, text="Bold", variable=self.title_bold_var,
                       command=self._apply_global).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(fs_f, text="Tick:").pack(side=tk.LEFT, padx=(8, 0))
        self.tick_size_var = tk.IntVar(value=18)   # default 18
        tk_spin = tk.Spinbox(fs_f, from_=6, to=40, textvariable=self.tick_size_var, width=4,
                             command=self._apply_global)
        tk_spin.pack(side=tk.LEFT)
        tk_spin.bind('<Return>', lambda e: self._apply_global())
        tk_spin.bind('<FocusOut>', lambda e: self._apply_global())

        # aspect ratio
        tk.Label(gf, text="Aspect Ratio:").grid(row=8, column=0, sticky="w")
        self.fig_ratio_var = tk.StringVar(value="4:3")   # default 4:3
        tk.OptionMenu(gf, self.fig_ratio_var, '4:3', '16:9', '1:1', '3:2',
                      command=lambda _: self.redraw()).grid(row=8, column=1, sticky="ew")

        # ===== Axis settings =====
        tk.Label(left, text="Axis Settings (empty=auto)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        axf = tk.Frame(left)
        axf.pack(fill=tk.X)

        def make_axis_row(parent, row, label, min_var, max_var, n_var, minor_var, minor_n_var, dir_var):
            tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 2))
            f = tk.Frame(parent)
            f.grid(row=row, column=1, sticky="ew")
            tk.Entry(f, textvariable=min_var, width=5).pack(side=tk.LEFT)
            tk.Label(f, text="–").pack(side=tk.LEFT)
            tk.Entry(f, textvariable=max_var, width=5).pack(side=tk.LEFT)
            tk.Label(f, text="n").pack(side=tk.LEFT, padx=(4, 0))
            tk.Entry(f, textvariable=n_var, width=3).pack(side=tk.LEFT)
            tk.Checkbutton(f, text="min", variable=minor_var,
                           command=self.redraw).pack(side=tk.LEFT, padx=(4, 0))
            tk.Entry(f, textvariable=minor_n_var, width=3).pack(side=tk.LEFT)
            tk.OptionMenu(f, dir_var, 'out', 'in',
                          command=lambda _: self.redraw()).pack(side=tk.LEFT, padx=(4, 0))
            parent.columnconfigure(1, weight=1)

        self.xmin_var = tk.StringVar(value="0")    # start default 0
        self.xmax_var = tk.StringVar(value="")
        self.xn_var = tk.StringVar(value="")
        self.xminor_var = tk.BooleanVar(value=True)  # minor ticks default on
        self.xminor_n_var = tk.StringVar(value="4")  # default 4 minors
        self.xdir_var = tk.StringVar(value="out")    # tick dir default out
        self.ymin_var = tk.StringVar(value="0")    # start default 0
        self.ymax_var = tk.StringVar(value="")
        self.yn_var = tk.StringVar(value="")
        self.yminor_var = tk.BooleanVar(value=True)  # minor ticks default on
        self.yminor_n_var = tk.StringVar(value="4")
        self.ydir_var = tk.StringVar(value="out")

        make_axis_row(axf, 0, "X:", self.xmin_var, self.xmax_var, self.xn_var, self.xminor_var, self.xminor_n_var, self.xdir_var)
        make_axis_row(axf, 1, "Y:", self.ymin_var, self.ymax_var, self.yn_var, self.yminor_var, self.yminor_n_var, self.ydir_var)

        tk.Button(left, text="Apply Axis", command=self.redraw).pack(fill=tk.X, pady=(2, 0))

        gf.columnconfigure(1, weight=1)

        # ===== Annotations =====
        tk.Label(left, text="Annotations", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        btn_row3 = tk.Frame(left)
        btn_row3.pack(fill=tk.X)
        tk.Button(btn_row3, text="+ Text", command=self.add_text_annotation).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row3, text="+ Line", command=self.add_line_annotation).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row3, text="✕ Clear", command=self.clear_annotations).pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ===== Output =====
        action_row = tk.Frame(left)
        action_row.pack(fill=tk.X, pady=(10, 2))
        tk.Button(action_row, text="🔄 Redraw", command=self.redraw, bg="#e8f0fe").pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(action_row, text="💾 Save", command=self.save_figure, bg="#e6f4e6").pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(action_row, text="📊 Export CSV", command=self.export_csv, bg="#fff3e0").pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ===== Right plot area =====
        self.plot_frame = tk.Frame(self.root)
        self.plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=4, pady=4)

    def _new_figure(self):
        for w in self.plot_frame.winfo_children():
            w.destroy()
        # aspect ratio（default 4:3）
        ratio = getattr(self, 'fig_ratio_var', None)
        r = ratio.get() if ratio else '4:3'
        sizes = {'4:3': (7, 5.25), '16:9': (8, 4.5), '1:1': (6, 6), '3:2': (7.5, 5)}
        w, h = sizes.get(r, (7, 5.25))
        self.fig = plt.Figure(figsize=(w, h), dpi=100)
        self.ax = self.fig.add_subplot(111)
        # spine linewidth (global, default 1)
        lw = getattr(self, 'spine_width_global', None)
        spine_lw = lw.get() if lw else 1.0
        for sp in self.ax.spines.values():
            sp.set_linewidth(spine_lw)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        # fixed canvas size (figsize×dpi)
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
    # upload
    # ------------------------------------------------------------------
    # auto color/marker cycling (7×10=70 combos)
    AUTO_MARKERS = ['o', 's', '^', 'v', 'D', 'x', '+', '*', 'p', 'h']

    def _pick_color(self, idx):
        return self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]

    def _auto_style(self, idx):
        """Assign color + marker in sequence"""
        color = self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]
        marker = self.AUTO_MARKERS[idx % len(self.AUTO_MARKERS)]
        return color, marker

    def add_curve(self):
        files = filedialog.askopenfilenames(
            title="Select CSV",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                df = pd.read_csv(f)
                if len(df.columns) < 2:
                    messagebox.showerror("Format Error", f"{os.path.basename(f)}\nNeed at least 2 columns")
                    continue
                # column picker dialog (unit + active area)
                name = os.path.splitext(os.path.basename(f))[0]
                info = self._ask_columns(df, name)
                if info is None:
                    continue
                v_col, i_col, unit, area = info
                color, marker = self._auto_style(len(self.curves))
                self.curves.append(ThreeElectrodeData(
                    name, df, v_col, i_col, color,
                    current_unit=unit, active_area=area, marker_style=marker))
                self._refresh_list()
            except Exception as e:
                messagebox.showerror("Load Failed", f"{f}\n{e}")
        self.redraw()

    def _ask_columns(self, df, fname):
        """Dialog: V/I columns + current unit + active area"""
        win = tk.Toplevel(self.root)
        win.title(f"Data Setup: {fname}")
        win.geometry("420x260")
        win.transient(self.root)
        win.grab_set()

        cols = list(df.columns)
        result = {'v': None, 'i': None, 'unit': 'A/cm2', 'area': 1.0}

        tk.Label(win, text=f"File: {fname}", font=("Segoe UI", 9, "bold")).pack(pady=(8, 2))
        tk.Label(win, text="Select V/I columns and current unit").pack()

        rf = tk.Frame(win); rf.pack(pady=4)
        tk.Label(rf, text="Voltage (V):").pack(side=tk.LEFT)
        v_var = tk.StringVar(value=cols[0])
        tk.OptionMenu(rf, v_var, *cols).pack(side=tk.LEFT)

        cf = tk.Frame(win); cf.pack(pady=4)
        tk.Label(cf, text="Current (I):").pack(side=tk.LEFT)
        i_var = tk.StringVar(value=cols[1] if len(cols) > 1 else cols[0])
        tk.OptionMenu(cf, i_var, *cols).pack(side=tk.LEFT)

        uf = tk.Frame(win); uf.pack(pady=4)
        tk.Label(uf, text="Current Unit:").pack(side=tk.LEFT)
        unit_var = tk.StringVar(value='mA/cm2')
        tk.OptionMenu(uf, unit_var, 'A', 'A/cm2', 'mA/cm2', 'uA/cm2').pack(side=tk.LEFT)
        tk.Label(uf, text="   Active Area (cm²):").pack(side=tk.LEFT)
        area_var = tk.StringVar(value="1")
        area_entry = tk.Entry(uf, textvariable=area_var, width=6)
        area_entry.pack(side=tk.LEFT)

        def on_unit_change(*_):
            # active area only needed for unit A
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
        tk.Button(bf, text="OK", command=ok, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT, padx=5)

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
        # reassign color/marker after sort
        self._reassign_styles()
        self._refresh_list()
        self.listbox.selection_set(new)
        self.redraw()

    def _reassign_styles(self):
        """Reassign color/marker by list order"""
        for i, c in enumerate(self.curves):
            color, marker = self._auto_style(i)
            c.color = color
            c.marker_style = marker

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, c in enumerate(self.curves):
            self.listbox.insert(tk.END, f"{i+1}. {c.name}")

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------
    def edit_props(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Info", "Please select a curve first")
            return
        self._edit_curve_props(sel[0])

    def _edit_curve_props(self, idx):
        c = self.curves[idx]
        win = tk.Toplevel(self.root)
        win.title(f"Properties: {c.name}")
        win.geometry("400x480")

        tk.Label(win, text=f"Curve: {c.name} (V: {c.v_col}, I: {c.i_col})",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=4)

        # custom label
        tf = tk.Frame(win); tf.pack(fill=tk.X, padx=8)
        tk.Label(tf, text="Legend Label:").pack(side=tk.LEFT)
        label_var = tk.StringVar(value=c.name)
        tk.Entry(tf, textvariable=label_var, width=22).pack(side=tk.LEFT)
        def set_label():
            c.name = label_var.get()
            self._refresh_list()
            self.redraw()
        tk.Button(tf, text="Apply", command=set_label).pack(side=tk.LEFT, padx=4)

        # color
        cf = tk.Frame(win); cf.pack(fill=tk.X, padx=8)
        tk.Label(cf, text="Color:").pack(side=tk.LEFT)
        color_btn = tk.Button(cf, bg=c.color, width=4,
                              command=lambda: self._pick_color_btn(color_btn, c))
        color_btn.pack(side=tk.LEFT, padx=4)

        # ×(-1) toggle
        nf = tk.Frame(win); nf.pack(fill=tk.X, padx=8)
        neg_var = tk.BooleanVar(value=c.negate)
        tk.Checkbutton(nf, text="Current ×(-1)", variable=neg_var,
                       command=lambda: (setattr(c, 'negate', neg_var.get()), self.redraw())).pack(side=tk.LEFT)
        negv_var = tk.BooleanVar(value=c.negate_v)
        tk.Checkbutton(nf, text="Voltage ×(-1)", variable=negv_var,
                       command=lambda: (setattr(c, 'negate_v', negv_var.get()), self.redraw())).pack(side=tk.LEFT, padx=(8, 0))

        # linestyle (per-dataset)
        lf = tk.Frame(win); lf.pack(fill=tk.X, padx=8)
        tk.Label(lf, text="Linestyle:").pack(side=tk.LEFT)
        ls_var = tk.StringVar(value=c.line_style)
        tk.OptionMenu(lf, ls_var, '-', '--', '-.', ':',
                      command=lambda v: (setattr(c, 'line_style', v), self.redraw())).pack(side=tk.LEFT)

        # marker style (per-dataset)
        mf = tk.Frame(win); mf.pack(fill=tk.X, padx=8)
        tk.Label(mf, text="Marker style:").pack(side=tk.LEFT)
        ms_var = tk.StringVar(value=c.marker_style)
        markers = ['o', 's', '^', 'v', 'D', 'x', '+', '*', '|', 'None']
        tk.OptionMenu(mf, ms_var, *markers,
                      command=lambda v: (setattr(c, 'marker_style', v), self.redraw())).pack(side=tk.LEFT, padx=4)

        # E0 (equilibrium potential for η) + R (resistance for iR)
        e0f = tk.Frame(win); e0f.pack(fill=tk.X, padx=8, pady=(4, 0))
        tk.Label(e0f, text="E0 (V) η:").pack(side=tk.LEFT)
        e0_var = tk.StringVar(value=str(c.e0))
        e0_entry = tk.Entry(e0f, textvariable=e0_var, width=8)
        e0_entry.pack(side=tk.LEFT, padx=4)
        def set_e0():
            try: c.e0 = float(e0_var.get())
            except ValueError: pass
            self.redraw()
        e0_entry.bind('<Return>', lambda e: set_e0())
        tk.Button(e0f, text="Apply", command=set_e0).pack(side=tk.LEFT, padx=4)

        rf = tk.Frame(win); rf.pack(fill=tk.X, padx=8)
        tk.Label(rf, text="R (Ω) iR:").pack(side=tk.LEFT)
        r_var = tk.StringVar(value=str(c.r))
        r_entry = tk.Entry(rf, textvariable=r_var, width=8)
        r_entry.pack(side=tk.LEFT, padx=4)
        def set_r():
            try: c.r = float(r_var.get())
            except ValueError: pass
            self.redraw()
        r_entry.bind('<Return>', lambda e: set_r())
        tk.Button(rf, text="Apply", command=set_r).pack(side=tk.LEFT, padx=4)

    def _pick_color_btn(self, btn, curve):
        rgb, _ = colorchooser.askcolor(color=curve.color, title="Choose Color")
        if rgb:
            curve.color = '#%02x%02x%02x' % rgb
            btn.config(bg=curve.color)
            self.redraw()

    # ------------------------------------------------------------------
    # global
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
    # potential reference conversion
    # ------------------------------------------------------------------
    ELEC_E0 = {
        'vs RHE': 0.0,
        'vs SHE': 0.0,
        'SCE': 0.241,
        'Ag/AgCl': None,   # by KCl conc
        'Hg/HgO': 0.098,
    }
    KCL_E0 = {   # Ag/AgCl by KCl conc (vs SHE)
        'sat.': 0.197,
        '3.5M': 0.205,
        '3M': 0.210,
        '1M': 0.235,
    }

    def _get_elec_e0(self):
        """Reference electrode E0 (vs SHE, V)"""
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
        """Nernst slope with temperature correction"""
        T = self._get_temp() + 273.15
        return 0.05916 * T / 298.15

    def _ref_conversion(self, V):
        """Convert source electrode → RHE:
        E_RHE = E_raw + E0_electrode + slope×pH
        Raw: no conversion
        """
        if self.ref_var.get() == 'Raw':
            return np.asarray(V, dtype=float)
        e0 = self._get_elec_e0()
        ph = self._get_ph()
        slope = self._nernst_slope()
        return np.asarray(V, dtype=float) + e0 + slope * ph

    # ------------------------------------------------------------------
    # Annotations
    # ------------------------------------------------------------------
    def add_text_annotation(self):
        x = simpledialog.askfloat("Text Annotation", "X pos:", initialvalue=0.5)
        if x is None: return
        y = simpledialog.askfloat("Text Annotation", "Y pos:", initialvalue=0.7)
        if y is None: return
        text = simpledialog.askstring("Text Annotation", "Text:")
        if not text: return
        self.annotations.append(('text', x, y, text, '#000000'))
        self.redraw()

    def add_line_annotation(self):
        x1 = simpledialog.askfloat("Line Annotation", "Start X:", initialvalue=0.3)
        if x1 is None: return
        y1 = simpledialog.askfloat("Line Annotation", "Start Y:", initialvalue=0.8)
        if y1 is None: return
        x2 = simpledialog.askfloat("Line Annotation", "End X:", initialvalue=0.5)
        if x2 is None: return
        y2 = simpledialog.askfloat("Line Annotation", "End Y:", initialvalue=0.8)
        if y2 is None: return
        self.annotations.append(('line', x1, y1, x2, y2, '#ff0000'))
        self.redraw()

    def clear_annotations(self):
        self.annotations.clear()
        self.redraw()

    # ------------------------------------------------------------------
    # legend interaction (drag/select+dbl-click)
    # ------------------------------------------------------------------
    def _on_legend_press(self, event):
        if event.inaxes is None: return
        leg = self.ax.get_legend()
        if leg is None: return
        if leg.get_window_extent().contains(event.x, event.y):
            # double-click → settings
            if event.dblclick:
                self._legend_settings()
                return
            # single-click → select + drag
            self.legend_selected = True
            self._draw_legend_selection(leg)
            self.legend_dragging = True
            self._drag_last = (event.x, event.y)
            leg_win = leg.get_window_extent()
            inv = self.fig.transFigure.inverted()
            fx, fy = inv.transform((leg_win.x0, leg_win.y0))
            self._drag_anchor = (fx, fy)
            # bind arrow keys (Tk bind more reliable)
            self.canvas.get_tk_widget().focus_set()
            self.canvas.get_tk_widget().bind('<KeyPress>', self._on_legend_key_tk)

    def _on_legend_key(self, event):
        """Arrow-key legend nudge (Matplotlib version)"""
        if not getattr(self, 'legend_selected', False):
            return
        leg = self.ax.get_legend()
        if leg is None: return
        step = 0.005   # 0.5% fig step
        ax, ay = self._drag_anchor
        if event.key == 'left':
            ax -= step
        elif event.key == 'right':
            ax += step
        elif event.key == 'up':
            ay += step
        elif event.key == 'down':
            ay -= step
        else:
            return
        leg.set_bbox_to_anchor((ax, ay), transform=self.fig.transFigure)
        self._drag_anchor = (ax, ay)
        self._legend_pos_custom = True
        self.canvas.draw_idle()

    def _on_legend_key_tk(self, event):
        """Tk key event (arrow-key legend nudge)"""
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
        """Draw red dashed selection box on legend"""
        # remove old selection box
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
        rect._legend_sel = True   # mark as selection box
        self.fig.patches.append(rect)
        self._legend_sel_patches.append(rect)
        self.canvas.draw_idle()

    def _legend_settings(self):
        """Double-click legend → settings dialog (frame/size/font)"""
        leg = self.ax.get_legend()
        if leg is None: return
        win = tk.Toplevel(self.root)
        win.title("Legend Settings")
        win.geometry("320x220")
        win.transient(self.root)
        win.grab_set()

        # frame toggle
        ff = tk.Frame(win); ff.pack(fill=tk.X, padx=10, pady=6)
        frame_var = tk.BooleanVar(value=leg.get_frame_on())
        tk.Checkbutton(ff, text="Show Frame", variable=frame_var,
                       command=lambda: (leg.set_frame_on(frame_var.get()),
                                        self.canvas.draw_idle())).pack(side=tk.LEFT)

        # font size
        sf = tk.Frame(win); sf.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(sf, text="Font Size:").pack(side=tk.LEFT)
        size_var = tk.IntVar(value=int(leg.get_texts()[0].get_fontsize()) if leg.get_texts() else 10)
        size_spin = tk.Spinbox(sf, from_=6, to=40, textvariable=size_var, width=5)
        size_spin.pack(side=tk.LEFT)

        # font
        ff2 = tk.Frame(win); ff2.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(ff2, text="Font:").pack(side=tk.LEFT)
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
        tk.Button(bf, text="Apply", command=apply_settings, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="Cancel", command=win.destroy, width=10).pack(side=tk.LEFT, padx=5)

    def _on_legend_drag(self, event):
        if not self.legend_dragging or event.inaxes is None: return
        leg = self.ax.get_legend()
        if leg is None: return
        # mouse delta → legend anchor
        last_x, last_y = self._drag_last
        dx = event.x - last_x
        dy = event.y - last_y
        self._drag_last = (event.x, event.y)
        ax, ay = self._drag_anchor
        # anchor is figure fraction
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
        # red box gone, selection kept
        # remove all selection boxes + redraw
        for p in list(self._legend_sel_patches):
            try:
                p.remove()
            except Exception:
                pass
        self._legend_sel_patches = []
        # clear leftover selection boxes
        keep = [p for p in self.fig.patches
                if not getattr(p, '_legend_sel', False)]
        self.fig.patches[:] = keep
        self.canvas.draw()   # force sync redraw

    # ------------------------------------------------------------------
    # minor ticks
    # ------------------------------------------------------------------
    def _apply_minor(self, axis='x'):
        """Apply minor ticks (n per major interval)"""
        from matplotlib.ticker import MultipleLocator

        if axis == 'x':
            ax = self.ax
            enabled = self.xminor_var.get()
            n_str = self.xminor_n_var.get()
            get_lim = ax.get_xlim
            set_loc = ax.xaxis.set_minor_locator
            major_ticks = ax.get_xticks()
        elif axis == 'y':
            ax = self.ax
            enabled = self.yminor_var.get()
            n_str = self.yminor_n_var.get()
            get_lim = ax.get_ylim
            set_loc = ax.yaxis.set_minor_locator
            major_ticks = ax.get_yticks()

        if not enabled:
            ax.minorticks_off()
            return

        try:
            n = int(n_str) if n_str else 4   # default 4 minors per major
            n = max(1, min(n, 20))
        except ValueError:
            n = 4

        # enable minors
        ax.minorticks_on()

        # major step → minor step
        if len(major_ticks) >= 2:
            major_step = abs(major_ticks[1] - major_ticks[0])
            if major_step > 0:
                set_loc(MultipleLocator(major_step / (n + 1)))
                return
        # fallback: axis range
        lo, hi = get_lim()
        if hi > lo:
            auto_step = (hi - lo) / 50.0
            set_loc(MultipleLocator(auto_step))

    # ------------------------------------------------------------------
    # plotting
    # ------------------------------------------------------------------
    def redraw(self):
        # rebuild on aspect change
        sizes = {'4:3': (7, 5.25), '16:9': (8, 4.5), '1:1': (6, 6), '3:2': (7.5, 5)}
        r = self.fig_ratio_var.get() if hasattr(self, 'fig_ratio_var') else '4:3'
        target = sizes.get(r, (7, 5.25))
        if self.fig.get_size_inches()[0] != target[0] or self.fig.get_size_inches()[1] != target[1]:
            self._new_figure()
        self.ax.clear()
        # clear leftover legend box
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
        # spine linewidth (Global Settings)
        spine_lw = self.spine_width_global.get()
        for sp in self.ax.spines.values():
            sp.set_linewidth(spine_lw)

        invert = self.axis_var.get().startswith("X=I")   # X=I → invert
        tafel = self.ymode_var.get().startswith("Tafel")
        unit_txt = self.unit_display_var.get()   # A/cm² / mA/cm² / µA/cm² / A

        # axis labels
        vlabel = 'Voltage (V vs RHE)' if self.ref_var.get() == 'vs RHE' else 'Voltage (V)'
        if self.eta_var.get():
            vlabel = 'Overpotential η (V)'
        ilabel = f'Current Density ({unit_txt})'
        if tafel:
            xlabel = vlabel
            ylabel = f'log|j| ({unit_txt})'
        elif invert:
            xlabel = ilabel
            ylabel = vlabel
        else:
            xlabel = vlabel
            ylabel = ilabel

        # display scale factor
        if unit_txt == 'mA/cm²':
            disp_scale = 1000.0
        elif unit_txt == 'µA/cm²':
            disp_scale = 1e6
        elif unit_txt == 'A':
            disp_scale = None   # per-curve active_area
        else:
            disp_scale = 1.0

        for c in self.curves:
            c.invert_xy = invert
            v = c.get_v()                          # raw voltage
            j = c.get_i_density()                  # A/cm² (internal)
            # reference potential conversion (source → RHE) or Raw
            v_conv = self._ref_conversion(v)
            # iR correction: V - i×R = V - (j×area)×R
            if self.ir_var.get():
                v_conv = v_conv - c.get_current_A() * c.r
            # η overpotential: V - E0
            if self.eta_var.get():
                v_conv = v_conv - c.e0
            # display current density
            if disp_scale is None:
                j_disp = j * c.active_area   # display A (raw)
            else:
                j_disp = j * disp_scale
            # axis role + Tafel
            if tafel:
                x_plot = v_conv
                y_plot = np.log10(np.abs(j_disp))
            elif invert:
                x_plot = j_disp
                y_plot = v_conv
            else:
                x_plot = v_conv
                y_plot = j_disp
            # marker: global toggle + per-dataset
            marker = c.marker_style if (self.marker_global.get()
                                        and c.marker_style != 'None') else None
            self.ax.plot(x_plot, y_plot, label=c.name, color=c.color,
                         linestyle=c.line_style, linewidth=self.line_width_global.get(),
                         marker=marker, markersize=self.marker_size_global.get())

        # Annotations
        for a in self.annotations:
            if a[0] == 'text':
                _, x, y, text, color = a
                self.ax.annotate(text, (x, y), color=color,
                                 fontsize=self.title_size - 1, fontname=self.font_name)
            elif a[0] == 'line':
                _, x1, y1, x2, y2, color = a
                self.ax.plot([x1, x2], [y1, y2], color=color, lw=1.5)

        # layout (bold toggle)
        fw = 'bold' if self.title_bold else 'normal'
        self.ax.set_xlabel(xlabel, fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        self.ax.set_ylabel(ylabel, fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        self.ax.tick_params(labelsize=self.tick_size)
        # tick direction (per-axis in/out)
        xdir = 'in' if self.xdir_var.get() == 'in' else 'out'
        ydir = 'in' if self.ydir_var.get() == 'in' else 'out'
        # tick width/length (major/minor ratio)
        tw = self.tick_width_global.get()
        tl = self.tick_len_global.get()
        self.ax.tick_params(axis='x', which='both', direction=xdir,
                            width=tw, length=3.5*tl)
        self.ax.tick_params(axis='y', which='both', direction=ydir,
                            width=tw, length=3.5*tl)
        # minor tick ratio (major × 0.6)
        self.ax.tick_params(axis='x', which='minor', length=2.1*tl)
        self.ax.tick_params(axis='y', which='minor', length=2.1*tl)

        # axis range: auto unless user sets
        if self.curves:
            self.ax.relim()
            self.ax.autoscale()
            # X axis range
            try:
                if self.xmin_var.get() or self.xmax_var.get():
                    xmin = float(self.xmin_var.get()) if self.xmin_var.get() else None
                    xmax_u = float(self.xmax_var.get()) if self.xmax_var.get() else None
                    self.ax.set_xlim(xmin, xmax_u)
            except ValueError:
                pass
            # Y1 axis range
            try:
                if self.ymin_var.get() or self.ymax_var.get():
                    ymin = float(self.ymin_var.get()) if self.ymin_var.get() else None
                    ymax_u = float(self.ymax_var.get()) if self.ymax_var.get() else None
                    self.ax.set_ylim(ymin, ymax_u)
            except ValueError:
                pass

            # X n-ticks
            try:
                if self.xn_var.get():
                    n = int(self.xn_var.get())
                    if n > 1:
                        lo, hi = self.ax.get_xlim()
                        self.ax.set_xticks(np.linspace(lo, hi, n))
            except ValueError:
                pass
            # X minor ticks
            self._apply_minor(axis='x')
            # Y1 n-ticks
            try:
                if self.yn_var.get():
                    n = int(self.yn_var.get())
                    if n > 1:
                        lo, hi = self.ax.get_ylim()
                        self.ax.set_yticks(np.linspace(lo, hi, n))
            except ValueError:
                pass
            # Y1 minor ticks
            self._apply_minor(axis='y')

        if self.curves:
            leg = self.ax.legend(loc='upper right', frameon=True,
                                 fontsize=14, prop={'family': 'Arial'})
            # preserve legend position if customized
            if getattr(self, '_legend_pos_custom', False) and self._drag_anchor is not None:
                leg.set_bbox_to_anchor(self._drag_anchor, transform=self.fig.transFigure)
            leg.set_draggable(True)
            self._legend = leg

        # unify tick font (after set_xticks)
        # tick and title share font
        for lbl in self.ax.get_xticklabels() + self.ax.get_yticklabels():
            lbl.set_fontname(self.font_name)

        self.fig.tight_layout()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    def save_figure(self):
        dpi = simpledialog.askinteger("Save", "DPI (suggest 300):", initialvalue=300, minvalue=50, maxvalue=1200)
        if dpi is None:
            dpi = 300
        f = filedialog.asksaveasfilename(
            title="Save Figure", defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("SVG", "*.svg"), ("PDF", "*.pdf")])
        if not f:
            return
        self.fig.savefig(f, dpi=dpi, bbox_inches='tight')
        messagebox.showinfo("Done", f"Saved: {f} (dpi={dpi})")

    def export_csv(self):
        """Export merged CSV: V, I_density, label"""
        if not self.curves:
            messagebox.showinfo("Info", "No curves to export")
            return
        f = filedialog.asksaveasfilename(
            title="Export CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="three_electrode_data.csv")
        if not f:
            return
        rows = []
        for c in self.curves:
            v = self._ref_conversion(c.get_v())
            i = c.get_i_density()
            for j in range(len(v)):
                rows.append({'V (V)': v[j], 'I_density (A/cm2)': i[j], 'label': c.name})
        out = pd.DataFrame(rows)
        out.to_csv(f, index=False)
        messagebox.showinfo("Done", f"Exported {len(rows)} rows → {f}")


# ------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = ThreeElectrodePlotterApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
