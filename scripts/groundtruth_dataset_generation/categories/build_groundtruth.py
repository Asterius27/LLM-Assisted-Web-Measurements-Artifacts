import json
from raw_curlie_categories_parser import normalize_host
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from playwright.sync_api import sync_playwright

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

def domain_check_playwright(domain, boolean=True):
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
                if boolean:
                    return False
                else:
                    return ""
            status = response.status
            if status >= 400:
                browser.close()
                if boolean:
                    return False
                else:
                    return ""
            page.wait_for_load_state("domcontentloaded")
            content = page.content()
            current_url = page.url
            browser.close()
            if boolean:
                return '<html' in content.lower() or '<!doctype html' in content.lower()
            else:
                return current_url
        except Exception as e:
            print(f"[ERROR] {e}")
            browser.close()
            if boolean:
                return False
            else:
                return ""

def filter_unreachable_urls(lst, full):
    result = []
    for domain in lst:
        if isinstance(domain, str):
            if not full:
                if domain_check_playwright(f"https://{domain}"):
                    result.append(domain)
            else:
                if domain_check_playwright(f"https://www.{domain}"):
                    result.append(f"https://www.{domain}")
                elif domain_check_playwright(f"http://www.{domain}"):
                    result.append(f"http://www.{domain}")
                elif domain_check_playwright(f"https://{domain}"):
                    result.append(f"https://{domain}")
                elif domain_check_playwright(f"http://{domain}"):
                    result.append(f"http://{domain}")
                else:
                    print(f"[WARN] No URL found for domain {domain}")
        else:
            result.append((domain[0], domain[1], domain_check_playwright(domain[1], boolean=False)))
    return result

def parallel_filter(domains, workers=10, chunk_size=5, full=True):
    chunks = [domains[i:i + chunk_size] for i in range(0, len(domains), chunk_size)]
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_chunk = {executor.submit(filter_unreachable_urls, chunk, full): chunk for chunk in chunks}
        for future in as_completed(future_to_chunk):
            try:
                results.extend(future.result())
            except Exception as e:
                print(f"[THREAD ERROR] {e}")
    return results

def load_urls(file):
    result = []
    with open(file) as f:
        data = json.load(f)
    for domain in data:
        if "confirmed" in data[domain]:
            result.append((domain, data[domain]["baseline_urls"][0]))
    print(f"Loaded {len(result)} URLs")
    return result, data

def filter_redirects(lst):
    result = {}
    for elem in lst:
        if not elem[2] == "":
            u = urlparse(elem[2])
            host = normalize_host(u.netloc)
            host_parts = set(host.lower().split("."))
            domain_parts = set(elem[0].lower().split("."))
            if (len(domain_parts) == len(host_parts.intersection(domain_parts))):
                result[elem[0]] = (elem[1], elem[2])
    return result

def save_gt(file, unfiltered_data, filtered_dct):
    result = {}
    for domain in filtered_dct:
        result[filtered_dct[domain][1]] = unfiltered_data[domain]["confirmed"]
    with open(file, "w") as f:
        json.dump(result, f, indent=4)

if __name__ == "__main__":
    urls_list, unfiltered_data = load_urls("new_unfiltered_groundtruth_from_scrape.json")
    filtered_urls_list = parallel_filter(urls_list, 7, 5)
    filtered_urls_dct = filter_redirects(filtered_urls_list)
    save_gt("new_groundtruth.json", unfiltered_data, filtered_urls_dct)
