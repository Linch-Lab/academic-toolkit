#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XRD Plotter — XRD data plotting GUI (Tkinter + Matplotlib)

Features:
  1. Sectioned upload: experiment vs reference
     each independent, count selectable
  2. Data: normalize (min-max 0-1) + Y offset
  3. Visual: color, font, size, marker
  4. Sort: list up/down (draw order/layer)
  5. Legend: settings + drag
  6. Annotations: add line/text
  7. Output: save PNG/SVG/PDF + dpi

Requirements:
  pip install matplotlib pandas numpy

Usage:
  python xrd_plotter.py
"""
import tkinter as tk
from tkinter import filedialog, colorchooser, messagebox, simpledialog
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
class ExperimentData:
    """Experiment data (2Theta, Intensity)"""
    def __init__(self, name, df, color, offset=0.0, normalize=True,
                 marker_on=True, marker_style='o', line_style='-', line_width=1.0):
        self.name = name
        self.df = df.copy()
        self.color = color
        self.offset = offset          # vertical offset
        self.normalize = normalize    # normalization
        self.marker_on = marker_on
        self.marker_style = marker_style
        self.line_style = line_style
        self.line_width = line_width

    def get_y(self):
        y = self.df['Intensity'].astype(float)
        if self.normalize and y.max() > y.min():
            y = (y - y.min()) / (y.max() - y.min())
        return y + self.offset


class DatabaseData:
    """Reference (2Theta, Intensity_Rel 0-100)"""
    def __init__(self, name, df, color, offset=0.0, marker_on=False,
                 marker_style='|', line_width=1.0):
        self.name = name
        self.df = df.copy()
        self.color = color
        self.offset = offset
        self.marker_on = marker_on
        self.marker_style = marker_style
        self.line_width = line_width

    def get_heights(self):
        return (self.df['Intensity_Rel'].astype(float) / 100.0) * 0.25


# ------------------------------------------------------------------
# Main window
# ------------------------------------------------------------------
class XRDPlotterApp:
    DEFAULT_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    def __init__(self, root):
        self.root = root
        self.root.title("XRD Plotter — XRD Data Plotting")
        self.root.geometry("1180x780")

        self.experiments = []   # list[ExperimentData]
        self.databases = []     # list[DatabaseData]
        self.annotations = []   # list[(type, x, y, text, color)] type: 'line'|'text'

        # global font settings
        self.font_name = 'DejaVu Sans'
        self.font_size = 10
        self.x_range = (10, 90)
        self.legend_dragging = False

        self._build_ui()
        self._new_figure()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        # left control panel
        left = tk.Frame(self.root, width=320)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left.pack_propagate(False)

        # ===== Experiment section =====
        tk.Label(left, text="Experiment", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
        btn_row1 = tk.Frame(left)
        btn_row1.pack(fill=tk.X)
        tk.Button(btn_row1, text="+ Add Experiment", command=self.add_experiment).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row1, text="✕ Remove", command=self.remove_experiment).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.exp_listbox = tk.Listbox(left, height=5, exportselection=False)
        self.exp_listbox.pack(fill=tk.X, pady=2)
        self.exp_listbox.bind('<<ListboxSelect>>', lambda e: self._select_entity('exp'))

        btn_row1b = tk.Frame(left)
        btn_row1b.pack(fill=tk.X)
        tk.Button(btn_row1b, text="↑ Up", command=lambda: self.move_item('exp', -1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row1b, text="↓ Down", command=lambda: self.move_item('exp', 1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row1b, text="✎ Properties", command=lambda: self.edit_props('exp')).pack(side=tk.LEFT, expand=True)

        # ===== Reference section =====
        tk.Label(left, text="Reference (PDF)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        btn_row2 = tk.Frame(left)
        btn_row2.pack(fill=tk.X)
        tk.Button(btn_row2, text="+ Add Reference", command=self.add_database).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row2, text="✕ Remove", command=self.remove_database).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.db_listbox = tk.Listbox(left, height=5, exportselection=False)
        self.db_listbox.pack(fill=tk.X, pady=2)
        self.db_listbox.bind('<<ListboxSelect>>', lambda e: self._select_entity('db'))

        btn_row2b = tk.Frame(left)
        btn_row2b.pack(fill=tk.X)
        tk.Button(btn_row2b, text="↑ Up", command=lambda: self.move_item('db', -1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row2b, text="↓ Down", command=lambda: self.move_item('db', 1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row2b, text="✎ Properties", command=lambda: self.edit_props('db')).pack(side=tk.LEFT, expand=True)

        # ===== Global Settings =====
        tk.Label(left, text="Global Settings", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        gf = tk.Frame(left)
        gf.pack(fill=tk.X)

        tk.Label(gf, text="Font:").grid(row=0, column=0, sticky="w")
        self.font_var = tk.StringVar(value=self.font_name)
        fonts = ['DejaVu Sans', 'Arial', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(gf, self.font_var, *fonts, command=lambda _: self._apply_global()).grid(row=0, column=1, sticky="ew")

        tk.Label(gf, text="Font Size:").grid(row=1, column=0, sticky="w")
        self.size_var = tk.IntVar(value=self.font_size)
        tk.Spinbox(gf, from_=6, to=30, textvariable=self.size_var, width=5,
                   command=self._apply_global).grid(row=1, column=1, sticky="w")

        tk.Label(gf, text="X Range:").grid(row=2, column=0, sticky="w")
        xf = tk.Frame(gf)
        xf.grid(row=2, column=1, sticky="ew")
        self.xmin_var = tk.StringVar(value="10")
        self.xmax_var = tk.StringVar(value="90")
        tk.Entry(xf, textvariable=self.xmin_var, width=5).pack(side=tk.LEFT)
        tk.Label(xf, text="–").pack(side=tk.LEFT)
        tk.Entry(xf, textvariable=self.xmax_var, width=5).pack(side=tk.LEFT)

        gf.columnconfigure(1, weight=1)

        # ===== Annotations =====
        tk.Label(left, text="Annotations", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        btn_row3 = tk.Frame(left)
        btn_row3.pack(fill=tk.X)
        tk.Button(btn_row3, text="+ TextAnnotations", command=self.add_text_annotation).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row3, text="+ LineAnnotations", command=self.add_line_annotation).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row3, text="✕ ClearAnnotations", command=self.clear_annotations).pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ===== Plot & Output =====
        action_row = tk.Frame(left)
        action_row.pack(fill=tk.X, pady=(10, 2))
        tk.Button(action_row, text="🔄 Redraw", command=self.redraw, bg="#e8f0fe").pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(action_row, text="💾 Save", command=self.save_figure, bg="#e6f4e6").pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ===== Right plot area =====
        right = tk.Frame(self.root)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.fig = None
        self.ax = None
        self.canvas = None
        self.toolbar = None
        self.plot_frame = right

    def _new_figure(self):
        for w in self.plot_frame.winfo_children():
            w.destroy()
        self.fig = plt.Figure(figsize=(7, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_frame)
        self.toolbar.update()
        # legend drag
        self.canvas.mpl_connect('button_press_event', self._on_legend_press)
        self.canvas.mpl_connect('motion_notify_event', self._on_legend_drag)
        self.canvas.mpl_connect('button_release_event', self._on_legend_release)

    # ------------------------------------------------------------------
    # data upload
    # ------------------------------------------------------------------
    def _pick_color(self, idx):
        return self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]

    def add_experiment(self):
        files = filedialog.askopenfilenames(
            title="Select experiment CSV (2Theta, Intensity)",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                df = pd.read_csv(f)
                if '2Theta' not in df.columns or 'Intensity' not in df.columns:
                    messagebox.showerror("Format Error", f"{os.path.basename(f)}\nNeeds: 2Theta, Intensity\nActual: {list(df.columns)}")
                    continue
                name = os.path.splitext(os.path.basename(f))[0]
                self.experiments.append(ExperimentData(
                    name, df, self._pick_color(len(self.experiments))))
                self._refresh_list('exp')
            except Exception as e:
                messagebox.showerror("Load Failed", f"{f}\n{e}")
        self.redraw()

    def add_database(self):
        files = filedialog.askopenfilenames(
            title="Select reference CSV (2Theta, Intensity_Rel)",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                df = pd.read_csv(f)
                if '2Theta' not in df.columns or 'Intensity_Rel' not in df.columns:
                    messagebox.showerror("Format Error", f"{os.path.basename(f)}\nNeeds: 2Theta, Intensity_Rel\nActual: {list(df.columns)}")
                    continue
                name = os.path.splitext(os.path.basename(f))[0]
                self.databases.append(DatabaseData(
                    name, df, self._pick_color(len(self.databases) + 5)))
                self._refresh_list('db')
            except Exception as e:
                messagebox.showerror("Load Failed", f"{f}\n{e}")
        self.redraw()

    def remove_experiment(self):
        sel = self.exp_listbox.curselection()
        if sel:
            idx = sel[0]
            del self.experiments[idx]
            self._refresh_list('exp')
            self.redraw()

    def remove_database(self):
        sel = self.db_listbox.curselection()
        if sel:
            idx = sel[0]
            del self.databases[idx]
            self._refresh_list('db')
            self.redraw()

    def move_item(self, kind, direction):
        lb = self.exp_listbox if kind == 'exp' else self.db_listbox
        items = self.experiments if kind == 'exp' else self.databases
        sel = lb.curselection()
        if not sel:
            return
        idx = sel[0]
        new = idx + direction
        if new < 0 or new >= len(items):
            return
        items[idx], items[new] = items[new], items[idx]
        self._refresh_list(kind)
        lb.selection_set(new)
        self.redraw()

    def _refresh_list(self, kind):
        lb = self.exp_listbox if kind == 'exp' else self.db_listbox
        items = self.experiments if kind == 'exp' else self.databases
        lb.delete(0, tk.END)
        for i, it in enumerate(items):
            lb.insert(tk.END, f"{i+1}. {it.name}")

    def _select_entity(self, kind):
        pass  # kept (for live preview on list select)

    # ------------------------------------------------------------------
    # property editing
    # ------------------------------------------------------------------
    def edit_props(self, kind):
        lb = self.exp_listbox if kind == 'exp' else self.db_listbox
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo("Info", "Please select an item first")
            return
        idx = sel[0]
        if kind == 'exp':
            self._edit_exp_props(idx)
        else:
            self._edit_db_props(idx)

    def _edit_exp_props(self, idx):
        d = self.experiments[idx]
        win = tk.Toplevel(self.root)
        win.title(f"Properties: {d.name}")
        win.geometry("360x330")

        tk.Label(win, text=f"Data: {d.name}").pack(anchor="w", padx=8, pady=4)

        # color
        cf = tk.Frame(win); cf.pack(fill=tk.X, padx=8)
        tk.Label(cf, text="Color:").pack(side=tk.LEFT)
        color_btn = tk.Button(cf, bg=d.color, width=4,
                              command=lambda: self._pick_color_btn(color_btn, d, 'exp'))
        color_btn.pack(side=tk.LEFT, padx=4)

        # offset
        of = tk.Frame(win); of.pack(fill=tk.X, padx=8)
        tk.Label(of, text="Y Offset:").pack(side=tk.LEFT)
        off_var = tk.DoubleVar(value=d.offset)
        tk.Spinbox(of, from_=-5, to=5, increment=0.1, textvariable=off_var, width=6).pack(side=tk.LEFT)
        def set_offset():
            d.offset = off_var.get()
            self.redraw()
        tk.Button(of, text="Apply", command=set_offset).pack(side=tk.LEFT, padx=4)

        # normalization
        nf = tk.Frame(win); nf.pack(fill=tk.X, padx=8)
        norm_var = tk.BooleanVar(value=d.normalize)
        tk.Checkbutton(nf, text="Normalize (0-1)", variable=norm_var,
                       command=lambda: (setattr(d, 'normalize', norm_var.get()), self.redraw())).pack(side=tk.LEFT)

        # linestyle
        lf = tk.Frame(win); lf.pack(fill=tk.X, padx=8)
        tk.Label(lf, text="Linestyle:").pack(side=tk.LEFT)
        ls_var = tk.StringVar(value=d.line_style)
        tk.OptionMenu(lf, ls_var, '-', '--', '-.', ':', command=lambda v: (setattr(d, 'line_style', v), self.redraw())).pack(side=tk.LEFT)

        # linewidth
        wf = tk.Frame(win); wf.pack(fill=tk.X, padx=8)
        tk.Label(wf, text="Linewidth:").pack(side=tk.LEFT)
        lw_var = tk.DoubleVar(value=d.line_width)
        tk.Spinbox(wf, from_=0.5, to=5, increment=0.1, textvariable=lw_var, width=6).pack(side=tk.LEFT)
        def set_lw():
            d.line_width = lw_var.get()
            self.redraw()
        tk.Button(wf, text="Apply", command=set_lw).pack(side=tk.LEFT, padx=4)

        # marker
        mf = tk.Frame(win); mf.pack(fill=tk.X, padx=8)
        mk_var = tk.BooleanVar(value=d.marker_on)
        tk.Checkbutton(mf, text="Show marker", variable=mk_var,
                       command=lambda: (setattr(d, 'marker_on', mk_var.get()), self.redraw())).pack(side=tk.LEFT)
        ms_var = tk.StringVar(value=d.marker_style)
        markers = ['o', 's', '^', 'v', 'D', 'x', '+', '*', '|', '_', 'None']
        tk.OptionMenu(mf, ms_var, *markers, command=lambda v: (setattr(d, 'marker_style', v), self.redraw())).pack(side=tk.LEFT, padx=4)

    def _edit_db_props(self, idx):
        d = self.databases[idx]
        win = tk.Toplevel(self.root)
        win.title(f"Properties: {d.name}")
        win.geometry("320x180")

        tk.Label(win, text=f"Reference: {d.name}").pack(anchor="w", padx=8, pady=4)

        cf = tk.Frame(win); cf.pack(fill=tk.X, padx=8)
        tk.Label(cf, text="Color:").pack(side=tk.LEFT)
        color_btn = tk.Button(cf, bg=d.color, width=4,
                              command=lambda: self._pick_color_btn(color_btn, d, 'db'))
        color_btn.pack(side=tk.LEFT, padx=4)

        of = tk.Frame(win); of.pack(fill=tk.X, padx=8)
        tk.Label(of, text="Y Offset:").pack(side=tk.LEFT)
        off_var = tk.DoubleVar(value=d.offset)
        tk.Spinbox(of, from_=-5, to=5, increment=0.1, textvariable=off_var, width=6).pack(side=tk.LEFT)
        def set_offset():
            d.offset = off_var.get()
            self.redraw()
        tk.Button(of, text="Apply", command=set_offset).pack(side=tk.LEFT, padx=4)

        wf = tk.Frame(win); wf.pack(fill=tk.X, padx=8)
        tk.Label(wf, text="Linewidth:").pack(side=tk.LEFT)
        lw_var = tk.DoubleVar(value=d.line_width)
        tk.Spinbox(wf, from_=0.5, to=5, increment=0.1, textvariable=lw_var, width=6).pack(side=tk.LEFT)
        def set_lw():
            d.line_width = lw_var.get()
            self.redraw()
        tk.Button(wf, text="Apply", command=set_lw).pack(side=tk.LEFT, padx=4)

    def _pick_color_btn(self, btn, obj, kind):
        rgb, _ = colorchooser.askcolor(color=obj.color, title="Choose Color")
        if rgb:
            obj.color = '#%02x%02x%02x' % rgb
            btn.config(bg=obj.color)
            self.redraw()

    # ------------------------------------------------------------------
    # Global Settings
    # ------------------------------------------------------------------
    def _apply_global(self):
        self.font_name = self.font_var.get()
        self.font_size = self.size_var.get()
        self.redraw()

    # ------------------------------------------------------------------
    # Annotations
    # ------------------------------------------------------------------
    def add_text_annotation(self):
        x = simpledialog.askfloat("Text Annotation", "X pos:", initialvalue=50)
        if x is None:
            return
        y = simpledialog.askfloat("Text Annotation", "Y pos:", initialvalue=1.0)
        if y is None:
            return
        text = simpledialog.askstring("Text Annotation", "Text:")
        if not text:
            return
        self.annotations.append(('text', x, y, text, '#000000'))
        self.redraw()

    def add_line_annotation(self):
        x1 = simpledialog.askfloat("Line Annotation", "Start X:", initialvalue=30)
        if x1 is None:
            return
        y1 = simpledialog.askfloat("Line Annotation", "Start Y:", initialvalue=0.5)
        if y1 is None:
            return
        x2 = simpledialog.askfloat("Line Annotation", "End X:", initialvalue=40)
        if x2 is None:
            return
        y2 = simpledialog.askfloat("Line Annotation", "End Y:", initialvalue=0.5)
        if y2 is None:
            return
        self.annotations.append(('line', x1, y1, x2, y2, '#ff0000'))
        self.redraw()

    def clear_annotations(self):
        self.annotations.clear()
        self.redraw()

    # ------------------------------------------------------------------
    # legend drag
    # ------------------------------------------------------------------
    def _on_legend_press(self, event):
        if event.inaxes is None:
            return
        leg = self.ax.get_legend()
        if leg is None:
            return
        bbox = leg.get_window_extent()
        if bbox.contains(event.x, event.y):
            self.legend_dragging = True

    def _on_legend_drag(self, event):
        if not self.legend_dragging or event.inaxes is None:
            return
        leg = self.ax.get_legend()
        if leg is None:
            return
        x, y = event.xdata, event.ydata
        leg.set_bbox_to_anchor((x, y), transform=self.ax.transData)
        self.canvas.draw_idle()

    def _on_legend_release(self, event):
        self.legend_dragging = False

    # ------------------------------------------------------------------
    # plotting
    # ------------------------------------------------------------------
    def redraw(self):
        self.ax.clear()
        try:
            xmin = float(self.xmin_var.get())
            xmax = float(self.xmax_var.get())
            self.x_range = (xmin, xmax)
        except ValueError:
            pass

        # experiment data
        for d in self.experiments:
            x = d.df['2Theta'].astype(float)
            y = d.get_y()
            marker = d.marker_style if d.marker_on and d.marker_style != 'None' else None
            self.ax.plot(x, y, label=d.name, color=d.color,
                         linestyle=d.line_style, linewidth=d.line_width,
                         marker=marker, markersize=3, markevery=5)

        # reference (sticks)
        for d in self.databases:
            x = d.df['2Theta'].astype(float)
            h = d.get_heights()
            self.ax.vlines(x, ymin=d.offset, ymax=d.offset + h,
                           colors=d.color, lw=d.line_width, label=d.name)
            self.ax.hlines(d.offset, xmin=self.x_range[0], xmax=self.x_range[1],
                           colors='gray', linestyles=':', lw=0.5)

        # Annotations
        for a in self.annotations:
            if a[0] == 'text':
                _, x, y, text, color = a
                self.ax.annotate(text, (x, y), color=color,
                                 fontsize=self.font_size - 1,
                                 fontname=self.font_name)
            elif a[0] == 'line':
                _, x1, y1, x2, y2, color = a
                self.ax.plot([x1, x2], [y1, y2], color=color, lw=1.5)

        # layout
        self.ax.set_xlim(*self.x_range)
        self.ax.set_xlabel('2θ (degrees)', fontsize=self.font_size, fontweight='bold',
                           fontname=self.font_name)
        self.ax.set_ylabel('Intensity (a.u.)', fontsize=self.font_size, fontweight='bold',
                           fontname=self.font_name)
        self.ax.set_yticks([])
        self.ax.tick_params(labelsize=self.font_size - 1)
        for lbl in self.ax.get_xticklabels():
            lbl.set_fontname(self.font_name)
        if self.experiments or self.databases:
            leg = self.ax.legend(loc='upper right', frameon=True,
                                 fontsize=self.font_size - 1)
            leg.set_draggable(True)  # built-in drag (fallback)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_figure(self):
        dpi = simpledialog.askinteger("Save", "DPI (suggest 300):", initialvalue=300, minvalue=50, maxvalue=1200)
        if dpi is None:
            dpi = 300
        f = filedialog.asksaveasfilename(
            title="Save Figure",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("SVG", "*.svg"), ("PDF", "*.pdf")])
        if not f:
            return
        self.fig.savefig(f, dpi=dpi, bbox_inches='tight')
        messagebox.showinfo("Done", f"Saved: {f} (dpi={dpi})")


# ------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = XRDPlotterApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
