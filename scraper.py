"""
Martin County Restaurant Lead Scraper
Reads ZIP codes and cities from shared tracker settings (mc-settings).
Pushes new leads to shared tracker storage (mc-leads) after each run.
Runs weekly via GitHub Actions every Monday at 8am ET.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import csv
import io
import json
import re
import os

COUNTY = "Martin"
STATE = "FL"

DEFAULT_ZIPS = ["34994", "34996", "34997", "34990", "34991", "34957", "34956"]
DEFAULT_CITIES = ["Stuart", "Palm City", "Jensen Beach", "Hobe Sound", "Indiantown", "Port Salerno", "Sewalls Point"]

KEYWORDS = [
    "restaurant", "grill", "kitchen", "cafe", "bistro", "bar", "tavern",
    "pizzeria", "bakery", "diner", "eatery", "taqueria", "sushi", "steakhouse",
    "bbq", "brewery", "pub", "lounge", "catering", "food truck", "ice cream",
    "coffee", "juice", "smoothie", "deli"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0; research purposes)"
}

TRACKER_STORAGE_URL = os.environ.get("TRACKER_STORAGE_URL", "")
TRACKER_STORAGE_KEY = os.environ.get("TRACKER_STORAGE_KEY", "")


def load_settings():
    """Load ZIP codes and cities from tracker shared storage, fall back to defaults."""
    zips = DEFAULT_ZIPS[:]
    cities = DEFAULT_CITIES[:]

    if not TRACKER_STORAGE_URL or not TRACKER_STORAGE_KEY:
        print("  No tracker storage configured — using default ZIPs and cities.")
        return zips, cities

    try:
        r = requests.get(
            f"{TRACKER_STORAGE_URL}/get",
            headers={"Authorization": f"Bearer {TRACKER_STORAGE_KEY}"},
            params={"key": "mc-settings"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("value")
            if data:
                parsed = json.loads(data)
                if parsed.get("zips"):
                    zips = parsed["zips"]
                    print(f"  Loaded {len(zips)} ZIP codes from tracker settings.")
                if parsed.get("cities"):
                    cities = parsed["cities"]
                    print(f"  Loaded {len(cities)} cities from tracker settings.")
    except Exception as e:
        print(f"  Could not load tracker settings: {e} — using defaults.")

    return zips, cities


def push_leads_to_tracker(new_leads):
    """Push new leads into the tracker shared storage (merges with existing)."""
    if not TRACKER_STORAGE_URL or not TRACKER_STORAGE_KEY:
        print("  Tracker storage not configured — skipping push.")
        return

    headers = {"Authorization": f"Bearer {TRACKER_STORAGE_KEY}"}

    try:
        r = requests.get(
            f"{TRACKER_STORAGE_URL}/get",
            headers=headers,
            params={"key": "mc-leads"},
            timeout=10
        )
        existing = []
        if r.status_code == 200:
            val = r.json().get("value")
            if val:
                existing = json.loads(val)

        existing_names = {l.get("name", "").lower() for l in existing}
        added = 0
        now_week = datetime.now().strftime("%Y-W%W")

        for lead in new_leads:
            if lead.get("name", "").lower() not in existing_names:
                lead.setdefault("id", f"{int(datetime.now().timestamp())}-{added}")
                lead.setdefault("checked", False)
                lead.setdefault("notes", "")
                lead.setdefault("priority", "hot" if "DBPR" in lead.get("source","") or "Sunbiz" in lead.get("source","") else "warm")
                lead.setdefault("week", now_week)
                existing.insert(0, lead)
                added += 1

        requests.post(
            f"{TRACKER_STORAGE_URL}/set",
            headers={**headers, "Content-Type": "application/json"},
            json={"key": "mc-leads", "value": json.dumps(existing)},
            timeout=10
        )
        print(f"  Pushed {added} new leads to tracker (skipped {len(new_leads)-added} duplicates).")
    except Exception as e:
        print(f"  Could not push leads to tracker: {e}")


def search_dbpr_licenses(zips, cities):
    leads = []
    try:
        url = "https://www2.myfloridalicense.com/sto/file_download/extracts/newfood.csv"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            reader = csv.reader(io.StringIO(resp.text))
            header = next(reader, None)
            if header:
                for row in reader:
                    try:
                        row_text = " ".join(row).upper()
                        row_zip = row[7].strip() if len(row) > 7 else ""
                        if ("MARTIN" in row_text
                                or any(city.upper() in row_text for city in cities)
                                or row_zip in zips):
                            leads.append({
                                "source": "FL DBPR New Food License",
                                "name": row[1] if len(row) > 1 else "Unknown",
                                "dba": row[2] if len(row) > 2 else "",
                                "address": row[4] if len(row) > 4 else "",
                                "city": row[5] if len(row) > 5 else "",
                                "zip": row_zip,
                                "license_type": row[9] if len(row) > 9 else "",
                                "status": "New License",
                                "date_found": datetime.now().strftime("%Y-%m-%d"),
                                "raw_data": " | ".join(row[:12])
                            })
                    except (IndexError, ValueError):
                        continue
        print(f"  DBPR: Found {len(leads)} Martin County food licenses")
    except Exception as e:
        print(f"  DBPR: Error - {e}")
    return leads


def search_dbpr_license_portal(cities):
    leads = []
    try:
        url = "https://www.myfloridalicense.com/wl11.asp"
        params = {"mode": "2", "SID": "", "brd": "H", "typ": "2",
                  "Dession": "", "LicName": "", "county": "MARTIN", "status": "ACT"}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for table in soup.find_all("table"):
                for row in table.find_all("tr")[1:]:
                    cols = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cols) >= 4:
                        leads.append({
                            "source": "FL DBPR License Portal",
                            "name": cols[0] if cols else "",
                            "address": cols[2] if len(cols) > 2 else "",
                            "city": cols[3] if len(cols) > 3 else "",
                            "license_type": "Food Service",
                            "status": "Active License",
                            "date_found": datetime.now().strftime("%Y-%m-%d"),
                            "raw_data": " | ".join(cols)
                        })
        print(f"  DBPR Portal: Found {len(leads)} entries")
    except Exception as e:
        print(f"  DBPR Portal: Error - {e}")
    return leads


def search_sunbiz_new_llcs(cities):
    leads = []
    try:
        for keyword in ["restaurant", "grill", "kitchen", "cafe", "taco",
                        "pizza", "bar", "bistro", "bakery"]:
            url = (f"https://search.sunbiz.org/Inquiry/CorporationSearch/SearchByName"
                   f"?searchNameOrder={keyword}&searchTerm={keyword}&listNameOrder=&listNameType=")
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                table = soup.find("table", {"id": "search-results"})
                if table:
                    for row in table.find_all("tr")[:50]:
                        cols = row.find_all("td")
                        if len(cols) >= 3:
                            name = cols[0].get_text(strip=True)
                            filing_date = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                            try:
                                filed = datetime.strptime(filing_date, "%m/%d/%Y")
                                if filed > datetime.now() - timedelta(days=90):
                                    link = cols[0].find("a")
                                    if link:
                                        detail_url = "https://search.sunbiz.org" + link["href"]
                                        detail = requests.get(detail_url, headers=HEADERS, timeout=10)
                                        if detail.status_code == 200 and any(
                                            city.upper() in detail.text.upper()
                                            for city in cities + ["MARTIN"]
                                        ):
                                            leads.append({
                                                "source": "Sunbiz LLC Filing",
                                                "name": name,
                                                "filing_date": filing_date,
                                                "status": "New LLC Filed",
                                                "date_found": datetime.now().strftime("%Y-%m-%d"),
                                                "detail_url": detail_url,
                                                "raw_data": f"{name} | Filed: {filing_date}"
                                            })
                            except ValueError:
                                continue
        print(f"  Sunbiz: Found {len(leads)} new restaurant LLCs in Martin County")
    except Exception as e:
        print(f"  Sunbiz: Error - {e}")
    return leads


def search_google_news(cities):
    leads = []
    queries = [f"new restaurant {city} Florida" for city in cities[:4]]
    queries += ["new restaurant Martin County Florida"]
    try:
        for query in queries:
            url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "xml")
                for item in soup.find_all("item")[:10]:
                    title = item.title.text if item.title else ""
                    link = item.link.text if item.link else ""
                    pub_date = item.pubDate.text if item.pubDate else ""
                    if any(kw in title.lower() for kw in ["restaurant","cafe","grill","bar","kitchen","opening","opens"]):
                        leads.append({
                            "source": "Google News",
                            "name": title,
                            "url": link,
                            "pub_date": pub_date,
                            "status": "News Mention",
                            "date_found": datetime.now().strftime("%Y-%m-%d"),
                            "raw_data": f"{title} | {pub_date}"
                        })
        seen, unique = set(), []
        for l in leads:
            if l["name"] not in seen:
                seen.add(l["name"]); unique.append(l)
        leads = unique
        print(f"  Google News: Found {len(leads)} restaurant news items")
    except Exception as e:
        print(f"  Google News: Error - {e}")
    return leads


def search_hometown_news():
    leads = []
    try:
        url = "https://www.hometownnewstc.com/search/?l=25&sd=desc&s=start_time&f=html&t=article&nsa=eedition&q=restaurant+martin+county&app%5B0%5D=editorial"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.find_all("div", class_="card-body") or soup.find_all("h3")
            for article in articles[:10]:
                link = article.find("a")
                if link:
                    title = link.get_text(strip=True)
                    href = link.get("href", "")
                    if any(kw in title.lower() for kw in ["restaurant","open","cafe","grill","kitchen","dining"]):
                        leads.append({
                            "source": "HometownNewsTC",
                            "name": title,
                            "url": f"https://www.hometownnewstc.com{href}" if href.startswith("/") else href,
                            "status": "News Mention",
                            "date_found": datetime.now().strftime("%Y-%m-%d"),
                            "raw_data": title
                        })
        print(f"  HometownNews: Found {len(leads)} articles")
    except Exception as e:
        print(f"  HometownNews: Error - {e}")
    return leads


def search_business_debut():
    leads = []
    try:
        url = "https://www.businessdebut.com/?s=martin+county+restaurant"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for article in (soup.find_all("article") or soup.find_all("h2", class_="entry-title"))[:10]:
                link = article.find("a")
                if link:
                    leads.append({
                        "source": "BusinessDebut",
                        "name": link.get_text(strip=True),
                        "url": link.get("href",""),
                        "status": "News Mention",
                        "date_found": datetime.now().strftime("%Y-%m-%d"),
                        "raw_data": link.get_text(strip=True)
                    })
        print(f"  BusinessDebut: Found {len(leads)} articles")
    except Exception as e:
        print(f"  BusinessDebut: Error - {e}")
    return leads


def run_all_scrapers():
    print(f"\n{'='*60}")
    print(f"Martin County Restaurant Lead Scraper")
    print(f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    print("Loading settings from tracker...")
    zips, cities = load_settings()
    print(f"  ZIPs: {', '.join(zips)}")
    print(f"  Cities: {', '.join(cities)}\n")

    all_leads = []
    print("Searching FL DBPR new food licenses...")
    all_leads.extend(search_dbpr_licenses(zips, cities))
    print("Searching FL DBPR license portal...")
    all_leads.extend(search_dbpr_license_portal(cities))
    print("Searching Sunbiz for new restaurant LLCs...")
    all_leads.extend(search_sunbiz_new_llcs(cities))
    print("Searching Google News...")
    all_leads.extend(search_google_news(cities))
    print("Searching HometownNewsTC...")
    all_leads.extend(search_hometown_news())
    print("Searching BusinessDebut...")
    all_leads.extend(search_business_debut())

    print(f"\n{'='*60}")
    print(f"TOTAL LEADS FOUND: {len(all_leads)}")
    print(f"{'='*60}\n")

    print("Pushing leads to tracker dashboard...")
    push_leads_to_tracker(all_leads)

    return all_leads


if __name__ == "__main__":
    leads = run_all_scrapers()
    output_file = "leads_raw.json"
    with open(output_file, "w") as f:
        json.dump(leads, f, indent=2, default=str)
    print(f"Raw results saved to {output_file}")
    by_source = {}
    for lead in leads:
        src = lead.get("source","Unknown")
        by_source[src] = by_source.get(src,0)+1
    print("\nBy source:")
    for src, count in sorted(by_source.items()):
        print(f"  {src}: {count}")
"""
Martin County Restaurant Lead Scraper
Searches public data sources for new restaurant openings in Martin County, FL.
Runs weekly via GitHub Actions and emails results.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import csv
import io
import json
import re
import os

