import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from expense_tracker import (
    CADENCE_MONTHLY,
    CADENCE_ONCE,
    CADENCE_QUARTERLY,
    CADENCE_WEEKLY,
    CADENCE_YEARLY,
    add_expense,
    create_expense,
    create_schema,
    get_category_totals,
    get_expenses_by_day,
    get_expenses_for_day,
    get_expenses_for_month,
    get_monthly_totals,
    get_totals_by,
    next_occurrence,
    get_paid_expense_ids,
    get_paid_total_for_month,
    get_total_for_month,
    get_upcoming,
    get_yearly_total,
    load_expenses,
    occurrences_in_month,
    occurs_on,
    remove_expense,
    set_expense_paid,
    update_expense,
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

    def test_every_expense_in_the_month_is_returned(self) -> None:
        expenses = [
            create_expense("Netflix", 15.0, "2026-08-10", "Main", "Subscription"),
            create_expense("Water", 20.0, "2026-08-10", "Main", "Utility"),
        ]

        result = get_expenses_for_month(expenses, 2026, 8)
        self.assertEqual([item.description for item in result], ["Netflix", "Water"])

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


class RecurrenceTests(unittest.TestCase):
    def test_yearly_subscription_repeats_once_a_year(self) -> None:
        domain = create_expense(
            "Domain renewal", 18.0, "2026-03-14", "Main", "Software", cadence=CADENCE_YEARLY
        )

        self.assertTrue(occurs_on(domain, date(2026, 3, 14)))
        self.assertTrue(occurs_on(domain, date(2027, 3, 14)))
        self.assertTrue(occurs_on(domain, date(2030, 3, 14)))
        self.assertFalse(occurs_on(domain, date(2026, 4, 14)))
        self.assertFalse(occurs_on(domain, date(2027, 3, 13)))
        # It must not be counted in every month the way a monthly one is.
        self.assertEqual(get_total_for_month([domain], 2026, 3), 18.0)
        self.assertEqual(get_total_for_month([domain], 2026, 4), 0.0)
        self.assertEqual(get_yearly_total([domain], 2026), 18.0)

    def test_quarterly_subscription_bills_every_third_month(self) -> None:
        water = create_expense("Water", 60.0, "2026-01-20", "Main", "Utility", cadence=CADENCE_QUARTERLY)

        for month in (1, 4, 7, 10):
            self.assertTrue(occurs_on(water, date(2026, month, 20)), f"expected a bill in month {month}")
        for month in (2, 3, 5, 6):
            self.assertFalse(occurs_on(water, date(2026, month, 20)), f"unexpected bill in month {month}")
        self.assertEqual(get_yearly_total([water], 2026), 240.0)

    def test_weekly_subscription_counts_every_occurrence_in_the_month(self) -> None:
        locker = create_expense("Locker", 5.0, "2026-08-03", "Main", "Other", cadence=CADENCE_WEEKLY)

        occurrences = occurrences_in_month(locker, 2026, 8)
        self.assertEqual([day.day for day in occurrences], [3, 10, 17, 24, 31])
        # Five billing days means five times the amount, not one.
        self.assertEqual(get_total_for_month([locker], 2026, 8), 25.0)

    def test_subscription_does_not_appear_before_it_starts(self) -> None:
        gym = create_expense("Gym", 40.0, "2026-06-15", "Main", "Health", cadence=CADENCE_MONTHLY)

        self.assertFalse(occurs_on(gym, date(2026, 5, 15)))
        self.assertTrue(occurs_on(gym, date(2026, 6, 15)))
        self.assertTrue(occurs_on(gym, date(2026, 7, 15)))
        self.assertEqual(get_total_for_month([gym], 2026, 5), 0.0)

    def test_cancelled_subscription_stops_after_its_end_date(self) -> None:
        streaming = create_expense(
            "Streaming", 12.0, "2026-01-10", "Main", "Subscription",
            cadence=CADENCE_MONTHLY, ends_on="2026-04-10",
        )

        self.assertTrue(occurs_on(streaming, date(2026, 4, 10)))
        self.assertFalse(occurs_on(streaming, date(2026, 5, 10)))
        self.assertEqual(get_total_for_month([streaming], 2026, 4), 12.0)
        self.assertEqual(get_total_for_month([streaming], 2026, 5), 0.0)

    def test_billing_day_is_clamped_to_short_months(self) -> None:
        rent = create_expense(
            "Rent", 900.0, "2026-01-31", "Main", "Housing", cadence=CADENCE_MONTHLY, due_day=31
        )

        # February has no 31st, so the charge lands on the last day instead.
        self.assertTrue(occurs_on(rent, date(2026, 2, 28)))
        self.assertFalse(occurs_on(rent, date(2026, 2, 27)))
        self.assertTrue(occurs_on(rent, date(2026, 4, 30)))
        self.assertEqual(len(occurrences_in_month(rent, 2026, 2)), 1)

    def test_one_off_expense_never_repeats(self) -> None:
        laptop = create_expense("Laptop", 1200.0, "2026-08-09", "Main", "Other", cadence=CADENCE_ONCE)

        self.assertTrue(occurs_on(laptop, date(2026, 8, 9)))
        self.assertFalse(occurs_on(laptop, date(2026, 9, 9)))

    def test_calendar_grouping_lists_every_billing_day(self) -> None:
        locker = create_expense("Locker", 5.0, "2026-08-03", "Main", "Other", cadence=CADENCE_WEEKLY)
        by_day = get_expenses_by_day([locker], 2026, 8)
        self.assertEqual(
            sorted(by_day), ["2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24", "2026-08-31"]
        )

    def test_upcoming_lists_bills_in_the_next_week(self) -> None:
        netflix = create_expense("Netflix", 15.0, "2026-08-01", "Main", "Subscription",
                                 cadence=CADENCE_MONTHLY, due_day=18)
        rent = create_expense("Rent", 900.0, "2026-08-01", "Main", "Housing",
                              cadence=CADENCE_MONTHLY, due_day=25)

        upcoming = get_upcoming([netflix, rent], date(2026, 8, 14), days=7)
        self.assertEqual([(day.isoformat(), item.description) for day, item in upcoming],
                         [("2026-08-18", "Netflix")])


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.data_file = Path(self.directory.name) / "expenses.db"
        create_schema(self.data_file)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_editing_a_subscription_keeps_its_paid_history(self) -> None:
        netflix = create_expense("Netflix", 15.0, "2026-08-10", "Main", "Subscription",
                                 cadence=CADENCE_MONTHLY, due_day=10)
        add_expense(self.data_file, netflix)
        set_expense_paid(self.data_file, netflix.id, 2026, 8, True)
        set_expense_paid(self.data_file, netflix.id, 2026, 7, True)

        raised = create_expense("Netflix", 17.99, "2026-08-10", "Main", "Subscription",
                                cadence=CADENCE_MONTHLY, due_day=10, expense_id=netflix.id)
        update_expense(self.data_file, raised)

        stored = load_expenses(self.data_file)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].amount, 17.99)
        self.assertEqual(stored[0].id, netflix.id)
        # The whole point of editing rather than delete-and-re-add.
        self.assertIn(netflix.id, get_paid_expense_ids(self.data_file, 2026, 8))
        self.assertIn(netflix.id, get_paid_expense_ids(self.data_file, 2026, 7))

    def test_cadence_and_end_date_survive_a_round_trip(self) -> None:
        insurance = create_expense("Insurance", 320.0, "2026-02-01", "Main", "Insurance",
                                   cadence=CADENCE_YEARLY, ends_on="2030-02-01")
        add_expense(self.data_file, insurance)

        stored = load_expenses(self.data_file)[0]
        self.assertEqual(stored.cadence, CADENCE_YEARLY)
        self.assertEqual(stored.ends_on, "2030-02-01")

    def test_legacy_database_without_cadence_is_migrated(self) -> None:
        legacy = Path(self.directory.name) / "legacy.db"
        connection = sqlite3.connect(legacy)
        connection.execute(
            """
            CREATE TABLE expenses (
                id TEXT PRIMARY KEY, description TEXT NOT NULL, amount REAL,
                date TEXT NOT NULL, account TEXT NOT NULL, category TEXT NOT NULL,
                recurring_monthly INTEGER NOT NULL DEFAULT 0, due_day INTEGER,
                expense_type TEXT NOT NULL DEFAULT 'Fixed',
                color TEXT NOT NULL DEFAULT '#f4a261'
            )
            """
        )
        connection.executemany(
            "INSERT INTO expenses (id, description, amount, date, account, category,"
            " recurring_monthly, due_day) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("a", "Netflix", 15.0, "2026-08-10", "Main", "Subscription", 1, 10),
                ("b", "Laptop", 1200.0, "2026-08-09", "Main", "Other", 0, None),
            ],
        )
        connection.commit()
        connection.close()

        create_schema(legacy)
        stored = {item.description: item for item in load_expenses(legacy)}
        self.assertEqual(stored["Netflix"].cadence, CADENCE_MONTHLY)
        self.assertEqual(stored["Laptop"].cadence, CADENCE_ONCE)
        self.assertIsNone(stored["Laptop"].ends_on)


