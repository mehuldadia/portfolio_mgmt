# Recommended Skills for Portfolio Analyzer

This file describes the engineering skills most useful for maintaining and extending this app. It is a project guide, not an executable VS Code Agent Skill.

## Core Skills

- **Python application development:** modules, data structures, exceptions, dates, and packaging code under `src/`.
- **Flask web development:** routes, request validation, forms, sessions, templates, redirects, and application configuration.
- **Pandas and Excel I/O:** reading and validating `.xlsx`/`.xls` workbooks, normalizing headers and dates, and producing useful row-level errors. Use `openpyxl` for `.xlsx` and `xlrd` for legacy `.xls` where needed.
- **Financial transaction modeling:** purchases, redemptions, fees, dividends, interest, holdings, and consistent decimal/rounding conventions.
- **FIFO cost-basis analysis:** matching sales with earlier lots and preserving transaction ordering and lot-level fees.
- **Jinja and browser UI:** maintaining Flask templates, accessible forms, validation feedback, tables, and the existing Bootstrap-based interface.
- **Testing and debugging:** focused tests for parsers, calculations, Flask routes, exports, and data persistence, including malformed and empty workbooks.

## Skills for the Save Workflow

- **Relational data modeling:** design tables for portfolios, upload batches, transactions, income records, and property assets; use stable IDs and constraints rather than row indexes as identifiers.
- **SQLite persistence:** the app currently uses Python's standard-library `sqlite3` module to store records and import metadata in `data/portfolio.sqlite3`. SQLAlchemy is a useful next step if the schema, migrations, or query patterns grow substantially.
- **Import workflow design:** stock and mutual-fund uploads are validated and previewed before the user explicitly saves or discards them. Accepted batches are recorded transactionally; original workbooks are retained only after Save.
- **Migrations and backups:** evolve the schema safely and provide a way to back up and restore the portfolio database.
- **Web security and privacy:** validate file type and size, generate server-side filenames, avoid trusting spreadsheet formulas or paths, keep secrets out of source, and add authentication/ownership before serving multiple users.

## Next Skills to Apply

1. Add permanent automated tests for import preview, save, discard, and restart reload.
2. Add database backup/restore and schema migration support as the stored model evolves.
3. Add duplicate-import detection and user ownership before expanding beyond a local single-user app.

## Important Data Rule

Treat uploaded workbooks as input sources and normalized transactions as the portfolio's durable data. Retain original workbooks only when the user chooses to keep them; do not confuse a file copied into `data/` with a successfully imported or saved portfolio.