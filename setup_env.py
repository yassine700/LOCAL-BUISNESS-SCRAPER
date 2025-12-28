#!/usr/bin/env python
"""
Helper script to create .env file with ScrapingBee API key.
Run this once to set up your environment.
"""
import os

def create_env_file():
    """Create .env file with ScrapingBee API key."""
    
    api_key = "Z88OFXQ7QLCKNND13S1D7CFCR8LN6JEHKZETKXOM5HHU2B7JLLGDFM4V97R3MWUX4C54QQ8S2OBJ0ID3"
    
    env_content = f"""# ScrapingBee API Configuration
# NEVER commit this file to Git!

SCRAPINGBEE_API_KEY={api_key}
SCRAPER_MODE=high_volume

# Database
DB_PATH=business_scraper.db

# Redis
REDIS_URL=redis://localhost:6379/0
"""
    
    env_file = ".env"
    
    if os.path.exists(env_file):
        print(f"[WARNING] {env_file} already exists!")
        response = input("Overwrite? (yes/no): ").strip().lower()
        if response != "yes":
            print("Cancelled.")
            return
    
    try:
        with open(env_file, "w") as f:
            f.write(env_content)
        print(f"[OK] Created {env_file} file with API key")
        print(f"[OK] API key configured (length: {len(api_key)} characters)")
        print("\nNext steps:")
        print("   1. Verify .env is in .gitignore")
        print("   2. Restart Docker: docker-compose up --build")
        print("   3. Or set environment variable manually")
    except Exception as e:
        print(f"[ERROR] Error creating .env file: {e}")

if __name__ == "__main__":
    create_env_file()

