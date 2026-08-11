#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XRD Plotter — XRD 數據繪圖 GUI（Tkinter + Matplotlib）

功能：
  1. 分區上傳：實驗數據（2Theta, Intensity）與資料庫譜線（2Theta, Intensity_Rel）
     各自獨立、數量可選
  2. 數據處理：強度歸一化（min-max 0-1）+ 垂直 offset 微調
  3. 視覺微調：顏色、字型、字體大小、marker（種類/開關）
  4. 排序：列表上下移動（決定繪圖順序與圖層）
  5. 圖例：設定 + 拖曳位置
  6. 標註：新增線段與文字（進一步標示）
  7. 輸出：儲存 PNG/SVG/PDF + 可選 dpi + 自訂檔名

環境需求：
  pip install matplotlib pandas numpy

用法：
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
# 資料容器
# ------------------------------------------------------------------
class ExperimentData:
    """實驗數據（2Theta, Intensity）"""
    def __init__(self, name, df, color, offset=0.0, normalize=True,
                 marker_on=True, marker_style='o', line_style='-', line_width=1.0):
        self.name = name
        self.df = df.copy()
        self.color = color
        self.offset = offset          # 垂直偏移
        self.normalize = normalize    # 歸一化
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
    """資料庫譜線（2Theta, Intensity_Rel 0-100）"""
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
# 主視窗
# ------------------------------------------------------------------
class XRDPlotterApp:
    DEFAULT_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    def __init__(self, root):
        self.root = root
        self.root.title("XRD Plotter — XRD 數據繪圖工具")
        self.root.geometry("1180x780")

        self.experiments = []   # list[ExperimentData]
        self.databases = []     # list[DatabaseData]
        self.annotations = []   # list[(type, x, y, text, color)] type: 'line'|'text'

        # 全域字型設定
        self.font_name = 'DejaVu Sans'
        self.font_size = 10
        self.x_range = (10, 90)
        self.legend_dragging = False

        self._build_ui()
        self._new_figure()

    # ------------------------------------------------------------------
    # UI 建構
    # ------------------------------------------------------------------
    def _build_ui(self):
        # 左側控制面板
        left = tk.Frame(self.root, width=320)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)
        left.pack_propagate(False)

        # ===== 實驗數據區 =====
        tk.Label(left, text="實驗數據 (Experiment)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
        btn_row1 = tk.Frame(left)
        btn_row1.pack(fill=tk.X)
        tk.Button(btn_row1, text="＋ 新增實驗數據", command=self.add_experiment).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row1, text="✕ 刪除選取", command=self.remove_experiment).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.exp_listbox = tk.Listbox(left, height=5, exportselection=False)
        self.exp_listbox.pack(fill=tk.X, pady=2)
        self.exp_listbox.bind('<<ListboxSelect>>', lambda e: self._select_entity('exp'))

        btn_row1b = tk.Frame(left)
        btn_row1b.pack(fill=tk.X)
        tk.Button(btn_row1b, text="↑ 上移", command=lambda: self.move_item('exp', -1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row1b, text="↓ 下移", command=lambda: self.move_item('exp', 1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row1b, text="✎ 屬性", command=lambda: self.edit_props('exp')).pack(side=tk.LEFT, expand=True)

        # ===== 資料庫譜線區 =====
        tk.Label(left, text="資料庫譜線 (Database / PDF)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        btn_row2 = tk.Frame(left)
        btn_row2.pack(fill=tk.X)
        tk.Button(btn_row2, text="＋ 新增譜線", command=self.add_database).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row2, text="✕ 刪除選取", command=self.remove_database).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.db_listbox = tk.Listbox(left, height=5, exportselection=False)
        self.db_listbox.pack(fill=tk.X, pady=2)
        self.db_listbox.bind('<<ListboxSelect>>', lambda e: self._select_entity('db'))

        btn_row2b = tk.Frame(left)
        btn_row2b.pack(fill=tk.X)
        tk.Button(btn_row2b, text="↑ 上移", command=lambda: self.move_item('db', -1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row2b, text="↓ 下移", command=lambda: self.move_item('db', 1)).pack(side=tk.LEFT, expand=True)
        tk.Button(btn_row2b, text="✎ 屬性", command=lambda: self.edit_props('db')).pack(side=tk.LEFT, expand=True)

        # ===== 全域設定 =====
        tk.Label(left, text="全域設定", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        gf = tk.Frame(left)
        gf.pack(fill=tk.X)

        tk.Label(gf, text="字型:").grid(row=0, column=0, sticky="w")
        self.font_var = tk.StringVar(value=self.font_name)
        fonts = ['DejaVu Sans', 'Arial', 'Times New Roman', 'SimHei', 'Microsoft JhengHei']
        tk.OptionMenu(gf, self.font_var, *fonts, command=lambda _: self._apply_global()).grid(row=0, column=1, sticky="ew")

        tk.Label(gf, text="字體大小:").grid(row=1, column=0, sticky="w")
        self.size_var = tk.IntVar(value=self.font_size)
        tk.Spinbox(gf, from_=6, to=30, textvariable=self.size_var, width=5,
                   command=self._apply_global).grid(row=1, column=1, sticky="w")

        tk.Label(gf, text="X 範圍:").grid(row=2, column=0, sticky="w")
        xf = tk.Frame(gf)
        xf.grid(row=2, column=1, sticky="ew")
        self.xmin_var = tk.StringVar(value="10")
        self.xmax_var = tk.StringVar(value="90")
        tk.Entry(xf, textvariable=self.xmin_var, width=5).pack(side=tk.LEFT)
        tk.Label(xf, text="–").pack(side=tk.LEFT)
        tk.Entry(xf, textvariable=self.xmax_var, width=5).pack(side=tk.LEFT)

        gf.columnconfigure(1, weight=1)

        # ===== 標註工具 =====
        tk.Label(left, text="標註工具 (Annotations)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        btn_row3 = tk.Frame(left)
        btn_row3.pack(fill=tk.X)
        tk.Button(btn_row3, text="＋ 文字標註", command=self.add_text_annotation).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row3, text="＋ 線段標註", command=self.add_line_annotation).pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(btn_row3, text="✕ 清除標註", command=self.clear_annotations).pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ===== 繪圖與輸出 =====
        action_row = tk.Frame(left)
        action_row.pack(fill=tk.X, pady=(10, 2))
        tk.Button(action_row, text="🔄 重繪", command=self.redraw, bg="#e8f0fe").pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Button(action_row, text="💾 儲存圖", command=self.save_figure, bg="#e6f4e6").pack(side=tk.LEFT, expand=True, fill=tk.X)

        # ===== 右側繪圖區 =====
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
        # 圖例拖曳
        self.canvas.mpl_connect('button_press_event', self._on_legend_press)
        self.canvas.mpl_connect('motion_notify_event', self._on_legend_drag)
        self.canvas.mpl_connect('button_release_event', self._on_legend_release)

    # ------------------------------------------------------------------
    # 資料上傳
    # ------------------------------------------------------------------
    def _pick_color(self, idx):
        return self.DEFAULT_COLORS[idx % len(self.DEFAULT_COLORS)]

    def add_experiment(self):
        files = filedialog.askopenfilenames(
            title="選擇實驗數據 CSV（2Theta, Intensity）",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                df = pd.read_csv(f)
                if '2Theta' not in df.columns or 'Intensity' not in df.columns:
                    messagebox.showerror("格式錯誤", f"{os.path.basename(f)}\n需要欄位: 2Theta, Intensity\n實際欄位: {list(df.columns)}")
                    continue
                name = os.path.splitext(os.path.basename(f))[0]
                self.experiments.append(ExperimentData(
                    name, df, self._pick_color(len(self.experiments))))
                self._refresh_list('exp')
            except Exception as e:
                messagebox.showerror("讀取失敗", f"{f}\n{e}")
        self.redraw()

    def add_database(self):
        files = filedialog.askopenfilenames(
            title="選擇資料庫譜線 CSV（2Theta, Intensity_Rel）",
            filetypes=[("CSV", "*.csv")])
        for f in files:
            try:
                df = pd.read_csv(f)
                if '2Theta' not in df.columns or 'Intensity_Rel' not in df.columns:
                    messagebox.showerror("格式錯誤", f"{os.path.basename(f)}\n需要欄位: 2Theta, Intensity_Rel\n實際欄位: {list(df.columns)}")
                    continue
                name = os.path.splitext(os.path.basename(f))[0]
                self.databases.append(DatabaseData(
                    name, df, self._pick_color(len(self.databases) + 5)))
                self._refresh_list('db')
            except Exception as e:
                messagebox.showerror("讀取失敗", f"{f}\n{e}")
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
        pass  # 保留（列表選擇時可做即時預覽）

    # ------------------------------------------------------------------
    # 屬性編輯
    # ------------------------------------------------------------------
    def edit_props(self, kind):
        lb = self.exp_listbox if kind == 'exp' else self.db_listbox
        sel = lb.curselection()
        if not sel:
            messagebox.showinfo("提示", "請先在列表中選擇一個項目")
            return
        idx = sel[0]
        if kind == 'exp':
            self._edit_exp_props(idx)
        else:
            self._edit_db_props(idx)

    def _edit_exp_props(self, idx):
        d = self.experiments[idx]
        win = tk.Toplevel(self.root)
        win.title(f"屬性: {d.name}")
        win.geometry("360x330")

        tk.Label(win, text=f"數據: {d.name}").pack(anchor="w", padx=8, pady=4)

        # 顏色
        cf = tk.Frame(win); cf.pack(fill=tk.X, padx=8)
        tk.Label(cf, text="顏色:").pack(side=tk.LEFT)
        color_btn = tk.Button(cf, bg=d.color, width=4,
                              command=lambda: self._pick_color_btn(color_btn, d, 'exp'))
        color_btn.pack(side=tk.LEFT, padx=4)

        # 偏移
        of = tk.Frame(win); of.pack(fill=tk.X, padx=8)
        tk.Label(of, text="垂直偏移:").pack(side=tk.LEFT)
        off_var = tk.DoubleVar(value=d.offset)
        tk.Spinbox(of, from_=-5, to=5, increment=0.1, textvariable=off_var, width=6).pack(side=tk.LEFT)
        def set_offset():
            d.offset = off_var.get()
            self.redraw()
        tk.Button(of, text="套用", command=set_offset).pack(side=tk.LEFT, padx=4)

        # 歸一化
        nf = tk.Frame(win); nf.pack(fill=tk.X, padx=8)
        norm_var = tk.BooleanVar(value=d.normalize)
        tk.Checkbutton(nf, text="強度歸一化 (0-1)", variable=norm_var,
                       command=lambda: (setattr(d, 'normalize', norm_var.get()), self.redraw())).pack(side=tk.LEFT)

        # 線型
        lf = tk.Frame(win); lf.pack(fill=tk.X, padx=8)
        tk.Label(lf, text="線型:").pack(side=tk.LEFT)
        ls_var = tk.StringVar(value=d.line_style)
        tk.OptionMenu(lf, ls_var, '-', '--', '-.', ':', command=lambda v: (setattr(d, 'line_style', v), self.redraw())).pack(side=tk.LEFT)

        # 線寬
        wf = tk.Frame(win); wf.pack(fill=tk.X, padx=8)
        tk.Label(wf, text="線寬:").pack(side=tk.LEFT)
        lw_var = tk.DoubleVar(value=d.line_width)
        tk.Spinbox(wf, from_=0.5, to=5, increment=0.1, textvariable=lw_var, width=6).pack(side=tk.LEFT)
        def set_lw():
            d.line_width = lw_var.get()
            self.redraw()
        tk.Button(wf, text="套用", command=set_lw).pack(side=tk.LEFT, padx=4)

        # marker
        mf = tk.Frame(win); mf.pack(fill=tk.X, padx=8)
        mk_var = tk.BooleanVar(value=d.marker_on)
        tk.Checkbutton(mf, text="顯示 marker", variable=mk_var,
                       command=lambda: (setattr(d, 'marker_on', mk_var.get()), self.redraw())).pack(side=tk.LEFT)
        ms_var = tk.StringVar(value=d.marker_style)
        markers = ['o', 's', '^', 'v', 'D', 'x', '+', '*', '|', '_', 'None']
        tk.OptionMenu(mf, ms_var, *markers, command=lambda v: (setattr(d, 'marker_style', v), self.redraw())).pack(side=tk.LEFT, padx=4)

    def _edit_db_props(self, idx):
        d = self.databases[idx]
        win = tk.Toplevel(self.root)
        win.title(f"屬性: {d.name}")
        win.geometry("320x180")

        tk.Label(win, text=f"譜線: {d.name}").pack(anchor="w", padx=8, pady=4)

        cf = tk.Frame(win); cf.pack(fill=tk.X, padx=8)
        tk.Label(cf, text="顏色:").pack(side=tk.LEFT)
        color_btn = tk.Button(cf, bg=d.color, width=4,
                              command=lambda: self._pick_color_btn(color_btn, d, 'db'))
        color_btn.pack(side=tk.LEFT, padx=4)

        of = tk.Frame(win); of.pack(fill=tk.X, padx=8)
        tk.Label(of, text="垂直偏移:").pack(side=tk.LEFT)
        off_var = tk.DoubleVar(value=d.offset)
        tk.Spinbox(of, from_=-5, to=5, increment=0.1, textvariable=off_var, width=6).pack(side=tk.LEFT)
        def set_offset():
            d.offset = off_var.get()
            self.redraw()
        tk.Button(of, text="套用", command=set_offset).pack(side=tk.LEFT, padx=4)

        wf = tk.Frame(win); wf.pack(fill=tk.X, padx=8)
        tk.Label(wf, text="線寬:").pack(side=tk.LEFT)
        lw_var = tk.DoubleVar(value=d.line_width)
        tk.Spinbox(wf, from_=0.5, to=5, increment=0.1, textvariable=lw_var, width=6).pack(side=tk.LEFT)
        def set_lw():
            d.line_width = lw_var.get()
            self.redraw()
        tk.Button(wf, text="套用", command=set_lw).pack(side=tk.LEFT, padx=4)

    def _pick_color_btn(self, btn, obj, kind):
        rgb, _ = colorchooser.askcolor(color=obj.color, title="選擇顏色")
        if rgb:
            obj.color = '#%02x%02x%02x' % rgb
            btn.config(bg=obj.color)
            self.redraw()

    # ------------------------------------------------------------------
    # 全域設定
    # ------------------------------------------------------------------
    def _apply_global(self):
        self.font_name = self.font_var.get()
        self.font_size = self.size_var.get()
        self.redraw()

    # ------------------------------------------------------------------
    # 標註
    # ------------------------------------------------------------------
    def add_text_annotation(self):
        x = simpledialog.askfloat("文字標註", "X 位置:", initialvalue=50)
        if x is None:
            return
        y = simpledialog.askfloat("文字標註", "Y 位置:", initialvalue=1.0)
        if y is None:
            return
        text = simpledialog.askstring("文字標註", "文字內容:")
        if not text:
            return
        self.annotations.append(('text', x, y, text, '#000000'))
        self.redraw()

    def add_line_annotation(self):
        x1 = simpledialog.askfloat("線段標註", "起點 X:", initialvalue=30)
        if x1 is None:
            return
        y1 = simpledialog.askfloat("線段標註", "起點 Y:", initialvalue=0.5)
        if y1 is None:
            return
        x2 = simpledialog.askfloat("線段標註", "終點 X:", initialvalue=40)
        if x2 is None:
            return
        y2 = simpledialog.askfloat("線段標註", "終點 Y:", initialvalue=0.5)
        if y2 is None:
            return
        self.annotations.append(('line', x1, y1, x2, y2, '#ff0000'))
        self.redraw()

    def clear_annotations(self):
        self.annotations.clear()
        self.redraw()

    # ------------------------------------------------------------------
    # 圖例拖曳
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
    # 繪圖
    # ------------------------------------------------------------------
    def redraw(self):
        self.ax.clear()
        try:
            xmin = float(self.xmin_var.get())
            xmax = float(self.xmax_var.get())
            self.x_range = (xmin, xmax)
        except ValueError:
            pass

        # 實驗數據
        for d in self.experiments:
            x = d.df['2Theta'].astype(float)
            y = d.get_y()
            marker = d.marker_style if d.marker_on and d.marker_style != 'None' else None
            self.ax.plot(x, y, label=d.name, color=d.color,
                         linestyle=d.line_style, linewidth=d.line_width,
                         marker=marker, markersize=3, markevery=5)

        # 資料庫譜線（棒狀）
        for d in self.databases:
            x = d.df['2Theta'].astype(float)
            h = d.get_heights()
            self.ax.vlines(x, ymin=d.offset, ymax=d.offset + h,
                           colors=d.color, lw=d.line_width, label=d.name)
            self.ax.hlines(d.offset, xmin=self.x_range[0], xmax=self.x_range[1],
                           colors='gray', linestyles=':', lw=0.5)

        # 標註
        for a in self.annotations:
            if a[0] == 'text':
                _, x, y, text, color = a
                self.ax.annotate(text, (x, y), color=color,
                                 fontsize=self.font_size - 1,
                                 fontname=self.font_name)
            elif a[0] == 'line':
                _, x1, y1, x2, y2, color = a
                self.ax.plot([x1, x2], [y1, y2], color=color, lw=1.5)

        # 版面
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
            leg.set_draggable(True)  # 內建拖曳（後備）
        self.fig.tight_layout()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # 儲存
    # ------------------------------------------------------------------
    def save_figure(self):
        dpi = simpledialog.askinteger("儲存", "DPI（建議 300）:", initialvalue=300, minvalue=50, maxvalue=1200)
        if dpi is None:
            dpi = 300
        f = filedialog.asksaveasfilename(
            title="儲存圖檔",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("SVG", "*.svg"), ("PDF", "*.pdf")])
        if not f:
            return
        self.fig.savefig(f, dpi=dpi, bbox_inches='tight')
        messagebox.showinfo("完成", f"已儲存: {f} (dpi={dpi})")


# ------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = XRDPlotterApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
