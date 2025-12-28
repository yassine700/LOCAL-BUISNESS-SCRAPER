# ⚠️ CRITICAL: API Key Security Setup

## ❌ NEVER DO THIS:

```python
# BAD - NEVER HARDCODE API KEYS!
API_KEY = "Z88OFXQ7QLCKNND13S1D7CFCR8LN6JEHKZETKXOM5HHU2B7JLLGDFM4V97R3MWUX4C54QQ8S2OBJ0ID3"
```

**Why this is dangerous:**
- API key exposed in source code
- Gets committed to Git (visible to everyone)
- Anyone with code access can use your quota
- Potential charges on your account

## ✅ CORRECT WAY: Environment Variables

### Option 1: Set Environment Variable (Temporary - Current Session Only)

**Linux/macOS:**
```bash
export SCRAPINGBEE_API_KEY="Z88OFXQ7QLCKNND13S1D7CFCR8LN6JEHKZETKXOM5HHU2B7JLLGDFM4V97R3MWUX4C54QQ8S2OBJ0ID3"
```

**Windows (PowerShell):**
```powershell
$env:SCRAPINGBEE_API_KEY="Z88OFXQ7QLCKNND13S1D7CFCR8LN6JEHKZETKXOM5HHU2B7JLLGDFM4V97R3MWUX4C54QQ8S2OBJ0ID3"
```

**Windows (CMD):**
```cmd
set SCRAPINGBEE_API_KEY=Z88OFXQ7QLCKNND13S1D7CFCR8LN6JEHKZETKXOM5HHU2B7JLLGDFM4V97R3MWUX4C54QQ8S2OBJ0ID3
```

### Option 2: Create .env File (Recommended for Development)

1. **Create `.env` file** in the project root:

```bash
# .env file
SCRAPINGBEE_API_KEY=Z88OFXQ7QLCKNND13S1D7CFCR8LN6JEHKZETKXOM5HHU2B7JLLGDFM4V97R3MWUX4C54QQ8S2OBJ0ID3
SCRAPER_MODE=high_volume
```

2. **Add `.env` to `.gitignore`** (should already be there):
```
.env
```

3. **Install python-dotenv** (if not already installed):
```bash
pip install python-dotenv
```

4. **Load .env in your code** (already handled by our config):

The code automatically reads from environment variables. Just make sure `.env` is loaded:
- Docker Compose automatically loads `.env`
- For local Python, use: `python-dotenv` or set manually

### Option 3: Docker Compose with .env File

1. Create `.env` file in project root:
```
SCRAPINGBEE_API_KEY=Z88OFXQ7QLCKNND13S1D7CFCR8LN6JEHKZETKXOM5HHU2B7JLLGDFM4V97R3MWUX4C54QQ8S2OBJ0ID3
SCRAPER_MODE=high_volume
```

2. Docker Compose automatically loads `.env` file (already configured)

3. Run:
```bash
docker-compose up --build
```

## ✅ Verify It's Working

Check if the API key is loaded correctly (without exposing it):

```python
import os
api_key = os.getenv("SCRAPINGBEE_API_KEY")
if api_key:
    print(f"✅ API key loaded (length: {len(api_key)} characters)")
    # NEVER print the actual key!
else:
    print("❌ API key not found")
```

Or check in the application logs - you should see ScrapingBee working without errors.

## 🔒 Security Checklist

- [ ] API key only in environment variable or `.env` file
- [ ] `.env` file in `.gitignore`
- [ ] No API key in source code
- [ ] No API key in commit history
- [ ] No API key in logs or error messages

## 🚨 If You Already Committed the API Key

If you accidentally committed the API key to Git:

1. **Revoke the API key immediately** in ScrapingBee dashboard
2. **Generate a new API key**
3. **Remove from Git history** (if repository is private)
4. **Use new key with environment variables**

## Current Code Security

Our code is already secure:
- ✅ Reads from `os.getenv("SCRAPINGBEE_API_KEY")`
- ✅ Never hardcodes API keys
- ✅ Never logs or prints API keys
- ✅ Validates without exposing the key

You just need to set the environment variable correctly!

