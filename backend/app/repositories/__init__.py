"""MP-031: typed Postgres repository functions.

One module per domain (profiles, catalog, history, availability, plans, jobs, notifications),
each a set of plain functions taking a psycopg connection (app.db.connect()) as their first
argument and returning app.models types. No module here opens its own connection or commits —
callers (app.jobs entrypoints, tests) own the transaction boundary.
"""
