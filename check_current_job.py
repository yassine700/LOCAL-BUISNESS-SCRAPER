import sqlite3

job_id = "ab25bc2b-8ac3-4a7c-beef-80db07384c35"

conn = sqlite3.connect('business_scraper.db')
conn.row_factory = sqlite3.Row

# Check if job exists
cursor = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,))
job = cursor.fetchone()

if job:
    print(f"Job ID: {job_id}")
    print(f"Keyword: {job['keyword']}")
    print(f"Status: {job['status']}")
    print(f"Tasks: {job['completed_tasks']}/{job['total_tasks']}")
    print()
    
    # Count businesses
    cursor = conn.execute('SELECT COUNT(*) as count FROM businesses WHERE job_id = ?', (job_id,))
    count = cursor.fetchone()['count']
    print(f"Businesses saved: {count}")
    
    # Check for duplicate patterns
    cursor = conn.execute('''
        SELECT business_name, website, city, COUNT(*) as count 
        FROM businesses 
        WHERE job_id = ?
        GROUP BY business_name, website, city
        HAVING count > 1
        LIMIT 5
    ''', (job_id,))
    duplicates = cursor.fetchall()
    if duplicates:
        print(f"\nDuplicate patterns:")
        for dup in duplicates:
            print(f"  {dup['business_name']} | {dup['website']} - appears {dup['count']} times")
    
    # Sample businesses
    cursor = conn.execute('SELECT business_name, website, city FROM businesses WHERE job_id = ? LIMIT 5', (job_id,))
    businesses = cursor.fetchall()
    if businesses:
        print(f"\nSample businesses:")
        for biz in businesses:
            print(f"  {biz['business_name']} | {biz['website']}")
else:
    print(f"Job {job_id} NOT FOUND in database")
    print("This means the job was created but not saved to DB, or it's a different job ID")

conn.close()

