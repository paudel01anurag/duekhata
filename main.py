from __future__ import annotations

import calendar
import hashlib
import hmac
import os
import secrets
import shutil
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk
from tkinter import font as tkfont

from tkcalendar import DateEntry

from expense_tracker import (
    CADENCE_LABELS,
    CADENCE_MONTHLY,
    CADENCE_ONCE,
    CADENCES,
    LABELS_TO_CADENCE,
    create_schema,
    add_expense,
    create_expense,
    delete_expense,
    get_upcoming,
    get_yearly_total,
    update_expense,
    get_expenses_by_day,
    get_expenses_for_day,
    get_paid_expense_ids,
    get_paid_total_for_month,
    get_total_for_month,
    load_expenses,
    clear_credentials,
    get_stored_credentials,
    save_credentials,
    set_expense_paid,
)


APP_VERSION = "2.0.0"
APP_DATA_FOLDER = "SubscriptionTracker"
AUTH_PASSWORD_ITERATIONS = 200_000
AUTH_PASSWORD_MIN_LENGTH = 8
AUTH_RECOVER_SENTINEL = "__subscription_tracker_recover__"


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except (ValueError, AttributeError):
        return None


def get_app_data_file() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        app_data_directory = Path(local_app_data) / APP_DATA_FOLDER
    else:
        app_data_directory = Path.home() / ".subscription_tracker"

    app_data_directory.mkdir(parents=True, exist_ok=True)
    source_directory = Path(__file__).resolve().parent
    database_file = app_data_directory / "expenses.db"

    # A packaged build must always start with an empty database. Seeding only
    # happens when running from source, so that no personal financial data or
    # stored credentials can ever travel inside a copy handed to someone else.
    if getattr(sys, "frozen", False):
        return database_file

    # Preserve existing development data on the first run after upgrading.
    for file_name in ("expenses.db", "expenses.json"):
        source_file = source_directory / file_name
        destination_file = app_data_directory / file_name
        if not destination_file.exists() and source_file.exists() and source_file.resolve() != destination_file.resolve():
            shutil.copy2(source_file, destination_file)

    return database_file


def _derive_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, AUTH_PASSWORD_ITERATIONS)
    return hashed.hex(), salt.hex()


def _is_strong_password(password: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if len(password) < AUTH_PASSWORD_MIN_LENGTH:
        errors.append(f"at least {AUTH_PASSWORD_MIN_LENGTH} characters")
    if not any(character.isupper() for character in password):
        errors.append("one capital letter")
    if not any(character.islower() for character in password):
        errors.append("one lower-case letter")
    if not any(character.isdigit() for character in password):
        errors.append("one number")
    if not any(not character.isalnum() for character in password):
        errors.append("one symbol")
    return not errors, errors


def _check_password(password: str, stored_hash: str, stored_salt: str, iterations: int = AUTH_PASSWORD_ITERATIONS) -> bool:
    try:
        decoded_salt = bytes.fromhex(stored_salt)
        compare_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            decoded_salt,
            iterations,
        ).hex()
        return hmac.compare_digest(stored_hash, compare_hash)
    except (TypeError, ValueError):
        return False


def _show_auth_dialog(root: tk.Tk, data_file: Path) -> str | None:
    while True:
        stored_credentials = get_stored_credentials(data_file)
        if stored_credentials is None:
            result = AuthDialog(root, data_file, is_setup=True).show()
        else:
            result = AuthDialog(root, data_file, is_setup=False, stored_username=stored_credentials[0]).show()

        if result == AUTH_RECOVER_SENTINEL:
            clear_credentials(data_file)
            continue

        if result is not None and result != "":
            return result
        return None


# ---------------------------------------------------------------------------
# Design tokens
#
# Typography, spacing and elevation follow one scale so that every surface in
# the application is built from the same vocabulary instead of ad-hoc numbers.
# ---------------------------------------------------------------------------

_FONT_TEXT = "Segoe UI"
_FONT_DISPLAY = "Segoe UI"
_FONT_ICON = ""

# Segoe Fluent Icons code points, used only when that font is installed.
ICON_CHEVRON_LEFT = chr(0xE76B)
ICON_CHEVRON_RIGHT = chr(0xE76C)
ICON_ADD = chr(0xE710)
ICON_LIGHT_MODE = chr(0xE706)
ICON_DARK_MODE = chr(0xE708)
ICON_PAID = chr(0xE73E)
ICON_DELETE = chr(0xE74D)
ICON_EDIT = chr(0xE70F)

# Fallback glyphs for machines without the icon font.
ICON_FALLBACK = {
    ICON_CHEVRON_LEFT: "‹",
    ICON_CHEVRON_RIGHT: "›",
    ICON_ADD: "+",
    ICON_LIGHT_MODE: "☼",
    ICON_DARK_MODE: "☾",
    ICON_PAID: "✓",
    ICON_DELETE: "✕",
    ICON_EDIT: "✎",
}

# 4px base grid.
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_5, SPACE_6 = 4, 8, 12, 16, 20, 24

RADIUS_CHIP = 8
RADIUS_CARD = 14
RADIUS_SHEET = 18


def resolve_fonts(root: tk.Misc) -> None:
    """Pick the best available font families once a Tk root exists."""
    global _FONT_TEXT, _FONT_DISPLAY, _FONT_ICON
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        return

    for candidate in ("Segoe UI Variable Text", "Segoe UI"):
        if candidate in families:
            _FONT_TEXT = candidate
            break
    for candidate in ("Segoe UI Variable Display", "Segoe UI"):
        if candidate in families:
            _FONT_DISPLAY = candidate
            break
    for candidate in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if candidate in families:
            _FONT_ICON = candidate
            break


def text_font(size: int, bold: bool = False) -> tuple:
    return (_FONT_TEXT, size, "bold") if bold else (_FONT_TEXT, size)


def display_font(size: int, bold: bool = True) -> tuple:
    return (_FONT_DISPLAY, size, "bold") if bold else (_FONT_DISPLAY, size)


def icon_font(size: int) -> tuple:
    return (_FONT_ICON, size) if _FONT_ICON else (_FONT_TEXT, size)


def icon(glyph: str) -> str:
    return glyph if _FONT_ICON else ICON_FALLBACK.get(glyph, glyph)


def _to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def mix(base: str, other: str, amount: float) -> str:
    """Blend `other` into `base`. Tk has no alpha, so tints are pre-computed."""
    amount = max(0.0, min(1.0, amount))
    base_rgb = _to_rgb(base)
    other_rgb = _to_rgb(other)
    blended = tuple(round(a + (b - a) * amount) for a, b in zip(base_rgb, other_rgb))
    return "#%02x%02x%02x" % blended


