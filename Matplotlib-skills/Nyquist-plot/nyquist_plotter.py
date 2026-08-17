#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Nyquist Plotter — EIS Nyquist GUI (Tkinter + Matplotlib)

Features:
  1. Parse DRTxECM export CSV, auto-extract:
     - raw data → marker only
     - fitted data → solid line
  2. Also supports standard EIS CSV (f, Z', Z'') -- manual columns
  3. Nyquist convention: X=Z', Y=-Z'' (arc up)
  4. X/Y equal aspect (set_aspect equal) -- switchable
  5. Full GUI: list, sort, properties, legend, axis

For: EIS analysis (fuel cells, electrolyzers)

Deps: pip install matplotlib pandas numpy
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
# data class
# ------------------------------------------------------------------
class NyquistData:
    """An EIS dataset (raw + fitted)"""
    def __init__(self, name, df, z_col, zpp_col,
                 color, has_fitted=False, branches=None,
                 marker_on=True, marker_style='o', marker_size=7,
                 line_style='-', line_width=2.0,
                 fitted_marker_style='o', fitted_line_style='-'):
        self.name = name
        self.df = df.copy()          # original DataFrame
        self.z_col = z_col           # Z' column
        self.zpp_col = zpp_col       # Z'' column
        self.color = color
        self.has_fitted = has_fitted  # whether fitted data exists
        self.branches = branches if branches else []  # [(z', zpp'), ...]
        self.marker_on = marker_on    # raw uses marker (default on)
        self.marker_style = marker_style
        self.marker_size = marker_size
        self.line_style = line_style  # raw extra linestyle (default None → marker only)
        self.line_width = line_width
        self.fitted_marker_style = fitted_marker_style  # fitted marker (default None → line only)
        self.fitted_line_style = fitted_line_style      # fitted linestyle (default solid)

    def _nyquist_y(self, zpp):
        """Nyquist Y: auto-detect sign convention
        - if median Z'' > 0 (already-negated) → use as-is
        - if median Z'' < 0 (standard) → negate so arc points up
        """
        arr = np.asarray(zpp, dtype=float)
        if len(arr) == 0:
            return arr
        if np.median(arr) > 0:
            return arr
        return -arr

    def get_raw_xy(self):
        """Raw Nyquist"""
        z = self.df[self.z_col].astype(float).values
        zpp = self.df[self.zpp_col].astype(float).values
        return z, self._nyquist_y(zpp)

    def get_fitted_xy(self):
        """Fitted Nyquist"""
        if not self.has_fitted:
            return None
        fz = self.df['fitted_z_prime'].astype(float).values
        fzpp = self.df['fitted_z_double_prime'].astype(float).values
        return fz, self._nyquist_y(fzpp)


# ------------------------------------------------------------------
# Main window
# ------------------------------------------------------------------
class NyquistPlotterApp:
    # Okabe-Ito colorblind-safe palette (7 colors)
    DEFAULT_COLORS = ['#0072B2', '#E69F00', '#56B4E9', '#009E73',
                      '#F0E442', '#CC79A7', '#D55E00']
    # auto color/marker cycling (7×10=70 combos)
    AUTO_MARKERS = ['o', 's', '^', 'v', 'D', 'x', '+', '*', 'p', 'h']

    def __init__(self, root):
        self.root = root
        self.root.title("Nyquist Plotter — EIS Nyquist")
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
        self._legend_cfg = {'fontsize': 12, 'fontname': 'Arial', 'frameon': True}  # Legend settings (persisted)
        self.aspect_equal = True   # X/Y equal aspect (default on)

        self._build_ui()
        self._new_figure()
        self.redraw()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        main = tk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True)

        # left controls
        left = tk.Frame(main, width=320)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left.pack_propagate(False)

        # data list
        tk.Label(left, text="EIS Data", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, height=8)
        self.listbox.pack(fill=tk.X)
        bf = tk.Frame(left)
        bf.pack(fill=tk.X, pady=2)
        tk.Button(bf, text="+ Add", command=self.add_curve, width=8).pack(side=tk.LEFT)
        tk.Button(bf, text="- Remove", command=self.remove_curve, width=8).pack(side=tk.LEFT)
        tk.Button(bf, text="↑", command=lambda: self.move_item(-1), width=3).pack(side=tk.LEFT)
        tk.Button(bf, text="↓", command=lambda: self.move_item(1), width=3).pack(side=tk.LEFT)
        tk.Button(bf, text="✎ Properties", command=self.edit_props, width=8).pack(side=tk.LEFT)

        # Global Settings
        gf = tk.LabelFrame(left, text="Global Settings")
        gf.pack(fill=tk.X, pady=(6, 0))

        # equal aspect
        tk.Label(gf, text="Equal Aspect:").grid(row=0, column=0, sticky="w")
        self.aspect_var = tk.BooleanVar(value=True)
        tk.Checkbutton(gf, text="(Nyquist convention)", variable=self.aspect_var,
                       command=self.redraw).grid(row=0, column=1, sticky="w")
        # Show branch (dashed)
        self.branch_var = tk.BooleanVar(value=False)
        tk.Checkbutton(gf, text="Show branch (dashed)", variable=self.branch_var,
                       command=self.redraw).grid(row=0, column=1, sticky="e")

        # curve style (global, 2 rows in container)
        tk.Label(gf, text="Curve Style:").grid(row=1, column=0, sticky="nw")
        ca_f = tk.Frame(gf)
        ca_f.grid(row=1, column=1, sticky="ew")
        # row 1
        cf2 = tk.Frame(ca_f)
        cf2.pack(fill=tk.X)
        self.marker_global = tk.BooleanVar(value=True)
        tk.Checkbutton(cf2, text="marker", variable=self.marker_global,
                       command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf2, text="size").pack(side=tk.LEFT, padx=(6, 0))
        self.marker_size_global = tk.DoubleVar(value=4.0)   # default 4
        tk.Spinbox(cf2, from_=1, to=20, increment=0.5,
                   textvariable=self.marker_size_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf2, text="line width").pack(side=tk.LEFT, padx=(6, 0))
        self.line_width_global = tk.DoubleVar(value=1.0)    # default 1
        tk.Spinbox(cf2, from_=0.5, to=5, increment=0.1,
                   textvariable=self.line_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        # row 2 (spine/tick width/length)
        cf3 = tk.Frame(ca_f)
        cf3.pack(fill=tk.X, pady=(2, 0))
        tk.Label(cf3, text="spine width").pack(side=tk.LEFT, padx=(0, 0))
        self.spine_width_global = tk.DoubleVar(value=1.1)   # default 1.1
        tk.Spinbox(cf3, from_=0.5, to=5, increment=0.1,
                   textvariable=self.spine_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf3, text="tickBold").pack(side=tk.LEFT, padx=(6, 0))
        self.tick_width_global = tk.DoubleVar(value=1.0)
        tk.Spinbox(cf3, from_=0.5, to=3, increment=0.5,
                   textvariable=self.tick_width_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)
        tk.Label(cf3, text="tick length").pack(side=tk.LEFT, padx=(6, 0))
        self.tick_len_global = tk.DoubleVar(value=1.5)      # default 1.5
        tk.Spinbox(cf3, from_=0.5, to=3, increment=0.5,
                   textvariable=self.tick_len_global, width=4,
                   command=self.redraw).pack(side=tk.LEFT)

        # font
        tk.Label(gf, text="Font:").grid(row=2, column=0, sticky="w")
        self.font_var = tk.StringVar(value='Arial')
        fonts = ['Arial', 'DejaVu Sans', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(gf, self.font_var, *fonts, command=lambda _: self._apply_global()).grid(row=2, column=1, sticky="ew")

        # font size (title + tick)
        tk.Label(gf, text="Title Size:").grid(row=3, column=0, sticky="w")
        fs_f = tk.Frame(gf)
        fs_f.grid(row=3, column=1, sticky="ew")
        self.title_size_var = tk.IntVar(value=18)
        ts_spin = tk.Spinbox(fs_f, from_=6, to=40, textvariable=self.title_size_var, width=4,
                             command=self._apply_global)
        ts_spin.pack(side=tk.LEFT)
        ts_spin.bind('<Return>', lambda e: self._apply_global())
        ts_spin.bind('<FocusOut>', lambda e: self._apply_global())
        self.title_bold_var = tk.BooleanVar(value=False)
        tk.Checkbutton(fs_f, text="Bold", variable=self.title_bold_var,
                       command=self._apply_global).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(fs_f, text="Tick:").pack(side=tk.LEFT, padx=(8, 0))
        self.tick_size_var = tk.IntVar(value=18)
        tk_spin = tk.Spinbox(fs_f, from_=6, to=40, textvariable=self.tick_size_var, width=4,
                             command=self._apply_global)
        tk_spin.pack(side=tk.LEFT)
        tk_spin.bind('<Return>', lambda e: self._apply_global())
        tk_spin.bind('<FocusOut>', lambda e: self._apply_global())

        # aspect ratio
        tk.Label(gf, text="Aspect Ratio:").grid(row=4, column=0, sticky="w")
        self.fig_ratio_var = tk.StringVar(value="4:3")
        tk.OptionMenu(gf, self.fig_ratio_var, '4:3', '16:9', '1:1', '3:2',
                      command=lambda _: self.redraw()).grid(row=4, column=1, sticky="ew")

        # unit + active area (own row)
        tk.Label(gf, text="Unit:").grid(row=5, column=0, sticky="w")
        uf = tk.Frame(gf)
        uf.grid(row=5, column=1, sticky="ew")
        self.unit_var = tk.StringVar(value="Ω")
        tk.OptionMenu(uf, self.unit_var, 'Ω', 'mΩ', 'Ω·cm²', 'mΩ·cm²',
                      command=lambda _: self.redraw()).pack(side=tk.LEFT)
        tk.Label(uf, text="Area:").pack(side=tk.LEFT, padx=(8, 0))
        self.area_var = tk.StringVar(value="1")   # default 1 cm²
        area_entry = tk.Entry(uf, textvariable=self.area_var, width=5)
        area_entry.pack(side=tk.LEFT)
        area_entry.bind('<Return>', lambda e: self.redraw())
        area_entry.bind('<FocusOut>', lambda e: self.redraw())

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
            tk.Label(f, text="N ticks").pack(side=tk.LEFT, padx=(4, 0))
            tk.Entry(f, textvariable=n_var, width=3).pack(side=tk.LEFT)
            tk.Checkbutton(f, text="min", variable=minor_var,
                           command=self.redraw).pack(side=tk.LEFT, padx=(4, 0))
            tk.Label(f, text="n minor").pack(side=tk.LEFT)
            tk.Entry(f, textvariable=minor_n_var, width=3).pack(side=tk.LEFT)
            tk.OptionMenu(f, dir_var, 'out', 'in',
                          command=lambda _: self.redraw()).pack(side=tk.LEFT, padx=(4, 0))
            parent.columnconfigure(1, weight=1)

        self.xmin_var = tk.StringVar(value="")
        self.xmax_var = tk.StringVar(value="")
        self.xn_var = tk.StringVar(value="")
        self.xminor_var = tk.BooleanVar(value=True)
        self.xminor_n_var = tk.StringVar(value="4")
        self.xdir_var = tk.StringVar(value="out")
        self.ymin_var = tk.StringVar(value="")
        self.ymax_var = tk.StringVar(value="")
        self.yn_var = tk.StringVar(value="")
        self.yminor_var = tk.BooleanVar(value=True)
        self.yminor_n_var = tk.StringVar(value="4")
        self.ydir_var = tk.StringVar(value="out")

        make_axis_row(axf, 0, "X:", self.xmin_var, self.xmax_var, self.xn_var, self.xminor_var, self.xminor_n_var, self.xdir_var)
        make_axis_row(axf, 1, "Y:", self.ymin_var, self.ymax_var, self.yn_var, self.yminor_var, self.yminor_n_var, self.ydir_var)

        tk.Button(left, text="Apply Axis", command=self.redraw).pack(fill=tk.X, pady=(2, 0))

        # Annotations
        tk.Label(left, text="Annotations", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        abf = tk.Frame(left)
        abf.pack(fill=tk.X)
        tk.Button(abf, text="+ Text", command=self.add_text_annotation, width=8).pack(side=tk.LEFT)
        tk.Button(abf, text="+ Line", command=self.add_line_annotation, width=8).pack(side=tk.LEFT)
        tk.Button(abf, text="Clear", command=self.clear_annotations, width=8).pack(side=tk.LEFT)

        # Output
        tk.Label(left, text="Output", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(6, 2))
        obf = tk.Frame(left)
        obf.pack(fill=tk.X)
        tk.Button(obf, text="Save", command=self.save_figure, width=10).pack(side=tk.LEFT)
        tk.Button(obf, text="Export CSV", command=self.export_csv, width=10).pack(side=tk.LEFT)

        # right plot area
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
        # spine linewidth
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
    # EIS file parsing
    # ------------------------------------------------------------------
    @staticmethod
    def parse_drtxecm_csv(path):
        """Parse DRTxECM export CSV → (df, has_fitted) or None
        Format: ECM parameter table, data block after 'Merged Frequency Response'
        """
        try:
            with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
                lines = f.readlines()
        except Exception:
            with open(path, 'r', errors='replace') as f:
                lines = f.readlines()

        # find data-block header (has 'Frequency' and 'Z_raw')
        header_idx = None
        for i, ln in enumerate(lines):
            if 'Frequency' in ln and 'Z_raw' in ln:
                header_idx = i
                break
        if header_idx is None:
            return None

        # parse header columns
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
        # column cleanup (strip units/spaces)
        df.columns = [c.split('(')[0].strip().replace(' ', '_') for c in df.columns]
        # verify required columns
        has_fitted = 'Total_Fitted_Z_prime' in df.columns
        # collect branch columns
        branches = []
        i = 1
        while f'Branch_{i}_Z_prime' in df.columns:
            branches.append((f'Branch_{i}_Z_prime', f'Branch_{i}_Z_double_prime'))
            i += 1
        return df, has_fitted, branches

    # ------------------------------------------------------------------
    # upload
    # ------------------------------------------------------------------
    def _auto_style(self, idx):
        color = self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]
        marker = self.AUTO_MARKERS[idx % len(self.AUTO_MARKERS)]
        return color, marker

    def add_curve(self):
        files = filedialog.askopenfilenames(
            title="Select EIS CSV",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                parsed = self.parse_drtxecm_csv(f)
                name = os.path.splitext(os.path.basename(f))[0]
                if parsed is not None:
                    df, has_fitted, branches = parsed
                    z_col = 'Z_raw_prime' if 'Z_raw_prime' in df.columns else df.columns[1]
                    zpp_col = 'Z_raw_double_prime' if 'Z_raw_double_prime' in df.columns else df.columns[2]
                    color, marker = self._auto_style(len(self.curves))
                    c = NyquistData(name, df, z_col, zpp_col, color,
                                    has_fitted=has_fitted, branches=branches,
                                    marker_style=marker)
                    # fitted column name
                    if has_fitted:
                        c.df['fitted_z_prime'] = df['Total_Fitted_Z_prime'].astype(float)
                        c.df['fitted_z_double_prime'] = df['Total_Fitted_Z_double_prime'].astype(float)
                    self.curves.append(c)
                else:
                    # standard EIS CSV (dialog)
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
                messagebox.showerror("Load Failed", f"{f}\n{e}")
        self.redraw()

    def _ask_columns(self, df, fname):
        """Standard CSV: dialog to pick Z'/Z'' columns"""
        win = tk.Toplevel(self.root)
        win.title(f"Select Columns: {fname}")
        win.geometry("380x180")
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=f"File: {fname}\nSelect Z' (real) and Z'' (imag) columns:",
                 justify=tk.LEFT).pack(anchor="w", padx=10, pady=6)

        cols = list(df.columns)
        z_var = tk.StringVar(value=cols[0] if cols else "")
        zpp_var = tk.StringVar(value=cols[1] if len(cols) > 1 else (cols[0] if cols else ""))

        f1 = tk.Frame(win); f1.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f1, text="Z' column:").pack(side=tk.LEFT)
        tk.OptionMenu(f1, z_var, *cols).pack(side=tk.LEFT, padx=4)
        f2 = tk.Frame(win); f2.pack(fill=tk.X, padx=10, pady=2)
        tk.Label(f2, text="Z'' column:").pack(side=tk.LEFT)
        tk.OptionMenu(f2, zpp_var, *cols).pack(side=tk.LEFT, padx=4)

        result = {'v': None}
        def ok():
            result['v'] = (z_var.get(), zpp_var.get())
            win.destroy()
        def cancel():
            win.destroy()

        bf = tk.Frame(win); bf.pack(pady=8)
        tk.Button(bf, text="OK", command=ok, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT, padx=5)
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
    # properties
    # ------------------------------------------------------------------
    def edit_props(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Info", "Please select a dataset first")
            return
        self._edit_curve_props(sel[0])

    def _edit_curve_props(self, idx):
        c = self.curves[idx]
        win = tk.Toplevel(self.root)
        win.title(f"Properties: {c.name}")
        win.geometry("420x400")
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=f"Data: {c.name}（Z′: {c.z_col}, Z″: {c.zpp_col}）",
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

        # raw marker style
        mf = tk.Frame(win); mf.pack(fill=tk.X, padx=8)
        tk.Label(mf, text="raw marker:").pack(side=tk.LEFT)
        ms_var = tk.StringVar(value=c.marker_style)
        markers = ['o', 's', '^', 'v', 'D', 'x', '+', '*', 'p', 'h', 'None']
        tk.OptionMenu(mf, ms_var, *markers,
                      command=lambda v: (setattr(c, 'marker_style', v), self.redraw())).pack(side=tk.LEFT, padx=4)

        # fitted linestyle
        lf = tk.Frame(win); lf.pack(fill=tk.X, padx=8)
        tk.Label(lf, text="fitted Linestyle:").pack(side=tk.LEFT)
        fl_var = tk.StringVar(value=c.fitted_line_style)
        tk.OptionMenu(lf, fl_var, '-', '--', '-.', ':',
                      command=lambda v: (setattr(c, 'fitted_line_style', v), self.redraw())).pack(side=tk.LEFT)

    def _pick_color_btn(self, btn, curve):
        rgb, _ = colorchooser.askcolor(color=curve.color, title="Choose Color")
        if rgb:
            curve.color = '#%02x%02x%02x' % rgb
            btn.config(bg=curve.color)
            self.redraw()

    # ------------------------------------------------------------------
    # global
    # ------------------------------------------------------------------
    def _get_scale(self):
        """Return scale factor by global unit + active area
        Ω: ×1 | mΩ: ×1000 | Ω·cm²: ×area | mΩ·cm²: ×1000×area
        """
        unit = self.unit_var.get()
        try:
            area = float(self.area_var.get()) if self.area_var.get() else 1.0
            if area <= 0:
                area = 1.0
        except ValueError:
            area = 1.0
        if unit == 'mΩ':
            return 1000.0, 'mΩ'
        elif unit == 'Ω·cm²':
            return area, 'Ω·cm²'
        elif unit == 'mΩ·cm²':
            return 1000.0 * area, 'mΩ·cm²'
        else:
            return 1.0, 'Ω'

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
    # legend interaction
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
        win.title("Legend Settings")
        win.geometry("320x220")
        win.transient(self.root)
        win.grab_set()
        ff = tk.Frame(win); ff.pack(fill=tk.X, padx=10, pady=6)
        frame_var = tk.BooleanVar(value=cfg['frameon'])
        tk.Checkbutton(ff, text="Show Frame", variable=frame_var).pack(side=tk.LEFT)
        sf = tk.Frame(win); sf.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(sf, text="Font Size:").pack(side=tk.LEFT)
        size_var = tk.IntVar(value=cfg['fontsize'])
        tk.Spinbox(sf, from_=6, to=40, textvariable=size_var, width=5).pack(side=tk.LEFT)
        ff2 = tk.Frame(win); ff2.pack(fill=tk.X, padx=10, pady=6)
        tk.Label(ff2, text="Font:").pack(side=tk.LEFT)
        font_var = tk.StringVar(value=cfg['fontname'])
        fonts = ['Arial', 'DejaVu Sans', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(ff2, font_var, *fonts).pack(side=tk.LEFT)
        def apply_settings():
            # persist settings (survive redraw)
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
        tk.Button(bf, text="Apply", command=apply_settings, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="Cancel", command=win.destroy, width=10).pack(side=tk.LEFT, padx=5)

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
    # minor ticks
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
        # spine linewidth
        spine_lw = self.spine_width_global.get()
        for sp in self.ax.spines.values():
            sp.set_linewidth(spine_lw)

        # plot each dataset (merged legend)
        scale, unit_label = self._get_scale()
        for c in self.curves:
            z, neg_zpp = c.get_raw_xy()
            z = z * scale
            neg_zpp = neg_zpp * scale
            # raw: marker only (main label)
            marker = c.marker_style if (self.marker_global.get()
                                        and c.marker_style != 'None') else None
            self.ax.plot(z, neg_zpp, label=c.name,
                         color=c.color, linestyle='None',
                         marker=marker, markersize=self.marker_size_global.get(),
                         linewidth=self.line_width_global.get())
            # fitted: solid line (no marker)
            if c.has_fitted:
                fz, fneg = c.get_fitted_xy()
                fz = fz * scale
                fneg = fneg * scale
                self.ax.plot(fz, fneg, label='_nolegend_',
                             color=c.color, linestyle=c.fitted_line_style,
                             linewidth=self.line_width_global.get(), alpha=0.8)
            # branch: dashed same color
            if self.branch_var.get() and c.branches:
                for bi, (bz_col, bzpp_col) in enumerate(c.branches):
                    bz = c.df[bz_col].astype(float).values * scale
                    bzpp = c._nyquist_y(c.df[bzpp_col].astype(float).values) * scale
                    self.ax.plot(bz, bzpp,
                                 label='_nolegend_',
                                 color=c.color, linestyle='--',
                                 linewidth=1.0, alpha=0.6)

        # Annotations
        for a in self.annotations:
            if a[0] == 'text':
                _, x, y, text, color = a
                self.ax.annotate(text, (x, y), color=color,
                                 fontsize=self.title_size - 1, fontname=self.font_name)
            elif a[0] == 'line':
                _, x1, y1, x2, y2, color = a
                self.ax.plot([x1, x2], [y1, y2], color=color, lw=1.5)

        # layout
        fw = 'bold' if self.title_bold else 'normal'
        self.ax.set_xlabel(f"Z′ ({unit_label})", fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        self.ax.set_ylabel(f"−Z″ ({unit_label})", fontsize=self.title_size, fontweight=fw, fontname=self.font_name)
        self.ax.tick_params(labelsize=self.tick_size)
        # tick direction + width/length
        xdir = 'in' if self.xdir_var.get() == 'in' else 'out'
        ydir = 'in' if self.ydir_var.get() == 'in' else 'out'
        tw = self.tick_width_global.get()
        tl = self.tick_len_global.get()
        self.ax.tick_params(axis='x', which='both', direction=xdir,
                            width=tw, length=3.5*tl)
        self.ax.tick_params(axis='y', which='both', direction=ydir,
                            width=tw, length=3.5*tl)
        self.ax.tick_params(axis='x', which='minor', length=2.1*tl)
        self.ax.tick_params(axis='y', which='minor', length=2.1*tl)

        # axis range：default auto scale
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
            # X n-ticks
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
            # X/Y equal aspect (Nyquist)
            if self.aspect_var.get():
                self.ax.set_aspect('equal', adjustable='box')
            else:
                self.ax.set_aspect('auto')

        # legend
        if self.curves:
            cfg = self._legend_cfg
            leg = self.ax.legend(loc='upper right',
                                 frameon=cfg['frameon'],
                                 fontsize=cfg['fontsize'],
                                 prop={'family': cfg['fontname']})
            # legend handle = marker + line
            handles = getattr(leg, 'legend_handles', None) or getattr(leg, 'legendHandles', None)
            if handles:
                for i, c in enumerate(self.curves):
                    try:
                        handle = handles[i]
                        handle.set_linestyle('-')
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

        # tick font
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
        try:
            self.fig.savefig(f, dpi=dpi, bbox_inches='tight')
            messagebox.showinfo("Done", f"Saved:\n{f}")
        except Exception as e:
            messagebox.showerror("Save Failed", str(e))

    def export_csv(self):
        """Export merged CSV"""
        if not self.curves:
            messagebox.showinfo("Info", "No data to export")
            return
        f = filedialog.asksaveasfilename(
            title="Export CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not f:
            return
        rows = []
        scale, unit_label = self._get_scale()
        for c in self.curves:
            z, nz = c.get_raw_xy()
            freq = c.df['Frequency'].astype(float).values if 'Frequency' in c.df.columns else np.arange(len(z))
            for i in range(len(z)):
                row = {'label': c.name, 'freq': freq[i],
                       'Z_raw_prime': z[i] * scale, 'neg_Z_raw_double_prime': nz[i] * scale,
                       'unit': unit_label}
                if c.has_fitted:
                    fz, fnz = c.get_fitted_xy()
                    row['Z_fit_prime'] = fz[i] * scale if i < len(fz) else np.nan
                    row['neg_Z_fit_double_prime'] = fnz[i] * scale if i < len(fnz) else np.nan
                rows.append(row)
        out = pd.DataFrame(rows)
        out.to_csv(f, index=False)
        messagebox.showinfo("Done", f"Exported:\n{f}")


def main():
    root = tk.Tk()
    app = NyquistPlotterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
