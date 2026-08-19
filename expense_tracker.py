from __future__ import annotations

import calendar
import json
import sqlite3
import textwrap
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator, List, Optional, Set


CADENCE_ONCE = "once"
CADENCE_WEEKLY = "weekly"
CADENCE_MONTHLY = "monthly"
CADENCE_QUARTERLY = "quarterly"
CADENCE_YEARLY = "yearly"

# Ordered for presentation in the user interface.
CADENCES = (
    CADENCE_ONCE,
    CADENCE_WEEKLY,
    CADENCE_MONTHLY,
    CADENCE_QUARTERLY,
    CADENCE_YEARLY,
)

CADENCE_LABELS = {
    CADENCE_ONCE: "One-off",
    CADENCE_WEEKLY: "Every week",
    CADENCE_MONTHLY: "Every month",
    CADENCE_QUARTERLY: "Every 3 months",
    CADENCE_YEARLY: "Every year",
}

LABELS_TO_CADENCE = {label: cadence for cadence, label in CADENCE_LABELS.items()}


@dataclass
class Expense:
    id: str
    description: str
    amount: Optional[float]
    date: str
    account: str
    category: str
    recurring_monthly: bool = False
    due_day: Optional[int] = None
    expense_type: str = "Fixed"
    color: str = "#f4a261"
    # How often the subscription bills. `date` is the first billing date and
    # `ends_on` the last one, inclusive; None means it has not been cancelled.
    cadence: str = ""
    ends_on: Optional[str] = None

    def __post_init__(self) -> None:
        # `cadence` supersedes the older `recurring_monthly` flag. Normalising
        # here keeps the two consistent no matter how the record was built:
        # from the database, from legacy JSON, or directly in a test.
        cadence = (self.cadence or "").strip().lower()
        if cadence not in CADENCES:
            cadence = CADENCE_MONTHLY if self.recurring_monthly else CADENCE_ONCE
        self.cadence = cadence
        self.recurring_monthly = cadence != CADENCE_ONCE
        self.ends_on = (self.ends_on or "").strip() or None


def _json_fallback_path(data_file: Path) -> Path:
    return data_file.with_suffix(".json")


@contextmanager
def _connect(data_file: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(data_file)
    try:
        connection.execute("PRAGMA foreign_keys = ON;")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _migrate_expense_columns(connection: sqlite3.Connection) -> None:
    """Add the cadence and end-date columns to databases created before them.

    Existing rows only carried the boolean `recurring_monthly`, so their cadence
    is back-filled from it rather than taking the column default. Anything that
    was recurring becomes monthly; everything else becomes a one-off.
    """
    existing = {row[1] for row in connection.execute("PRAGMA table_info(expenses)").fetchall()}

    if "cadence" not in existing:
        connection.execute("ALTER TABLE expenses ADD COLUMN cadence TEXT")
    if "ends_on" not in existing:
        connection.execute("ALTER TABLE expenses ADD COLUMN ends_on TEXT")

    connection.execute(
        """
        UPDATE expenses
        SET cadence = CASE WHEN recurring_monthly = 1 THEN ? ELSE ? END
        WHERE cadence IS NULL OR TRIM(cadence) = ''
        """,
        (CADENCE_MONTHLY, CADENCE_ONCE),
    )


def create_schema(data_file: Path) -> None:
    data_file.parent.mkdir(parents=True, exist_ok=True)
    with _connect(data_file) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                amount REAL,
                date TEXT NOT NULL,
                account TEXT NOT NULL,
                category TEXT NOT NULL,
                recurring_monthly INTEGER NOT NULL DEFAULT 0,
                due_day INTEGER,
                expense_type TEXT NOT NULL DEFAULT 'Fixed',
                color TEXT NOT NULL DEFAULT '#f4a261',
                cadence TEXT,
                ends_on TEXT
            )
            """
        )
        _migrate_expense_columns(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expense_payments (
                expense_id TEXT NOT NULL,
                paid_year INTEGER NOT NULL,
                paid_month INTEGER NOT NULL,
                paid_on TEXT NOT NULL DEFAULT (DATE('now')),
                PRIMARY KEY (expense_id, paid_year, paid_month),
                FOREIGN KEY (expense_id) REFERENCES expenses (id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_credentials (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                iterations INTEGER NOT NULL CHECK (iterations > 0),
                created_at TEXT NOT NULL DEFAULT (DATETIME('now'))
            )
            """
        )


