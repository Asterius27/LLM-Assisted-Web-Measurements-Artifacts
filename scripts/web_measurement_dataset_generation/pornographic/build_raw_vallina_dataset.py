import csv
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

KEYWORDS = ["porn", "sex", "gay", "lesbian", "xxx"]
PAGES = [
    "https://toppornsites.com/",
    "https://mypornbible.com/",
    "https://www.only4adults.net/adults-en.html"
]

def filter_tranco(input_file, output_file):
    domains = set()
    with open(input_file, newline="", encoding="utf-8") as csv_in, \
        open(output_file, "w", newline="", encoding="utf-8") as csv_out:
        reader = csv.DictReader(csv_in)
        writer = csv.DictWriter(csv_out, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            domain = row['domain']
            if any(keyword in domain for keyword in KEYWORDS):
                writer.writerow(row)
                domains.add(domain)
    return domains

def normalize_domain(domain):
    if domain.startswith("www."):
        return domain[4:]
    return domain

def get_external_domains(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return set()
    soup = BeautifulSoup(r.text, "html.parser")
    domains = set()
    base_domain = urlparse(url).netloc
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"].strip())
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != base_domain:
            domain = normalize_domain(parsed.netloc)
            domains.add(domain)
    return domains

def extract_porno_websites(out_file, filt):
    unique_domains = set()
    for page in PAGES:
        print(f"Extracting from: {page}")
        domains = get_external_domains(page)
        print(f"Number of domains found: {len(domains)}")
        unique_domains.update(domains)
    with open(out_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["domain"])
        for domain in sorted(unique_domains):
            if domain not in filt:
                writer.writerow([domain])

if __name__ == "__main__":
    bot_domains = filter_tranco("../tranco_bot_50k.csv", "tranco_bot_50k_keyword_porno_filtered.csv")
    top_domains = filter_tranco("../tranco_top_50k.csv", "tranco_top_50k_keyword_porno_filtered.csv")
    merge = bot_domains.union(top_domains)
    extract_porno_websites("porno_websites_from_scrape.csv", merge)
