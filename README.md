# Subscription Tracker

A desktop application for tracking recurring subscriptions and other monthly payments. It provides a responsive calendar, projected and remaining monthly totals, account filtering, payment status tracking, and warm light and dark themes.

## Features

- Add fixed or variable monthly payments
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