def has_local_credentials(data_file: Path) -> bool:
    try:
        with _connect(data_file) as connection:
            result = connection.execute("SELECT COUNT(*) FROM app_credentials").fetchone()
        return bool(result and result[0] > 0)
    except sqlite3.OperationalError:
        return False


def get_stored_credentials(data_file: Path) -> tuple[str, str, str, int] | None:
    try:
        with _connect(data_file) as connection:
            row = connection.execute(
                """
                SELECT username, password_hash, password_salt, iterations
                FROM app_credentials
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.OperationalError:
        return None

    if row is None:
        return None
    return row[0], row[1], row[2], int(row[3])


def save_credentials(data_file: Path, username: str, password_hash: str, password_salt: str, iterations: int) -> None:
    create_schema(data_file)
    with _connect(data_file) as connection:
        connection.execute(
            """
            INSERT INTO app_credentials (username, password_hash, password_salt, iterations)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                password_salt = excluded.password_salt,
                iterations = excluded.iterations
            """
        , (username, password_hash, password_salt, iterations)
        )


def clear_credentials(data_file: Path) -> None:
    if not data_file.exists():
        return
    with _connect(data_file) as connection:
        try:
            connection.execute("DELETE FROM app_credentials")
        except sqlite3.OperationalError:
            return


def _read_legacy_json(json_file: Path) -> List[Expense]:
    if not json_file.exists():
        return []
    try:
        with json_file.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []

    expenses: List[Expense] = []
    for item in raw:
        expenses.append(
            Expense(
                id=item["id"],
                description=item["description"],
                amount=None if item.get("amount") is None else round(float(item["amount"]), 2),
                date=item.get("date", ""),
                account=item.get("account", "Main"),
                category=item.get("category", "General"),
                recurring_monthly=bool(item.get("recurring_monthly", False)),
                due_day=item.get("due_day"),
                cadence=item.get("cadence", ""),
                ends_on=item.get("ends_on"),
                expense_type=item.get("expense_type", "Fixed"),
                color=item.get("color", "#f4a261"),
            )
        )
    return expenses


def _to_dict(expense: Expense) -> dict[str, object]:
    return {
        "id": expense.id,
        "description": expense.description,
        "amount": expense.amount,
        "date": expense.date,
        "account": expense.account,
        "category": expense.category,
        "recurring_monthly": int(expense.recurring_monthly),
        "due_day": expense.due_day,
        "expense_type": expense.expense_type,
        "color": expense.color,
        "cadence": expense.cadence,
        "ends_on": expense.ends_on,
    }


def _upsert_expenses(connection: sqlite3.Connection, expenses: List[Expense]) -> None:
    data = [_to_dict(item) for item in expenses]
    if data:
        # ON CONFLICT ... DO UPDATE rather than INSERT OR REPLACE: the latter
        # deletes the conflicting row first, and expense_payments cascades on
        # delete, so replacing a row would silently wipe its paid history.
        connection.executemany(
            """
            INSERT INTO expenses (
                id, description, amount, date, account, category,
                recurring_monthly, due_day, expense_type, color, cadence, ends_on
            ) VALUES (
                :id, :description, :amount, :date, :account, :category,
                :recurring_monthly, :due_day, :expense_type, :color, :cadence, :ends_on
            )
            ON CONFLICT(id) DO UPDATE SET
                description = excluded.description,
                amount = excluded.amount,
                date = excluded.date,
                account = excluded.account,
                category = excluded.category,
                recurring_monthly = excluded.recurring_monthly,
                due_day = excluded.due_day,
                expense_type = excluded.expense_type,
                color = excluded.color,
                cadence = excluded.cadence,
                ends_on = excluded.ends_on
            """,
            data,
        )


def _replace_all_expenses_in_db(data_file: Path, expenses: List[Expense]) -> None:
    with _connect(data_file) as connection:
        _upsert_expenses(connection, expenses)


def _existing_expense_ids_in_db(data_file: Path) -> List[str]:
    with _connect(data_file) as connection:
        rows = connection.execute("SELECT id FROM expenses").fetchall()
    return [row[0] for row in rows]


def _ensure_db_initialized_and_seeded(data_file: Path) -> None:
    create_schema(data_file)
    with _connect(data_file) as connection:
        total = connection.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        migration_complete = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'legacy_json_migrated'"
        ).fetchone()

    if migration_complete is None and total == 0:
        legacy_expenses = _read_legacy_json(_json_fallback_path(data_file))
        if legacy_expenses:
            _replace_all_expenses_in_db(data_file, legacy_expenses)

    if migration_complete is None:
        with _connect(data_file) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO app_metadata (key, value) VALUES ('legacy_json_migrated', '1')"
            )


def load_expenses(data_file: Path) -> List[Expense]:
    if data_file.suffix.lower() == ".json":
        return _read_legacy_json(data_file)

    _ensure_db_initialized_and_seeded(data_file)
    with _connect(data_file) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, description, amount, date, account, category, recurring_monthly,
                   due_day, expense_type, color, cadence, ends_on
            FROM expenses
            ORDER BY date, description
            """
        ).fetchall()

    return [
        Expense(
            id=row["id"],
            description=row["description"],
            amount=None if row["amount"] is None else float(row["amount"]),
            date=row["date"] or "",
            account=row["account"] or "Main",
            category=row["category"] or "General",
            recurring_monthly=bool(row["recurring_monthly"]),
            due_day=row["due_day"] if row["due_day"] is not None else None,
            expense_type=row["expense_type"] or "Fixed",
            color=row["color"] or "#f4a261",
            cadence=row["cadence"] or "",
            ends_on=row["ends_on"],
        )
        for row in rows
    ]


