from __future__ import annotations

import calendar
import os
import shutil
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk
from tkinter import font as tkfont

from tkcalendar import DateEntry

from expense_tracker import (
    add_expense,
    create_expense,
    delete_expense,
    get_expenses_by_day,
    get_expenses_for_day,
    get_paid_expense_ids,
    get_paid_total_for_month,
    get_total_for_month,
    load_expenses,
    set_expense_paid,
)


APP_DATA_FOLDER = "SubscriptionTracker"


def get_app_data_file() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        app_data_directory = Path(local_app_data) / APP_DATA_FOLDER
    else:
        app_data_directory = Path.home() / ".subscription_tracker"

    app_data_directory.mkdir(parents=True, exist_ok=True)
    source_directory = Path(__file__).resolve().parent
    database_file = app_data_directory / "expenses.db"

    # Preserve existing development data on the first run after upgrading.
    # PyInstaller does not bundle these files, so distributed copies start clean.
    for file_name in ("expenses.db", "expenses.json"):
        source_file = source_directory / file_name
        destination_file = app_data_directory / file_name
        if not destination_file.exists() and source_file.exists() and source_file.resolve() != destination_file.resolve():
            shutil.copy2(source_file, destination_file)

    return database_file


WARM_LIGHT = {
    "background": "#f4efeb",
    "panel": "#eadfd7",
    "panel_alt": "#f8f2ee",
    "surface": "#fffaf7",
    "hero": "#674733",
    "hero_border": "#8b6650",
    "hero_text": "#fffaf6",
    "hero_text_secondary": "#eadbd0",
    "text": "#382820",
    "text_secondary": "#69544a",
    "text_muted": "#8a7469",
    "accent": "#b65f3c",
    "accent_hover": "#994a2d",
    "border": "#d5c1b5",
    "calendar_bg": "#eee7e2",
    "calendar_cell": "#fffaf7",
    "calendar_selected": "#ead1c1",
    "calendar_selected_border": "#a65a3b",
    "calendar_today": "#e5d9d1",
    "calendar_today_border": "#91644f",
    "list_bg": "#fffaf7",
    "list_header": "#e4d4ca",
    "list_row_alt": "#f5ece7",
    "list_selected": "#c98262",
    "input_cursor": "#382820",
    "header_control": "#674733",
    "header_control_hover": "#7c5540",
    "header_control_text": "#fffaf6",
    "header_field": "#fffaf7",
}

WARM_DARK = {
    "background": "#1b130f",
    "panel": "#291f1a",
    "panel_alt": "#231a16",
    "surface": "#2d211b",
    "hero": "#302318",
    "hero_border": "#6e5038",
    "hero_text": "#fffaf6",
    "hero_text_secondary": "#d9c4b5",
    "text": "#f4e9dd",
    "text_secondary": "#e3d1be",
    "text_muted": "#bfab98",
    "accent": "#ff9f43",
    "accent_hover": "#ff8f2b",
    "border": "#553b2c",
    "calendar_bg": "#221a15",
    "calendar_cell": "#2d221b",
    "calendar_selected": "#5f4330",
    "calendar_selected_border": "#a36b3d",
    "calendar_today": "#6c4f38",
    "calendar_today_border": "#ba7f4d",
    "list_bg": "#2a201a",
    "list_header": "#3a2c24",
    "list_row_alt": "#221910",
    "list_selected": "#5f4635",
    "input_cursor": "#ffffff",
    "header_control": "#5a3d2e",
    "header_control_hover": "#76513d",
    "header_control_text": "#fffaf6",
    "header_field": "#2d211b",
}


def draw_rounded_rect(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int,
    fill: str,
    outline: str,
    width: int = 1,
) -> None:
    # Fill the shape without outlining its overlapping pieces. Drawing the
    # border separately avoids visible seams across rounded cards and cells.
    canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline="")
    canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline="")
    canvas.create_arc(x1, y1, x1 + 2 * radius, y1 + 2 * radius, start=90, extent=90, style="pieslice", fill=fill, outline="")
    canvas.create_arc(x2 - 2 * radius, y1, x2, y1 + 2 * radius, start=0, extent=90, style="pieslice", fill=fill, outline="")
    canvas.create_arc(x1, y2 - 2 * radius, x1 + 2 * radius, y2, start=180, extent=90, style="pieslice", fill=fill, outline="")
    canvas.create_arc(x2 - 2 * radius, y2 - 2 * radius, x2, y2, start=270, extent=90, style="pieslice", fill=fill, outline="")

    canvas.create_line(x1 + radius, y1, x2 - radius, y1, fill=outline, width=width)
    canvas.create_line(x2, y1 + radius, x2, y2 - radius, fill=outline, width=width)
    canvas.create_line(x1 + radius, y2, x2 - radius, y2, fill=outline, width=width)
    canvas.create_line(x1, y1 + radius, x1, y2 - radius, fill=outline, width=width)
    canvas.create_arc(x1, y1, x1 + 2 * radius, y1 + 2 * radius, start=90, extent=90, style="arc", outline=outline, width=width)
    canvas.create_arc(x2 - 2 * radius, y1, x2, y1 + 2 * radius, start=0, extent=90, style="arc", outline=outline, width=width)
    canvas.create_arc(x1, y2 - 2 * radius, x1 + 2 * radius, y2, start=180, extent=90, style="arc", outline=outline, width=width)
    canvas.create_arc(x2 - 2 * radius, y2 - 2 * radius, x2, y2, start=270, extent=90, style="arc", outline=outline, width=width)


class ExpenseTrackerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Subscription Tracker")
        self.root.geometry("1180x800")
        self.root.minsize(1020, 700)
        self.root.configure(bg=WARM_LIGHT["background"])

        self.data_file = get_app_data_file()
        self.expenses = load_expenses(self.data_file)
        self.current_date = date.today().replace(day=1)
        self.selected_date = date.today()
        self.account_filter = tk.StringVar(value="All accounts")
        self.theme_mode = tk.StringVar(value="light")
        self.paid_expense_ids: set[str] = set()
        self.day_summary_text = ""
        self.calendar_font = tkfont.Font(self.root, family="Segoe UI", size=8)
        self._apply_theme()

        self.build_ui()
        self.refresh_view()

    def _apply_theme(self) -> None:
        theme = self._theme()
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=theme["background"])
        style.configure("TLabel", background=theme["background"], foreground=theme["text"])
        style.configure(
            "TButton",
            padding=(10, 6),
            background=theme["panel_alt"],
            foreground=theme["text"],
        )
        style.map(
            "TButton",
            background=[("active", theme["border"]), ("pressed", theme["calendar_today_border"])],
            foreground=[("active", theme["text"]), ("pressed", theme["text"])],
        )
        style.configure(
            "TEntry",
            fieldbackground=theme["panel_alt"],
            foreground=theme["text"],
            insertcolor=theme["input_cursor"],
            padding=(6, 4),
        )
        style.configure(
            "TCombobox",
            fieldbackground=theme["panel_alt"],
            foreground=theme["text"],
            insertcolor=theme["input_cursor"],
            padding=(6, 4),
        )
        style.map("TCombobox", fieldbackground=[("readonly", theme["panel_alt"])])
        style.configure("Treeview", background=theme["list_bg"], fieldbackground=theme["list_bg"], foreground=theme["text"])
        style.configure("Treeview.Heading", background=theme["list_header"], foreground=theme["text"])
        style.map("Treeview", background=[("selected", theme["list_selected"])], foreground=[("selected", "#ffffff")])
        style.configure("Card.TFrame", background=theme["panel"], relief="flat")
        style.configure("Card.TLabel", background=theme["panel"], foreground=theme["text"], font=("Segoe UI", 10))
        style.configure(
            "Header.TButton",
            padding=(14, 7),
            background=theme["header_control"],
            foreground=theme["header_control_text"],
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Header.TButton",
            background=[
                ("active", theme["header_control_hover"]),
                ("pressed", theme["accent_hover"]),
            ],
            foreground=[
                ("active", theme["header_control_text"]),
                ("pressed", theme["header_control_text"]),
            ],
        )
        style.configure(
            "Nav.TButton",
            padding=(8, 5),
            background=theme["header_control"],
            foreground=theme["header_control_text"],
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Nav.TButton",
            background=[
                ("active", theme["header_control_hover"]),
                ("pressed", theme["accent_hover"]),
            ],
            foreground=[
                ("active", theme["header_control_text"]),
                ("pressed", theme["header_control_text"]),
            ],
        )
        style.configure(
            "Header.TCombobox",
            padding=(7, 5),
            fieldbackground=theme["header_field"],
            background=theme["header_control"],
            foreground=theme["text"],
            arrowcolor=theme["header_control_text"],
            bordercolor=theme["border"],
            insertcolor=theme["input_cursor"],
        )
        style.map(
            "Header.TCombobox",
            fieldbackground=[("readonly", theme["header_field"])],
            background=[("readonly", theme["header_control"]), ("active", theme["header_control_hover"])],
            foreground=[("readonly", theme["text"])],
        )

        self.root.option_add("*insertBackground", theme["input_cursor"])
        self.root.configure(bg=theme["background"])

    def _theme(self) -> dict[str, str]:
        return WARM_DARK if self.theme_mode.get() == "dark" else WARM_LIGHT

    def toggle_theme(self) -> None:
        self.theme_mode.set("dark" if self.theme_mode.get() == "light" else "light")
        self._apply_theme()
        self._refresh_theme_button()
        self.refresh_view()

    def _draw_welcome_card(self) -> None:
        if not hasattr(self, "welcome_canvas"):
            return
        theme = self._theme()
        self.welcome_canvas.configure(bg=theme["background"])
        self.welcome_canvas.delete("all")
        width = max(self.welcome_canvas.winfo_width(), 1)
        card_width = max(420, min(980, width - 40))
        x1 = (width - card_width) // 2
        y1 = 8
        x2 = x1 + card_width
        y2 = 88
        draw_rounded_rect(
            self.welcome_canvas,
            x1,
            y1,
            x2,
            y2,
            18,
            theme["hero"],
            theme["hero_border"],
            width=2,
        )
        self.welcome_canvas.create_text(
            (x1 + x2) // 2,
            y1 + 15,
            text=self._welcome_text(),
            anchor="n",
            fill=theme["hero_text"],
            font=("Segoe UI", 19, "bold"),
        )
        self.welcome_canvas.create_text(
            (x1 + x2) // 2,
            y1 + 53,
            text="Track your monthly subscriptions with clean visual cards and quick paid status.",
            width=card_width - 64,
            anchor="n",
            fill=theme["hero_text_secondary"],
            font=("Segoe UI", 10),
            justify="center",
        )

    def _draw_day_summary_card(self) -> None:
        if not hasattr(self, "day_summary_canvas"):
            return
        theme = self._theme()
        self.day_summary_canvas.configure(bg=theme["panel"])
        self.day_summary_canvas.delete("all")
        width = max(self.day_summary_canvas.winfo_width(), 1)
        height = max(self.day_summary_canvas.winfo_height(), 1)
        draw_rounded_rect(
            self.day_summary_canvas,
            1,
            1,
            width - 2,
            height - 2,
            12,
            theme["surface"],
            theme["border"],
        )
        self.day_summary_canvas.create_text(
            14,
            height // 2,
            text=self.day_summary_text,
            anchor="w",
            fill=theme["text"],
            font=("Segoe UI", 10),
        )

    def _refresh_theme_button(self) -> None:
        if not hasattr(self, "theme_button"):
            return
        if self.theme_mode.get() == "light":
            self.theme_button.configure(text="Dark mode")
        else:
            self.theme_button.configure(text="Light mode")

    def _welcome_text(self) -> str:
        return f"Welcome, your subscriptions are ready | {date.today().strftime('%B %d, %Y')}"

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        theme = self._theme()
        header = tk.Frame(self.root, bg=theme["background"])
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=0)

        hero_holder = tk.Frame(header, bg=theme["background"])
        hero_holder.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        hero_holder.columnconfigure(0, weight=1)
        self.welcome_canvas = tk.Canvas(hero_holder, height=98, bg=theme["background"], highlightthickness=0)
        self.welcome_canvas.grid(row=0, column=0, sticky="ew")
        self.welcome_canvas.bind("<Configure>", lambda _event: self._draw_welcome_card())

        nav = tk.Frame(header, bg=theme["background"])
        nav.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))
        ttk.Button(nav, text="<", width=4, style="Nav.TButton", command=self.previous_month).grid(row=0, column=0, padx=(0, 8))
        self.month_label = ttk.Label(nav, text="", font=("Segoe UI", 16, "bold"))
        self.month_label.grid(row=0, column=1, sticky="w")
        ttk.Button(nav, text=">", width=4, style="Nav.TButton", command=self.next_month).grid(row=0, column=2, padx=(8, 0))

        controls = tk.Frame(header, bg=theme["background"])
        controls.grid(row=1, column=1, sticky="e", padx=16, pady=(0, 8))
        ttk.Label(controls, text="Account:").grid(row=0, column=0, padx=(0, 6))
        self.account_box = ttk.Combobox(
            controls,
            textvariable=self.account_filter,
            state="readonly",
            width=18,
            style="Header.TCombobox",
        )
        self.account_box.grid(row=0, column=1, padx=(0, 8))
        self.account_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_view())
        ttk.Button(
            controls,
            text="Add payment",
            command=self.open_add_dialog,
            style="Header.TButton",
        ).grid(row=0, column=2, padx=(0, 8))
        self.theme_button = ttk.Button(
            controls,
            text="Dark mode",
            command=self.toggle_theme,
            style="Header.TButton",
        )
        self.theme_button.grid(row=0, column=3)

        main = tk.Frame(self.root, bg=theme["background"])
        main.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(1, weight=1)

        summary = ttk.Frame(main, style="Card.TFrame", padding=12)
        summary.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)
        self.projected_label = ttk.Label(summary, text="", style="Card.TLabel", font=("Segoe UI", 12, "bold"))
        self.remaining_label = ttk.Label(summary, text="", style="Card.TLabel", font=("Segoe UI", 12, "bold"))
        self.projected_label.grid(row=0, column=0, sticky="w")
        self.remaining_label.grid(row=0, column=1, sticky="w")
        self.day_summary_canvas = tk.Canvas(
            summary,
            width=360,
            height=34,
            bg=theme["panel"],
            highlightthickness=0,
        )
        self.day_summary_canvas.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.day_summary_canvas.bind("<Configure>", lambda _event: self._draw_day_summary_card())
        self.today_label = ttk.Label(summary, text="", style="Card.TLabel", font=("Segoe UI", 10))
        self.today_label.grid(row=1, column=1, sticky="w", pady=(6, 0), columnspan=2)

        self.calendar_frame = ttk.Frame(main)
        self.calendar_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        for column_index in range(7):
            self.calendar_frame.columnconfigure(column_index, weight=1, uniform="calendar_columns")
        self.calendar_frame.rowconfigure(0, weight=0)
        for row_index in range(1, 7):
            self.calendar_frame.rowconfigure(row_index, weight=1, uniform="calendar_rows")

        self.details_frame = ttk.Frame(main)
        self.details_frame.grid(row=1, column=1, sticky="nsew")
        self.details_frame.columnconfigure(0, weight=1)
        self.details_frame.rowconfigure(1, weight=1)

        ttk.Label(self.details_frame, text="Selected day", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.details_list = ttk.Treeview(
            self.details_frame,
            columns=("description", "amount", "account", "status"),
            show="headings",
            height=14,
        )
        self.details_list.heading("description", text="Description")
        self.details_list.heading("amount", text="Amount")
        self.details_list.heading("account", text="Account")
        self.details_list.heading("status", text="Status")
        self.details_list.column("description", width=200, anchor="w")
        self.details_list.column("amount", width=90, anchor="e")
        self.details_list.column("account", width=100, anchor="w")
        self.details_list.column("status", width=90, anchor="center")
        self.details_list.grid(row=1, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(self.details_frame, orient="vertical", command=self.details_list.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.details_list.configure(yscrollcommand=scrollbar.set)
        self.details_list.bind("<Delete>", self.delete_selected_entry)
        self.details_list.bind("<Double-1>", self.toggle_selected_paid)
        self.details_list.bind("<Button-3>", self.show_context_menu)

        actions = ttk.Frame(self.details_frame)
        actions.grid(row=2, column=0, columnspan=2, sticky="e", pady=(6, 0))
        ttk.Button(actions, text="Mark paid / unmark", command=self.toggle_selected_paid).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Delete", command=self.delete_selected_entry).grid(row=0, column=1)

    def _available_accounts(self) -> list[str]:
        accounts = ["All accounts", "Main", "Wife", "Shared"]
        for expense in self.expenses:
            if expense.account not in accounts:
                accounts.append(expense.account)
        return accounts

    def _format_total_rows(self, projected: float, remaining: float) -> tuple[str, str]:
        return (
            f"Projected monthly total: ${projected:.2f}",
            f"Remaining this month: ${remaining:.2f}",
        )

    def _wrap_calendar_text(self, text: str, max_width: int, max_lines: int = 2) -> list[str]:
        if not text:
            return [""]

        tokens = text.split()
        lines: list[str] = []
        current = ""
        for token in tokens:
            if not token:
                continue
            candidate = f"{current} {token}".strip()
            if self.calendar_font.measure(candidate) <= max_width:
                current = candidate
                continue

            if current:
                lines.append(current)
            else:
                split_token = ""
                for ch in token:
                    if self.calendar_font.measure(split_token + ch) <= max_width:
                        split_token += ch
                    else:
                        break
                if not split_token:
                    split_token = token[:1]
                lines.append(split_token)
            current = ""
            if len(lines) >= max_lines:
                break

        if current and len(lines) < max_lines:
            lines.append(current)

        if lines and len(lines) == max_lines:
            line_end = token if tokens else ""
            if line_end and line_end not in lines[-1]:
                lines[-1] = (lines[-1].rstrip(" .") + "...") if not lines[-1].endswith("...") else lines[-1]

        return lines[:max_lines]

    def refresh_view(self) -> None:
        self.expenses = load_expenses(self.data_file)
        self.paid_expense_ids = get_paid_expense_ids(self.data_file, self.current_date.year, self.current_date.month, self.account_filter.get())
        self._refresh_theme_button()

        self.account_box["values"] = self._available_accounts()
        if self.account_filter.get() not in self.account_box["values"]:
            self.account_filter.set("All accounts")
        self.account_box.set(self.account_filter.get() or "All accounts")
        self.month_label.config(text=self.current_date.strftime("%B %Y"))

        projected_total = get_total_for_month(self.expenses, self.current_date.year, self.current_date.month, self.account_filter.get())
        paid_total = get_paid_total_for_month(
            self.expenses,
            self.paid_expense_ids,
            self.current_date.year,
            self.current_date.month,
            self.account_filter.get(),
        )
        remaining_total = round(projected_total - paid_total, 2)
        projected_text, remaining_text = self._format_total_rows(projected_total, remaining_total)
        self.projected_label.config(text=projected_text)
        self.remaining_label.config(text=remaining_text)

        day_expenses = get_expenses_for_day(self.expenses, self.selected_date, self.account_filter.get())
        day_total = sum(expense.amount or 0 for expense in day_expenses)
        day_paid = sum(expense.amount or 0 for expense in day_expenses if expense.id in self.paid_expense_ids)
        self.day_summary_text = f"Selected day total: ${day_total:.2f}  |  Paid: ${day_paid:.2f}"
        self._draw_day_summary_card()
        self.today_label.config(text=f"Today: {date.today().strftime('%b %d, %Y')}")
        self._apply_color_pallets()
        self._draw_welcome_card()

        self.populate_calendar()
        self.populate_details()

    def _apply_color_pallets(self) -> None:
        theme = self._theme()
        self.root.configure(bg=theme["background"])

        def recolor_containers(widget) -> None:
            for child in widget.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg=theme["background"])
                recolor_containers(child)

        recolor_containers(self.root)

    def _render_calendar_cell(
        self,
        cell: tk.Canvas,
        current_day: date | None,
        items: list,
        is_selected: bool = False,
        is_today: bool = False,
    ) -> None:
        theme = self._theme()
        cell.delete("all")
        width = max(cell.winfo_width(), 72)
        height = max(cell.winfo_height(), 72)

        if current_day is None:
            bg_color = theme["calendar_bg"]
            outline_color = theme["border"]
        elif is_selected:
            bg_color = theme["calendar_selected"]
            outline_color = theme["calendar_selected_border"]
        elif is_today:
            bg_color = theme["calendar_today"]
            outline_color = theme["calendar_today_border"]
        else:
            bg_color = theme["calendar_cell"]
            outline_color = theme["border"]

        radius = max(7, min(11, min(width, height) // 8))
        draw_rounded_rect(cell, 2, 2, width - 3, height - 3, radius, bg_color, outline_color, width=1)
        if current_day is None:
            return

        cell.create_text(11, 9, text=str(current_day.day), anchor="nw", fill=theme["text"], font=("Segoe UI", 10, "bold"))
        if is_today:
            cell.create_text(width - 11, 10, text="*", anchor="ne", fill=theme["text_secondary"], font=("Segoe UI", 9, "bold"))

        if not items:
            return

        y = 30
        row_height = 25
        capacity = max(1, min(3, (height - y - 6) // row_height))
        max_visible = capacity
        if len(items) > capacity and capacity > 1:
            max_visible -= 1

        for expense in items[:max_visible]:
            bullet_color = expense.color or theme["accent"]
            cell.create_oval(11, y + 2, 17, y + 8, fill=bullet_color, outline=bullet_color)
            lines = self._wrap_calendar_text(expense.description, max(28, width - 34), max_lines=1)
            cell.create_text(22, y, text=lines[0], anchor="nw", fill=theme["text"], font=("Segoe UI", 8))
            if expense.amount is not None:
                cell.create_text(22, y + 12, text=f"${expense.amount:.2f}", anchor="nw", fill=theme["text_secondary"], font=("Segoe UI", 8, "bold"))
            if expense.id in self.paid_expense_ids:
                cell.create_text(width - 10, y + 12, text="P", anchor="ne", fill=theme["text_secondary"], font=("Segoe UI", 8, "bold"))
            y += row_height

        if len(items) > max_visible:
            more_tag = f"calendar_more_{current_day.isoformat()}"
            more_y = min(y + 1, height - 17)
            cell.create_text(
                11,
                more_y,
                text=f"+{len(items) - max_visible} more",
                anchor="nw",
                fill=theme["text_secondary"],
                font=("Segoe UI", 8, "underline"),
                tags=(more_tag,),
            )
            cell.tag_bind(
                more_tag,
                "<Button-1>",
                lambda _event, clicked_items=tuple(items), clicked_day=current_day: self.open_day_expenses_popup(clicked_day, list(clicked_items)),
            )

    def populate_calendar(self) -> None:
        theme = self._theme()
        for child in self.calendar_frame.winfo_children():
            child.destroy()

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for index, day_name in enumerate(day_names):
            label = tk.Label(
                self.calendar_frame,
                text=day_name,
                bg=theme["background"],
                fg=theme["text_secondary"],
                font=("Segoe UI", 10, "bold"),
            )
            label.grid(row=0, column=index, sticky="ew", padx=2, pady=(0, 4))

        month_calendar = calendar.monthcalendar(self.current_date.year, self.current_date.month)
        day_map = get_expenses_by_day(self.expenses, self.current_date.year, self.current_date.month, self.account_filter.get())
        today = date.today()
        row = 1
        for week in month_calendar:
            for col, day in enumerate(week):
                if day == 0:
                    cell = tk.Canvas(self.calendar_frame, width=84, height=72, bg=theme["calendar_bg"], highlightthickness=0)
                    cell.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
                    cell.bind("<Configure>", lambda _event, target=cell: self._render_calendar_cell(target, None, []))
                    continue

                current_day = date(self.current_date.year, self.current_date.month, day)
                is_selected = current_day == self.selected_date
                is_today = current_day == today
                items = day_map.get(current_day.strftime("%Y-%m-%d"), [])
                cell = tk.Canvas(self.calendar_frame, width=84, height=72, bg=theme["calendar_bg"], highlightthickness=0)
                cell.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
                cell.bind(
                    "<Configure>",
                    lambda _event, target=cell, clicked_day=current_day, clicked_items=tuple(items), selected=is_selected, today_cell=is_today: self._render_calendar_cell(
                        target,
                        clicked_day,
                        list(clicked_items),
                        selected,
                        today_cell,
                    ),
                )

                cell.bind("<Button-1>", lambda _event, clicked_day=current_day: self.select_day(clicked_day))
            row += 1

    def open_day_expenses_popup(self, selected_day: date, expenses: list) -> None:
        popup = tk.Toplevel(self.root)
        popup.title(selected_day.strftime("%A, %b %d"))
        popup.configure(bg=self._theme()["background"])
        popup.transient(self.root)
        popup.grab_set()
        popup_width = min(720, max(620, self.root.winfo_width() - 120))
        popup_height = min(500, max(420, self.root.winfo_height() - 160))
        popup_x = max(20, self.root.winfo_rootx() + (self.root.winfo_width() - popup_width) // 2)
        popup_y = max(20, self.root.winfo_rooty() + (self.root.winfo_height() - popup_height) // 2)
        popup.geometry(f"{popup_width}x{popup_height}+{popup_x}+{popup_y}")
        popup.minsize(620, 400)

        content = ttk.Frame(popup, padding=12)
        content.pack(fill="both", expand=True)

        ttk.Label(
            content,
            text=f"{selected_day.strftime('%B %d, %Y')} subscriptions",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        list_frame = ttk.Frame(content)
        list_frame.pack(fill="both", expand=True)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        detail_list = ttk.Treeview(
            list_frame,
            columns=("description", "amount", "account", "status"),
            show="headings",
            height=12,
        )
        detail_list.heading("description", text="Description")
        detail_list.heading("amount", text="Amount")
        detail_list.heading("account", text="Account")
        detail_list.heading("status", text="Status")
        detail_list.column("description", width=280, minwidth=180, anchor="w", stretch=True)
        detail_list.column("amount", width=90, minwidth=80, anchor="e", stretch=False)
        detail_list.column("account", width=130, minwidth=100, anchor="w", stretch=True)
        detail_list.column("status", width=90, minwidth=80, anchor="center", stretch=False)
        detail_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=detail_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        detail_list.configure(yscrollcommand=scrollbar.set)

        for expense in expenses:
            amount_text = "Planned" if expense.amount is None else f"${expense.amount:.2f}"
            status_text = "Paid" if expense.id in self.paid_expense_ids else "Pending"
            title = expense.description
            if expense.amount is None and expense.due_day is not None:
                title = f"{title} (due {expense.due_day})"
            detail_list.insert("", "end", values=(title, amount_text, expense.account, status_text), iid=expense.id)

        button_row = ttk.Frame(content)
        button_row.pack(fill="x", anchor="e", pady=(8, 0))
        ttk.Button(button_row, text="Close", command=popup.destroy).pack(side="right")
        popup.bind("<Escape>", lambda _event: popup.destroy())

    def populate_details(self) -> None:
        for row_id in self.details_list.get_children():
            self.details_list.delete(row_id)

        expenses = get_expenses_for_day(self.expenses, self.selected_date, self.account_filter.get())
        theme = self._theme()
        for index, expense in enumerate(expenses):
            amount_text = "Planned" if expense.amount is None else f"${expense.amount:.2f}"
            status_text = "Paid" if expense.id in self.paid_expense_ids else "Pending"
            description = expense.description
            if expense.amount is None and expense.due_day is not None:
                description = f"{description}  (due {expense.due_day})"

            self.details_list.insert(
                "",
                "end",
                values=(description, amount_text, expense.account, status_text),
                iid=expense.id,
            )
            if index % 2 == 1:
                self.details_list.item(expense.id, tags=("odd",))
        self.details_list.tag_configure("odd", background=theme["list_row_alt"])

    def select_day(self, selected_day: date) -> None:
        self.selected_date = selected_day
        self.refresh_view()

    def show_context_menu(self, event) -> None:
        selected = self.details_list.identify_row(event.y)
        if selected:
            self.details_list.selection_set(selected)
        else:
            self.details_list.selection_clear()

        selected_items = self.details_list.selection()
        if not selected_items:
            return

        expense_id = selected_items[0]
        expense_paid = expense_id in self.paid_expense_ids
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Mark as paid" if not expense_paid else "Mark as pending", command=self.toggle_selected_paid)
        menu.add_separator()
        menu.add_command(label="Delete", command=self.delete_selected_entry)
        menu.post(event.x_root, event.y_root)

    def toggle_selected_paid(self, _event=None) -> None:
        selected_items = self.details_list.selection()
        if not selected_items:
            return
        expense_id = selected_items[0]
        is_paid = expense_id in self.paid_expense_ids
        set_expense_paid(self.data_file, expense_id, self.current_date.year, self.current_date.month, not is_paid)
        self.refresh_view()

    def delete_selected_entry(self, _event=None) -> None:
        selected_items = self.details_list.selection()
        if not selected_items:
            return
        expense_id = selected_items[0]
        expense = next((item for item in self.expenses if item.id == expense_id), None)
        if expense is None:
            return
        confirmed = messagebox.askyesno("Delete expense", f"Delete '{expense.description}'?")
        if not confirmed:
            return

        delete_expense(self.data_file, expense_id)
        self.refresh_view()

    def previous_month(self) -> None:
        if self.current_date.month == 1:
            self.current_date = self.current_date.replace(year=self.current_date.year - 1, month=12)
        else:
            self.current_date = self.current_date.replace(month=self.current_date.month - 1)
        self.selected_date = self.current_date.replace(day=1)
        self.refresh_view()

    def next_month(self) -> None:
        if self.current_date.month == 12:
            self.current_date = self.current_date.replace(year=self.current_date.year + 1, month=1)
        else:
            self.current_date = self.current_date.replace(month=self.current_date.month + 1)
        self.selected_date = self.current_date.replace(day=1)
        self.refresh_view()

    def open_add_dialog(self) -> None:
        dialog = AddExpenseDialog(
            self.root,
            self.data_file,
            self.refresh_view,
            self.selected_date,
            self.expenses,
            theme_mode=self.theme_mode.get(),
        )
        dialog.grab_set()
        self.root.wait_window(dialog)


class AddExpenseDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Tk,
        data_file: Path,
        refresh_callback,
        initial_date: date,
        existing_expenses: list,
        theme_mode: str = "light",
    ) -> None:
        super().__init__(master)
        self.title("Add payment")
        self.data_file = data_file
        self.refresh_callback = refresh_callback
        self.existing_expenses = existing_expenses
        self.theme = WARM_DARK if theme_mode == "dark" else WARM_LIGHT
        self.option_add("*insertBackground", self.theme["input_cursor"])

        self.description_var = tk.StringVar()
        self.amount_var = tk.StringVar()
        self.date_var = tk.StringVar(value=initial_date.strftime("%Y-%m-%d"))
        self.calendar_date = initial_date
        self.account_var = tk.StringVar(value="Main")
        self.category_var = tk.StringVar(value="Subscription")
        self.expense_type_var = tk.StringVar(value="Fixed")
        self.color_var = tk.StringVar(value="#f2c14e")
        self.color_choices_visible = False
        self.recurring_var = tk.BooleanVar(value=True)
        self.paid_now_var = tk.BooleanVar(value=False)

        self.configure(bg=self.theme["panel_alt"])
        self.resizable(False, False)

        header = tk.Frame(self, bg=self.theme["panel"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6))
        tk.Label(
            header,
            text="Add new subscription",
            bg=self.theme["panel"],
            fg=self.theme["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left", anchor="w")

        ttk.Label(self, text="Description").grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))
        tk.Entry(
            self,
            textvariable=self.description_var,
            width=40,
            bg=self.theme["panel_alt"],
            fg=self.theme["text"],
            insertbackground=self.theme["input_cursor"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["border"],
            highlightcolor=self.theme["accent"],
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10), ipady=5)

        ttk.Label(self, text="Amount").grid(row=3, column=0, sticky="w", padx=12, pady=(0, 4))
        tk.Entry(
            self,
            textvariable=self.amount_var,
            width=22,
            bg=self.theme["panel_alt"],
            fg=self.theme["text"],
            insertbackground=self.theme["input_cursor"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["border"],
            highlightcolor=self.theme["accent"],
        ).grid(row=4, column=0, sticky="w", padx=12, pady=(0, 10), ipady=5)
        ttk.Label(self, text="Date").grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(0, 4))
        self.date_entry = DateEntry(
            self,
            textvariable=self.date_var,
            width=18,
            date_pattern="yyyy-mm-dd",
            background=self.theme["panel_alt"],
            foreground=self.theme["text"],
            bordercolor=self.theme["border"],
            headersbackground=self.theme["list_header"],
            selectbackground=self.theme["accent"],
            selectforeground="#ffffff",
            justify="left",
        )
        self.date_entry.grid(row=4, column=1, sticky="w", padx=(12, 0), pady=(0, 10))
        self.date_entry.set_date(self.calendar_date)
        self.date_entry.bind("<<DateEntrySelected>>", self._sync_calendar_date)

        ttk.Label(self, text="Account").grid(row=5, column=0, sticky="w", padx=12, pady=(0, 4))
        account_box = ttk.Combobox(self, textvariable=self.account_var, state="normal", width=20)
        account_box["values"] = self._suggested_accounts()
        account_box.grid(row=6, column=0, sticky="w", padx=12, pady=(0, 10))

        ttk.Label(self, text="Category").grid(row=5, column=1, sticky="w", padx=(12, 0), pady=(0, 4))
        category_box = ttk.Combobox(self, textvariable=self.category_var, state="normal", width=20)
        category_box["values"] = self._suggested_categories()
        category_box.grid(row=6, column=1, sticky="w", padx=(12, 0), pady=(0, 10))

        ttk.Label(self, text="Type").grid(row=7, column=0, sticky="w", padx=12, pady=(0, 4))
        type_box = ttk.Combobox(self, textvariable=self.expense_type_var, state="readonly", width=20)
        type_box["values"] = ["Fixed", "Variable"]
        type_box.grid(row=8, column=0, sticky="w", padx=12, pady=(0, 10))

        recurring_frame = tk.Frame(self, bg=self.theme["panel_alt"])
        recurring_frame.grid(row=7, column=1, sticky="w", padx=(12, 0), pady=(0, 10))
        tk.Checkbutton(
            recurring_frame,
            text="Recurring monthly",
            variable=self.recurring_var,
            bg=self.theme["panel_alt"],
            fg=self.theme["text"],
            selectcolor=self.theme["list_header"],
            activebackground=self.theme["panel_alt"],
            activeforeground=self.theme["text"],
            highlightthickness=0,
        ).pack(anchor="w")
        tk.Checkbutton(
            recurring_frame,
            text="Mark as paid this month",
            variable=self.paid_now_var,
            bg=self.theme["panel_alt"],
            fg=self.theme["text"],
            selectcolor=self.theme["list_header"],
            activebackground=self.theme["panel_alt"],
            activeforeground=self.theme["text"],
            highlightthickness=0,
        ).pack(anchor="w")

        color_panel = tk.Frame(self, bg=self.theme["panel_alt"])
        color_panel.grid(row=8, column=1, sticky="w", padx=(12, 0), pady=(0, 10))
        tk.Label(color_panel, text="Color", bg=self.theme["panel_alt"], fg=self.theme["text"]).pack(side="left", padx=(0, 8))
        self.color_preview = tk.Label(
            color_panel,
            text=" ",
            bg=self.color_var.get(),
            width=4,
            height=1,
            bd=0,
            relief="flat",
        )
        self.color_preview.pack(side="left", padx=(0, 8))
        self.color_toggle_button = ttk.Button(color_panel, text="Choose color", command=self._toggle_color_choices)
        self.color_toggle_button.pack(side="left")

        self.color_choices = tk.Frame(self, bg=self.theme["panel_alt"])
        self.color_choices.grid(row=9, column=0, columnspan=2, sticky="e", padx=12, pady=(0, 10))
        for color in ["#f2c14e", "#d97745", "#668f80", "#5f7db8"]:
            tk.Button(
                self.color_choices,
                bg=color,
                activebackground=color,
                width=3,
                bd=0,
                relief="flat",
                command=lambda chosen=color: self._set_color(chosen),
            ).pack(side="left", padx=(0, 7), ipady=3)
        ttk.Button(self.color_choices, text="Custom", command=self._pick_color).pack(side="left")
        self.color_choices.grid_remove()

        actions = ttk.Frame(self)
        actions.grid(row=10, column=0, columnspan=2, sticky="e", padx=12, pady=(6, 12))
        ttk.Button(actions, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Save", command=self.save_expense).grid(row=0, column=1)

    def _suggested_accounts(self) -> list[str]:
        accounts = ["Main", "Wife", "Shared"]
        for expense in self.existing_expenses:
            if expense.account not in accounts:
                accounts.append(expense.account)
        return accounts

    def _suggested_categories(self) -> list[str]:
        categories = ["Subscription", "Credit Card", "Utility", "Entertainment", "Food", "Other"]
        for expense in self.existing_expenses:
            if expense.category not in categories:
                categories.append(expense.category)
        return categories

    def _set_color(self, color: str) -> None:
        self.color_var.set(color)
        self.color_preview.configure(bg=color)
        if self.color_choices_visible:
            self.color_choices.grid_remove()
            self.color_choices_visible = False
            self.color_toggle_button.configure(text="Choose color")

    def _toggle_color_choices(self) -> None:
        self.color_choices_visible = not self.color_choices_visible
        if self.color_choices_visible:
            self.color_choices.grid()
            self.color_toggle_button.configure(text="Hide colors")
        else:
            self.color_choices.grid_remove()
            self.color_toggle_button.configure(text="Choose color")

    def _pick_color(self) -> None:
        selected_color = colorchooser.askcolor(title="Choose a color")[1]
        if selected_color:
            self._set_color(selected_color)

    def _sync_calendar_date(self, _event=None) -> None:
        try:
            self.calendar_date = self.date_entry.get_date()
            self.date_var.set(self.calendar_date.strftime("%Y-%m-%d"))
        except Exception:
            return

    def _parse_amount(self) -> float | None:
        amount_text = self.amount_var.get().strip()
        if not amount_text:
            return None

        normalized = amount_text.replace(" ", "").replace("$", "")
        if "," in normalized and "." in normalized:
            normalized = normalized.replace(",", "")
        else:
            normalized = normalized.replace(",", ".")

        try:
            return round(float(normalized), 2)
        except ValueError:
            return None

    def save_expense(self) -> None:
        description = self.description_var.get().strip()
        if not description:
            messagebox.showwarning("Missing fields", "Please enter a description.")
            return

        amount = self._parse_amount()
        if self.amount_var.get().strip() and amount is None:
            messagebox.showwarning("Invalid amount", "Use a numeric amount, for example 9.99.")
            return

        amount_text = self.date_var.get().strip()
        try:
            self.calendar_date = date.fromisoformat(amount_text)
        except ValueError:
            messagebox.showwarning("Invalid date", "Use YYYY-MM-DD format.")
            return

        due_day = self.calendar_date.day if self.recurring_var.get() else None
        expense = create_expense(
            description=description,
            amount=amount,
            expense_date=self.date_var.get().strip(),
            account=self.account_var.get().strip() or "Main",
            category=self.category_var.get().strip() or "Other",
            recurring_monthly=bool(self.recurring_var.get()),
            due_day=due_day,
            expense_type=self.expense_type_var.get().strip() or "Fixed",
            color=self.color_var.get() or "#f2c14e",
        )

        add_expense(self.data_file, expense)
        if amount is not None and self.paid_now_var.get():
            set_expense_paid(self.data_file, expense.id, self.calendar_date.year, self.calendar_date.month, True)

        self.refresh_callback()
        self.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ExpenseTrackerApp(root)
    root.mainloop()
