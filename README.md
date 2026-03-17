# Martin County Restaurant Lead Scraper

Automatically finds new restaurant openings in Martin County, FL and emails a weekly report. Runs on GitHub Actions every Monday morning.

## What It Searches

| Source | What it finds | Why it matters |
|--------|--------------|----------------|
| FL DBPR Licenses | New food service license applications | Catches restaurants before they open |
| Sunbiz LLC Filings | New LLCs with restaurant-related names | Catches businesses at formation stage |
| Google News | Restaurant opening announcements | Catches public announcements |
| HometownNewsTC | Local Martin County restaurant news | Hyper-local coverage |
| BusinessDebut.com | Florida new restaurant roundups | Statewide new opening tracker |

## Setup (15 minutes)

### 1. Create a SendGrid account (free)

1. Go to [sendgrid.com](https://sendgrid.com) and sign up (free tier = 100 emails/day)
2. Go to **Settings > Sender Authentication** and verify a sender email address
3. Go to **Settings > API Keys** and create an API key with "Mail Send" permission
4. Copy the API key (you'll need it in step 3)

### 2. Create a GitHub repo

1. Create a new **personal** repo on GitHub (can be private)
2. Push all these files to the repo:

```bash
cd martin-county-leads
git init
git add .
git commit -m "Initial commit - restaurant lead scraper"
git remote add origin https://github.com/YOUR_USERNAME/martin-county-leads.git
git push -u origin main
```

### 3. Add secrets to GitHub

Go to your repo > **Settings** > **Secrets and variables** > **Actions** > **New repository secret**

Add these three secrets:

| Secret name | Value |
|------------|-------|
| `SENDGRID_API_KEY` | Your SendGrid API key from step 1 |
| `SENDER_EMAIL` | The email you verified in SendGrid |
| `RECIPIENT_EMAIL` | `shanealee@icloud.com` (or your friend's email) |

### 4. Test it

1. Go to **Actions** tab in your repo
2. Click **Weekly Restaurant Lead Scraper**
3. Click **Run workflow** > **Run workflow**
4. Check your email in a few minutes

## Change the schedule

Edit `.github/workflows/weekly_leads.yml` and update the cron expression:

```yaml
# Every Monday at 8am ET
- cron: '0 12 * * 1'

# Every day at 8am ET
- cron: '0 12 * * *'

# Every Wednesday and Friday at 9am ET
- cron: '0 13 * * 3,5'
```

## Run locally

```bash
pip install -r requirements.txt

# Set environment variables
export SENDGRID_API_KEY="your_key"
export SENDER_EMAIL="you@example.com"
export RECIPIENT_EMAIL="shanealee@icloud.com"

# Run
python main.py
```

## Change the target area

Edit the top of `scraper.py` to change the county, cities, or keywords:

```python
COUNTY = "Martin"
CITIES = ["Stuart", "Palm City", "Jensen Beach", "Hobe Sound", "Indiantown"]
KEYWORDS = ["restaurant", "grill", "kitchen", "cafe", ...]
```