def luminance(color: str) -> float:
    red, green, blue = (channel / 255 for channel in _to_rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def readable_on(color: str, dark: str = "#2b1c14", light: str = "#fff8f3") -> str:
    return dark if luminance(color) > 0.55 else light


WARM_LIGHT = {
    "background": "#f6f1ed",
    "panel": "#eadfd7",
    "panel_alt": "#f8f2ee",
    "surface": "#fffbf8",
    "surface_1": "#fdf7f2",
    "surface_2": "#f8efe8",
    "surface_3": "#f2e6dd",
    "hero": "#674733",
    "hero_border": "#8b6650",
    "hero_text": "#fffaf6",
    "hero_text_secondary": "#eadbd0",
    "text": "#2e1e16",
    "text_secondary": "#6b564b",
    "text_muted": "#97847a",
    "accent": "#b65f3c",
    "accent_hover": "#994a2d",
    "on_accent": "#fffaf6",
    "accent_soft": "#f5e2d8",
    "positive": "#4f7a4a",
    "border": "#d5c1b5",
    "outline": "#dccabe",
    "outline_variant": "#ece0d7",
    "shadow": "#4a2c1c",
    "calendar_bg": "#f6f1ed",
    "calendar_cell": "#fffbf8",
    "calendar_selected": "#f7e3d8",
    "calendar_selected_border": "#b65f3c",
    "calendar_today": "#fdf3ec",
    "calendar_today_border": "#c88b64",
    "calendar_outside": "#f1eae5",
    "list_bg": "#fffbf8",
    "list_header": "#f6efea",
    "list_row_alt": "#fbf5f1",
    "list_selected": "#f2ddd1",
    "input_cursor": "#2e1e16",
    "header_control": "#674733",
    "header_control_hover": "#7c5540",
    "header_control_text": "#fffaf6",
    "header_field": "#fffbf8",
}

WARM_DARK = {
    "background": "#17100c",
    "panel": "#291f1a",
    "panel_alt": "#231a16",
    "surface": "#241a14",
    "surface_1": "#2b1f18",
    "surface_2": "#33251c",
    "surface_3": "#3b2b21",
    "hero": "#302318",
    "hero_border": "#6e5038",
    "hero_text": "#fffaf6",
    "hero_text_secondary": "#d9c4b5",
    "text": "#f4e9dd",
    "text_secondary": "#e3d1be",
    "text_muted": "#bfab98",
    "accent": "#ff9f43",
    "accent_hover": "#ffb162",
    "on_accent": "#241a15",
    "accent_soft": "#40291a",
    "positive": "#8bc48a",
    "border": "#553b2c",
    "outline": "#4d3728",
    "outline_variant": "#35271e",
    "shadow": "#000000",
    "calendar_bg": "#17100c",
    "calendar_cell": "#251b14",
    "calendar_selected": "#43301f",
    "calendar_selected_border": "#ff9f43",
    "calendar_today": "#2e2118",
    "calendar_today_border": "#a36f3f",
    "calendar_outside": "#1c1410",
    "list_bg": "#241a14",
    "list_header": "#2b1f18",
    "list_row_alt": "#281d16",
    "list_selected": "#4a3524",
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
    outline: str | None = None,
    width: int = 1,
    tags: tuple = (),
) -> None:
    # Fill the shape without outlining its overlapping pieces. Drawing the
    # border separately avoids visible seams across rounded cards and cells.
    radius = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    if fill:
        canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline="", tags=tags)
        canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline="", tags=tags)
        if radius:
            for x_start, y_start, start_angle in (
                (x1, y1, 90),
                (x2 - 2 * radius, y1, 0),
                (x1, y2 - 2 * radius, 180),
                (x2 - 2 * radius, y2 - 2 * radius, 270),
            ):
                canvas.create_arc(
                    x_start,
                    y_start,
                    x_start + 2 * radius,
                    y_start + 2 * radius,
                    start=start_angle,
                    extent=90,
                    style="pieslice",
                    fill=fill,
                    outline="",
                    tags=tags,
                )

    if not outline or width <= 0:
        return

    canvas.create_line(x1 + radius, y1, x2 - radius, y1, fill=outline, width=width, tags=tags)
    canvas.create_line(x2, y1 + radius, x2, y2 - radius, fill=outline, width=width, tags=tags)
    canvas.create_line(x1 + radius, y2, x2 - radius, y2, fill=outline, width=width, tags=tags)
    canvas.create_line(x1, y1 + radius, x1, y2 - radius, fill=outline, width=width, tags=tags)
    if radius:
        for x_start, y_start, start_angle in (
            (x1, y1, 90),
            (x2 - 2 * radius, y1, 0),
            (x1, y2 - 2 * radius, 180),
            (x2 - 2 * radius, y2 - 2 * radius, 270),
        ):
            canvas.create_arc(
                x_start,
                y_start,
                x_start + 2 * radius,
                y_start + 2 * radius,
                start=start_angle,
                extent=90,
                style="arc",
                outline=outline,
                width=width,
                tags=tags,
            )


def draw_elevation(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    radius: int,
    behind: str,
    shadow: str,
    level: int = 1,
) -> None:
    """Approximate a Material drop shadow.

    The Tk canvas has no alpha channel, so each ring of the shadow is a rounded
    rectangle pre-blended against whatever sits behind the card. Rings are drawn
    outermost first so the darkest edge ends up nearest the card.
    """
    spread = 2 + level * 2
    strongest = 0.05 + 0.045 * level
    for ring in range(spread, 0, -1):
        strength = strongest * (1.0 - (ring - 1) / spread) ** 1.6
        draw_rounded_rect(
            canvas,
            x1 - ring,
            y1 - ring + level,
            x2 + ring,
            y2 + ring + level,
            radius + ring,
            mix(behind, shadow, strength),
        )


