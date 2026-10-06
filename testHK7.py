import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
import threading
import time
from datetime import datetime
import os
import re
import csv
import io
import sys
import xml.etree.ElementTree as ET
from PIL import Image, ImageTk

TEMPLATE_HEADERS = ["设备名称", "IP地址", "用户名", "密码", "设备品牌"]
MAX_PROBE_CHANNELS = 64
CONSECUTIVE_FAIL_STOP = 5

BRAND_AUTO = "auto"
BRAND_HIKVISION = "hikvision"
BRAND_DAHUA = "dahua"
BRAND_UNIVIEW = "uniview"

BRAND_LABELS = {
    BRAND_AUTO: "自动识别",
    BRAND_HIKVISION: "海康威视",
    BRAND_DAHUA: "大华",
    BRAND_UNIVIEW: "宇视",
}
BRAND_ALIASES = {
    "自动": BRAND_AUTO,
    "自动识别": BRAND_AUTO,
    "auto": BRAND_AUTO,
    "海康": BRAND_HIKVISION,
    "海康威视": BRAND_HIKVISION,
    "hikvision": BRAND_HIKVISION,
    "hik": BRAND_HIKVISION,
    "大华": BRAND_DAHUA,
    "dahua": BRAND_DAHUA,
    "宇视": BRAND_UNIVIEW,
    "uniview": BRAND_UNIVIEW,
    "unv": BRAND_UNIVIEW,
}

COLOR_BG = "#f3f4f6"
COLOR_SIDEBAR = "#ffffff"
COLOR_CARD = "#ffffff"
COLOR_TEXT = "#1f2937"
COLOR_MUTED = "#6b7280"
COLOR_ACCENT = "#2563eb"
COLOR_ACCENT_HOVER = "#1d4ed8"
COLOR_SELECTED = "#e8f1ff"
COLOR_BORDER = "#e5e7eb"
COLOR_LOG = "#f8fafc"
COLOR_SUCCESS = "#16a34a"
COLOR_WARN = "#d97706"
COLOR_ERROR = "#dc2626"


def get_resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def sanitize_filename(text):
    if not text:
        return ""
    return re.sub(r'[<>:"/\\|?*\s]+', "_", str(text).strip()).strip("_")


