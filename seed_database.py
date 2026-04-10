"""
One-time script to seed the SQLite database from the existing authorized_users.csv.
This replicates the same logic used by the admin CSV upload in main.py.

Run this once after switching from PostgreSQL to SQLite:
    python seed_database.py
"""

import os
import sys
import csv
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import AuthorizedUser, get_db, close_db, DB_TYPE, DATABASE_URL

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'authorized_users.csv')

def seed_authorized_users():
    """Import authorized_users.csv into the authorized_users table"""
    if not os.path.exists(CSV_PATH):
        logger.error(f"CSV file not found: {CSV_PATH}")
        return False

    logger.info(f"Database type: {DB_TYPE}")
    logger.info(f"Database URL: {DATABASE_URL}")
    logger.info(f"Reading CSV: {CSV_PATH}")

    # Read CSV
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    logger.info(f"Read {len(rows)} rows from CSV")

    # Group by (last_name, email) and collect lo_root_ids, same as admin upload
    user_groups = defaultdict(list)
    for row in rows:
        status = row.get('status', '').strip().lower()
        if status != 'active':
            continue
        last_name = row.get('last_name', '').strip()
        email = row.get('email', '').strip().lower()
        if last_name and email:
            user_groups[(last_name, email)].append(row)

    logger.info(f"Found {len(user_groups)} unique active users")

    # Build users_data in the same format as the admin upload
    users_data = []
    for (last_name, email), group_rows in user_groups.items():
        first_row = group_rows[0]
        user_code = first_row.get('user_id', first_row.get('user_code', ''))
        class_name = first_row.get('training_title', first_row.get('class_name', ''))
        date = first_row.get('completed_date', first_row.get('date', ''))

        lo_root_ids = []
        for r in group_rows:
            lo_id = r.get('lo_root_id', '').strip()
            if lo_id and lo_id not in lo_root_ids:
                lo_root_ids.append(lo_id)

        if lo_root_ids:
            users_data.append({
                'user_code': user_code,
                'last_name': last_name,
                'email': email,
                'status': 'active',
                'class_name': class_name,
                'date': date,
                'lo_root_ids': ';'.join(lo_root_ids)
            })

    logger.info(f"Prepared {len(users_data)} users for database insert")

    # Insert into database
    db = get_db()
    try:
        existing_count = db.query(AuthorizedUser).count()
        logger.info(f"Current authorized_users in database: {existing_count}")

        AuthorizedUser.bulk_insert(db, users_data)
        db.commit()

        final_count = db.query(AuthorizedUser).count()
        logger.info(f"SUCCESS: {final_count} authorized users now in database")
        return True

    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
        return False
    finally:
        close_db(db)


if __name__ == '__main__':
    print("=" * 60)
    print("  Seeding SQLite database from authorized_users.csv")
    print("=" * 60)
    
    success = seed_authorized_users()
    
    if success:
        print("\nDone! You can now:")
        print("  1. Run: python main.py")
        print("  2. Go to http://127.0.0.1:5000/register")
        print("  3. Register with your last name and email from the CSV")
        print("  4. Set your password")
        print("  5. Log in and use the admin panel to manage everything")
    else:
        print("\nSeeding failed. Check the errors above.")
