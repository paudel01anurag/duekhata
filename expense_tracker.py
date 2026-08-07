from __future__ import annotations

import calendar
import json
import sqlite3
import textwrap
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, List, Optional, Set


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
                color TEXT NOT NULL DEFAULT '#f4a261'
            )
            """
        )
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
    }


def _upsert_expenses(connection: sqlite3.Connection, expenses: List[Expense]) -> None:
    data = [_to_dict(item) for item in expenses]
    if data:
        connection.executemany(
            """
            INSERT OR REPLACE INTO expenses (
                id, description, amount, date, account, category,
                recurring_monthly, due_day, expense_type, color
            ) VALUES (
                :id, :description, :amount, :date, :account, :category,
                :recurring_monthly, :due_day, :expense_type, :color
            )
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
            SELECT id, description, amount, date, account, category, recurring_monthly, due_day, expense_type, color
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
                due_day, expense_type, color
            ) VALUES (
                :id, :description, :amount, :date, :account, :category, :recurring_monthly,
                :due_day, :expense_type, :color
            )
            """,
            payload,
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
        id=datetime.now().strftime("%Y%m%d%H%M%S%f"),
        description=description.strip(),
        amount=normalized_amount,
        date=normalized_date,
        account=account.strip() or "Main",
        category=category.strip() or "General",
        recurring_monthly=bool(recurring_monthly),
        due_day=due_day,
        expense_type=expense_type.strip() or "Fixed",
        color=color,
    )


def _is_in_target_month(expense: Expense, year: int, month: int) -> bool:
    month_prefix = f"{year:04d}-{month:02d}-"
    last_day = calendar.monthrange(year, month)[1]

    if expense.recurring_monthly:
        return expense.due_day is not None and 1 <= expense.due_day <= last_day

    return expense.date.startswith(month_prefix)


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
    month_expenses = get_expenses_for_month(expenses, year, month, account)
    return round(sum(expense.amount or 0 for expense in month_expenses if expense.amount is not None), 2)


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
    month_expenses = get_expenses_for_month(expenses, year, month, account)
    return round(
        sum(expense.amount or 0 for expense in month_expenses if expense.id in paid_expense_ids and expense.amount is not None),
        2,
    )


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
    day_string = day.strftime("%Y-%m-%d")
    day_number = day.day
    unique_by_id: dict[str, Expense] = {}

    for expense in expenses:
        if account and account != "All accounts" and expense.account != account:
            continue

        is_match = False
        if not expense.recurring_monthly and expense.date == day_string:
            is_match = True
        elif expense.due_day == day_number and expense.due_day is not None and not expense.amount is None and expense.recurring_monthly:
            is_match = True
        elif expense.amount is None and expense.recurring_monthly and expense.due_day == day_number:
            is_match = True
        elif not expense.recurring_monthly and expense.amount is None and expense.date == day_string:
            is_match = True

        if is_match:
            unique_by_id[expense.id] = expense

    return sorted(unique_by_id.values(), key=lambda item: (item.account, item.description.lower()))


def get_expenses_by_day(expenses: List[Expense], year: int, month: int, account: Optional[str] = None) -> dict[str, List[Expense]]:
    month_prefix = f"{year:04d}-{month:02d}-"
    by_day: dict[str, List[Expense]] = {}
    for expense in get_expenses_for_month(expenses, year, month, account):
        if expense.date.startswith(month_prefix):
            day_key = expense.date
        elif expense.due_day is not None and 1 <= expense.due_day <= calendar.monthrange(year, month)[1]:
            day_key = f"{year:04d}-{month:02d}-{expense.due_day:02d}"
        else:
            continue

        by_day.setdefault(day_key, [])
        if expense not in by_day[day_key]:
            by_day[day_key].append(expense)

    return by_day


def remove_expense(expenses: List[Expense], expense_id: str) -> List[Expense]:
    return [expense for expense in expenses if expense.id != expense_id]