class CategoryAndTrendTests(unittest.TestCase):
    def _sample(self):
        return [
            create_expense("Netflix", 10.0, "2026-01-05", "Main", "Streaming",
                           cadence=CADENCE_MONTHLY, due_day=5),
            create_expense("Disney", 5.0, "2026-01-08", "Main", "Streaming",
                           cadence=CADENCE_MONTHLY, due_day=8),
            create_expense("Gym", 40.0, "2026-01-12", "Main", "Health",
                           cadence=CADENCE_MONTHLY, due_day=12),
            create_expense("Coffee", 3.0, "2026-08-03", "Main", "Food",
                           cadence=CADENCE_WEEKLY),
        ]

    def test_categories_are_summed_and_ranked_by_size(self):
        totals = get_category_totals(self._sample(), 2026, 8)
        names = [name for name, _ in totals]
        self.assertEqual(names[0], "Health")
        self.assertEqual(dict(totals)["Streaming"], 15.0)

    def test_weekly_subscription_counts_every_occurrence(self):
        # August 2026 has five Mondays from the 3rd, so a weekly $3 item is $15.
        totals = dict(get_category_totals(self._sample(), 2026, 8))
        self.assertEqual(totals["Food"], 15.0)

    def test_expenses_without_an_amount_are_skipped(self):
        expenses = [create_expense("Planned", None, "2026-08-04", "Main", "Other")]
        self.assertEqual(get_category_totals(expenses, 2026, 8), [])

    def test_monthly_totals_returns_twelve_values_january_first(self):
        totals = get_monthly_totals(self._sample(), 2026)
        self.assertEqual(len(totals), 12)
        # Nothing starts before January, and the three monthly items total $55.
        self.assertEqual(totals[0], 55.0)

    def test_monthly_totals_are_empty_before_anything_starts(self):
        expenses = [create_expense("Later", 20.0, "2026-06-01", "Main", "Other",
                                   cadence=CADENCE_MONTHLY, due_day=1)]
        totals = get_monthly_totals(expenses, 2026)
        self.assertEqual(totals[:5], [0.0, 0.0, 0.0, 0.0, 0.0])
        self.assertEqual(totals[5], 20.0)