def local_tag(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def normalize_brand(value, default=BRAND_AUTO):
    if value is None:
        return default
    key = str(value).strip().lower()
    if not key:
        return default
    return BRAND_ALIASES.get(key, BRAND_ALIASES.get(str(value).strip(), default))


def brand_label(brand):
    return BRAND_LABELS.get(brand, BRAND_LABELS[BRAND_AUTO])


def request_with_auth(method, url, username, password, timeout=10, **kwargs):
    last_error = None
    last_response = None
    for auth in (HTTPDigestAuth(username, password), HTTPBasicAuth(username, password)):
        try:
            response = requests.request(method, url, auth=auth, timeout=timeout, **kwargs)
            last_response = response
            if response.status_code != 401:
                return response
        except Exception as exc:
            last_error = exc
    if last_response is not None:
        return last_response
    if last_error:
        raise last_error
    raise RuntimeError("请求失败")


def looks_like_image(content, content_type=""):
    if not content:
        return False
    if content[:3] == b"\xff\xd8\xff":
        return True
    ctype = (content_type or "").lower()
    if "image" in ctype:
        return True
    try:
        Image.open(io.BytesIO(content))
        return True
    except Exception:
        return False


class NVRMultiChannelSnapshot:
    def __init__(self, root):
        self.root = root
        self.root.title("NVR 多通道截图工具")
        self.root.geometry("1120x760")
        self.root.minsize(980, 680)
        self.root.configure(bg=COLOR_BG)

        self.running = False
        self.success_count = 0
        self.fail_count = 0
        self.valid_channel_hashes = set()
        self.batch_devices = []
        self.device_checked = {}
        self.current_page = "single"
        self.nav_buttons = {}
        self.header_icon = None

        self._apply_window_icon()
        self._setup_style()
        self.create_widgets()

    def _apply_window_icon(self):
        ico_path = get_resource_path("app.ico")
        png_path = get_resource_path("nvr_app_icon.png")
        try:
            if os.path.exists(ico_path):
                self.root.iconbitmap(ico_path)
        except Exception:
            pass
        try:
            if os.path.exists(png_path):
                image = Image.open(png_path).convert("RGBA")
                w, h = image.size
                side = min(w, h)
                image = image.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
                self.header_icon = ImageTk.PhotoImage(image.resize((72, 72), Image.LANCZOS))
                self.window_icon = ImageTk.PhotoImage(image.resize((128, 128), Image.LANCZOS))
                self.root.iconphoto(True, self.window_icon)
        except Exception:
            self.header_icon = None

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=COLOR_BG)
        style.configure("Sidebar.TFrame", background=COLOR_SIDEBAR)
        style.configure("Card.TFrame", background=COLOR_CARD)
        style.configure("Card.TLabelframe", background=COLOR_CARD, foreground=COLOR_TEXT, bordercolor=COLOR_BORDER)
        style.configure("Card.TLabelframe.Label", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("App.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("Muted.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Subtitle.TLabel", background=COLOR_BG, foreground=COLOR_MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("SidebarTitle.TLabel", background=COLOR_SIDEBAR, foreground=COLOR_TEXT, font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("SidebarMuted.TLabel", background=COLOR_SIDEBAR, foreground=COLOR_MUTED, font=("Microsoft YaHei UI", 8))
        style.configure("App.TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("App.TEntry", fieldbackground="#ffffff", foreground=COLOR_TEXT, bordercolor=COLOR_BORDER)
        style.configure("App.TCombobox", fieldbackground="#ffffff", foreground=COLOR_TEXT)
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 9, "bold"), foreground="#ffffff", background=COLOR_ACCENT, borderwidth=0)
        style.map("Accent.TButton", background=[("active", COLOR_ACCENT_HOVER), ("disabled", "#93c5fd")])
        style.configure("Ghost.TButton", font=("Microsoft YaHei UI", 9), foreground=COLOR_TEXT, background="#eef2f7", borderwidth=0)
        style.map("Ghost.TButton", background=[("active", "#e5e7eb"), ("disabled", "#f3f4f6")])
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=COLOR_TEXT, rowheight=28, font=("Microsoft YaHei UI", 9))
        style.configure("Treeview.Heading", background="#f8fafc", foreground=COLOR_MUTED, font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", COLOR_SELECTED)], foreground=[("selected", COLOR_TEXT)])
        style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure("Horizontal.TProgressbar", troughcolor="#e5e7eb", background=COLOR_ACCENT)

    def create_widgets(self):
        shell = tk.Frame(self.root, bg=COLOR_BG)
        shell.pack(fill="both", expand=True)

        self._create_sidebar(shell)

        main = tk.Frame(shell, bg=COLOR_BG)
        main.pack(side="left", fill="both", expand=True)

        self.page_host = tk.Frame(main, bg=COLOR_BG)
        self.page_host.pack(fill="both", expand=True, padx=22, pady=18)

        self.single_page = tk.Frame(self.page_host, bg=COLOR_BG)
        self.batch_page = tk.Frame(self.page_host, bg=COLOR_BG)
        for page in (self.single_page, self.batch_page):
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.create_single_tab()
        self.create_batch_tab()
        self.show_page("single")

    def _create_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=COLOR_SIDEBAR, width=220, highlightthickness=1, highlightbackground=COLOR_BORDER)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=COLOR_SIDEBAR)
        brand.pack(fill="x", padx=18, pady=(22, 12))

        if self.header_icon:
            tk.Label(brand, image=self.header_icon, bg=COLOR_SIDEBAR).pack()
        else:
            tk.Label(brand, text="▣", bg=COLOR_SIDEBAR, fg=COLOR_ACCENT, font=("Segoe UI Symbol", 28)).pack()

        nav = tk.Frame(sidebar, bg=COLOR_SIDEBAR)
        nav.pack(fill="x", padx=12, pady=8)

        self._add_nav_item(nav, "single", "单设备抓图", "⌂")
        self._add_nav_item(nav, "batch", "批量设备抓图", "≣")

        footer = tk.Frame(sidebar, bg=COLOR_SIDEBAR)
        footer.pack(side="bottom", fill="x", padx=16, pady=16)
        tk.Frame(footer, bg=COLOR_BORDER, height=1).pack(fill="x", pady=(0, 12))
        self.status_label = tk.Label(footer, text="就绪", bg=COLOR_SIDEBAR, fg=COLOR_MUTED, font=("Microsoft YaHei UI", 8), wraplength=180, justify="left", anchor="w")
        self.status_label.pack(anchor="w")
        self.stats_label = tk.Label(footer, text="海康 / 大华 / 宇视", bg=COLOR_SIDEBAR, fg=COLOR_ACCENT, font=("Microsoft YaHei UI", 8), anchor="w")
        self.stats_label.pack(anchor="w", pady=(6, 0))

    def _add_nav_item(self, parent, page_id, text, icon):
        btn = tk.Frame(parent, bg=COLOR_SIDEBAR, cursor="hand2")
        btn.pack(fill="x", pady=3)
        inner = tk.Frame(btn, bg=COLOR_SIDEBAR)
        inner.pack(fill="x", padx=4, pady=8)
        icon_lbl = tk.Label(inner, text=icon, bg=COLOR_SIDEBAR, fg=COLOR_TEXT, font=("Segoe UI Symbol", 11), width=3)
        icon_lbl.pack(side="left")
        text_lbl = tk.Label(inner, text=text, bg=COLOR_SIDEBAR, fg=COLOR_TEXT, font=("Microsoft YaHei UI", 10), anchor="w")
        text_lbl.pack(side="left", fill="x", expand=True)

        def on_click(_event=None):
            self.show_page(page_id)

        for widget in (btn, inner, icon_lbl, text_lbl):
            widget.bind("<Button-1>", on_click)
        self.nav_buttons[page_id] = (btn, inner, icon_lbl, text_lbl)

    def show_page(self, page_id):
        self.current_page = page_id
        target = self.single_page if page_id == "single" else self.batch_page
        target.lift()
        for key, widgets in self.nav_buttons.items():
            selected = key == page_id
            bg = COLOR_SELECTED if selected else COLOR_SIDEBAR
            fg = COLOR_ACCENT if selected else COLOR_TEXT
            for widget in widgets:
                widget.configure(bg=bg)
            widgets[2].configure(fg=fg)
            widgets[3].configure(fg=fg, font=("Microsoft YaHei UI", 10, "bold" if selected else "normal"))

    def _page_header(self, parent, title, subtitle):
        header = tk.Frame(parent, bg=COLOR_BG)
        header.pack(fill="x", pady=(0, 14))
        text_box = tk.Frame(header, bg=COLOR_BG)
        text_box.pack(side="left", fill="x", expand=True)
        ttk.Label(text_box, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(text_box, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(4, 0))
        actions = tk.Frame(parent, bg=COLOR_BG)
        actions.pack(fill="x", pady=(0, 12))
        return actions

    def _card(self, parent, title, expand=False):
        card = tk.Frame(parent, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
        card.pack(fill="both" if expand else "x", expand=expand, pady=(0, 12))
        inner = tk.Frame(card, bg=COLOR_CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(inner, text=title, bg=COLOR_CARD, fg=COLOR_TEXT, font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 10))
        body = tk.Frame(inner, bg=COLOR_CARD)
        body.pack(fill="both", expand=True)
        return body

    def create_single_tab(self):
        actions = self._page_header(self.single_page, "单设备抓图", "连接一台录像机，按通道范围抓取实时画面")
        self.start_btn = ttk.Button(actions, text="开始抓图", style="Accent.TButton", command=self.start_snapshot)
        self.start_btn.pack(side="left", padx=(0, 8), ipadx=10, ipady=4)
        self.stop_btn = ttk.Button(actions, text="停止", style="Ghost.TButton", command=self.stop_snapshot, state="disabled")
        self.stop_btn.pack(side="left", ipadx=10, ipady=4)

        config = self._card(self.single_page, "设备配置")
        for col in range(6):
            config.grid_columnconfigure(col, weight=1 if col in (1, 3, 5) else 0)

        ttk.Label(config, text="设备品牌", style="App.TLabel").grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        self.brand_var = tk.StringVar(value=BRAND_LABELS[BRAND_AUTO])
        self.brand_combo = ttk.Combobox(
            config,
            textvariable=self.brand_var,
            values=list(BRAND_LABELS.values()),
            state="readonly",
            width=16,
            style="App.TCombobox",
        )
        self.brand_combo.grid(row=0, column=1, padx=(0, 16), pady=6, sticky="w")

        ttk.Label(config, text="设备 IP", style="App.TLabel").grid(row=0, column=2, padx=(0, 8), pady=6, sticky="w")
        self.ip_addr = ttk.Entry(config, width=22, style="App.TEntry")
        self.ip_addr.grid(row=0, column=3, padx=(0, 16), pady=6, sticky="ew")
        self.ip_addr.insert(0, "192.168.1.64")

        ttk.Label(config, text="用户名", style="App.TLabel").grid(row=1, column=0, padx=(0, 8), pady=6, sticky="w")
        self.username = ttk.Entry(config, width=18, style="App.TEntry")
        self.username.grid(row=1, column=1, padx=(0, 16), pady=6, sticky="w")
        self.username.insert(0, "admin")

        ttk.Label(config, text="密码", style="App.TLabel").grid(row=1, column=2, padx=(0, 8), pady=6, sticky="w")
        self.password = ttk.Entry(config, width=22, show="*", style="App.TEntry")
        self.password.grid(row=1, column=3, padx=(0, 16), pady=6, sticky="ew")
        self.password.insert(0, "12345")

        ttk.Label(config, text="通道从", style="App.TLabel").grid(row=2, column=0, padx=(0, 8), pady=6, sticky="w")
        self.channel_start = ttk.Entry(config, width=8, style="App.TEntry")
        self.channel_start.grid(row=2, column=1, padx=(0, 16), pady=6, sticky="w")
        self.channel_start.insert(0, "1")

        ttk.Label(config, text="通道到", style="App.TLabel").grid(row=2, column=2, padx=(0, 8), pady=6, sticky="w")
        self.channel_end = ttk.Entry(config, width=8, style="App.TEntry")
        self.channel_end.grid(row=2, column=3, padx=(0, 16), pady=6, sticky="w")
        self.channel_end.insert(0, "4")

        ttk.Label(config, text="保存路径", style="App.TLabel").grid(row=3, column=0, padx=(0, 8), pady=6, sticky="w")
        path_wrap = tk.Frame(config, bg=COLOR_CARD)
        path_wrap.grid(row=3, column=1, columnspan=5, pady=6, sticky="ew")
        self.save_path = ttk.Entry(path_wrap, style="App.TEntry")
        self.save_path.pack(side="left", fill="x", expand=True, padx=(0, 8))
        default_path = os.path.join(os.path.expanduser("~"), "Desktop", "NVR多通道截图")
        self.save_path.insert(0, default_path)
        ttk.Button(path_wrap, text="浏览", style="Ghost.TButton", command=self.browse_save_path).pack(side="left")

        self.duplicate_check = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            config,
            text="自动跳过重复画面的通道（适合单通道设备）",
            variable=self.duplicate_check,
            style="App.TCheckbutton",
        ).grid(row=4, column=0, columnspan=5, pady=(8, 0), sticky="w")

        log_body = self._card(self.single_page, "执行日志", expand=True)
        self.log_text = self._create_log_widget(log_body)

    def create_batch_tab(self):
        actions = self._page_header(self.batch_page, "批量设备抓图", "导入设备表后一键抓取，支持海康、大华、宇视")
        self.batch_start_btn = ttk.Button(actions, text="一键执行", style="Accent.TButton", command=self.start_batch_snapshot)
        self.batch_start_btn.pack(side="left", padx=(0, 8), ipadx=10, ipady=4)
        self.batch_stop_btn = ttk.Button(actions, text="停止", style="Ghost.TButton", command=self.stop_snapshot, state="disabled")
        self.batch_stop_btn.pack(side="left", ipadx=10, ipady=4)

        list_body = self._card(self.batch_page, "设备列表", expand=False)
        tool_frame = tk.Frame(list_body, bg=COLOR_CARD)
        tool_frame.pack(fill="x", pady=(0, 8))
        ttk.Button(tool_frame, text="下载导入模板", style="Ghost.TButton", command=self.download_template).pack(side="left", padx=(0, 6))
        ttk.Button(tool_frame, text="导入设备表", style="Ghost.TButton", command=self.import_devices).pack(side="left", padx=6)
        ttk.Button(tool_frame, text="全选", style="Ghost.TButton", command=self.select_all_devices).pack(side="left", padx=6)
        ttk.Button(tool_frame, text="取消全选", style="Ghost.TButton", command=self.deselect_all_devices).pack(side="left", padx=6)
        ttk.Label(tool_frame, text="点击行可切换选中状态", style="Muted.TLabel").pack(side="left", padx=10)

        tree_frame = tk.Frame(list_body, bg=COLOR_CARD)
        tree_frame.pack(fill="both", expand=True)
        columns = ("checked", "name", "ip", "brand", "username")
        self.device_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=7)
        self.device_tree.heading("checked", text="选择")
        self.device_tree.heading("name", text="设备名称")
        self.device_tree.heading("ip", text="IP 地址")
        self.device_tree.heading("brand", text="品牌")
        self.device_tree.heading("username", text="用户名")
        self.device_tree.column("checked", width=56, anchor="center")
        self.device_tree.column("name", width=180, anchor="w")
        self.device_tree.column("ip", width=140, anchor="w")
        self.device_tree.column("brand", width=90, anchor="center")
        self.device_tree.column("username", width=100, anchor="w")
        self.device_tree.pack(side="left", fill="both", expand=True)
        self.device_tree.bind("<ButtonRelease-1>", self.toggle_device_selection)
        tree_scroll = ttk.Scrollbar(tree_frame, command=self.device_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.device_tree.config(yscrollcommand=tree_scroll.set)

        option_body = self._card(self.batch_page, "抓图选项")
        naming_frame = tk.Frame(option_body, bg=COLOR_CARD)
        naming_frame.pack(fill="x")
        ttk.Label(naming_frame, text="文件命名包含", style="App.TLabel").pack(side="left", padx=(0, 10))

        self.name_device = tk.BooleanVar(value=True)
        self.name_ip = tk.BooleanVar(value=True)
        self.name_channel_name = tk.BooleanVar(value=True)
        self.name_channel_id = tk.BooleanVar(value=True)
        self.name_date = tk.BooleanVar(value=True)
        self.name_time = tk.BooleanVar(value=True)
        for text, var in [
            ("设备名", self.name_device),
            ("IP", self.name_ip),
            ("通道名", self.name_channel_name),
            ("通道编号", self.name_channel_id),
            ("日期", self.name_date),
            ("时间", self.name_time),
        ]:
            ttk.Checkbutton(naming_frame, text=text, variable=var, style="App.TCheckbutton").pack(side="left", padx=4)

        self.batch_duplicate_check = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            option_body,
            text="自动跳过重复画面的通道",
            variable=self.batch_duplicate_check,
            style="App.TCheckbutton",
        ).pack(anchor="w", pady=(10, 8))

        path_frame = tk.Frame(option_body, bg=COLOR_CARD)
        path_frame.pack(fill="x")
        ttk.Label(path_frame, text="保存路径", style="App.TLabel").pack(side="left")
        self.batch_save_path = ttk.Entry(path_frame, style="App.TEntry")
        self.batch_save_path.pack(side="left", padx=8, fill="x", expand=True)
        default_path = os.path.join(os.path.expanduser("~"), "Desktop", "NVR批量截图")
        self.batch_save_path.insert(0, default_path)
        ttk.Button(path_frame, text="浏览", style="Ghost.TButton", command=self.browse_batch_save_path).pack(side="left")

        log_body = self._card(self.batch_page, "执行日志", expand=True)
        self.batch_log_text = self._create_log_widget(log_body)

    def _create_log_widget(self, parent):
        wrap = tk.Frame(parent, bg=COLOR_LOG, highlightthickness=1, highlightbackground=COLOR_BORDER)
        wrap.pack(fill="both", expand=True)
        text = tk.Text(
            wrap,
            height=10,
            state="disabled",
            bg=COLOR_LOG,
            fg=COLOR_TEXT,
            relief="flat",
            font=("Consolas", 9),
            padx=10,
            pady=8,
            wrap="word",
        )
        text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(wrap, command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.config(yscrollcommand=scrollbar.set)
        text.tag_configure("time", foreground="#9ca3af")
        text.tag_configure("info", foreground=COLOR_ACCENT)
        text.tag_configure("ok", foreground=COLOR_SUCCESS)
        text.tag_configure("warn", foreground=COLOR_WARN)
        text.tag_configure("err", foreground=COLOR_ERROR)
        return text

    def browse_save_path(self):
        path = filedialog.askdirectory(title="选择截图保存目录")
        if path:
            self.save_path.delete(0, tk.END)
            self.save_path.insert(0, path)

    def browse_batch_save_path(self):
        path = filedialog.askdirectory(title="选择批量截图保存目录")
        if path:
            self.batch_save_path.delete(0, tk.END)
            self.batch_save_path.insert(0, path)

    def _log_tag(self, message):
        if any(word in message for word in ("错误", "失败", "连接失败")):
            return "err"
        if any(word in message for word in ("跳过", "警告")):
            return "warn"
        if "成功" in message:
            return "ok"
        return "info"

    def log(self, message, batch=False):
        widget = self.batch_log_text if batch else self.log_text
        stamp = datetime.now().strftime("%H:%M:%S")
        tag = self._log_tag(message)

        def append():
            widget.config(state="normal")
            widget.insert(tk.END, f"{stamp}  ", "time")
            widget.insert(tk.END, f"{message}\n", tag)
            widget.see(tk.END)
            widget.config(state="disabled")

        self.root.after(0, append)

    def is_valid_ip(self, ip):
        pattern = r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
        match = re.match(pattern, ip)
        if not match:
            return False
        return all(0 <= int(part) <= 255 for part in match.groups())

    def selected_brand(self):
        return normalize_brand(self.brand_var.get(), BRAND_AUTO)

    def get_channel_list(self):
        try:
            start = int(self.channel_start.get().strip())
            end = int(self.channel_end.get().strip())
            if start < 1 or end < start:
                return []
            return [{"channel_id": cid, "channel_name": f"通道{cid}"} for cid in range(start, end + 1)]
        except ValueError:
            return []

    def get_image_hash(self, image_data):
        try:
            img = Image.open(io.BytesIO(image_data)).convert("L")
            img = img.resize((8, 8), Image.LANCZOS)
            avg_pixel = sum(img.getdata()) / 64
            return "".join(["1" if p > avg_pixel else "0" for p in img.getdata()])
        except Exception:
            return None

    def build_filename(self, device_name, ip, channel_name, channel_id, naming_options, now=None):
        now = now or datetime.now()
        parts = []
        if naming_options.get("device"):
            parts.append(sanitize_filename(device_name) or "设备")
        if naming_options.get("ip"):
            parts.append(sanitize_filename(ip))
        if naming_options.get("channel_name"):
            parts.append(sanitize_filename(channel_name) or f"通道{channel_id}")
        if naming_options.get("channel_id"):
            parts.append(f"CH{channel_id:02d}")
        if naming_options.get("date"):
            parts.append(now.strftime("%Y%m%d"))
        if naming_options.get("time"):
            parts.append(now.strftime("%H%M%S"))
        if not parts:
            parts = [sanitize_filename(ip) or "device", f"CH{channel_id:02d}", now.strftime("%Y%m%d_%H%M%S")]
        return "_".join(parts) + ".jpg"

    def get_naming_options(self, batch=False):
        if batch:
            return {
                "device": self.name_device.get(),
                "ip": self.name_ip.get(),
                "channel_name": self.name_channel_name.get(),
                "channel_id": self.name_channel_id.get(),
                "date": self.name_date.get(),
                "time": self.name_time.get(),
            }
        return {
            "device": False,
            "ip": True,
            "channel_name": False,
            "channel_id": True,
            "date": True,
            "time": True,
        }

    def parse_channels_from_xml(self, xml_text, source):
        channels = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return channels

        if source == "input_proxy":
            for item in root.iter():
                if local_tag(item.tag) != "InputProxyChannel":
                    continue
                channel_id = None
                channel_name = None
                for child in item:
                    tag = local_tag(child.tag)
                    if tag == "id" and child.text:
                        channel_id = int(child.text.strip())
                    elif tag == "name" and child.text:
                        channel_name = child.text.strip()
                if channel_id is not None:
                    channels.append({"channel_id": channel_id, "channel_name": channel_name or f"通道{channel_id}"})
        elif source == "video_inputs":
            for item in root.iter():
                if local_tag(item.tag) != "VideoInputChannel":
                    continue
                channel_id = None
                channel_name = None
                for child in item:
                    tag = local_tag(child.tag)
                    if tag == "id" and child.text:
                        channel_id = int(child.text.strip())
                    elif tag in ("name", "inputName") and child.text and not channel_name:
                        channel_name = child.text.strip()
                if channel_id is not None:
                    channels.append({"channel_id": channel_id, "channel_name": channel_name or f"通道{channel_id}"})
        else:
            seen = set()
            for item in root.iter():
                if local_tag(item.tag) != "StreamingChannel":
                    continue
                channel_id = None
                channel_name = None
                for child in item:
                    tag = local_tag(child.tag)
                    if tag == "id" and child.text:
                        stream_id = int(child.text.strip())
                        channel_id = stream_id // 100
                    elif tag == "channelName" and child.text:
                        channel_name = child.text.strip()
                if channel_id and channel_id not in seen:
                    seen.add(channel_id)
                    channels.append({"channel_id": channel_id, "channel_name": channel_name or f"通道{channel_id}"})

        channels.sort(key=lambda x: x["channel_id"])
        return channels

    def parse_dahua_channel_title(self, text):
        channels = []
        for match in re.finditer(r"ChannelTitle\[(\d+)\]\.Name=(.*)", text or ""):
            index = int(match.group(1))
            name = match.group(2).strip() or f"通道{index + 1}"
            channels.append({"channel_id": index + 1, "channel_name": name})
        channels.sort(key=lambda x: x["channel_id"])
        return channels

    def parse_uniview_channels(self, payload):
        channels = []
        seen = set()

        def walk(node):
            if isinstance(node, dict):
                channel_id = None
                for key in ("ChannelID", "channelID", "ID", "Id", "id", "Channel", "channel"):
                    if key in node and str(node[key]).strip().isdigit():
                        channel_id = int(str(node[key]).strip())
                        break
                name = None
                for key in ("ChannelName", "channelName", "Name", "name", "DeviceName"):
                    if key in node and node[key]:
                        name = str(node[key]).strip()
                        break
                enable = node.get("Enable", node.get("Online", True))
                if channel_id is not None and enable not in (False, 0, "false", "False"):
                    if channel_id not in seen:
                        seen.add(channel_id)
                        channels.append({"channel_id": channel_id, "channel_name": name or f"通道{channel_id}"})
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        channels.sort(key=lambda x: x["channel_id"])
        return channels

    def detect_brand(self, ip, username, password):
        probes = [
            (BRAND_HIKVISION, f"http://{ip}/ISAPI/System/deviceInfo", "xml"),
            (BRAND_DAHUA, f"http://{ip}/cgi-bin/magicBox.cgi?action=getSystemInfo", "text"),
            (BRAND_DAHUA, f"http://{ip}/cgi-bin/magicBox.cgi?action=getDeviceType", "text"),
            (BRAND_UNIVIEW, f"http://{ip}/LAPI/V1.0/System/DeviceBasicInfo", "json"),
            (BRAND_UNIVIEW, f"http://{ip}/LAPI/V1.0/System/Time", "json"),
        ]
        for brand, url, kind in probes:
            try:
                response = request_with_auth("GET", url, username, password, timeout=8)
                if response.status_code != 200:
                    continue
                body = response.text or ""
                if brand == BRAND_HIKVISION and ("<deviceName" in body or "ISAPI" in body or "<DeviceInfo" in body):
                    return brand
                if brand == BRAND_DAHUA and ("table." in body or "deviceType" in body.lower() or "serialNumber" in body):
                    return brand
                if brand == BRAND_UNIVIEW:
                    try:
                        data = response.json()
                    except Exception:
                        continue
                    if isinstance(data, dict) and ("Response" in data or "ResponseCode" in data):
                        return brand
            except Exception:
                continue
        return None

    def resolve_brand(self, ip, username, password, preferred=BRAND_AUTO):
        brand = normalize_brand(preferred, BRAND_AUTO)
        if brand != BRAND_AUTO:
            return brand, None
        detected = self.detect_brand(ip, username, password)
        if detected:
            return detected, None
        return None, "无法识别设备品牌，请手动选择海康、大华或宇视"

    def snapshot_candidates(self, ip, brand, channel_id):
        if brand == BRAND_HIKVISION:
            stream_id = channel_id * 100 + 1
            return [f"http://{ip}/ISAPI/Streaming/channels/{stream_id}/picture"]
        if brand == BRAND_DAHUA:
            urls = [f"http://{ip}/cgi-bin/snapshot.cgi?channel={channel_id}"]
            if channel_id > 0:
                urls.append(f"http://{ip}/cgi-bin/snapshot.cgi?channel={channel_id - 1}")
            return urls
        if brand == BRAND_UNIVIEW:
            urls = [f"http://{ip}/LAPI/V1.0/Channels/{channel_id}/Media/Video/Streams/0/Snapshot"]
            if channel_id > 0:
                urls.append(f"http://{ip}/LAPI/V1.0/Channels/{channel_id - 1}/Media/Video/Streams/0/Snapshot")
            urls.append(f"http://{ip}/images/snapshot.jpg?chn={channel_id}")
            return urls
        return []

    def probe_channels(self, ip, username, password, brand):
        channels = []
        consecutive_fail = 0
        for channel_id in range(1, MAX_PROBE_CHANNELS + 1):
            ok = False
            for url in self.snapshot_candidates(ip, brand, channel_id):
                try:
                    response = request_with_auth("GET", url, username, password, timeout=6)
                    if response.status_code == 200 and looks_like_image(response.content, response.headers.get("Content-Type", "")):
                        ok = True
                        break
                except Exception:
                    continue
            if ok:
                channels.append({"channel_id": channel_id, "channel_name": f"通道{channel_id}"})
                consecutive_fail = 0
            else:
                consecutive_fail += 1
            if consecutive_fail >= CONSECUTIVE_FAIL_STOP and channels:
                break
        return channels

    def discover_channels(self, ip, username, password, brand):
        if brand == BRAND_HIKVISION:
            endpoints = [
                ("input_proxy", f"http://{ip}/ISAPI/ContentMgmt/InputProxy/channels"),
                ("streaming", f"http://{ip}/ISAPI/Streaming/channels"),
                ("video_inputs", f"http://{ip}/ISAPI/System/Video/inputs/channels"),
            ]
            for source, url in endpoints:
                try:
                    response = request_with_auth("GET", url, username, password, timeout=10)
                    if response.status_code != 200:
                        continue
                    channels = self.parse_channels_from_xml(response.text, source)
                    if channels:
                        return channels, None
                except Exception:
                    continue
        elif brand == BRAND_DAHUA:
            urls = [
                f"http://{ip}/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle",
                f"http://{ip}/cgi-bin/configManager.cgi?action=getConfig&name=RemoteDevice",
            ]
            for url in urls:
                try:
                    response = request_with_auth("GET", url, username, password, timeout=10)
                    if response.status_code != 200:
                        continue
                    channels = self.parse_dahua_channel_title(response.text)
                    if channels:
                        return channels, None
                except Exception:
                    continue
        elif brand == BRAND_UNIVIEW:
            urls = [
                f"http://{ip}/LAPI/V1.0/Channels/System/ChannelDetailInfos",
                f"http://{ip}/LAPI/V1.0/Channels/System/DeviceInfos",
                f"http://{ip}/LAPI/V1.0/Channels/System/ChannelInfos",
            ]
            for url in urls:
                try:
                    response = request_with_auth("GET", url, username, password, timeout=10)
                    if response.status_code != 200:
                        continue
                    try:
                        payload = response.json()
                    except Exception:
                        continue
                    channels = self.parse_uniview_channels(payload)
                    if channels:
                        return channels, None
                except Exception:
                    continue

        try:
            channels = self.probe_channels(ip, username, password, brand)
            if channels:
                return channels, None
            return [], "未发现可用通道"
        except Exception as exc:
            return [], str(exc)

    def test_device_connection(self, ip, username, password, brand):
        urls = {
            BRAND_HIKVISION: [
                f"http://{ip}/ISAPI/System/deviceInfo",
                f"http://{ip}/ISAPI/Streaming/channels/101/picture",
            ],
            BRAND_DAHUA: [
                f"http://{ip}/cgi-bin/magicBox.cgi?action=getSystemInfo",
                f"http://{ip}/cgi-bin/snapshot.cgi?channel=1",
            ],
            BRAND_UNIVIEW: [
                f"http://{ip}/LAPI/V1.0/System/DeviceBasicInfo",
                f"http://{ip}/LAPI/V1.0/System/Time",
                f"http://{ip}/LAPI/V1.0/Channels/1/Media/Video/Streams/0/Snapshot",
            ],
        }.get(brand, [])
        last_error = "连接失败"
        for url in urls:
            try:
                response = request_with_auth("GET", url, username, password, timeout=10)
                if response.status_code == 200:
                    return True, None
                last_error = f"HTTP {response.status_code}"
            except Exception as exc:
                last_error = str(exc)
        return False, last_error

    def capture_single_channel(
        self,
        ip,
        username,
        password,
        channel_id,
        save_dir,
        device_name="",
        channel_name=None,
        naming_options=None,
        duplicate_check=True,
        log_prefix="",
        batch=False,
        brand=BRAND_HIKVISION,
    ):
        channel_name = channel_name or f"通道{channel_id}"
        naming_options = naming_options or self.get_naming_options(batch=batch)
        last_error = "无可用抓图地址"

        try:
            content = None
            for snapshot_url in self.snapshot_candidates(ip, brand, channel_id):
                try:
                    response = request_with_auth("GET", snapshot_url, username, password, timeout=10)
                except Exception as exc:
                    last_error = str(exc)
                    continue
                if response.status_code != 200:
                    last_error = f"状态码 {response.status_code}"
                    continue
                if not looks_like_image(response.content, response.headers.get("Content-Type", "")):
                    last_error = "返回内容不是有效图片"
                    continue
                content = response.content
                break

            if content is None:
                self.log(f"{log_prefix}失败：{channel_name}（编号 {channel_id}，{last_error}）", batch=batch)
                self.fail_count += 1
                return False

            if duplicate_check:
                img_hash = self.get_image_hash(content)
                if img_hash and img_hash in self.valid_channel_hashes:
                    self.log(f"{log_prefix}跳过：{channel_name}（编号 {channel_id}，画面重复）", batch=batch)
                    self.fail_count += 1
                    return False
                if img_hash:
                    self.valid_channel_hashes.add(img_hash)

            filename = self.build_filename(device_name, ip, channel_name, channel_id, naming_options)
            save_path = os.path.join(save_dir, filename)
            with open(save_path, "wb") as f:
                f.write(content)

            self.log(f"{log_prefix}成功：{channel_name}（编号 {channel_id}）-> {filename}", batch=batch)
            self.success_count += 1
            return True
        except Exception as exc:
            self.log(f"{log_prefix}错误：{channel_name}（编号 {channel_id}，{exc}）", batch=batch)
            self.fail_count += 1
            return False

    def batch_snapshot(self):
        ip = self.ip_addr.get().strip()
        username = self.username.get().strip()
        password = self.password.get().strip()
        save_dir = self.save_path.get().strip()
        channels = self.get_channel_list()

        if not (self.is_valid_ip(ip) and username and password and channels):
            messagebox.showerror("输入错误", "请填写有效参数，通道范围需为正整数（如1-4）")
            self.reset_state()
            return

        brand, brand_error = self.resolve_brand(ip, username, password, self.selected_brand())
        if not brand:
            messagebox.showerror("品牌识别失败", brand_error)
            self.reset_state()
            return

        self.valid_channel_hashes.clear()
        os.makedirs(save_dir, exist_ok=True)
        total_channels = len(channels)
        self.log(
            f"开始对 {ip}（{brand_label(brand)}）通道 {channels[0]['channel_id']}-{channels[-1]['channel_id']} 抓图，共 {total_channels} 个通道"
        )
        self.success_count = 0
        self.fail_count = 0
        naming_options = self.get_naming_options(batch=False)

        for i, channel in enumerate(channels):
            if not self.running:
                break
            channel_id = channel["channel_id"]
            self._set_status(f"正在处理：通道 {channel_id}（{i + 1}/{total_channels}）")
            self.capture_single_channel(
                ip,
                username,
                password,
                channel_id,
                save_dir,
                channel_name=channel["channel_name"],
                naming_options=naming_options,
                duplicate_check=self.duplicate_check.get(),
                brand=brand,
            )
            time.sleep(1)

        self.log(f"处理完成 - 成功：{self.success_count} 个，失败/重复：{self.fail_count} 个")
        self._set_status(f"处理完成 - 成功：{self.success_count}，失败/重复：{self.fail_count}")
        self.reset_state()

    def _set_status(self, text):
        self.root.after(0, lambda: self.status_label.config(text=text))

    def start_snapshot(self):
        self.running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.batch_start_btn.config(state="disabled")
        self.batch_stop_btn.config(state="normal")
        self._set_status("准备中...")
        threading.Thread(target=self.batch_snapshot, daemon=True).start()

    def stop_snapshot(self):
        self.running = False
        self._set_status("正在停止...")
        self.stop_btn.config(state="disabled")
        self.batch_stop_btn.config(state="disabled")

    def reset_state(self):
        self.running = False

        def restore():
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.batch_start_btn.config(state="normal")
            self.batch_stop_btn.config(state="disabled")

        self.root.after(0, restore)

    def download_template(self):
        path = filedialog.asksaveasfilename(
            title="保存设备导入模板",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            initialfile="设备导入模板.csv",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(TEMPLATE_HEADERS)
                writer.writerow(["示例海康站点", "192.168.1.64", "admin", "12345", "海康"])
                writer.writerow(["示例大华站点", "192.168.1.65", "admin", "12345", "大华"])
                writer.writerow(["示例宇视站点", "192.168.1.66", "admin", "12345", "宇视"])
            messagebox.showinfo("成功", f"模板已保存到：\n{path}")
        except Exception as exc:
            messagebox.showerror("错误", f"保存模板失败：{exc}")

    def import_devices(self):
        path = filedialog.askopenfilename(
            title="选择设备表",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
        )
        if not path:
            return

        imported = []
        errors = []
        required = ["设备名称", "IP地址", "用户名", "密码"]

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                field_map = {}
                if reader.fieldnames:
                    normalized = {name.strip(): name for name in reader.fieldnames if name}
                    for header in TEMPLATE_HEADERS:
                        if header in normalized:
                            field_map[header] = normalized[header]

                if any(header not in field_map for header in required):
                    messagebox.showerror("导入错误", "表头不正确，至少需要：设备名称、IP地址、用户名、密码。可选列：设备品牌")
                    return

                for row_no, row in enumerate(reader, start=2):
                    name = row.get(field_map["设备名称"], "").strip()
                    ip = row.get(field_map["IP地址"], "").strip()
                    username = row.get(field_map["用户名"], "").strip()
                    password = row.get(field_map["密码"], "").strip()
                    brand_raw = row.get(field_map.get("设备品牌", ""), "").strip() if "设备品牌" in field_map else ""

                    if not any([name, ip, username, password, brand_raw]):
                        continue
                    if not name:
                        errors.append(f"第 {row_no} 行：设备名称不能为空")
                        continue
                    if not self.is_valid_ip(ip):
                        errors.append(f"第 {row_no} 行：IP 地址无效（{ip}）")
                        continue
                    if not username or not password:
                        errors.append(f"第 {row_no} 行：用户名或密码不能为空")
                        continue

                    imported.append(
                        {
                            "name": name,
                            "ip": ip,
                            "username": username,
                            "password": password,
                            "brand": normalize_brand(brand_raw, BRAND_AUTO),
                        }
                    )
        except Exception as exc:
            messagebox.showerror("导入错误", f"读取文件失败：{exc}")
            return

        if not imported:
            messagebox.showwarning("导入结果", "未导入任何有效设备。" + ("\n" + "\n".join(errors[:5]) if errors else ""))
            return

        self.batch_devices = imported
        self.refresh_device_tree(default_checked=True)
        msg = f"成功导入 {len(imported)} 台设备。"
        if errors:
            msg += f"\n跳过 {len(errors)} 行无效数据。"
        messagebox.showinfo("导入完成", msg)
        self.log(f"导入设备表完成，共 {len(imported)} 台设备", batch=True)

    def refresh_device_tree(self, default_checked=True):
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        self.device_checked.clear()
        for index, device in enumerate(self.batch_devices):
            item_id = f"dev_{index}"
            self.device_checked[item_id] = default_checked
            mark = "☑" if default_checked else "☐"
            self.device_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(mark, device["name"], device["ip"], brand_label(device.get("brand", BRAND_AUTO)), device["username"]),
            )

    def toggle_device_selection(self, event):
        region = self.device_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        item_id = self.device_tree.identify_row(event.y)
        if not item_id:
            return
        current = self.device_checked.get(item_id, False)
        self.device_checked[item_id] = not current
        values = list(self.device_tree.item(item_id, "values"))
        values[0] = "☑" if not current else "☐"
        self.device_tree.item(item_id, values=values)

    def select_all_devices(self):
        for item_id in self.device_tree.get_children():
            self.device_checked[item_id] = True
            values = list(self.device_tree.item(item_id, "values"))
            values[0] = "☑"
            self.device_tree.item(item_id, values=values)

    def deselect_all_devices(self):
        for item_id in self.device_tree.get_children():
            self.device_checked[item_id] = False
            values = list(self.device_tree.item(item_id, "values"))
            values[0] = "☐"
            self.device_tree.item(item_id, values=values)

    def get_selected_devices(self):
        selected = []
        for index, device in enumerate(self.batch_devices):
            item_id = f"dev_{index}"
            if self.device_checked.get(item_id, False):
                selected.append(device)
        return selected

    def start_batch_snapshot(self):
        selected = self.get_selected_devices()
        if not selected:
            messagebox.showwarning("提示", "请至少选择一台设备")
            return
        save_dir = self.batch_save_path.get().strip()
        if not save_dir:
            messagebox.showerror("输入错误", "请填写保存路径")
            return
        self.running = True
        self.batch_start_btn.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.batch_stop_btn.config(state="normal")
        self._set_status("批量抓图准备中...")
        threading.Thread(target=self.run_batch_devices, args=(selected, save_dir), daemon=True).start()

    def run_batch_devices(self, devices, save_dir):
        os.makedirs(save_dir, exist_ok=True)
        naming_options = self.get_naming_options(batch=True)
        duplicate_check = self.batch_duplicate_check.get()
        total_devices = len(devices)
        device_summaries = []

        self.log(f"开始批量抓图，共选择 {total_devices} 台设备", batch=True)
        self.log("=" * 50, batch=True)

        for index, device in enumerate(devices, start=1):
            if not self.running:
                break

            name = device["name"]
            ip = device["ip"]
            username = device["username"]
            password = device["password"]
            prefix = f"[{name}|{ip}] "

            self._set_status(f"正在处理设备 {index}/{total_devices}：{name} ({ip})")
            self.log(f"{prefix}开始识别并连接...", batch=True)

            self.valid_channel_hashes.clear()
            self.success_count = 0
            self.fail_count = 0

            brand, brand_error = self.resolve_brand(ip, username, password, device.get("brand", BRAND_AUTO))
            if not brand:
                summary = f"{prefix}品牌识别失败：{brand_error}，成功 0 通道"
                self.log(summary, batch=True)
                device_summaries.append(
                    {"name": name, "ip": ip, "success": False, "ok": 0, "fail": 0, "total": 0, "message": brand_error}
                )
                self.log("-" * 50, batch=True)
                continue

            self.log(f"{prefix}设备品牌：{brand_label(brand)}", batch=True)

            connected, conn_error = self.test_device_connection(ip, username, password, brand)
            if not connected:
                summary = f"{prefix}设备连接失败：{conn_error}，成功 0 通道，失败 0 通道"
                self.log(summary, batch=True)
                device_summaries.append(
                    {"name": name, "ip": ip, "success": False, "ok": 0, "fail": 0, "total": 0, "message": conn_error}
                )
                self.log("-" * 50, batch=True)
                continue

            channels, discover_error = self.discover_channels(ip, username, password, brand)
            if not channels:
                summary = f"{prefix}未发现可用通道：{discover_error or '未知原因'}，成功 0 通道"
                self.log(summary, batch=True)
                device_summaries.append(
                    {
                        "name": name,
                        "ip": ip,
                        "success": False,
                        "ok": 0,
                        "fail": 0,
                        "total": 0,
                        "message": discover_error or "无通道",
                    }
                )
                self.log("-" * 50, batch=True)
                continue

            device_dir = os.path.join(save_dir, sanitize_filename(name) or sanitize_filename(ip))
            os.makedirs(device_dir, exist_ok=True)
            self.log(f"{prefix}连接成功，发现 {len(channels)} 个通道，开始逐通道抓图...", batch=True)

            for channel in channels:
                if not self.running:
                    break
                self.capture_single_channel(
                    ip,
                    username,
                    password,
                    channel["channel_id"],
                    device_dir,
                    device_name=name,
                    channel_name=channel["channel_name"],
                    naming_options=naming_options,
                    duplicate_check=duplicate_check,
                    log_prefix=prefix,
                    batch=True,
                    brand=brand,
                )
                time.sleep(0.5)

            device_ok = self.success_count > 0
            summary = (
                f"{prefix}设备抓图{'成功' if device_ok else '失败'}："
                f"共 {len(channels)} 个通道，成功 {self.success_count} 个，失败/跳过 {self.fail_count} 个"
            )
            self.log(summary, batch=True)
            device_summaries.append(
                {
                    "name": name,
                    "ip": ip,
                    "success": device_ok,
                    "ok": self.success_count,
                    "fail": self.fail_count,
                    "total": len(channels),
                    "message": "完成",
                }
            )
            self.log("-" * 50, batch=True)

        success_devices = sum(1 for item in device_summaries if item["success"])
        total_channels_ok = sum(item["ok"] for item in device_summaries)
        total_channels_fail = sum(item["fail"] for item in device_summaries)

        self.log("批量抓图汇总", batch=True)
        for item in device_summaries:
            status = "成功" if item["success"] else "失败"
            self.log(
                f"  - {item['name']} ({item['ip']})：{status}，通道 {item['total']} 个，"
                f"成功 {item['ok']}，失败/跳过 {item['fail']}",
                batch=True,
            )

        final_text = (
            f"批量完成：设备 {success_devices}/{len(device_summaries)} 台成功，"
            f"通道成功 {total_channels_ok} 个，失败/跳过 {total_channels_fail} 个"
        )
        self.log(final_text, batch=True)
        self._set_status(final_text)
        self.reset_state()


if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    app = NVRMultiChannelSnapshot(root)
    root.mainloop()
