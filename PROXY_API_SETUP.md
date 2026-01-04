# Quick Start Guide: Proxy API Configuration

## 🎯 Choose Your Scraping Method

### Option 1: FREE Direct IP Scraping
**Best for:** Testing, low-volume scraping, budget-conscious users

1. Open http://localhost:8000 in your browser
2. Enter keyword and cities
3. **Leave "Proxy API Key" field EMPTY**
4. Click "Start Scraping"

**Pros:**
- ✅ Completely free
- ✅ No signup required
- ✅ No API key needed

**Cons:**
- ❌ Slower (~1-2 seconds per page)
- ❌ May be rate-limited
- ❌ Some sites may block you

---

### Option 2: Use ScrapingBee (Recommended for Beginners)
**Best for:** Reliable scraping, anti-bot protection, good free tier

1. Sign up at https://www.scrapingbee.com/
2. Go to Settings → API Key
3. Copy your API key
4. Open http://localhost:8000
5. Enter keyword and cities
6. **Paste API key into "Proxy API Key" field**
7. Click "Start Scraping"

**Pricing:**
- Free tier: 1,000 requests/month
- Paid: $20-200+/month depending on volume

**Speed:** ~0.5-1 second per page (fast)

---

### Option 3: Use Bright Data
**Best for:** High-volume scraping, advanced features, enterprise

1. Sign up at https://brightdata.com/
2. Create a residential proxy zone
3. Get your API credentials
4. Open http://localhost:8000
5. Enter keyword and cities
6. **Paste API key into "Proxy API Key" field**
7. Click "Start Scraping"

**Pricing:**
- Custom pricing based on traffic
- Typically $300+/month

**Speed:** ~0.3-0.8 second per page (very fast)

---

### Option 4: Use Apify
**Best for:** Web automation, advanced scraping, integrations

1. Sign up at https://apify.com/
2. Create an actor or get API key
3. Open http://localhost:8000
4. Enter keyword and cities
5. **Paste API key into "Proxy API Key" field**
6. Click "Start Scraping"

**Pricing:**
- Free tier: $5 monthly credit
- Paid: $25+/month

**Speed:** ~0.5-1 second per page

---

### Option 5: Use Any Other Proxy Service
**Best for:** Custom requirements, specific providers

If you use a different proxy service (Oxylabs, SmartProxy, etc):

1. Get your API key from their dashboard
2. Open http://localhost:8000
3. Enter keyword and cities
4. **Paste API key into "Proxy API Key" field**
5. Click "Start Scraping"

**Note:** Most proxy services using standard HTTP APIs should work.

---

## 📊 Provider Comparison

| Provider | Free Tier | Price | Speed | Reliability | Ease of Use |
|----------|-----------|-------|-------|-------------|------------|
| Direct IP | Yes (unlimited) | Free | Slow | Low | Easy |
| ScrapingBee | 1,000 req/mo | $20+ | Medium | High | Very Easy |
| Bright Data | None | $300+ | Fast | Very High | Medium |
| Apify | $5 credit | $25+ | Medium | High | Easy |
| Oxylabs | None | $200+ | Fast | Very High | Medium |

---

## 🚀 Performance Tips

### For Direct IP Scraping
- Scrape fewer cities at a time
- Run during off-peak hours
- Be patient (may take 5-10 min per city)

### For API-Based Scraping
- Use ScrapingBee for best ease/price balance
- Bright Data for maximum reliability
- Can scrape 50+ cities in parallel
- Typically 2-5 minutes for 50 cities

---

## 🔐 Security Notes

- **API keys are sent securely over HTTPS**
- **Never share your API key publicly**
- **API key is only used for proxy requests**
- **Your password is not stored** (field is temporary)

---

## ❓ FAQ

**Q: Can I change API keys between scrapes?**
A: Yes! Just clear the field or enter a new key for each scrape.

**Q: What if my API key runs out of credits?**
A: Switch to direct IP scraping (free) or use a different API key.

**Q: Will the scraper work without any API key?**
A: Yes! It will use direct IP scraping (free but slower).

**Q: Can I use multiple proxy services?**
A: One at a time per scrape, but you can alternate between scrapes.

**Q: Is my API key stored anywhere?**
A: No. It's only used during the scrape and not saved to disk.

---

## 🆘 Troubleshooting

**Problem:** Results are empty with direct IP scraping
**Solution:** Try with a proxy API key (ScrapingBee, etc.)

**Problem:** API key not working
**Solution:** 
- Copy key again carefully (no spaces)
- Check your account has remaining credits
- Try direct IP scraping to verify system works

**Problem:** Results take too long
**Solution:** Use a faster proxy service (Bright Data)

**Problem:** Getting blocked even with API key
**Solution:** Try a different proxy service or direct IP with longer delays

---

## 📝 Example Workflow

```
1. Test with FREE direct IP:
   - Empty API key field
   - Scrape 1 city
   - See if results look good
   - Observe speed and reliability
   
2. If happy with results → stick with direct IP
   
3. If need faster speeds → get ScrapingBee API key
   - Free tier gives 1,000 requests
   - Plenty to test with
   
4. Once confident → upgrade to paid provider
   - Reliable for production use
   - Faster speeds
   - Better support
```

---

**Ready to start?** Open http://localhost:8000 and begin scraping! 🎉