COUNTY = "Martin"
STATE = "FL"
KEYWORDS = [
    "restaurant", "grill", "kitchen", "cafe", "bistro", "bar", "tavern",
    "pizzeria", "bakery", "diner", "eatery", "taqueria", "sushi",
    "steakhouse", "bbq", "brewery", "pub", "lounge", "catering",
    "food truck", "ice cream", "coffee", "juice", "smoothie", "deli"
]
CITIES = ["Stuart", "Palm City", "Jensen Beach", "Hobe Sound", "Indiantown", "Port Salerno", "Sewalls Point"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LeadBot/1.0; research purposes)"
}


def search_dbpr_licenses():
    """Search FL DBPR for new food service licenses in Martin County."""
    leads = []
    try:
        # Try downloading the DBPR new food establishments CSV
        url = "https://www2.myfloridalicense.com/sto/file_download/extracts/newfood.csv"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            reader = csv.reader(io.StringIO(resp.text))
            header = next(reader, None)
            if header:
                # Find column indices (DBPR CSV format)
                for row in reader:
                    try:
                        row_text = " ".join(row).upper()
                        if "MARTIN" in row_text or any(city.upper() in row_text for city in CITIES):
                            leads.append({
                                "source": "FL DBPR New Food License",
                                "name": row[1] if len(row) > 1 else "Unknown",
                                "dba": row[2] if len(row) > 2 else "",
                                "address": row[4] if len(row) > 4 else "",
                                "city": row[5] if len(row) > 5 else "",
                                "zip": row[7] if len(row) > 7 else "",
                                "license_type": row[9] if len(row) > 9 else "",
                                "status": "New License",
                                "date_found": datetime.now().strftime("%Y-%m-%d"),
                                "raw_data": " | ".join(row[:12])
                            })
                    except (IndexError, ValueError):
                        continue
        print(f"  DBPR: Found {len(leads)} Martin County food licenses")
    except Exception as e:
        print(f"  DBPR: Error - {e}")
    return leads


