# Subscription Tracker

A desktop application for tracking recurring subscriptions and other monthly payments. It provides a responsive calendar, projected and remaining monthly totals, account filtering, payment status tracking, and warm light and dark themes.

## Features

- Protect the application behind a local username and password
- Add fixed or variable payments that repeat weekly, monthly, quarterly, yearly, or not at all
- Edit an existing subscription without losing its paid history
- Record a cancellation date so a finished subscription stops billing
- Record a description, amount, date, account, category, and color
- Display subscriptions in a responsive monthly calendar
- View projected and remaining expenses for the selected month
- Filter subscriptions by account
- Mark individual subscriptions as paid or pending each month
- Review every subscription for a selected day
- Open a scrollable list when a calendar day contains several subscriptions
- Choose between warm light and dark themes
- Store application data locally in SQLite

New subscriptions use yellow calendar markers by default. Additional curated colors and a custom color picker are available from the add-payment dialog.

## Requirements

- Python 3.10 or newer
- `tkcalendar`
- Tkinter, normally included with standard Python installations on Windows

Install the external dependency:

```bash
python -m pip install tkcalendar
```

## Run the application

From the project directory:

```bash
python main.py
```

## How repetition works

Every subscription has a **start date**, a **repeat cadence**, and an optional **end date**.

- The start date is the first day it bills. A subscription never appears in a month before it
  started, so historical months show what you were actually paying at the time.
- The cadence is one of one-off, weekly, monthly, every three months, or yearly. Monthly, quarterly
  and yearly entries bill on the same day of the month as the start date; if that day does not exist
  in a shorter month, the charge falls on the last day instead, so a payment due on the 31st bills
  on 28 February.
- The end date is the last day it can bill, and is left empty while a subscription is still active.
  Set it when you cancel something, and past months keep showing it correctly.

A monthly total counts every billing day in that month, so a weekly subscription is counted four or
five times rather than once.

Use `Edit` in the selected-day panel to change any of this. Editing keeps the subscription's
identity, so the months you already marked as paid are preserved — deleting and re-adding would
lose them.

## Account login

The first launch asks you to create a local account. The password must contain at least eight
characters, one capital letter, one lower-case letter, one number, and one symbol. Every later
launch asks for that username and password before the tracker opens.

Passwords are never stored directly. They are hashed with PBKDF2-HMAC-SHA256 using 200,000
iterations and a random per-account salt, and the stored hash is compared in constant time.

This login is a convenience gate rather than a security boundary. The subscription data itself is
stored in an unencrypted SQLite database that any database tool can open, and the `Recover account`
button on the login screen clears the saved credentials so a new account can be created without
proving who you are. Do not rely on it to protect sensitive information on a shared computer.

## Data storage

Subscriptions and monthly payment statuses are stored locally in SQLite. The database is created automatically in the current Windows user's application-data directory:

```text
%LOCALAPPDATA%\SubscriptionTracker\expenses.db
```

When running from source, an existing project-level `expenses.db` or `expenses.json` is copied into that directory on the first run. Legacy JSON migration is recorded after it runs once, preventing deleted subscriptions from being restored later.

## Calendar controls

- Use the left and right arrow buttons to move between months.
- Use the account dropdown to filter the calendar and totals.
- Select a calendar day to view its subscriptions in the right-side list.
- Select `+N more` to open the complete scrollable list for a busy day.
- Double-click a subscription in the selected-day list to change its paid status.
- Use the theme button to switch between light and dark modes.

## Run the tests

```bash
python -m unittest discover -s tests
```

The current automated tests cover expense filtering, monthly totals, paid totals, recurring and planned entries, removal helpers, and text wrapping.

## Build a portable Windows executable

Install the build dependencies:

```powershell
python -m pip install -r requirements-build.txt
```

Create the executable:

```powershell
.\build_windows.ps1
```

The finished application is written to `dist\Subscription Tracker.exe`. Send only that executable, preferably inside a ZIP file. Do not distribute your personal `expenses.db` or `expenses.json` files.

The portable version does not require Python and gives every Windows user a separate database under `%LOCALAPPDATA%`. Because the executable is unsigned, Windows SmartScreen may show an unrecognized-app warning when it is downloaded on another computer.

## Project files

- `main.py`: Tkinter user interface and dialog behavior
- `expense_tracker.py`: expense model, recurrence calculations, and SQLite storage
- `tests/test_expense_tracker.py`: automated unit tests
- `%LOCALAPPDATA%\SubscriptionTracker\expenses.db`: local SQLite data, created at runtime
- `expenses.json`: legacy data used for migration
- `build_windows.ps1`: repeatable Windows executable build
- `requirements-build.txt`: packaging dependencies
