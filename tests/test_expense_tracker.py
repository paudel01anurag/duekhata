import unittest
from datetime import date

from expense_tracker import (
    create_expense,
    get_expenses_for_day,
    get_expenses_for_month,
    get_paid_total_for_month,
    get_total_for_month,
    remove_expense,
    wrap_text,
)


class ExpenseTrackerTests(unittest.TestCase):
    def test_month_total_is_sum_of_matching_expenses(self) -> None:
        expenses = [
            create_expense("Netflix", 15.0, "2026-08-10", "Main", "Subscription"),
            create_expense("Electricity", 72.5, "2026-08-15", "Main", "Utility"),
            create_expense("Spotify", 10.0, "2026-09-01", "Wife", "Subscription"),
        ]

        self.assertEqual(get_total_for_month(expenses, 2026, 8), 87.5)
        self.assertEqual(get_total_for_month(expenses, 2026, 9), 10.0)

    def test_account_filter_only_returns_matching_expenses(self) -> None:
        expenses = [
            create_expense("Netflix", 15.0, "2026-08-10", "Main", "Subscription"),
            create_expense("Water", 20.0, "2026-08-10", "Wife", "Utility"),
        ]

        result = get_expenses_for_month(expenses, 2026, 8, account="Main")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].description, "Netflix")

    def test_planned_expense_without_amount_appears_on_due_day(self) -> None:
        expenses = [
            create_expense(
                "Credit card",
                None,
                "2026-08-01",
                "Main",
                "Credit Card",
                recurring_monthly=True,
                due_day=25,
                expense_type="Variable",
                color="#ff7a59",
            )
        ]

        result = get_expenses_for_day(expenses, date(2026, 8, 25))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].description, "Credit card")

    def test_non_recurring_planned_entry_is_not_replicated_monthly(self) -> None:
        expenses = [
            create_expense(
                "Credit card",
                None,
                "2026-07-25",
                "Main",
                "Credit Card",
                recurring_monthly=False,
                due_day=25,
                expense_type="Variable",
                color="#ff7a59",
            )
        ]

        august = get_expenses_for_month(expenses, 2026, 8)
        july = get_expenses_for_month(expenses, 2026, 7)
        self.assertEqual(len(august), 0)
        self.assertEqual(len(july), 1)

    def test_paid_total_is_sum_of_marked_monthly_entries(self) -> None:
        expenses = [
            create_expense("Netflix", 12.0, "2026-08-10", "Main", "Subscription", recurring_monthly=True, due_day=10),
            create_expense("Spotify", 8.0, "2026-08-10", "Main", "Subscription", recurring_monthly=True, due_day=10),
        ]

        paid_total = get_paid_total_for_month(
            expenses,
            paid_expense_ids={expenses[0].id},
            year=2026,
            month=8,
            account="Main",
        )
        self.assertEqual(paid_total, 12.0)

    def test_remove_expense_deletes_matching_entry(self) -> None:
        first = create_expense("Netflix", 15.0, "2026-08-10", "Main", "Subscription")
        second = create_expense("Spotify", 10.0, "2026-08-10", "Main", "Subscription")
        expenses = [first, second]

        updated = remove_expense(expenses, first.id)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].id, second.id)

    def test_wrap_text_breaks_long_descriptions(self) -> None:
        wrapped = wrap_text("Discover card payment due soon", width=10)
        self.assertIn("\n", wrapped)
        self.assertTrue(wrapped.startswith("Discover"))


if __name__ == "__main__":
    unittest.main()
