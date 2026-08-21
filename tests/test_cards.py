import tempfile
import unittest
from datetime import date
from pathlib import Path

from expense_tracker import (
    card_due_date,
    get_card_year_totals,
    get_card_payments_for_year,
    get_card_years,
    create_card,
    create_expense,
    create_schema,
    delete_card,
    get_card_payment_history,
    get_card_payments,
    get_cards_due_between,
    get_cards_due_in_month,
    get_total_for_month,
    load_cards,
    save_card,
    set_card_payment,
)


class CardModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data_file = Path(tempfile.mkdtemp()) / "expenses.db"
        create_schema(self.data_file)

    def _card(self, name="Chase Freedom", due_day=15):
        card = create_card(name, due_day)
        save_card(self.data_file, card)
        return card

    def test_a_saved_card_comes_back(self) -> None:
        self._card()
        cards = load_cards(self.data_file)
        self.assertEqual([c.name for c in cards], ["Chase Freedom"])
        self.assertEqual(cards[0].due_day, 15)

    def test_cards_are_ordered_by_when_they_fall_due(self) -> None:
        self._card("Discover", 22)
        self._card("Chase", 4)
        self.assertEqual([c.name for c in load_cards(self.data_file)], ["Chase", "Discover"])

    def test_a_card_needs_a_name_and_a_sensible_due_day(self) -> None:
        with self.assertRaises(ValueError):
            create_card("   ", 10)
        with self.assertRaises(ValueError):
            create_card("Card", 0)
        with self.assertRaises(ValueError):
            create_card("Card", 32)

    def test_editing_a_card_keeps_its_payment_history(self) -> None:
        card = self._card()
        set_card_payment(self.data_file, card.id, 2026, 7, 380.10)

        card.name = "Chase Freedom Unlimited"
        save_card(self.data_file, card)

        self.assertEqual(get_card_payments(self.data_file, 2026, 7), {card.id: 380.10})
        self.assertEqual(load_cards(self.data_file)[0].name, "Chase Freedom Unlimited")

    def test_deleting_a_card_removes_its_payments(self) -> None:
        card = self._card()
        set_card_payment(self.data_file, card.id, 2026, 7, 380.10)
        delete_card(self.data_file, card.id)

        self.assertEqual(load_cards(self.data_file), [])
        self.assertEqual(get_card_payments(self.data_file, 2026, 7), {})

    def test_a_month_can_be_recorded_then_corrected_then_cleared(self) -> None:
        card = self._card()
        set_card_payment(self.data_file, card.id, 2026, 8, 412.60)
        self.assertEqual(get_card_payments(self.data_file, 2026, 8), {card.id: 412.60})

        set_card_payment(self.data_file, card.id, 2026, 8, 500.0)
        self.assertEqual(get_card_payments(self.data_file, 2026, 8), {card.id: 500.0})

        set_card_payment(self.data_file, card.id, 2026, 8, None)
        self.assertEqual(get_card_payments(self.data_file, 2026, 8), {})

    def test_history_is_newest_first(self) -> None:
        card = self._card()
        set_card_payment(self.data_file, card.id, 2026, 6, 100.0)
        set_card_payment(self.data_file, card.id, 2026, 8, 300.0)
        set_card_payment(self.data_file, card.id, 2026, 7, 200.0)

        history = get_card_payment_history(self.data_file, card.id)
        self.assertEqual(history, [(2026, 8, 300.0), (2026, 7, 200.0), (2026, 6, 100.0)])

    def test_a_due_day_past_the_end_of_the_month_lands_on_the_last_day(self) -> None:
        card = create_card("Late", 31)
        self.assertEqual(card_due_date(card, 2026, 2), date(2026, 2, 28))
        self.assertEqual(card_due_date(card, 2026, 1), date(2026, 1, 31))

    def test_cards_are_placed_on_their_day_of_the_month(self) -> None:
        card = self._card("Chase", 15)
        by_day = get_cards_due_in_month(load_cards(self.data_file), 2026, 8)
        self.assertEqual(list(by_day), ["2026-08-15"])
        self.assertEqual(by_day["2026-08-15"][0].name, "Chase")

    def test_upcoming_spans_the_month_boundary(self) -> None:
        self._card("Chase", 2)
        upcoming = get_cards_due_between(load_cards(self.data_file), date(2026, 8, 25), days=14)
        self.assertEqual([day for day, _card in upcoming], [date(2026, 9, 2)])

    def test_a_year_of_payments_can_be_backfilled_and_totalled(self) -> None:
        card = self._card()
        for month, amount in ((1, 301.0), (2, 302.0), (3, 303.0)):
            set_card_payment(self.data_file, card.id, 2026, month, amount)

        self.assertEqual(
            get_card_payments_for_year(self.data_file, card.id, 2026),
            {1: 301.0, 2: 302.0, 3: 303.0},
        )
        self.assertEqual(get_card_year_totals(self.data_file, 2026), {card.id: 906.0})

    def test_year_totals_keep_the_years_apart(self) -> None:
        card = self._card()
        set_card_payment(self.data_file, card.id, 2025, 12, 100.0)
        set_card_payment(self.data_file, card.id, 2026, 1, 250.0)

        self.assertEqual(get_card_year_totals(self.data_file, 2026), {card.id: 250.0})
        self.assertEqual(get_card_year_totals(self.data_file, 2025), {card.id: 100.0})
        self.assertEqual(get_card_years(self.data_file), [2026, 2025])

    def test_year_totals_add_every_card_together(self) -> None:
        first = self._card("Chase", 4)
        second = self._card("Discover", 20)
        set_card_payment(self.data_file, first.id, 2026, 1, 100.0)
        set_card_payment(self.data_file, second.id, 2026, 1, 50.0)

        totals = get_card_year_totals(self.data_file, 2026)
        self.assertEqual(round(sum(totals.values()), 2), 150.0)

    def test_cards_never_reach_a_spending_total(self) -> None:
        """The whole point: a card payment must not be counted as spending."""
        card = self._card()
        set_card_payment(self.data_file, card.id, 2026, 8, 412.60)

        expenses = [create_expense("Netflix", 22.99, "2026-08-03", "Main", "Streaming",
                                   cadence="monthly", due_day=3)]
        self.assertEqual(get_total_for_month(expenses, 2026, 8), 22.99)


if __name__ == "__main__":
    unittest.main()
