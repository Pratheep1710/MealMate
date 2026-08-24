"""MP-029: service layer — orchestrates one or more app.repositories calls into a business
operation. Services depend on repositories, never the reverse; app.jobs entrypoints call into
services, not repositories directly, once a given operation has service-layer logic worth
isolating (see notification_slo.py for the one concrete example this phase adds).
"""