def search_dbpr_license_portal():
    """Search DBPR online license verification for Martin County restaurants."""
    leads = []
    try:
        url = "https://www.myfloridalicense.com/wl11.asp"
        params = {
            "mode": "2",
            "SID": "",
            "brd": "H",  # Hotels & Restaurants
            "typ": "2",  # Food service
            "Dession": "",
            "LicName": "",
            "county": "MARTIN",
            "status": "ACT"
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows[1:]:  # skip header
                    cols = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cols) >= 4:
                        leads.append({
                            "source": "FL DBPR License Portal",
                            "name": cols[0] if cols else "",
                            "address": cols[2] if len(cols) > 2 else "",
                            "city": cols[3] if len(cols) > 3 else "",
                            "license_type": "Food Service",
                            "status": "Active License",
                            "date_found": datetime.now().strftime("%Y-%m-%d"),
                            "raw_data": " | ".join(cols)
                        })
        print(f"  DBPR Portal: Found {len(leads)} entries")
    except Exception as e:
        print(f"  DBPR Portal: Error - {e}")
    return leads


def search_sunbiz_new_llcs():
    """Search Sunbiz for new LLCs with restaurant-related names in Martin County."""
    leads = []
    try:
        for keyword in ["restaurant", "grill", "kitchen", "cafe", "taco", "pizza", "bar", "bistro", "bakery"]:
            url = f"https://search.sunbiz.org/Inquiry/CorporationSearch/SearchByName?searchNameOrder={keyword}&searchTerm={keyword}&listNameOrder=&listNameType="
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                table = soup.find("table", {"id": "search-results"})
                if table:
                    rows = table.find_all("tr")
                    for row in rows[:50]:  # check first 50 results
                        cols = row.find_all("td")
                        if len(cols) >= 3:
                            name = cols[0].get_text(strip=True)
                            filing_date = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                            # Check if filed in last 90 days
                            try:
                                filed = datetime.strptime(filing_date, "%m/%d/%Y")
                                if filed > datetime.now() - timedelta(days=90):
                                    # Get detail page to check if Martin County
                                    link = cols[0].find("a")
                                    if link:
                                        detail_url = "https://search.sunbiz.org" + link["href"]
                                        detail = requests.get(detail_url, headers=HEADERS, timeout=10)
                                        if detail.status_code == 200 and any(
                                            city.upper() in detail.text.upper() for city in CITIES + ["MARTIN"]
                                        ):
                                            leads.append({
                                                "source": "Sunbiz LLC Filing",
                                                "name": name,
                                                "filing_date": filing_date,
                                                "status": "New LLC Filed",
                                                "date_found": datetime.now().strftime("%Y-%m-%d"),
                                                "detail_url": detail_url,
                                                "raw_data": f"{name} | Filed: {filing_date}"
                                            })
                            except ValueError:
                                continue
        print(f"  Sunbiz: Found {len(leads)} new restaurant LLCs in Martin County")
    except Exception as e:
        print(f"  Sunbiz: Error - {e}")
    return leads


