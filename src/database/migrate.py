#!/usr/bin/env python3
"""
Database Migration Script

Creates all database tables defined in models.py.
Supports PostgreSQL (production) and SQLite (development/testing).
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from database.models import Base


def get_database_url() -> str:
    """Get database URL from environment or use default."""
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        # Fallback to SQLite for local development
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "deepfield.db",
        )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        database_url = f"sqlite:///{db_path}"
        print(f"No DATABASE_URL found, using SQLite: {database_url}")

    return database_url


def run_migrations():
    """Run database migrations - create all tables."""
    database_url = get_database_url()
    print(f"Connecting to database: {database_url}")

    # Create engine
    engine = create_engine(database_url)

    # For PostgreSQL, check connection first
    if database_url.startswith("postgresql"):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
        except Exception as e:
            print(f"✗ Database connection failed: {e}")
            sys.exit(1)

    # Create all tables
    print("Creating database tables...")
    Base.metadata.create_all(engine)
    print("✓ All tables created successfully")

    # Verify tables were created
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\nTables in database ({len(tables)}):")
    for table in sorted(tables):
        print(f"  - {table}")

    print("\n✓ Migration completed successfully!")


if __name__ == "__main__":
    run_migrations()
