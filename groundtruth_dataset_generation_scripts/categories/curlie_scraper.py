import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import os
import json
import time
import random
import csv
from urllib.parse import urlparse

def load_csv_uris(path, max=1000000000):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        if lines[0].strip() == 'rank,domain':
            lines = lines[1:]
        return {normalize_uri(line.split(",")[1]) for line in lines[:max] if line.strip()}

def normalize_uri(uri: str) -> str:
    uri = uri.strip()
    if not re.match(r'^[a-zA-Z]+://', uri):
        uri = 'http://' + uri
    parsed = urlparse(uri)
    host = parsed.hostname or ''
    host = re.sub(r'^www\.', '', host, flags=re.IGNORECASE)
    return host

def load_url_dict(file, uid_set, train=False):
    urls = {}
    with open(file, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            uid = int(row['uid'])
            if not train:
                if uid in uid_set:
                    urls[uid] = row['url']
            else:
                if uid not in uid_set:
                    urls[uid] = row['url']
    return urls

def uid_filter(file):
    with open(file) as f:
        uid_set = set(int(line.strip()) for line in f if line.strip())
    return uid_set

def extract_site_description(item):
    descr = item.select_one("div.site-descr")
    if not descr:
        return None
    text = descr.get_text(" ", strip=True)
    return text.replace("\xad", "")

def extract_sites_total_results(soup):
    node_range = soup.select_one("h3#site-list-header .node-range")
    if not node_range:
        return None
    text = node_range.get_text(" ", strip=True)
    m = re.search(r"\bof\s+([\d,]+)", text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))

def extract_total_results(soup):
    total = extract_sites_total_results(soup)
    if total is not None:
        return total
    info = soup.select_one("div.search-info")
    if not info:
        return None
    text = info.get_text(" ", strip=True)
    m = re.search(r"([\d,]+)\s*$", text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))

def extract_category_tree_from_ref(ref):
    parts = []
    for s in ref.stripped_strings:
        clean = s.replace("\xad", "").strip()
        if clean:
            parts.append(clean)
    return parts

def extract_category_trees_from_search(html, base_url="https://curlie.org/"):
    soup = BeautifulSoup(html, "html.parser")
    total_sites = extract_sites_total_results(soup)
    results = []
    for item in soup.select("div.site-item"):
        site_link = item.select_one("div.site-url a")
        if not site_link:
            continue
        site_url = site_link.get("href")
        ref = item.select_one("div.site-ref a")
        if not ref:
            continue
        category_tree = extract_category_tree_from_ref(ref)
        cat_href = ref.get("href")
        cat_url = urljoin(base_url, cat_href)
        description = extract_site_description(item)
        results.append({
            "site_url": site_url,
            "category_url": cat_url,
            "category_tree": category_tree,
            "raw_category_path": cat_href.strip("/"),
            "description": description
        })
    return results, total_sites

def curlie_category_trees_for_domain(domain, max_retry=5):
    start = 0
    total_sites = 1
    results = []
    retry = 0
    while start <= total_sites:
        params = {
            "q": domain,
            "start": start,
            "type": "next",
            "all": "null",
            "t": "null",
            "cat": "",
            "lang": "",
            "stime": 92452189
        }
        try:
            r = requests.get(
                "https://curlie.org/search",
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            )
            r.raise_for_status()
            if total_sites == 1:
                res, total_sites_t = extract_category_trees_from_search(r.text)
                if total_sites_t:
                    total_sites = total_sites_t
                else:
                    total_sites = start + 21
            else:
                res, _ = extract_category_trees_from_search(r.text)
            print(f"[{start}/{total_sites}] {domain}")
            start += 20
            results.extend(res)
            time.sleep(2)
        except Exception as e:
            retry += 1
            if retry >= max_retry:
                start += 20
                retry = 0
            print(f"[{start}/{total_sites}] {domain}: {e}")
            time.sleep(30)
    return results

def scrape_curlie(folder, maxx, tot, reprocess_domains=False):
    os.makedirs(folder, exist_ok=True)
    processed_domains = os.listdir(folder)
    tranco_list = load_csv_uris('../../tranco.csv', max=maxx)
    uid_set = uid_filter('homepage2vec/test_uid.txt')
    urls_uid_map = load_url_dict('homepage2vec/curlie_filtered.csv', uid_set, train=False)
    domains = set()
    for uid in urls_uid_map:
        domain = normalize_uri(urls_uid_map[uid])
        domains.add(domain)
    domains_in_tranco = domains.intersection(tranco_list)
    domains_not_in_tranco = list(domains - domains_in_tranco)
    sampled_domains_not_in_tranco = random.sample(domains_not_in_tranco, tot - len(domains_in_tranco))
    for domain in domains_in_tranco:
        if domain in tranco_list and (f"{domain}.jsonl" not in processed_domains or reprocess_domains):
            cats = curlie_category_trees_for_domain(f'"{domain}"')
            with open(f"{folder}/{domain}.jsonl", "w") as f:
                for item in cats:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(f"Finished scraping tranco domain: {domain}")
    for domain in sampled_domains_not_in_tranco:
        if (f"{domain}.jsonl" not in processed_domains or reprocess_domains):
            cats = curlie_category_trees_for_domain(f'"{domain}"')
            with open(f"{folder}/{domain}.jsonl", "w") as f:
                for item in cats:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(f"Finished scraping sampled domain: {domain}")

if __name__ == "__main__":
    scrape_curlie("raw_curlie_categories_intersect_tranco_top_100k", 100000, 40000, False)