def search_google_news():
    """Search Google News RSS for new restaurant announcements in Martin County."""
    leads = []
    queries = [
        "new restaurant Stuart Florida",
        "new restaurant Martin County Florida",
        "restaurant opening Palm City Florida",
        "restaurant opening Jensen Beach Florida",
    ]
    try:
        for query in queries:
            url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "xml")
                items = soup.find_all("item")
                cutoff = datetime.now() - timedelta(days=30)
                for item in items[:10]:
                    title = item.title.text if item.title else ""
                    link = item.link.text if item.link else ""
                    pub_date = item.pubDate.text if item.pubDate else ""
                    if any(kw in title.lower() for kw in ["restaurant", "cafe", "grill", "bar", "kitchen", "opening", "opens"]):
                        leads.append({
                            "source": "Google News",
                            "name": title,
                            "url": link,
                            "pub_date": pub_date,
                            "status": "News Mention",
                            "date_found": datetime.now().strftime("%Y-%m-%d"),
                            "raw_data": f"{title} | {pub_date}"
                        })
        # Deduplicate by title
        seen = set()
        unique = []
        for lead in leads:
            if lead["name"] not in seen:
                seen.add(lead["name"])
                unique.append(lead)
        leads = unique
        print(f"  Google News: Found {len(leads)} restaurant news items")
    except Exception as e:
        print(f"  Google News: Error - {e}")
    return leads