def save_expenses(data_file: Path, expenses: List[Expense]) -> None:
    if data_file.suffix.lower() == ".json":
        data_file.parent.mkdir(parents=True, exist_ok=True)
        with data_file.open("w", encoding="utf-8") as handle:
            json.dump([asdict(item) for item in expenses], handle, indent=2)
        return

    _ensure_db_initialized_and_seeded(data_file)
    ids = [expense.id for expense in expenses]
    with _connect(data_file) as connection:
        connection.execute("DELETE FROM expense_payments WHERE expense_id NOT IN (SELECT id FROM expenses)")

        if ids:
            connection.execute(
                f"DELETE FROM expenses WHERE id NOT IN ({','.join('?' for _ in ids)})",
                ids,
            )
        else:
            connection.execute("DELETE FROM expenses")

        _upsert_expenses(connection, expenses)


def add_expense(data_file: Path, expense: Expense) -> None:
    if data_file.suffix.lower() == ".json":
        expenses = load_expenses(data_file)
        expenses.append(expense)
        save_expenses(data_file, expenses)
        return

    _ensure_db_initialized_and_seeded(data_file)
    with _connect(data_file) as connection:
        payload = _to_dict(expense)
        connection.execute(
            """
            INSERT INTO expenses (
                id, description, amount, date, account, category, recurring_monthly,
                due_day, expense_type, color, cadence, ends_on
            ) VALUES (
                :id, :description, :amount, :date, :account, :category, :recurring_monthly,
                :due_day, :expense_type, :color, :cadence, :ends_on
            )
            """,
            payload,
        )


def update_expense(data_file: Path, expense: Expense) -> None:
    """Change an existing subscription in place, keeping its paid history.

    The id is deliberately never touched: expense_payments references it, so
    rewriting the row under a new id — or deleting and re-adding — would lose
    every month the user had already marked as paid.
    """
    if data_file.suffix.lower() == ".json":
        expenses = [expense if item.id == expense.id else item for item in load_expenses(data_file)]
        save_expenses(data_file, expenses)
        return

    _ensure_db_initialized_and_seeded(data_file)
    with _connect(data_file) as connection:
        connection.execute(
            """
            UPDATE expenses SET
                description = :description,
                amount = :amount,
                date = :date,
                account = :account,
                category = :category,
                recurring_monthly = :recurring_monthly,
                due_day = :due_day,
                expense_type = :expense_type,
                color = :color,
                cadence = :cadence,
                ends_on = :ends_on
            WHERE id = :id
            """,
            _to_dict(expense),
        )


def delete_expense(data_file: Path, expense_id: str) -> None:
    if data_file.suffix.lower() == ".json":
        expenses = [item for item in load_expenses(data_file) if item.id != expense_id]
        save_expenses(data_file, expenses)
        return

    if not data_file.exists():
        return
    with _connect(data_file) as connection:
        connection.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))


def wrap_text(text: str, width: int = 18) -> str:
    if not text:
        return ""
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False))


