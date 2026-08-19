# Changelog

What changed in each version. Newest first. Every version can be downloaded from the
[releases page](https://github.com/paudel01anurag/duekhata/releases).

## v3.1.0 — 19 August 2026

**Renamed to DueKhata.** *Due* for what is owed, *khata* (खाता) for the ledger it is written in.

**Changed**

- The application, the executable and the data folder are now named DueKhata.

**Migration**

- Upgrading from Subscription Tracker keeps everything. On first run the old
  `%LOCALAPPDATA%\SubscriptionTracker` folder is copied to `%LOCALAPPDATA%\DueKhata`, subscriptions
  and login included. The old folder is left in place as a fallback and can be deleted once you are
  satisfied nothing is missing.

## v3.0.0 — 18 August 2026

A new layout. The calendar is still here, but it is now one view among four rather than the whole
application.

**Added**

- A dashboard: monthly totals, spending by category, what is due in the next fortnight, and the
  year's spending month by month.
- A Subscriptions view listing everything tracked, with how often each repeats and when it is next
  due, soonest first. Finished subscriptions sort to the bottom.
- A Statistics view: monthly spending across the year, and each category's share of it.
- A sidebar for moving between the four views. The account filter and the Add button stay in place
  while switching.

**Changed**

- Column headings sit over their data rather than floating mid-column.
- Font selection falls back through the macOS and Linux system faces instead of assuming Segoe is
  installed.
- Build ZIPs are written to `dist\archive`, leaving `dist` holding only the current executable.

**Unchanged**

- How repeat dates are worked out. Entries from v2 behave exactly as before, and no migration is
  needed.

## v2.0.0 — 14 August 2026

Recurrence became a real model rather than a single flag, and subscriptions became editable.

**Added**

- Five billing rhythms: one-off, weekly, monthly, quarterly and yearly. An annual renewal now
  appears once a year instead of every month or never.
- A start date and an optional end date, so a cancelled subscription stops filling the calendar.
- Editing an existing subscription, without losing any month already marked as paid.
- A local username and password gate.
- A redesigned interface: warm light and dark themes, rounded surfaces, coloured payment chips on
  each billing day.

**Changed**

- A subscription no longer appears in months before its start date. This is the behaviour change
  most likely to be noticed: months earlier than a subscription's start now look emptier, correctly.
- Old databases migrate automatically. Entries that were marked recurring become monthly; the rest
  become one-off and may need their cadence setting by hand.

**Fixed**

- Running `python main.py` hung with no error. The login dialog was created while the main window
  was hidden, which left it invisible and the program waiting on a window nobody could see.
- Editing a subscription destroyed its payment history, because the underlying write deleted and
  reinserted the row.
- The calendar shrank whenever a dialog opened, and never recovered.
- Packaged builds could copy a database sitting next to the source into the new user's profile.

## v1 — 7 to 9 August 2026

The first working version, shared as a build rather than a tagged release.

- A month calendar with subscriptions shown on their due day.
- Fixed and variable monthly payments, with description, amount, date, account, category and colour.
- Projected and remaining totals for the month, and filtering by account.
- Marking subscriptions paid or pending.
- Warm light and dark themes.
- Local SQLite storage under `%LOCALAPPDATA%`.
