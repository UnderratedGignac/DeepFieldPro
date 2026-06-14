import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "book_accounts.db")


def init_account_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS book_accounts (
        book_name TEXT PRIMARY KEY,
        tier INTEGER,
        current_balance DECIMAL(10,2),
        max_stake DECIMAL(10,2),
        status TEXT,
        last_bet_at TIMESTAMP,
        total_staked DECIMAL(10,2),
        total_pnl DECIMAL(10,2)
    )
    """
    )

    # Initialize default books if empty
    cursor.execute("SELECT COUNT(*) FROM book_accounts")
    if cursor.fetchone()[0] == 0:
        default_books = [
            ("Betfair", 1, 5000.0, 5000.0, "active", 0.0, 0.0),
            ("Pinnacle", 1, 3000.0, 3000.0, "active", 0.0, 0.0),
            ("Bet365", 2, 500.0, 50.0, "active", 0.0, 0.0),
            ("DraftKings", 3, 200.0, 20.0, "active", 0.0, 0.0),
        ]
        cursor.executemany(
            """
            INSERT INTO book_accounts (book_name, tier, current_balance, max_stake, status, total_staked, total_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            default_books,
        )

    conn.commit()
    conn.close()


def get_best_book_for_stake(stake_required):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Prioritize Tier 1, then 2, then 3. Must be active and have enough balance and max_stake > stake
    query = """
        SELECT book_name, current_balance, max_stake 
        FROM book_accounts 
        WHERE status = 'active' 
          AND current_balance >= ?
          AND max_stake >= ?
        ORDER BY tier ASC, current_balance DESC
    """

    cursor.execute(query, (stake_required, stake_required))
    row = cursor.fetchone()
    conn.close()

    if row:
        return row[0]  # Returns the best book name
    return None


def update_account_post_bet(book_name, stake):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        UPDATE book_accounts 
        SET current_balance = current_balance - ?,
            total_staked = total_staked + ?,
            last_bet_at = ?
        WHERE book_name = ?
    """,
        (stake, stake, now, book_name),
    )

    conn.commit()
    conn.close()
    print(f"Account {book_name} updated: Stake ${stake:.2f} deducted.")


def mark_account_limited(book_name, new_max_stake):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    status = "limited" if new_max_stake > 0 else "banned"

    cursor.execute(
        """
        UPDATE book_accounts 
        SET max_stake = ?, status = ?
        WHERE book_name = ?
    """,
        (new_max_stake, status, book_name),
    )

    conn.commit()
    conn.close()
    print(
        f"Account {book_name} marked as {status} with new max stake ${new_max_stake:.2f}."
    )


if __name__ == "__main__":
    init_account_db()
    best_book = get_best_book_for_stake(100.0)
    print(f"Best book for $100 stake: {best_book}")