def create_expense(
    description: str,
    amount: Optional[float],
    expense_date: str,
    account: str,
    category: str,
    recurring_monthly: bool = False,
    due_day: Optional[int] = None,
    expense_type: str = "Fixed",
    color: str = "#f4a261",
    cadence: str = "",
    ends_on: Optional[str] = None,
    expense_id: Optional[str] = None,
) -> Expense:
    normalized_amount = None if amount is None else round(float(amount), 2)
    normalized_date = expense_date or ""
    if due_day is not None:
        try:
            due_day = int(due_day)
        except (TypeError, ValueError):
            due_day = None

    if normalized_amount is None and due_day is None and normalized_date:
        try:
            parsed_day = int(normalized_date.split("-")[-1])
            due_day = parsed_day
        except ValueError:
            due_day = None

    return Expense(
        id=expense_id or datetime.now().strftime("%Y%m%d%H%M%S%f"),
        description=description.strip(),
        amount=normalized_amount,
        date=normalized_date,
        account=account.strip() or "Main",
        category=category.strip() or "General",
        recurring_monthly=bool(recurring_monthly),
        due_day=due_day,
        expense_type=expense_type.strip() or "Fixed",
        color=color,
        cadence=cadence,
        ends_on=ends_on,
    )


def _parse_iso(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _day_in_month(year: int, month: int, day: int) -> date:
    """Clamp a day-of-month to a real date, so a 31st bills on the 30th in June."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _billing_day(expense: Expense) -> int:
    if expense.due_day is not None and 1 <= expense.due_day <= 31:
        return expense.due_day
    start = _parse_iso(expense.date)
    return start.day if start else 1


def occurs_on(expense: Expense, day: date) -> bool:
    """Does this subscription bill on the given day?

    The stored `date` is the first billing date and `ends_on` the last, so a
    subscription never appears before it started or after it was cancelled.
    """
    start = _parse_iso(expense.date)
    if start is None or day < start:
        return False

    end = _parse_iso(expense.ends_on)
    if end is not None and day > end:
        return False

    cadence = expense.cadence
    if cadence == CADENCE_ONCE:
        return day == start
    if cadence == CADENCE_WEEKLY:
        return (day - start).days % 7 == 0

    if day != _day_in_month(day.year, day.month, _billing_day(expense)):
        return False

    if cadence == CADENCE_MONTHLY:
        return True
    months_apart = (day.year - start.year) * 12 + (day.month - start.month)
    if cadence == CADENCE_QUARTERLY:
        return months_apart % 3 == 0
    if cadence == CADENCE_YEARLY:
        return months_apart % 12 == 0
    return False


def occurrences_in_month(expense: Expense, year: int, month: int) -> List[date]:
    last_day = calendar.monthrange(year, month)[1]
    return [
        candidate
        for candidate in (date(year, month, number) for number in range(1, last_day + 1))
        if occurs_on(expense, candidate)
    ]


def _is_in_target_month(expense: Expense, year: int, month: int) -> bool:
    return bool(occurrences_in_month(expense, year, month))


def get_expenses_for_month(expenses: List[Expense], year: int, month: int, account: Optional[str] = None) -> List[Expense]:
    month_expenses = [expense for expense in expenses if _is_in_target_month(expense, year, month)]
    if account and account != "All accounts":
        month_expenses = [expense for expense in month_expenses if expense.account == account]

    return sorted(
        month_expenses,
        key=lambda item: (
            item.date or "",
            item.due_day if item.due_day is not None else 0,
            item.account,
            item.description.lower(),
        ),
    )


def get_total_for_month(expenses: List[Expense], year: int, month: int, account: Optional[str] = None) -> float:
    # A weekly subscription bills several times a month, so the month's cost is
    # the amount multiplied by how often it actually falls due.
    total = 0.0
    for expense in get_expenses_for_month(expenses, year, month, account):
        if expense.amount is not None:
            total += expense.amount * len(occurrences_in_month(expense, year, month))
    return round(total, 2)


def get_yearly_total(expenses: List[Expense], year: int, account: Optional[str] = None) -> float:
    return round(sum(get_total_for_month(expenses, year, month, account) for month in range(1, 13)), 2)


def next_occurrence(expense: Expense, start: date, horizon_days: int = 800):
    """The first day on or after `start` that this subscription bills.

    Returns None when nothing is left, which is the case for a one-off already in
    the past or a subscription whose end date has gone by. The horizon covers
    slightly over two years so that an annual renewal is always found.
    """
    end = _parse_iso(expense.ends_on)
    for offset in range(horizon_days + 1):
        day = start + timedelta(days=offset)
        if end is not None and day > end:
            return None
        if occurs_on(expense, day):
            return day
    return None


GROUP_FIELDS = ("category", "account")


def get_totals_by(
    expenses: List[Expense], year: int, month: int, field: str = "category",
    account: Optional[str] = None,
) -> List[tuple]:
    """Spend for one month grouped by `field`, largest first.

    Uses the same occurrence counting as get_total_for_month, so a weekly
    subscription contributes every time it falls due rather than once.
    """
    if field not in GROUP_FIELDS:
        raise ValueError(f"cannot group by {field!r}; expected one of {GROUP_FIELDS}")

    totals: dict = {}
    for expense in get_expenses_for_month(expenses, year, month, account):
        if expense.amount is None:
            continue
        occurrences = len(occurrences_in_month(expense, year, month))
        name = getattr(expense, field) or "Uncategorised"
        totals[name] = totals.get(name, 0.0) + expense.amount * occurrences

    ranked = [(name, round(value, 2)) for name, value in totals.items()]
    ranked.sort(key=lambda item: (-item[1], item[0].lower()))
    return ranked


def get_category_totals(
    expenses: List[Expense], year: int, month: int, account: Optional[str] = None
) -> List[tuple]:
    return get_totals_by(expenses, year, month, "category", account)


def get_monthly_totals(expenses: List[Expense], year: int, account: Optional[str] = None) -> List[float]:
    """Twelve monthly totals for `year`, January first."""
    return [get_total_for_month(expenses, year, month, account) for month in range(1, 13)]


def get_paid_expense_ids(data_file: Path, year: int, month: int, account: Optional[str] = None) -> Set[str]:
    if data_file.suffix.lower() == ".json":
        return set()

    if not data_file.exists():
        return set()

    if account and account != "All accounts":
        query = """
            SELECT p.expense_id
            FROM expense_payments p
            JOIN expenses e ON e.id = p.expense_id
            WHERE p.paid_year = ? AND p.paid_month = ? AND e.account = ?
        """
        params = (year, month, account)
    else:
        query = "SELECT expense_id FROM expense_payments WHERE paid_year = ? AND paid_month = ?"
        params = (year, month)

    with _connect(data_file) as connection:
        rows = connection.execute(query, params).fetchall()
    return {row[0] for row in rows}


def get_paid_total_for_month(
    expenses: List[Expense], paid_expense_ids: Set[str], year: int, month: int, account: Optional[str] = None
) -> float:
    total = 0.0
    for expense in get_expenses_for_month(expenses, year, month, account):
        if expense.amount is not None and expense.id in paid_expense_ids:
            total += expense.amount * len(occurrences_in_month(expense, year, month))
    return round(total, 2)


def set_expense_paid(data_file: Path, expense_id: str, year: int, month: int, paid: bool) -> None:
    if data_file.suffix.lower() == ".json":
        return

    if not data_file.exists():
        return

    with _connect(data_file) as connection:
        if paid:
            connection.execute(
                """
                INSERT OR REPLACE INTO expense_payments (expense_id, paid_year, paid_month, paid_on)
                VALUES (?, ?, ?, DATE('now'))
                """,
                (expense_id, year, month),
            )
        else:
            connection.execute(
                "DELETE FROM expense_payments WHERE expense_id = ? AND paid_year = ? AND paid_month = ?",
                (expense_id, year, month),
            )


def get_expenses_for_day(
    expenses: List[Expense], day: date, account: Optional[str] = None
) -> List[Expense]:
    unique_by_id: dict[str, Expense] = {}
    for expense in expenses:
        if account and account != "All accounts" and expense.account != account:
            continue
        if occurs_on(expense, day):
            unique_by_id[expense.id] = expense

    return sorted(unique_by_id.values(), key=lambda item: (item.account, item.description.lower()))


def get_expenses_by_day(expenses: List[Expense], year: int, month: int, account: Optional[str] = None) -> dict[str, List[Expense]]:
    by_day: dict[str, List[Expense]] = {}
    for expense in get_expenses_for_month(expenses, year, month, account):
        for occurrence in occurrences_in_month(expense, year, month):
            by_day.setdefault(occurrence.isoformat(), []).append(expense)
    return by_day


def get_upcoming(expenses: List[Expense], start: date, days: int = 7, account: Optional[str] = None) -> List[tuple]:
    """Every billing date in the next `days` days, as (date, expense) pairs."""
    upcoming: List[tuple] = []
    for offset in range(days + 1):
        day = start + timedelta(days=offset)
        for expense in get_expenses_for_day(expenses, day, account):
            upcoming.append((day, expense))
    return upcoming


def remove_expense(expenses: List[Expense], expense_id: str) -> List[Expense]:
    return [expense for expense in expenses if expense.id != expense_id]