class NextOccurrenceTests(unittest.TestCase):
    def test_finds_the_next_monthly_billing_day(self):
        expense = create_expense("Netflix", 10.0, "2026-01-10", "Main", "Streaming",
                                 cadence=CADENCE_MONTHLY, due_day=10)
        self.assertEqual(next_occurrence(expense, date(2026, 8, 3)), date(2026, 8, 10))

    def test_a_billing_day_today_counts_as_next(self):
        expense = create_expense("Netflix", 10.0, "2026-01-10", "Main", "Streaming",
                                 cadence=CADENCE_MONTHLY, due_day=10)
        self.assertEqual(next_occurrence(expense, date(2026, 8, 10)), date(2026, 8, 10))

    def test_returns_none_once_the_end_date_has_passed(self):
        expense = create_expense("Cancelled", 10.0, "2026-01-10", "Main", "Streaming",
                                 cadence=CADENCE_MONTHLY, due_day=10, ends_on="2026-05-10")
        self.assertIsNone(next_occurrence(expense, date(2026, 8, 1)))

    def test_returns_none_for_a_one_off_already_past(self):
        expense = create_expense("Laptop", 900.0, "2026-02-02", "Main", "Other")
        self.assertIsNone(next_occurrence(expense, date(2026, 8, 1)))

    def test_finds_an_annual_renewal_far_ahead(self):
        expense = create_expense("Domain", 18.0, "2026-01-14", "Main", "Software",
                                 cadence=CADENCE_YEARLY, due_day=14)
        self.assertEqual(next_occurrence(expense, date(2026, 8, 1)), date(2027, 1, 14))


class GroupedTotalsTests(unittest.TestCase):
    def _sample(self):
        return [
            create_expense("Netflix", 10.0, "2026-01-05", "Main", "Streaming",
                           cadence=CADENCE_MONTHLY, due_day=5),
            create_expense("Adobe", 60.0, "2026-01-12", "Business", "Software",
                           cadence=CADENCE_MONTHLY, due_day=12),
            create_expense("Notion", 12.0, "2026-01-18", "Business", "Software",
                           cadence=CADENCE_MONTHLY, due_day=18),
        ]

    def test_grouping_by_category_matches_the_named_helper(self):
        sample = self._sample()
        self.assertEqual(
            get_totals_by(sample, 2026, 8, "category"),
            get_category_totals(sample, 2026, 8),
        )

    def test_an_unknown_field_is_rejected(self):
        with self.assertRaises(ValueError):
            get_totals_by(self._sample(), 2026, 8, "colour")


if __name__ == "__main__":
    unittest.main()
