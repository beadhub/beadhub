from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Request
from pgdbm import AsyncDatabaseManager, DatabaseConfig
from pgdbm.migrations import AsyncMigrationManager

from .config import get_settings


class DatabaseInfra:
    """
    Shared pgdbm infrastructure for BeadHub.

    Creates a single shared pool and schema-specific managers
    for core modules (server, beads).
    """

    def __init__(self) -> None:
        self._shared_pool: Optional[Any] = None
        self._managers: Dict[str, AsyncDatabaseManager] = {}
        self._initialized: bool = False
        self._init_lock: asyncio.Lock = asyncio.Lock()
        self._owns_pool: bool = True

    async def initialize(self, *, shared_pool: Optional[Any] = None) -> None:
        if self._initialized:
            return

        async with self._init_lock:
            # Double-check after acquiring lock (another coroutine may have initialized)
            if self._initialized:
                return  # type: ignore[unreachable]  # Valid double-checked locking

            if shared_pool is None:
                settings = get_settings()
                config = DatabaseConfig(connection_string=settings.database_url)
                shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
                self._owns_pool = True
            else:
                # Host application owns lifecycle of the pool.
                self._owns_pool = False

            self._shared_pool = shared_pool

            self._managers["server"] = AsyncDatabaseManager(
                pool=shared_pool,
                schema="server",
            )
            self._managers["beads"] = AsyncDatabaseManager(
                pool=shared_pool,
                schema="beads",
            )
            # BeadHub implements the aweb protocol; keep identity/coordination tables
            # in a dedicated schema for clean extraction.
            self._managers["aweb"] = AsyncDatabaseManager(
                pool=shared_pool,
                schema="aweb",
            )

            base_dir = Path(__file__).resolve().parent
            migrations_root = base_dir / "migrations"

            for name, db in self._managers.items():
                # Ensure schema exists before applying migrations
                await db.execute(f'CREATE SCHEMA IF NOT EXISTS "{db.schema}"')

                if name == "aweb":
                    # Apply aweb protocol migrations using the same module_name as the
                    # standalone aweb server so migration history is shared.
                    import aweb as aweb_pkg

                    aweb_root = Path(aweb_pkg.__file__).resolve().parent
                    module_migrations = aweb_root / "migrations" / "aweb"
                    module_name = "aweb-aweb"
                else:
                    module_migrations = migrations_root / name
                    module_name = f"beadhub-{name}"

                if module_migrations.is_dir():
                    manager = AsyncMigrationManager(
                        db,
                        migrations_path=str(module_migrations),
                        module_name=module_name,
                    )
                    await manager.apply_pending_migrations()

            self._initialized = True

    async def close(self) -> None:
        if self._shared_pool is not None and self._owns_pool:
            await self._shared_pool.close()

        self._managers.clear()
        self._shared_pool = None
        self._initialized = False
        self._owns_pool = True

    @property
    def is_initialized(self) -> bool:
        """Check if the database infrastructure is initialized."""
        return self._initialized

    def get_manager(self, name: str = "server") -> AsyncDatabaseManager:
        if not self._initialized:
            raise RuntimeError(
                "DatabaseInfra is not initialized. Call 'await db_infra.initialize()' first."
            )
        manager = self._managers.get(name)
        if manager is None:
            available = ", ".join(sorted(self._managers.keys())) or "(none)"
            raise RuntimeError(
                f"Unknown database manager '{name}'. Available managers: {available}"
            )
        return manager


db_infra = DatabaseInfra()


def get_db_infra(request: Request) -> DatabaseInfra:
    """FastAPI dependency that returns the DatabaseInfra from app state.

    Works in both standalone and library modes since both set app.state.db.
    """
    return request.app.state.db