def search_hometown_news():
    """Check HometownNewsTC for Martin County restaurant news."""
    leads = []
    try:
        url = "https://www.hometownnewstc.com/search/?l=25&sd=desc&s=start_time&f=html&t=article&nsa=eedition&q=restaurant+martin+county&app%5B0%5D=editorial"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.find_all("div", class_="card-body") or soup.find_all("h3")
            for article in articles[:10]:
                link = article.find("a")
                if link:
                    title = link.get_text(strip=True)
                    href = link.get("href", "")
                    if any(kw in title.lower() for kw in ["restaurant", "open", "cafe", "grill", "kitchen", "dining"]):
                        leads.append({
                            "source": "HometownNewsTC",
                            "name": title,
                            "url": f"https://www.hometownnewstc.com{href}" if href.startswith("/") else href,
                            "status": "News Mention",
                            "date_found": datetime.now().strftime("%Y-%m-%d"),
                            "raw_data": title
                        })
        print(f"  HometownNews: Found {len(leads)} articles")
    except Exception as e:
        print(f"  HometownNews: Error - {e}")
    return leads


def search_business_debut():
    """Check BusinessDebut.com for new Florida restaurant openings."""
    leads = []
    try:
        url = "https://www.businessdebut.com/?s=martin+county+restaurant"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.find_all("article") or soup.find_all("h2", class_="entry-title")
            for article in articles[:10]:
                link = article.find("a")
                if link:
                    title = link.get_text(strip=True)
                    href = link.get("href", "")
                    leads.append({
                        "source": "BusinessDebut",
                        "name": title,
                        "url": href,
                        "status": "News Mention",
                        "date_found": datetime.now().strftime("%Y-%m-%d"),
                        "raw_data": title
                    })
        print(f"  BusinessDebut: Found {len(leads)} articles")
    except Exception as e:
        print(f"  BusinessDebut: Error - {e}")
    return leads


def run_all_scrapers():
    """Run all scrapers and return combined results."""
    print(f"\n{'='*60}")
    print(f"Martin County Restaurant Lead Scraper")
    print(f"Run date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    all_leads = []

    print("Searching FL DBPR new food licenses...")
    all_leads.extend(search_dbpr_licenses())

    print("Searching FL DBPR license portal...")
    all_leads.extend(search_dbpr_license_portal())

    print("Searching Sunbiz for new restaurant LLCs...")
    all_leads.extend(search_sunbiz_new_llcs())

    print("Searching Google News...")
    all_leads.extend(search_google_news())

    print("Searching HometownNewsTC...")
    all_leads.extend(search_hometown_news())

    print("Searching BusinessDebut...")
    all_leads.extend(search_business_debut())

    print(f"\n{'='*60}")
    print(f"TOTAL LEADS FOUND: {len(all_leads)}")
    print(f"{'='*60}\n")

    return all_leads


if __name__ == "__main__":
    leads = run_all_scrapers()

    # Save raw results to JSON
    output_file = "leads_raw.json"
    with open(output_file, "w") as f:
        json.dump(leads, f, indent=2, default=str)
    print(f"Raw results saved to {output_file}")

    # Print summary
    by_source = {}
    for lead in leads:
        src = lead.get("source", "Unknown")
        by_source[src] = by_source.get(src, 0) + 1
    print("\nBy source:")
    for src, count in sorted(by_source.items()):
        print(f"  {src}: {count}")
