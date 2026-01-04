import sqlite3
import json

job_id = "e78108f3-b8d4-4f79-a8fd-3f8aba3b7d3f"

conn = sqlite3.connect('business_scraper.db')
conn.row_factory = sqlite3.Row

# Check schema
cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='businesses'")
schema = cursor.fetchone()
if schema:
    print("Businesses table schema:")
    print(schema['sql'])
    print()

# Check businesses saved
cursor = conn.execute('SELECT COUNT(*) as count FROM businesses WHERE job_id = ?', (job_id,))
total = cursor.fetchone()['count']
print(f"Total businesses saved for job {job_id}: {total}")

# Check unique websites
cursor = conn.execute('SELECT COUNT(DISTINCT website) as count FROM businesses WHERE job_id = ? AND website IS NOT NULL AND website != ""', (job_id,))
unique_websites = cursor.fetchone()['count']
print(f"Unique websites: {unique_websites}")

# Check top websites
cursor = conn.execute('SELECT website, COUNT(*) as cnt FROM businesses WHERE job_id = ? GROUP BY website ORDER BY cnt DESC LIMIT 10', (job_id,))
print("\nTop websites by count:")
for row in cursor.fetchall():
    print(f"  {row['website']}: {row['cnt']} businesses")

# Check recent businesses
cursor = conn.execute('SELECT business_name, website, city FROM businesses WHERE job_id = ? ORDER BY scraped_at DESC LIMIT 10', (job_id,))
print("\nMost recent businesses:")
for row in cursor.fetchall():
    print(f"  {row['business_name']} | {row['website']} | {row['city']}")

conn.close()