def draw_chip(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    fill: str,
    accent: str,
    label: str,
    text_color: str,
    font: tuple,
    trailing: str = "",
    trailing_color: str | None = None,
    tags: tuple = (),
) -> None:
    """A subscription pill: tinted body with a saturated leading bar."""
    height = y2 - y1
    radius = min(RADIUS_CHIP, height // 2)
    draw_rounded_rect(canvas, x1, y1, x2, y2, radius, fill, tags=tags)
    bar_width = 3
    draw_rounded_rect(canvas, x1, y1, x1 + bar_width * 2, y2, radius, accent, tags=tags)
    canvas.create_rectangle(x1 + bar_width, y1, x1 + bar_width * 2, y2, fill=fill, outline="", tags=tags)

    text_x = x1 + bar_width + 6
    canvas.create_text(
        text_x,
        (y1 + y2) // 2,
        text=label,
        anchor="w",
        fill=text_color,
        font=font,
        tags=tags,
    )
    if trailing:
        canvas.create_text(
            x2 - 6,
            (y1 + y2) // 2,
            text=trailing,
            anchor="e",
            fill=trailing_color or text_color,
            font=font,
            tags=tags,
        )


class _StatefulCanvasButton(tk.Canvas):
    """Shared hover / press plumbing for the canvas-drawn controls.

    ttk cannot round a corner or tint a control on hover without a themed
    element image, so the buttons that need a modern finish are painted by hand.
    """

    def __init__(self, master: tk.Misc, theme: dict, **kwargs) -> None:
        super().__init__(master, highlightthickness=0, bd=0, takefocus=0, **kwargs)
        self.theme = theme
        self.surface = theme["background"]
        self.enabled = True
        self._hovered = False
        self._pressed = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set_theme(self, theme: dict, surface: str | None = None) -> None:
        self.theme = theme
        self.surface = surface or theme["background"]
        self.configure(bg=self.surface)
        self.redraw()

    def _on_enter(self, _event=None) -> None:
        self._hovered = True
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self.redraw()

    def _on_leave(self, _event=None) -> None:
        self._hovered = False
        self._pressed = False
        self.redraw()

    def _on_press(self, _event=None) -> None:
        if not self.enabled:
            return
        self._pressed = True
        self.redraw()

    def _on_release(self, _event=None) -> None:
        was_pressed = self._pressed
        self._pressed = False
        self.redraw()
        if was_pressed and self.enabled and self._hovered:
            self.invoke()

    def invoke(self) -> None:
        raise NotImplementedError

    def redraw(self) -> None:
        raise NotImplementedError

    def _state_overlay(self, base: str) -> str:
        """Material state layers: a tint of the foreground over the base."""
        if not self.enabled:
            return base
        if self._pressed:
            return mix(base, self.theme["text"], 0.16)
        if self._hovered:
            return mix(base, self.theme["text"], 0.08)
        return base


class IconButton(_StatefulCanvasButton):
    def __init__(
        self,
        master: tk.Misc,
        glyph: str,
        command,
        theme: dict,
        size: int = 38,
        variant: str = "ghost",
        glyph_size: int = 12,
    ) -> None:
        super().__init__(master, theme, width=size, height=size)
        self.glyph = glyph
        self.command = command
        self.size = size
        self.variant = variant
        self.glyph_size = glyph_size
        self.configure(bg=self.surface)
        self.redraw()

    def set_glyph(self, glyph: str) -> None:
        self.glyph = glyph
        self.redraw()

    def invoke(self) -> None:
        if self.command:
            self.command()

    def redraw(self) -> None:
        self.delete("all")
        theme = self.theme
        size = self.size
        if self.variant == "filled":
            base, foreground = theme["accent"], theme["on_accent"]
        elif self.variant == "tonal":
            base, foreground = theme["accent_soft"], theme["accent"]
        else:
            base, foreground = self.surface, theme["text_secondary"]

        fill = self._state_overlay(base)
        if self.variant == "ghost" and fill == self.surface:
            fill = self.surface
        self.create_oval(1, 1, size - 2, size - 2, fill=fill, outline="")
        if self.variant == "ghost" and (self._hovered or self._pressed):
            foreground = theme["text"]
        self.create_text(
            size // 2,
            size // 2,
            text=icon(self.glyph),
            fill=foreground,
            font=icon_font(self.glyph_size),
        )


class PillButton(_StatefulCanvasButton):
    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command,
        theme: dict,
        variant: str = "filled",
        glyph: str = "",
        height: int = 38,
        min_width: int = 0,
    ) -> None:
        super().__init__(master, theme, height=height)
        self.text = text
        self.command = command
        self.variant = variant
        self.glyph = glyph
        self.height = height
        self.min_width = min_width
        self._font = tkfont.Font(master, font=text_font(10, bold=True))
        self.configure(bg=self.surface)
        self._resize()
        self.redraw()

    def set_text(self, text: str, glyph: str = "") -> None:
        self.text = text
        if glyph:
            self.glyph = glyph
        self._resize()
        self.redraw()

    def _resize(self) -> None:
        width = self._font.measure(self.text) + SPACE_6
        if self.glyph:
            width += 22
        self.configure(width=max(self.min_width, width))

    def invoke(self) -> None:
        if self.command:
            self.command()

    def redraw(self) -> None:
        self.delete("all")
        theme = self.theme
        width = max(self.winfo_reqwidth(), 1)
        height = self.height
        if self.variant == "filled":
            base, foreground = theme["accent"], theme["on_accent"]
        elif self.variant == "tonal":
            base, foreground = theme["accent_soft"], theme["accent"]
        else:
            base, foreground = self.surface, theme["text_secondary"]

        fill = self._state_overlay(base)
        radius = height // 2
        outline = theme["outline"] if self.variant == "outlined" else None
        draw_rounded_rect(self, 1, 1, width - 2, height - 2, radius, fill, outline)

        text_x = width // 2
        if self.glyph:
            glyph_width = 18
            total = self._font.measure(self.text) + glyph_width
            start = (width - total) // 2
            self.create_text(
                start + glyph_width // 2,
                height // 2,
                text=icon(self.glyph),
                fill=foreground,
                font=icon_font(11),
            )
            text_x = start + glyph_width + self._font.measure(self.text) // 2
        self.create_text(text_x, height // 2, text=self.text, fill=foreground, font=text_font(10, bold=True))


class AuthDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        data_file: Path,
        is_setup: bool = True,
        stored_username: str = "",
    ) -> None:
        super().__init__(master)
        self.data_file = data_file
        self.is_setup = is_setup
        self.stored_username = stored_username
        self.result: str | None = None

        self.title("Create account" if self.is_setup else "Log in")
        self.configure(bg=WARM_DARK["background"])
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _event: self._on_cancel())
        self.bind("<Return>", lambda _event: self._submit())
        self._build_ui()
        self._apply_layout()
        self._show_password.set(False)
        self._sync_password_visibility()

    def _build_ui(self) -> None:
        container = tk.Frame(self, bg=WARM_DARK["surface_1"])
        container.pack(fill="both", expand=True, padx=20, pady=20)
        container.columnconfigure(0, weight=1)

        stored_name = (self.stored_username or "").strip()
        display_name = (stored_name[:1].upper() + stored_name[1:]) if stored_name else "user"
        title_text = "Set your account password" if self.is_setup else f"Welcome back, {display_name}"
        tk.Label(
            container,
            text=title_text,
            fg=WARM_DARK["hero_text"],
            bg=WARM_DARK["surface_1"],
            font=display_font(17),
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        self._show_password = tk.BooleanVar(value=False)

        tk.Label(container, text="Username", fg=WARM_DARK["text_secondary"], bg=WARM_DARK["surface_1"], font=text_font(9, bold=True)).grid(
            row=1, column=0, sticky="w", pady=(12, 4)
        )
        self.username_var = tk.StringVar(value=self.stored_username)
        self.username_entry = tk.Entry(
            container,
            textvariable=self.username_var,
            width=32,
            font=text_font(11),
            bg=WARM_DARK["surface_2"],
            fg=WARM_DARK["text"],
            insertbackground=WARM_DARK["input_cursor"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=WARM_DARK["outline"],
            highlightcolor=WARM_DARK["accent"],
            readonlybackground=WARM_DARK["surface_3"],
            disabledforeground=WARM_DARK["text_secondary"],
            exportselection=False,
        )
        self.username_entry.grid(row=2, column=0, sticky="ew")
        if not self.is_setup:
            self.username_entry.configure(state="readonly")

        tk.Label(container, text="Password", fg=WARM_DARK["text_secondary"], bg=WARM_DARK["surface_1"], font=text_font(9, bold=True)).grid(
            row=3, column=0, sticky="w", pady=(12, 4)
        )
        self.password_var = tk.StringVar()
        self.password_entry = tk.Entry(
            container,
            textvariable=self.password_var,
            show="*",
            width=32,
            font=text_font(11),
            bg=WARM_DARK["surface_2"],
            fg=WARM_DARK["text"],
            insertbackground=WARM_DARK["input_cursor"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=WARM_DARK["outline"],
            highlightcolor=WARM_DARK["accent"],
            exportselection=False,
        )
        self.password_entry.grid(row=4, column=0, sticky="ew")

        if self.is_setup:
            tk.Label(container, text="Confirm password", fg=WARM_DARK["text_secondary"], bg=WARM_DARK["surface_1"], font=text_font(9, bold=True)).grid(
                row=5, column=0, sticky="w", pady=(12, 4)
            )
            self.confirm_var = tk.StringVar()
            self.confirm_entry = tk.Entry(
                container,
                textvariable=self.confirm_var,
                show="*",
                width=32,
                font=text_font(11),
                bg=WARM_DARK["surface_2"],
                fg=WARM_DARK["text"],
                insertbackground=WARM_DARK["input_cursor"],
                relief="flat",
                highlightthickness=1,
                highlightbackground=WARM_DARK["outline"],
                highlightcolor=WARM_DARK["accent"],
                exportselection=False,
            )
            self.confirm_entry.grid(row=6, column=0, sticky="ew")
            hint = "Must contain at least 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 symbol."
            tk.Label(
                container,
                text=hint,
                fg=WARM_DARK["text_secondary"],
                bg=WARM_DARK["surface_1"],
                font=text_font(9),
                wraplength=360,
                justify="left",
            ).grid(row=7, column=0, sticky="w", pady=(8, 8))
            focus_target = self.password_entry
            self.confirm_row = 6
        else:
            self.confirm_var = tk.StringVar()
            self.confirm_entry = None
            self.confirm_row = None
            focus_target = self.password_entry

        footer = tk.Frame(container, bg=WARM_DARK["surface_1"])
        footer.grid(row=(self.confirm_row or 4) + 2, column=0, sticky="ew", pady=(2, 0))
        footer.columnconfigure(0, weight=1)

        # This dialog runs before the app configures ttk, and the native
        # indicator ignores selectcolor, so style a dark checkbutton here.
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Auth.TCheckbutton",
            background=WARM_DARK["surface_1"],
            foreground=WARM_DARK["text"],
            focuscolor=WARM_DARK["surface_1"],
            indicatorbackground=WARM_DARK["surface_2"],
            indicatorforeground=WARM_DARK["on_accent"],
            bordercolor=WARM_DARK["outline"],
            lightcolor=WARM_DARK["surface_2"],
            darkcolor=WARM_DARK["surface_2"],
            font=text_font(10),
        )
        style.map(
            "Auth.TCheckbutton",
            background=[("active", WARM_DARK["surface_1"])],
            indicatorbackground=[("selected", WARM_DARK["accent"])],
            bordercolor=[("selected", WARM_DARK["accent"])],
        )
        ttk.Checkbutton(
            footer,
            text="Show password",
            variable=self._show_password,
            command=self._sync_password_visibility,
            style="Auth.TCheckbutton",
        ).grid(row=0, column=0, sticky="w")

        self.message_var = tk.StringVar()
        tk.Label(
            container,
            textvariable=self.message_var,
            fg="#ff9e9e",
            bg=WARM_DARK["surface_1"],
            font=text_font(9),
            wraplength=360,
            justify="left",
        ).grid(row=(self.confirm_row or 4) + 3, column=0, sticky="w")

        action_area = tk.Frame(container, bg=WARM_DARK["surface_1"])
        action_area.grid(row=(self.confirm_row or 4) + 4, column=0, sticky="e", pady=(12, 0))
        if not self.is_setup:
            PillButton(
                action_area,
                "Recover account",
                self._request_recovery,
                WARM_DARK,
                variant="outlined",
            ).pack(side="left", padx=(0, SPACE_2))
        PillButton(
            action_area,
            "Cancel",
            self._on_cancel,
            WARM_DARK,
            variant="tonal",
        ).pack(side="left", padx=(0, SPACE_2))
        self._primary_button = PillButton(
            action_area,
            "Create account" if self.is_setup else "Log in",
            self._submit,
            WARM_DARK,
            variant="filled",
        )
        self._primary_button.pack(side="left")
        focus_target.focus_set()

    def _apply_layout(self) -> None:
        self.update_idletasks()
        width = max(420, self.winfo_reqwidth())
        height = max(self.winfo_reqheight(), 260)
        x_position = max(0, (self.winfo_screenwidth() - width) // 2)
        y_position = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x_position}+{y_position}")
        # Tk withdraws a transient window whenever its master is withdrawn. The login
        # dialog runs before the main window is shown, so marking it transient here
        # would unmap it and leave the process waiting on a window nobody can see.
        if self.master is not None and self.master.winfo_viewable():
            self.transient(self.master)
        self.deiconify()
        self.lift()
        self.grab_set()
        self.focus_force()

    def _sync_password_visibility(self) -> None:
        char = "" if self._show_password.get() else "*"
        self.password_entry.config(show=char)
        if self.is_setup and self.confirm_entry is not None:
            self.confirm_entry.config(show=char)

    def _set_error(self, message: str) -> None:
        self.message_var.set(message)

    def _submit(self) -> None:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username:
            self._set_error("Please enter a username.")
            return

        if self.is_setup:
            confirm = self.confirm_var.get()
            if password != confirm:
                self._set_error("Password fields do not match.")
                return

            is_ok, missing = _is_strong_password(password)
            if not is_ok:
                self._set_error("Password requires: " + ", ".join(missing))
                return

            password_hash, salt = _derive_password(password)
            save_credentials(self.data_file, username, password_hash, salt, AUTH_PASSWORD_ITERATIONS)
            self.result = username
            self.destroy()
            return

        stored = get_stored_credentials(self.data_file)
        if stored is None:
            # Flipping is_setup in place would leave the login layout on screen without a
            # confirm field, so every later submit would fail the match check. Close instead
            # and let the caller reopen the dialog in setup mode.
            self.result = AUTH_RECOVER_SENTINEL
            self.destroy()
            return

        stored_username, stored_hash, stored_salt, _stored_iterations = stored
        if username != stored_username or not _check_password(password, stored_hash, stored_salt, _stored_iterations):
            self._set_error("Invalid username or password.")
            self.password_var.set("")
            self.password_entry.focus_set()
            return

        self.result = username
        self.destroy()

    def _request_recovery(self) -> None:
        proceed = messagebox.askyesno(
            "Recover account",
            "This will remove the existing login and let you set a new username and password.\n"
            "Stored subscriptions are not deleted.\n\nDo you want to continue?",
        )
        if not proceed:
            return

        self.result = AUTH_RECOVER_SENTINEL
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self) -> str | None:
        self.wait_window()
        return self.result


class ExpenseTrackerApp:
    def __init__(self, root: tk.Tk, data_file: Path, username: str | None = None) -> None:
        self.root = root
        self.root.title("Subscription Tracker")
        self.root.geometry("1180x800")
        self.root.minsize(1020, 700)
        self.root.configure(bg=WARM_LIGHT["background"])

        self.data_file = data_file
        self.authenticated_username = username or ""
        self.expenses = load_expenses(self.data_file)
        self.current_date = date.today().replace(day=1)
        self.selected_date = date.today()
        self.account_filter = tk.StringVar(value="All accounts")
        self.theme_mode = tk.StringVar(value="light")
        self.paid_expense_ids: set[str] = set()
        self.day_summary_text = ""
        resolve_fonts(self.root)
        self.calendar_font = tkfont.Font(self.root, font=text_font(8))
        self.themed_buttons: list[_StatefulCanvasButton] = []
        self.stat_values = {"projected": 0.0, "remaining": 0.0, "paid": 0.0, "yearly": 0.0}
        self._apply_theme()

        self.build_ui()
        self.refresh_view()

    def _apply_theme(self) -> None:
        theme = self._theme()
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=theme["background"])
        style.configure("TLabel", background=theme["background"], foreground=theme["text"], font=text_font(10))
        style.configure("Muted.TLabel", background=theme["background"], foreground=theme["text_secondary"], font=text_font(9))
        style.configure("Section.TLabel", background=theme["background"], foreground=theme["text"], font=text_font(12, bold=True))

        # Text fields: a hairline outline that turns accent on focus.
        style.configure(
            "TEntry",
            fieldbackground=theme["surface"],
            foreground=theme["text"],
            insertcolor=theme["input_cursor"],
            bordercolor=theme["outline"],
            lightcolor=theme["outline"],
            darkcolor=theme["outline"],
            borderwidth=1,
            relief="flat",
            padding=(10, 7),
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", theme["accent"])],
            lightcolor=[("focus", theme["accent"])],
            darkcolor=[("focus", theme["accent"])],
        )

        # The combobox is filled rather than outlined: clam draws the same border
        # around the field and the arrow, so an outline would bevel the arrow too.
        style.configure(
            "TCombobox",
            fieldbackground=theme["surface_2"],
            background=theme["surface_2"],
            foreground=theme["text"],
            insertcolor=theme["input_cursor"],
            bordercolor=theme["surface_2"],
            lightcolor=theme["surface_2"],
            darkcolor=theme["surface_2"],
            arrowcolor=theme["text_secondary"],
            borderwidth=1,
            relief="flat",
            padding=(10, 7),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", theme["surface_2"]), ("hover", theme["surface_3"])],
            background=[("readonly", theme["surface_2"]), ("active", theme["surface_3"])],
            bordercolor=[("focus", theme["accent"])],
            lightcolor=[("focus", theme["accent"])],
            darkcolor=[("focus", theme["accent"])],
            arrowcolor=[("active", theme["text"])],
            foreground=[("readonly", theme["text"])],
        )

        # The combobox popup is a classic Tk listbox and needs option-database colours.
        self.root.option_add("*TCombobox*Listbox.background", theme["surface"])
        self.root.option_add("*TCombobox*Listbox.foreground", theme["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", theme["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", theme["on_accent"])
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)

        # Treeview: strip the sunken border, drop the bevelled headings, give rows room.
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Treeview",
            background=theme["list_bg"],
            fieldbackground=theme["list_bg"],
            foreground=theme["text"],
            borderwidth=0,
            relief="flat",
            rowheight=36,
            font=text_font(10),
        )
        style.configure(
            "Treeview.Heading",
            background=theme["background"],
            foreground=theme["text_muted"],
            relief="flat",
            borderwidth=0,
            padding=(10, 6),
            font=text_font(9, bold=True),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", theme["background"])],
            foreground=[("active", theme["text_secondary"])],
        )
        style.map(
            "Treeview",
            background=[("selected", theme["list_selected"])],
            foreground=[("selected", theme["text"])],
        )

        # Drop the stepper arrows so only a thumb remains, as on mobile.
        style.layout(
            "Vertical.TScrollbar",
            [(
                "Vertical.Scrollbar.trough",
                {"sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]},
            )],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=theme["outline"],
            troughcolor=theme["background"],
            bordercolor=theme["background"],
            lightcolor=theme["outline"],
            darkcolor=theme["outline"],
            arrowcolor=theme["text_muted"],
            borderwidth=0,
            relief="flat",
            width=8,
        )
        style.map("Vertical.TScrollbar", background=[("active", theme["accent"])])

        style.configure(
            "TCheckbutton",
            background=theme["background"],
            foreground=theme["text"],
            focuscolor=theme["background"],
            indicatorbackground=theme["surface"],
            indicatorforeground=theme["on_accent"],
            bordercolor=theme["outline"],
            lightcolor=theme["surface"],
            darkcolor=theme["surface"],
            padding=(2, 5),
            font=text_font(10),
        )
        style.map(
            "TCheckbutton",
            background=[("active", theme["background"])],
            indicatorbackground=[("selected", theme["accent"]), ("active", theme["surface_2"])],
            bordercolor=[("selected", theme["accent"])],
        )

        style.configure("Card.TFrame", background=theme["surface"], relief="flat")
        style.configure("Card.TLabel", background=theme["surface"], foreground=theme["text"], font=text_font(10))

        style.configure(
            "TButton",
            padding=(14, 8),
            background=theme["surface_2"],
            foreground=theme["text"],
            borderwidth=0,
            relief="flat",
            font=text_font(10),
        )
        style.map(
            "TButton",
            background=[("active", theme["surface_3"]), ("pressed", theme["surface_3"])],
            foreground=[("active", theme["text"])],
        )

        self.root.option_add("*insertBackground", theme["input_cursor"])
        self.root.configure(bg=theme["background"])
        for button in getattr(self, "themed_buttons", []):
            button.set_theme(theme)

    def _theme(self) -> dict[str, str]:
        return WARM_DARK if self.theme_mode.get() == "dark" else WARM_LIGHT

    def toggle_theme(self) -> None:
        self.theme_mode.set("dark" if self.theme_mode.get() == "light" else "light")
        self._apply_theme()
        self._refresh_theme_button()
        self.refresh_view()

    def _draw_welcome_card(self) -> None:
        """The top app bar: product name, greeting, and an avatar monogram."""
        if not hasattr(self, "welcome_canvas"):
            return
        theme = self._theme()
        self.welcome_canvas.configure(bg=theme["background"])
        self.welcome_canvas.delete("all")
        width = max(self.welcome_canvas.winfo_width(), 1)
        height = max(self.welcome_canvas.winfo_height(), 1)

        avatar_size = 40
        avatar_x2 = width - SPACE_2
        avatar_x1 = avatar_x2 - avatar_size
        avatar_y1 = (height - avatar_size) // 2

        title = "Subscription Tracker"
        self.welcome_canvas.create_text(
            SPACE_2,
            height // 2 - 11,
            text=title,
            anchor="w",
            fill=theme["text"],
            font=display_font(20),
        )
        title_width = tkfont.Font(self.root, font=display_font(20)).measure(title)
        self.welcome_canvas.create_text(
            SPACE_2 + title_width + SPACE_2,
            height // 2 - 7,
            text=f"v{APP_VERSION}",
            anchor="w",
            fill=theme["text_muted"],
            font=text_font(9),
        )
        self.welcome_canvas.create_text(
            SPACE_2 + 1,
            height // 2 + 13,
            text=self._welcome_text(),
            anchor="w",
            fill=theme["text_secondary"],
            font=text_font(10),
        )

        initial = (self.authenticated_username or "?").strip()[:1].upper()
        self.welcome_canvas.create_oval(
            avatar_x1,
            avatar_y1,
            avatar_x2,
            avatar_y1 + avatar_size,
            fill=theme["accent_soft"],
            outline=theme["accent"],
            width=1,
        )
        self.welcome_canvas.create_text(
            (avatar_x1 + avatar_x2) // 2,
            avatar_y1 + avatar_size // 2,
            text=initial,
            fill=theme["accent"],
            font=text_font(14, bold=True),
        )

    def _draw_stat_cards(self) -> None:
        """Three elevated cards: projected, remaining, and paid this month."""
        if not hasattr(self, "stats_canvas"):
            return
        theme = self._theme()
        self.stats_canvas.configure(bg=theme["background"])
        self.stats_canvas.delete("all")
        width = max(self.stats_canvas.winfo_width(), 1)
        height = max(self.stats_canvas.winfo_height(), 1)

        cards = [
            ("PROJECTED THIS MONTH", self.stat_values["projected"], theme["text"]),
            ("REMAINING", self.stat_values["remaining"], theme["accent"]),
            ("PAID", self.stat_values["paid"], theme["positive"]),
            (f"TOTAL IN {self.current_date.year}", self.stat_values["yearly"], theme["text_secondary"]),
        ]
        gap = SPACE_3
        card_width = (width - gap * (len(cards) - 1) - 2) // len(cards)
        top = 5
        bottom = height - 7

        for index, (label, value, value_color) in enumerate(cards):
            x1 = 1 + index * (card_width + gap)
            x2 = x1 + card_width
            draw_elevation(self.stats_canvas, x1, top, x2, bottom, RADIUS_CARD, theme["background"], theme["shadow"], level=1)
            draw_rounded_rect(
                self.stats_canvas,
                x1,
                top,
                x2,
                bottom,
                RADIUS_CARD,
                theme["surface"],
                theme["outline_variant"],
            )
            self.stats_canvas.create_text(
                x1 + SPACE_4,
                top + SPACE_4,
                text=label,
                anchor="nw",
                fill=theme["text_muted"],
                font=text_font(8, bold=True),
            )
            self.stats_canvas.create_text(
                x1 + SPACE_4,
                top + SPACE_4 + 17,
                text=f"${value:,.2f}",
                anchor="nw",
                fill=value_color,
                font=display_font(19),
            )

    def _draw_day_summary_card(self) -> None:
        if not hasattr(self, "day_summary_canvas"):
            return
        theme = self._theme()
        self.day_summary_canvas.configure(bg=theme["background"])
        self.day_summary_canvas.delete("all")
        width = max(self.day_summary_canvas.winfo_width(), 1)
        height = max(self.day_summary_canvas.winfo_height(), 1)
        draw_rounded_rect(
            self.day_summary_canvas,
            1,
            1,
            width - 2,
            height - 2,
            (height - 2) // 2,
            theme["surface_2"],
        )
        self.day_summary_canvas.create_text(
            SPACE_4,
            height // 2,
            text=self.day_summary_text,
            anchor="w",
            fill=theme["text_secondary"],
            font=text_font(9),
        )

    def _refresh_theme_button(self) -> None:
        if not hasattr(self, "theme_button"):
            return
        self.theme_button.set_glyph(ICON_DARK_MODE if self.theme_mode.get() == "light" else ICON_LIGHT_MODE)

    def _display_name(self) -> str:
        """Show the stored username with a capital first letter, leaving any
        deliberate inner capitals (for example "McKay") untouched."""
        name = self.authenticated_username.strip()
        return name[:1].upper() + name[1:] if name else ""

    def _welcome_text(self) -> str:
        if self.authenticated_username:
            return f"Welcome back, {self._display_name()}  ·  {date.today().strftime('%A, %B %d, %Y')}"
        return f"{date.today().strftime('%A, %B %d, %Y')}"

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        theme = self._theme()
        header = tk.Frame(self.root, bg=theme["background"])
        header.grid(row=0, column=0, sticky="ew", padx=SPACE_6, pady=(SPACE_4, SPACE_2))
        header.columnconfigure(0, weight=1)

        # Top app bar.
        self.welcome_canvas = tk.Canvas(header, height=52, bg=theme["background"], highlightthickness=0)
        self.welcome_canvas.grid(row=0, column=0, sticky="ew")
        self.welcome_canvas.bind("<Configure>", lambda _event: self._draw_welcome_card())

        # Summary statistics.
        self.stats_canvas = tk.Canvas(header, height=86, bg=theme["background"], highlightthickness=0)
        self.stats_canvas.grid(row=1, column=0, sticky="ew", pady=(SPACE_3, 0))
        self.stats_canvas.bind("<Configure>", lambda _event: self._draw_stat_cards())

        # Month navigation and filters.
        toolbar = tk.Frame(header, bg=theme["background"])
        toolbar.grid(row=2, column=0, sticky="ew", pady=(SPACE_4, 0))
        toolbar.columnconfigure(2, weight=1)

        self.previous_button = IconButton(toolbar, ICON_CHEVRON_LEFT, self.previous_month, theme, variant="tonal")
        self.previous_button.grid(row=0, column=0)
        self.next_button = IconButton(toolbar, ICON_CHEVRON_RIGHT, self.next_month, theme, variant="tonal")
        self.next_button.grid(row=0, column=1, padx=(SPACE_2, SPACE_3))
        self.month_label = ttk.Label(toolbar, text="", font=display_font(17))
        self.month_label.grid(row=0, column=2, sticky="w")

        self.account_box = ttk.Combobox(
            toolbar,
            textvariable=self.account_filter,
            state="readonly",
            width=17,
            font=text_font(10),
        )
        self.account_box.grid(row=0, column=3, padx=(0, SPACE_2))
        self.account_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_view())

        self.add_button = PillButton(toolbar, "Add payment", self.open_add_dialog, theme, glyph=ICON_ADD)
        self.add_button.grid(row=0, column=4, padx=(0, SPACE_2))
        self.theme_button = IconButton(toolbar, ICON_DARK_MODE, self.toggle_theme, theme, variant="tonal")
        self.theme_button.grid(row=0, column=5)
        self.themed_buttons = [self.previous_button, self.next_button, self.add_button, self.theme_button]

        main = tk.Frame(self.root, bg=theme["background"])
        main.grid(row=1, column=0, sticky="nsew", padx=SPACE_6, pady=(SPACE_4, SPACE_6))
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        self.calendar_frame = ttk.Frame(main)
        self.calendar_frame.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_5))
        for column_index in range(7):
            self.calendar_frame.columnconfigure(column_index, weight=1, uniform="calendar_columns")
        self.calendar_frame.rowconfigure(0, weight=0)
        for row_index in range(1, 7):
            self.calendar_frame.rowconfigure(row_index, weight=1, uniform="calendar_rows")

        # A stretchable Treeview column writes its stretched width back into the
        # column, which inflates the frame's requested width and steals space from
        # the calendar every time the layout is recalculated. Pinning the frame's
        # own size stops that feedback loop from reaching the parent grid.
        self.details_frame = ttk.Frame(main, width=430)
        self.details_frame.grid(row=0, column=1, sticky="nsew")
        self.details_frame.grid_propagate(False)
        self.details_frame.columnconfigure(0, weight=1)
        self.details_frame.rowconfigure(2, weight=1)

        self.selected_day_label = ttk.Label(self.details_frame, text="Selected day", style="Section.TLabel")
        self.selected_day_label.grid(row=0, column=0, columnspan=2, sticky="w")

        self.day_summary_canvas = tk.Canvas(
            self.details_frame,
            height=32,
            bg=theme["background"],
            highlightthickness=0,
        )
        self.day_summary_canvas.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(SPACE_2, SPACE_3))
        self.day_summary_canvas.bind("<Configure>", lambda _event: self._draw_day_summary_card())

        self.details_list = ttk.Treeview(
            self.details_frame,
            columns=("description", "amount", "account", "status"),
            show="headings",
            height=14,
        )
        self.details_list.heading("description", text="DESCRIPTION")
        self.details_list.heading("amount", text="AMOUNT")
        self.details_list.heading("account", text="ACCOUNT")
        self.details_list.heading("status", text="STATUS")
        self.details_list.column("description", width=150, minwidth=110, anchor="w", stretch=True)
        self.details_list.column("amount", width=80, minwidth=70, anchor="e", stretch=False)
        self.details_list.column("account", width=85, minwidth=70, anchor="w", stretch=False)
        self.details_list.column("status", width=80, minwidth=70, anchor="center", stretch=False)
        self.details_list.grid(row=2, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(self.details_frame, orient="vertical", command=self.details_list.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.details_list.configure(yscrollcommand=scrollbar.set)
        self.details_list.bind("<Delete>", self.delete_selected_entry)
        self.details_list.bind("<Double-1>", self.toggle_selected_paid)
        self.details_list.bind("<Button-3>", self.show_context_menu)

        actions = tk.Frame(self.details_frame, bg=theme["background"])
        actions.grid(row=3, column=0, columnspan=2, sticky="e", pady=(SPACE_3, 0))
        self.paid_button = PillButton(
            actions,
            "Mark paid",
            self.toggle_selected_paid,
            theme,
            variant="tonal",
            glyph=ICON_PAID,
        )
        self.paid_button.grid(row=0, column=0, padx=(0, SPACE_2))
        self.edit_button = PillButton(
            actions,
            "Edit",
            self.edit_selected_entry,
            theme,
            variant="tonal",
            glyph=ICON_EDIT,
        )
        self.edit_button.grid(row=0, column=1, padx=(0, SPACE_2))
        self.delete_button = PillButton(
            actions,
            "Delete",
            self.delete_selected_entry,
            theme,
            variant="outlined",
            glyph=ICON_DELETE,
        )
        self.delete_button.grid(row=0, column=2)
        self.themed_buttons.extend([self.paid_button, self.edit_button, self.delete_button])

    def _available_accounts(self) -> list[str]:
        accounts = ["All accounts", "Main", "Spouse", "Shared"]
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
        self.stat_values = {
            "projected": projected_total,
            "remaining": remaining_total,
            "paid": paid_total,
            "yearly": get_yearly_total(self.expenses, self.current_date.year, self.account_filter.get()),
        }

        day_expenses = get_expenses_for_day(self.expenses, self.selected_date, self.account_filter.get())
        day_total = sum(expense.amount or 0 for expense in day_expenses)
        day_paid = sum(expense.amount or 0 for expense in day_expenses if expense.id in self.paid_expense_ids)
        entry_word = "subscription" if len(day_expenses) == 1 else "subscriptions"
        self.day_summary_text = (
            f"{len(day_expenses)} {entry_word}  ·  ${day_total:,.2f} due  ·  ${day_paid:,.2f} paid"
        )
        self.selected_day_label.config(text=self.selected_date.strftime("%A, %B %d"))
        self._apply_color_pallets()
        self._draw_welcome_card()
        self._draw_stat_cards()
        self._draw_day_summary_card()

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
        is_dark = self.theme_mode.get() == "dark"

        if current_day is None:
            # Days from the neighbouring month stay flat and unlabelled.
            draw_rounded_rect(cell, 2, 2, width - 3, height - 3, RADIUS_CARD, theme["calendar_outside"])
            return

        if is_selected:
            bg_color = theme["calendar_selected"]
            outline_color = theme["calendar_selected_border"]
            outline_width = 2
        elif is_today:
            bg_color = theme["calendar_today"]
            outline_color = theme["calendar_today_border"]
            outline_width = 1
        else:
            bg_color = theme["calendar_cell"]
            outline_color = theme["outline_variant"]
            outline_width = 1

        draw_elevation(cell, 3, 3, width - 4, height - 5, RADIUS_CARD, theme["calendar_bg"], theme["shadow"], level=1)
        draw_rounded_rect(cell, 3, 3, width - 4, height - 5, RADIUS_CARD, bg_color, outline_color, width=outline_width)

        # Today's date sits inside a filled accent disc, as on Android.
        day_text = str(current_day.day)
        if is_today:
            disc_radius = 11
            centre_x, centre_y = SPACE_3 + disc_radius - 3, SPACE_3 + disc_radius - 4
            cell.create_oval(
                centre_x - disc_radius,
                centre_y - disc_radius,
                centre_x + disc_radius,
                centre_y + disc_radius,
                fill=theme["accent"],
                outline="",
            )
            cell.create_text(centre_x, centre_y, text=day_text, fill=theme["on_accent"], font=text_font(10, bold=True))
        else:
            cell.create_text(SPACE_3, SPACE_2 + 1, text=day_text, anchor="nw", fill=theme["text"], font=text_font(10, bold=True))

        if not items:
            return

        # A day cell is barely 100px wide, so the chips carry the names and the
        # day's total is summarised once in the header instead of per chip.
        day_total = sum(expense.amount or 0 for expense in items)
        if day_total:
            cell.create_text(
                width - SPACE_3,
                SPACE_2 + 2,
                text=f"${day_total:,.0f}",
                anchor="ne",
                fill=theme["text_secondary"],
                font=text_font(9, bold=True),
            )

        chip_height = 18
        chip_gap = 3
        top = SPACE_2 + 22
        available = height - top - SPACE_2 - 6
        capacity = max(1, available // (chip_height + chip_gap))
        max_visible = capacity
        if len(items) > capacity:
            max_visible = max(1, capacity - 1)

        chip_font = text_font(8)
        left = SPACE_2
        right = width - SPACE_2 - 4
        y = top

        for expense in items[:max_visible]:
            accent_color = expense.color or theme["accent"]
            is_paid = expense.id in self.paid_expense_ids
            tint = 0.30 if is_dark else 0.42
            chip_fill = mix(bg_color, accent_color, tint * (0.45 if is_paid else 1.0))
            label_color = theme["text_muted"] if is_paid else theme["text"]

            prefix = f"{icon(ICON_PAID)} " if is_paid else ""
            label = self._truncate_to_width(
                prefix + expense.description,
                max(18, right - left - 16),
            )

            draw_chip(
                cell,
                left,
                y,
                right,
                y + chip_height,
                chip_fill,
                mix(accent_color, theme["surface"], 0.4) if is_paid else accent_color,
                label,
                label_color,
                chip_font,
            )
            y += chip_height + chip_gap

        if len(items) > max_visible:
            more_tag = f"calendar_more_{current_day.isoformat()}"
            remaining = len(items) - max_visible
            cell.create_text(
                left + 4,
                min(y + chip_height // 2, height - 14),
                text=f"+{remaining} more",
                anchor="w",
                fill=theme["accent"],
                font=text_font(8, bold=True),
                tags=(more_tag,),
            )
            cell.tag_bind(
                more_tag,
                "<Button-1>",
                lambda _event, clicked_items=tuple(items), clicked_day=current_day: self.open_day_expenses_popup(clicked_day, list(clicked_items)),
            )
            cell.tag_bind(more_tag, "<Enter>", lambda _event, target=cell: target.configure(cursor="hand2"))
            cell.tag_bind(more_tag, "<Leave>", lambda _event, target=cell: target.configure(cursor=""))

    def _truncate_to_width(self, text: str, max_width: int) -> str:
        if self.calendar_font.measure(text) <= max_width:
            return text
        ellipsis = "…"
        trimmed = text
        while trimmed and self.calendar_font.measure(trimmed + ellipsis) > max_width:
            trimmed = trimmed[:-1]
        return (trimmed.rstrip() + ellipsis) if trimmed else ellipsis

    def populate_calendar(self) -> None:
        theme = self._theme()
        for child in self.calendar_frame.winfo_children():
            child.destroy()

        day_names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        for index, day_name in enumerate(day_names):
            label = tk.Label(
                self.calendar_frame,
                text=day_name,
                bg=theme["background"],
                fg=theme["text_muted"],
                font=text_font(8, bold=True),
            )
            label.grid(row=0, column=index, sticky="ew", padx=SPACE_1, pady=(0, SPACE_2))

        month_calendar = calendar.monthcalendar(self.current_date.year, self.current_date.month)
        day_map = get_expenses_by_day(self.expenses, self.current_date.year, self.current_date.month, self.account_filter.get())
        today = date.today()
        row = 1
        for week in month_calendar:
            for col, day in enumerate(week):
                if day == 0:
                    cell = tk.Canvas(self.calendar_frame, width=70, height=86, bg=theme["calendar_bg"], highlightthickness=0)
                    cell.grid(row=row, column=col, sticky="nsew", padx=SPACE_1, pady=SPACE_1)
                    cell.bind("<Configure>", lambda _event, target=cell: self._render_calendar_cell(target, None, []))
                    continue

                current_day = date(self.current_date.year, self.current_date.month, day)
                is_selected = current_day == self.selected_date
                is_today = current_day == today
                items = day_map.get(current_day.strftime("%Y-%m-%d"), [])
                cell = tk.Canvas(self.calendar_frame, width=70, height=86, bg=theme["calendar_bg"], highlightthickness=0)
                cell.grid(row=row, column=col, sticky="nsew", padx=SPACE_1, pady=SPACE_1)
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
            text=f"{selected_day.strftime('%B %d, %Y')}",
            font=display_font(15),
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
            detail_list.insert(
                "", "end",
                values=(self._describe(expense), amount_text, expense.account, status_text),
                iid=expense.id,
            )

        button_row = ttk.Frame(content)
        button_row.pack(fill="x", anchor="e", pady=(8, 0))
        ttk.Button(button_row, text="Close", command=popup.destroy).pack(side="right")
        popup.bind("<Escape>", lambda _event: popup.destroy())

    def _describe(self, expense) -> str:
        """Name plus anything that is not obvious from the calendar position."""
        parts = []
        if expense.cadence != CADENCE_MONTHLY:
            parts.append(CADENCE_LABELS[expense.cadence].lower())
        if expense.ends_on:
            parts.append(f"until {expense.ends_on}")
        if expense.amount is None and expense.due_day is not None:
            parts.append(f"due {expense.due_day}")
        return f"{expense.description}  ({', '.join(parts)})" if parts else expense.description

    def populate_details(self) -> None:
        for row_id in self.details_list.get_children():
            self.details_list.delete(row_id)

        expenses = get_expenses_for_day(self.expenses, self.selected_date, self.account_filter.get())
        theme = self._theme()
        for index, expense in enumerate(expenses):
            amount_text = "Planned" if expense.amount is None else f"${expense.amount:.2f}"
            status_text = "Paid" if expense.id in self.paid_expense_ids else "Pending"
            description = self._describe(expense)

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
        menu.add_command(label="Edit subscription…", command=self.edit_selected_entry)
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

    def _selected_expense(self):
        selection = self.details_list.selection()
        if not selection:
            return None
        return next((item for item in self.expenses if item.id == selection[0]), None)

    def edit_selected_entry(self, _event=None) -> None:
        expense = self._selected_expense()
        if expense is None:
            messagebox.showinfo("Nothing selected", "Select a subscription in the list first.")
            return

        dialog = AddExpenseDialog(
            self.root,
            self.data_file,
            self.refresh_view,
            self.selected_date,
            self.expenses,
            theme_mode=self.theme_mode.get(),
            expense=expense,
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
        expense=None,
    ) -> None:
        super().__init__(master)
        self.editing = expense is not None
        self.original = expense
        self.title("Edit subscription" if self.editing else "Add payment")
        self.data_file = data_file
        self.refresh_callback = refresh_callback
        self.existing_expenses = existing_expenses
        self.theme = WARM_DARK if theme_mode == "dark" else WARM_LIGHT
        self.option_add("*insertBackground", self.theme["input_cursor"])

        start_date = initial_date
        if self.editing:
            parsed_start = _parse_date(expense.date)
            if parsed_start is not None:
                start_date = parsed_start

        self.description_var = tk.StringVar(value=expense.description if self.editing else "")
        self.amount_var = tk.StringVar(
            value=("" if not self.editing or expense.amount is None else f"{expense.amount:.2f}")
        )
        self.date_var = tk.StringVar(value=start_date.strftime("%Y-%m-%d"))
        self.calendar_date = start_date
        self.account_var = tk.StringVar(value=expense.account if self.editing else "Main")
        self.category_var = tk.StringVar(value=expense.category if self.editing else "Subscription")
        self.expense_type_var = tk.StringVar(value=expense.expense_type if self.editing else "Fixed")
        self.color_var = tk.StringVar(value=(expense.color if self.editing else "#f2c14e"))
        self.color_choices_visible = False
        self.cadence_var = tk.StringVar(
            value=CADENCE_LABELS[expense.cadence if self.editing else CADENCE_MONTHLY]
        )
        self.ends_on_var = tk.StringVar(value=(expense.ends_on or "") if self.editing else "")
        self.paid_now_var = tk.BooleanVar(value=False)

        self.configure(bg=self.theme["background"])
        self.resizable(False, False)

        header = tk.Frame(self, bg=self.theme["background"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=SPACE_5, pady=(SPACE_5, SPACE_4))
        tk.Label(
            header,
            text="Add new subscription",
            bg=self.theme["background"],
            fg=self.theme["text"],
            font=display_font(16),
        ).pack(side="left", anchor="w")

        ttk.Label(self, text="Description").grid(row=1, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_1))
        tk.Entry(
            self,
            textvariable=self.description_var,
            width=40,
            bg=self.theme["surface"],
            fg=self.theme["text"],
            font=text_font(10),
            insertbackground=self.theme["input_cursor"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["outline"],
            highlightcolor=self.theme["accent"],
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=SPACE_5, pady=(0, SPACE_3), ipady=7)

        ttk.Label(self, text="Amount").grid(row=3, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_1))
        tk.Entry(
            self,
            textvariable=self.amount_var,
            width=22,
            bg=self.theme["surface"],
            fg=self.theme["text"],
            font=text_font(10),
            insertbackground=self.theme["input_cursor"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["outline"],
            highlightcolor=self.theme["accent"],
        ).grid(row=4, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_3), ipady=7)
        ttk.Label(self, text="Date").grid(row=3, column=1, sticky="w", padx=(SPACE_5, 0), pady=(0, SPACE_1))
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
        self.date_entry.grid(row=4, column=1, sticky="w", padx=(SPACE_5, 0), pady=(0, SPACE_3))
        self.date_entry.set_date(self.calendar_date)
        self.date_entry.bind("<<DateEntrySelected>>", self._sync_calendar_date)

        ttk.Label(self, text="Account").grid(row=5, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_1))
        account_box = ttk.Combobox(self, textvariable=self.account_var, state="normal", width=20)
        account_box["values"] = self._suggested_accounts()
        account_box.grid(row=6, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_1))

        ttk.Label(self, text="Category").grid(row=5, column=1, sticky="w", padx=(SPACE_5, 0), pady=(0, SPACE_1))
        category_box = ttk.Combobox(self, textvariable=self.category_var, state="normal", width=20)
        category_box["values"] = self._suggested_categories()
        category_box.grid(row=6, column=1, sticky="w", padx=(SPACE_5, 0), pady=(0, SPACE_1))

        # Both fields accept free text; without a caption they look read-only
        # like the Type field beneath them.
        tk.Label(
            self,
            text="Pick a suggestion or type your own — new ones are remembered.",
            bg=self.theme["background"],
            fg=self.theme["text_muted"],
            font=text_font(9),
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=SPACE_5, pady=(0, SPACE_3))

        ttk.Label(self, text="Repeats").grid(row=8, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_1))
        self.cadence_box = ttk.Combobox(self, textvariable=self.cadence_var, state="readonly", width=20)
        self.cadence_box["values"] = [CADENCE_LABELS[name] for name in CADENCES]
        self.cadence_box.grid(row=9, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_1))
        self.cadence_box.bind("<<ComboboxSelected>>", lambda _event: self._sync_end_date_state())

        ttk.Label(self, text="Ends on").grid(row=8, column=1, sticky="w", padx=(SPACE_5, 0), pady=(0, SPACE_1))
        self.ends_on_entry = tk.Entry(
            self,
            textvariable=self.ends_on_var,
            width=20,
            bg=self.theme["surface"],
            fg=self.theme["text"],
            font=text_font(10),
            insertbackground=self.theme["input_cursor"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["outline"],
            highlightcolor=self.theme["accent"],
        )
        self.ends_on_entry.grid(row=9, column=1, sticky="w", padx=(SPACE_5, 0), pady=(0, SPACE_1), ipady=4)

        self.ends_on_hint = tk.Label(
            self,
            text="Leave “Ends on” empty while the subscription is still active; set it to the last "
            "billing date when you cancel.",
            bg=self.theme["background"],
            fg=self.theme["text_muted"],
            font=text_font(9),
            wraplength=430,
            justify="left",
        )
        self.ends_on_hint.grid(row=10, column=0, columnspan=2, sticky="w", padx=SPACE_5, pady=(0, SPACE_3))

        ttk.Label(self, text="Type").grid(row=11, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_1))
        type_box = ttk.Combobox(self, textvariable=self.expense_type_var, state="readonly", width=20)
        type_box["values"] = ["Fixed", "Variable"]
        type_box.grid(row=12, column=0, sticky="w", padx=SPACE_5, pady=(0, SPACE_3))

        recurring_frame = tk.Frame(self, bg=self.theme["background"])
        recurring_frame.grid(row=12, column=1, sticky="w", padx=(SPACE_5, 0), pady=(0, SPACE_3))
        ttk.Checkbutton(
            recurring_frame,
            text="Mark as paid this month",
            variable=self.paid_now_var,
        ).pack(anchor="w")
        self._sync_end_date_state()

        color_panel = tk.Frame(self, bg=self.theme["background"])
        color_panel.grid(row=13, column=0, columnspan=2, sticky="w", padx=SPACE_5, pady=(SPACE_2, SPACE_3))
        tk.Label(color_panel, text="Color", bg=self.theme["background"], fg=self.theme["text"], font=text_font(10)).pack(side="left", padx=(0, SPACE_2))
        self.color_preview = tk.Canvas(
            color_panel,
            width=26,
            height=26,
            bg=self.theme["background"],
            highlightthickness=0,
        )
        self.color_preview.pack(side="left", padx=(0, SPACE_2))
        self._paint_color_preview()
        self.color_toggle_button = PillButton(
            color_panel,
            "Choose color",
            self._toggle_color_choices,
            self.theme,
            variant="tonal",
            height=32,
        )
        self.color_toggle_button.pack(side="left")

        self.color_choices = tk.Frame(self, bg=self.theme["background"])
        self.color_choices.grid(row=14, column=0, columnspan=2, sticky="w", padx=SPACE_5, pady=(0, SPACE_3))
        for color in ["#f2c14e", "#d97745", "#668f80", "#5f7db8", "#8d6fb0"]:
            swatch = tk.Canvas(
                self.color_choices,
                width=28,
                height=28,
                bg=self.theme["background"],
                highlightthickness=0,
                cursor="hand2",
            )
            swatch.create_oval(2, 2, 25, 25, fill=color, outline=mix(color, "#000000", 0.15))
            swatch.pack(side="left", padx=(0, SPACE_2))
            swatch.bind("<Button-1>", lambda _event, chosen=color: self._set_color(chosen))
        self.custom_color_button = PillButton(
            self.color_choices,
            "Custom",
            self._pick_color,
            self.theme,
            variant="outlined",
            height=32,
        )
        self.custom_color_button.pack(side="left")
        self.color_choices.grid_remove()

        actions = tk.Frame(self, bg=self.theme["background"])
        actions.grid(row=15, column=0, columnspan=2, sticky="e", padx=SPACE_5, pady=(SPACE_2, SPACE_5))
        PillButton(actions, "Cancel", self.destroy, self.theme, variant="tonal").grid(row=0, column=0, padx=(0, SPACE_2))
        PillButton(actions, "Save subscription", self.save_expense, self.theme, variant="filled").grid(row=0, column=1)

    def _paint_color_preview(self) -> None:
        self.color_preview.delete("all")
        color = self.color_var.get()
        self.color_preview.create_oval(1, 1, 24, 24, fill=color, outline=mix(color, "#000000", 0.2))

    def _suggested_accounts(self) -> list[str]:
        accounts = ["Main", "Spouse", "Shared"]
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
        self._paint_color_preview()
        if self.color_choices_visible:
            self.color_choices.grid_remove()
            self.color_choices_visible = False
            self.color_toggle_button.set_text("Choose color")

    def _toggle_color_choices(self) -> None:
        self.color_choices_visible = not self.color_choices_visible
        if self.color_choices_visible:
            self.color_choices.grid()
            self.color_toggle_button.set_text("Hide colors")
        else:
            self.color_choices.grid_remove()
            self.color_toggle_button.set_text("Choose color")

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

    def _selected_cadence(self) -> str:
        return LABELS_TO_CADENCE.get(self.cadence_var.get(), CADENCE_MONTHLY)

    def _sync_end_date_state(self) -> None:
        """A one-off payment has a single date, so an end date is meaningless."""
        is_once = self._selected_cadence() == CADENCE_ONCE
        self.ends_on_entry.configure(state="disabled" if is_once else "normal")
        if is_once:
            self.ends_on_var.set("")
        self.ends_on_hint.configure(
            text="A one-off payment happens once, on the date above."
            if is_once
            else "Leave “Ends on” empty while the subscription is still active; set it to the "
            "last billing date when you cancel."
        )

    def save_expense(self) -> None:
        description = self.description_var.get().strip()
        if not description:
            messagebox.showwarning("Missing fields", "Please enter a description.")
            return

        amount = self._parse_amount()
        if self.amount_var.get().strip() and amount is None:
            messagebox.showwarning("Invalid amount", "Use a numeric amount, for example 9.99.")
            return

        start_date = _parse_date(self.date_var.get())
        if start_date is None:
            messagebox.showwarning("Invalid date", "Use YYYY-MM-DD format for the start date.")
            return
        self.calendar_date = start_date

        cadence = self._selected_cadence()
        ends_on_text = self.ends_on_var.get().strip()
        ends_on = None
        if ends_on_text and cadence != CADENCE_ONCE:
            ends_on_date = _parse_date(ends_on_text)
            if ends_on_date is None:
                messagebox.showwarning("Invalid date", "Use YYYY-MM-DD format for the end date, or leave it empty.")
                return
            if ends_on_date < start_date:
                messagebox.showwarning(
                    "Check the dates",
                    "The end date is before the start date, so this subscription would never bill.",
                )
                return
            ends_on = ends_on_date.isoformat()

        due_day = None if cadence in (CADENCE_ONCE, "weekly") else start_date.day
        expense = create_expense(
            description=description,
            amount=amount,
            expense_date=start_date.isoformat(),
            account=self.account_var.get().strip() or "Main",
            category=self.category_var.get().strip() or "Other",
            due_day=due_day,
            expense_type=self.expense_type_var.get().strip() or "Fixed",
            color=self.color_var.get() or "#f2c14e",
            cadence=cadence,
            ends_on=ends_on,
            # Reuse the id when editing so the paid history survives the change.
            expense_id=self.original.id if self.editing else None,
        )

        if self.editing:
            update_expense(self.data_file, expense)
        else:
            add_expense(self.data_file, expense)

        if amount is not None and self.paid_now_var.get():
            set_expense_paid(self.data_file, expense.id, self.calendar_date.year, self.calendar_date.month, True)

        self.refresh_callback()
        self.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    resolve_fonts(root)
    data_file = get_app_data_file()
    create_schema(data_file)
    authenticated_user = _show_auth_dialog(root, data_file)

    if authenticated_user is None:
        root.destroy()
    else:
        app = ExpenseTrackerApp(root, data_file=data_file, username=authenticated_user)
        root.deiconify()
        root.mainloop()
