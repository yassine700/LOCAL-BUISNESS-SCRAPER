#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test if all imports work correctly."""
import sys

try:
    from backend.main import app
    print("[OK] FastAPI app imports successfully")
    
    from backend.database import db
    print("[OK] Database module imports successfully")
    
    from backend.scrapers.yellowpages import YellowPagesScraper
    from backend.scrapers.yelp import YelpScraper
    print("[OK] Scrapers import successfully")
    
    from backend.celery_app import celery_app
    print("[OK] Celery app imports successfully")
    
    print("\n[SUCCESS] All modules imported successfully!")
    print("\nNext steps:")
    print("1. Make sure Redis is running")
    print("2. Start API: python -m uvicorn backend.main:app --reload")
    print("3. Start worker: celery -A backend.celery_app worker --loglevel=info")
    
except ImportError as e:
    print(f"ERROR: Import error: {e}")
    print("\nTry installing missing packages:")
    print("pip install fastapi uvicorn celery redis httpx beautifulsoup4 lxml")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

