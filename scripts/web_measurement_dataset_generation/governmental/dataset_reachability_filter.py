import csv
from build_raw_tld_filtered_dataset import save_to_csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from playwright.sync_api import sync_playwright
import re
from urllib.parse import urlparse
import time

DESKTOP_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.199 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15; rv:120.0) Gecko/20100101 Firefox/120.0"
]

def random_desktop_ua():
    return random.choice(DESKTOP_UAS)

def normalize_host(netloc):
    return netloc.split("@")[-1].split(":")[0].lower().strip(".")

def normalize_uri(uri: str) -> str:
    uri = uri.strip()
    if not re.match(r'^[a-zA-Z]+://', uri):
        uri = 'http://' + uri
    parsed = urlparse(uri)
    host = parsed.hostname or ''
    host = re.sub(r'^www\.', '', host, flags=re.IGNORECASE)
    return host

def domain_check_playwright(domain, screen, folder):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=[
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu"
        ])
        page = browser.new_page(ignore_https_errors=True, user_agent=random_desktop_ua())
        try:
            response = page.goto(domain, timeout=30000)
            if response is None:
                browser.close()
                return False, ""
            status = response.status
            if status >= 400:
                browser.close()
                return False, ""
            page.wait_for_load_state("domcontentloaded")
            content = page.content()
            current_url = page.url
            if not screen:
                browser.close()
                return '<html' in content.lower() or '<!doctype html' in content.lower(), current_url
            else:
                if '<html' in content.lower() or '<!doctype html' in content.lower():
                    time.sleep(8)
                    page.screenshot(path=f"{folder}/{normalize_uri(domain)}.png", full_page=True)
                    browser.close()
                    return True, current_url
                else:
                    browser.close()
                    return False, ""
        except Exception as e:
            print(f"[ERROR] {e}")
            browser.close()
            return False, ""

def filter_redirects(url, domain):
    if not url == "":
        u = urlparse(url)
        host = normalize_host(u.netloc)
        host_parts = set(host.lower().split("."))
        domain_parts = set(domain.lower().split("."))
        if (len(domain_parts) == len(host_parts.intersection(domain_parts))):
            return True
    return False

def filter_unreachable_urls(lst, screen, folder, full):
    result = []
    for domain in lst:
        if not full:
            respon, url = domain_check_playwright(f"https://{domain}", screen, folder)
            if respon:
                result.append(domain)
        else:
            respon, url = domain_check_playwright(f"https://www.{domain}", screen, folder)
            if respon and filter_redirects(url, domain):
                result.append(f"https://www.{domain}")
            else:
                respon, url = domain_check_playwright(f"http://www.{domain}", screen, folder)
                if respon and filter_redirects(url, domain):
                    result.append(f"http://www.{domain}")
                else:
                    respon, url = domain_check_playwright(f"https://{domain}", screen, folder)
                    if respon and filter_redirects(url, domain):
                        result.append(f"https://{domain}")
                    else:
                        respon, url = domain_check_playwright(f"http://{domain}", screen, folder)
                        if respon and filter_redirects(url, domain):
                            result.append(f"http://{domain}")
                        else:
                            print(f"[WARN] No URL found for domain {domain}")
    return result

def parallel_filter(domains, screen=False, folder="", workers=10, chunk_size=5, full=True):
    chunks = [domains[i:i + chunk_size] for i in range(0, len(domains), chunk_size)]
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_chunk = {executor.submit(filter_unreachable_urls, chunk, screen, folder, full): chunk for chunk in chunks}
        for future in as_completed(future_to_chunk):
            try:
                results.extend(future.result())
            except Exception as e:
                print(f"[THREAD ERROR] {e}")
    return results

def load_dataset(file):
    domains = []
    with open(file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            domains.append(row['domain'])
    return domains

if __name__ == "__main__":
    top_domains = load_dataset("tranco_top_50k_only_gov_tld.csv")
    bot_domains = load_dataset("tranco_bot_50k_only_gov_tld.csv")
    filtered_top_domains = parallel_filter(top_domains, workers=20, chunk_size=20, full=False)
    filtered_bot_domains = parallel_filter(bot_domains, workers=20, chunk_size=20, full=False)
    save_to_csv("tranco_top_50k_only_gov_tld_reachable.csv", filtered_top_domains)
    save_to_csv("tranco_bot_50k_only_gov_tld_reachable.csv", filtered_bot_domains)
