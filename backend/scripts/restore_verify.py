"""Read-only PostgreSQL restore integrity verification with JSON evidence."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import and_, exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.services.bootstrap import SCHEMA_HEAD

_SCHEMA = "bojro.restore-verification.v1"
_COUNT_TABLES = frozenset(
    {
        "audit_logs",
        "consent_events",
        "geo_districts",
        "geo_divisions",
        "geo_upazilas",
        "order_items",
        "orders",
        "product_variants",
        "products",
        "site_settings",
        "users",
    }
)
_REQUIRED_TRIGGERS = frozenset(
    {
        "consent_events_append_only",
        "trg_audit_logs_append_only",
        "trg_audit_logs_chain",
        "trg_audit_logs_no_truncate",
    }
)


@dataclass(frozen=True, slots=True)
class RestoreVerifyConfig:
    database_url: str
    environment: str
    timeout_seconds: float = 60.0
    expected_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("restore verification requires postgresql+asyncpg DATABASE_URL")
        if not 1 <= self.timeout_seconds <= 120:
            raise ValueError("RESTORE_VERIFY_TIMEOUT_SECONDS must be in [1, 120]")
        expected_tables = set(Base.metadata.tables)
        for table_name, count in self.expected_counts.items():
            if table_name not in expected_tables:
                raise ValueError(f"unknown expected-count table: {table_name}")
            if isinstance(count, bool) or count < 0:
                raise ValueError(f"expected count for {table_name} must be non-negative")

    @classmethod
    def from_environment(cls) -> RestoreVerifyConfig:
        raw_counts = json.loads(os.getenv("RESTORE_EXPECTED_COUNTS_JSON", "{}"))
        if not isinstance(raw_counts, dict):
            raise ValueError("RESTORE_EXPECTED_COUNTS_JSON must be a JSON object")
        expected_counts: dict[str, int] = {}
        for name, value in raw_counts.items():
            if not isinstance(name, str) or not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("restore expected counts must map table names to integers")
            expected_counts[name] = value
        return cls(
            database_url=(os.getenv("RESTORE_DATABASE_URL") or os.getenv("DATABASE_URL", "") or ""),
            environment=os.getenv("APP_ENV", "unknown"),
            timeout_seconds=float(os.getenv("RESTORE_VERIFY_TIMEOUT_SECONDS", "60")),
            expected_counts=expected_counts,
        )


async def verify_restore(
    config: RestoreVerifyConfig,
    *,
    engine: AsyncEngine | None = None,
) -> dict[str, object]:
    owned_engine = engine is None
    resolved_engine = engine or create_async_engine(
        config.database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        hide_parameters=True,
    )
    checks: dict[str, dict[str, object]] = {}
    counts: dict[str, int] = {}
    try:
        async with asyncio.timeout(config.timeout_seconds):
            async with resolved_engine.connect() as connection, connection.begin():
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                await connection.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": f"{int(config.timeout_seconds * 1000)}ms"},
                )
                read_only = await connection.scalar(text("SHOW transaction_read_only"))
                _record(checks, "read_only", read_only == "on", f"transaction={read_only}")

                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                _record(
                    checks,
                    "schema_head",
                    revision == SCHEMA_HEAD,
                    f"expected={SCHEMA_HEAD},actual={revision}",
                )

                present_tables = set(
                    await connection.scalars(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
                        )
                    )
                )
                expected_tables = set(Base.metadata.tables)
                missing_tables = sorted(expected_tables - present_tables)
                _record(
                    checks,
                    "tables",
                    not missing_tables,
                    "ok" if not missing_tables else "missing=" + ",".join(missing_tables),
                )

                if not missing_tables:
                    counts = await _table_counts(connection, config.expected_counts)
                    mismatches = sorted(
                        name
                        for name, expected in config.expected_counts.items()
                        if counts.get(name) != expected
                    )
                    _record(
                        checks,
                        "counts",
                        not mismatches,
                        "ok" if not mismatches else "mismatch=" + ",".join(mismatches),
                    )

                    invalid_constraints = list(
                        await connection.scalars(
                            text(
                                "SELECT conname FROM pg_constraint constraint_row "
                                "JOIN pg_namespace namespace_row "
                                "ON namespace_row.oid = constraint_row.connamespace "
                                "WHERE namespace_row.nspname = current_schema() "
                                "AND constraint_row.contype IN ('f','c') "
                                "AND NOT constraint_row.convalidated"
                            )
                        )
                    )
                    orphaned = await _foreign_key_orphans(connection)
                    fk_failures = sorted({*invalid_constraints, *orphaned})
                    _record(
                        checks,
                        "foreign_keys",
                        not fk_failures,
                        "ok" if not fk_failures else "invalid=" + ",".join(fk_failures),
                    )

                    missing_indexes, invalid_indexes = await _index_failures(connection)
                    index_failures = sorted({*missing_indexes, *invalid_indexes})
                    _record(
                        checks,
                        "indexes",
                        not index_failures,
                        "ok" if not index_failures else "invalid=" + ",".join(index_failures),
                    )

                    query_failures = await _query_integrity_failures(connection)
                    _record(
                        checks,
                        "queries",
                        not query_failures,
                        "ok" if not query_failures else "invalid=" + ",".join(query_failures),
                    )
    except (TimeoutError, OSError, RuntimeError, ValueError, TypeError) as error:
        _record(checks, "verification_runtime", False, type(error).__name__)
    except Exception as error:
        _record(checks, "verification_runtime", False, type(error).__name__)
    finally:
        if owned_engine:
            await resolved_engine.dispose()

    failed = sorted(name for name, check in checks.items() if check["status"] != "ok")
    return {
        "schema": _SCHEMA,
        "status": "fail" if failed else "pass",
        "environment": config.environment,
        "schema_head": SCHEMA_HEAD,
        "checked_at": datetime.now(UTC).isoformat(),
        "failed_checks": failed,
        "counts": counts,
        "checks": checks,
    }


async def _table_counts(
    connection: AsyncConnection, expected_counts: dict[str, int]
) -> dict[str, int]:
    names = sorted(_COUNT_TABLES | set(expected_counts))
    counts: dict[str, int] = {}
    for name in names:
        table = Base.metadata.tables[name]
        value = await connection.scalar(select(func.count()).select_from(table))
        counts[name] = int(value or 0)
    return counts


async def _foreign_key_orphans(connection: AsyncConnection) -> list[str]:
    failures: list[str] = []
    for table in Base.metadata.sorted_tables:
        for constraint in table.foreign_key_constraints:
            elements = list(constraint.elements)
            if not elements:
                continue
            parent_table = elements[0].column.table
            child = table.alias("restore_child")
            parent = parent_table.alias("restore_parent")
            populated = and_(*(child.c[item.parent.name].is_not(None) for item in elements))
            matches = and_(
                *(child.c[item.parent.name] == parent.c[item.column.name] for item in elements)
            )
            orphan_query = (
                select(1)
                .select_from(child)
                .where(populated, ~exists(select(1).select_from(parent).where(matches)))
                .limit(1)
            )
            if bool(await connection.scalar(select(exists(orphan_query)))):
                failures.append(str(constraint.name or f"{table.name}:unnamed_fk"))
    return failures


async def _index_failures(connection: AsyncConnection) -> tuple[list[str], list[str]]:
    expected = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.name is not None
    }
    rows = (
        await connection.execute(
            text(
                "SELECT index_class.relname, index_row.indisvalid, index_row.indisready "
                "FROM pg_index index_row "
                "JOIN pg_class table_class ON table_class.oid = index_row.indrelid "
                "JOIN pg_class index_class ON index_class.oid = index_row.indexrelid "
                "JOIN pg_namespace namespace_row ON namespace_row.oid = table_class.relnamespace "
                "WHERE namespace_row.nspname = current_schema()"
            )
        )
    ).all()
    present = {str(row[0]) for row in rows}
    invalid = sorted(str(row[0]) for row in rows if not bool(row[1]) or not bool(row[2]))
    return sorted(expected - present), invalid


async def _query_integrity_failures(connection: AsyncConnection) -> list[str]:
    failures: list[str] = []
    await connection.execute(
        text(
            "SELECT product_row.id FROM products product_row "
            "JOIN product_variants variant_row ON variant_row.product_id = product_row.id "
            "LEFT JOIN product_images image_row ON image_row.product_id = product_row.id "
            "ORDER BY product_row.id LIMIT 1"
        )
    )
    await connection.execute(
        text(
            "SELECT order_row.id, count(item_row.id) FROM orders order_row "
            "LEFT JOIN order_items item_row ON item_row.order_id = order_row.id "
            "GROUP BY order_row.id ORDER BY order_row.id LIMIT 1"
        )
    )
    broken_chain = await connection.scalar(
        text(
            "WITH audit_chain AS ("
            "SELECT previous_hash, lag(entry_hash) OVER (ORDER BY at, id) AS expected_previous "
            "FROM audit_logs"
            ") SELECT EXISTS (SELECT 1 FROM audit_chain "
            "WHERE previous_hash <> coalesce(expected_previous, repeat('0', 64)))"
        )
    )
    if bool(broken_chain):
        failures.append("audit_log_chain")
    triggers = set(
        await connection.scalars(
            text(
                "SELECT trigger_row.tgname FROM pg_trigger trigger_row "
                "JOIN pg_class table_row ON table_row.oid = trigger_row.tgrelid "
                "JOIN pg_namespace namespace_row ON namespace_row.oid = table_row.relnamespace "
                "WHERE namespace_row.nspname = current_schema() AND NOT trigger_row.tgisinternal"
            )
        )
    )
    failures.extend(sorted(_REQUIRED_TRIGGERS - triggers))
    return failures


def _record(checks: dict[str, dict[str, object]], name: str, passed: bool, detail: str) -> None:
    checks[name] = {
        "status": "ok" if passed else "unavailable",
        "required": True,
        "detail": detail,
    }


def _error_evidence(error: Exception) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "status": "fail",
        "environment": os.getenv("APP_ENV", "unknown"),
        "schema_head": SCHEMA_HEAD,
        "checked_at": datetime.now(UTC).isoformat(),
        "failed_checks": ["config"],
        "counts": {},
        "checks": {
            "config": {
                "status": "unavailable",
                "required": True,
                "detail": type(error).__name__,
            }
        },
    }


def main() -> None:
    try:
        evidence = asyncio.run(verify_restore(RestoreVerifyConfig.from_environment()))
    except Exception as error:
        evidence = _error_evidence(error)
    print(json.dumps(evidence, ensure_ascii=True, sort_keys=True))
    if evidence["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
