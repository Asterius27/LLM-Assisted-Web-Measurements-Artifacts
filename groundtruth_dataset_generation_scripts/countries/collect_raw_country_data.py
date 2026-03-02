from collections import Counter
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import socket
from urllib.parse import urlparse
import requests
import pycountry_convert as pc
import os
import csv
import random
import re
import time
import shutil
import tempfile
import subprocess
import gcld3

REGION_TO_BCP47 = {
    "ca": "en-CA",
    "au": "en-AU",
    "es": "es-ES",
    "nl": "nl-NL",
    "it": "it-IT",
    "lt": "lt-LT",
    "fr": "fr-FR",
    "mx": "es-MX",
    "gb": "en-GB",
    "pt": "pt-PT",
    "de": "de-DE",
    "br": "pt-BR",
    "cn": "zh-CN",
    "us": "en-US",
    "id": "id-ID",
    "jp": "ja-JP",
    "tr": "tr-TR",
    "in": "hi-IN",
    "kr": "ko-KR",
    "ru": "ru-RU"
}

CSV_DIR = "tranco_lists"
FASTTEXT_MODEL_PATH = "lid.176.bin"
EXTENSION_PATH = "I-Still-Dont-Care-About-Cookies-1.1.9"
COMPLETE_COUNTRIES_WHITELIST_GT = ["nl", "it", "de", "cn", "id", "jp", "in", "kr", "tr"]
RESTART_COUNTRIES_WHITELIST_GT = ["nl", "it", "de", "cn", "id", "jp", "in", "kr", "tr"]
INT_LOCALES = [REGION_TO_BCP47.get(x) for x in ["nl", "it", "de", "cn", "id", "jp", "in", "kr", "tr"]]
IPINFO_TOKEN = ""

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

gid = gcld3.NNetLanguageIdentifier(min_num_bytes=0, max_num_bytes=1000)

def detect_languages_gcld3(text):
    res = gid.FindLanguage(text)
    if res is None:
        return "unknown", 0.0, False
    return res.language, res.probability, res.is_reliable

def detect_languages_fasttext_cli(text, model_path, k=3):
    cmd = ["fasttext", "predict-prob", model_path, "-", str(k)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(text, timeout=1800)

        if proc.returncode != 0:
            return []

        parts = out.strip().split()
        results = []
        for i in range(0, len(parts), 2):
            label = parts[i].replace("__label__", "")
            prob = float(parts[i+1])
            results.append((label, prob))

        return results
    except Exception as e:
        proc.kill()
        out, err = proc.communicate()
        print(e)
        return []

def weighted_mean(values):
    total_weight = sum(w for _, w in values)
    if total_weight == 0:
        return 0.0
    return sum(v * w for v, w in values) / total_weight

def analyze_text_segments(segments):
    ft_agg = {}
    cld3_agg = {}

    for segment in segments:
        seg_len = len(segment)
        ft_preds = detect_languages_fasttext_cli(segment, FASTTEXT_MODEL_PATH)
        for lang, prob in ft_preds:
            if lang not in ft_agg:
                ft_agg[lang] = []
            ft_agg[lang].append((prob, seg_len))

        cld3_lang, cld3_prob, cld3_reliable = detect_languages_gcld3(segment)
        if cld3_lang not in cld3_agg:
            cld3_agg[cld3_lang] = []
        cld3_agg[cld3_lang].append((cld3_prob, seg_len, cld3_reliable))

    ft_summary = {}
    for lang, entries in ft_agg.items():
        weighted = weighted_mean(entries)
        ft_summary[lang] = weighted

    cld3_summary = {}
    for lang, data in cld3_agg.items():
        prob_entries = []
        rel_entries = []

        for prob, seg_len, reliable in data:
            prob_entries.append((prob, seg_len))
            rel_entries.append((1.0 if reliable else 0.0, seg_len))

        mean_prob = weighted_mean(prob_entries)
        mean_rel = weighted_mean(rel_entries)

        cld3_summary[lang] = {
            "mean_prob": mean_prob,
            "mean_reliable": mean_rel
        }

    sorted_ft = sorted(ft_summary.items(), key=lambda x: x[1], reverse=True)

    sorted_cld3 = sorted(
        cld3_summary.items(),
        key=lambda x: (x[1]["mean_prob"], x[1]["mean_reliable"]),
        reverse=True
    )

    return sorted_ft[:3], sorted_cld3[:3]

def generate_urls(domain):
    prefixes = ["https://", "http://"]
    subdomains = ["", "www."]
    urls = []
    for p in prefixes:
        for s in subdomains:
            urls.append(f"{p}{s}{domain}")
    return urls

def try_connect(url, target_language):
    with sync_playwright() as p:
        temp_dir = tempfile.mkdtemp()
        browser = p.chromium.launch_persistent_context(
            user_data_dir=temp_dir,
            headless=False,
            ignore_https_errors=True,
            user_agent=random_desktop_ua(),
            locale=target_language,
            args=[
                f"--disable-extensions-except={EXTENSION_PATH}",
                f"--load-extension={EXTENSION_PATH}",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu"
            ]
        )
        try:
            page = browser.new_page()
            page.set_default_timeout(30000)
            page.set_default_navigation_timeout(30000)
            response = page.goto(url, timeout=30000)
            if response is None:
                browser.close()
                shutil.rmtree(temp_dir)
                return None, None
            status = response.status
            if status >= 400:
                browser.close()
                shutil.rmtree(temp_dir)
                return None, None
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            time.sleep(5)
            text = page.locator("body").inner_text()
            current_url = page.url
            page.close()
            browser.close()
            shutil.rmtree(temp_dir)
            return text, current_url
        except Exception as e:
            print(e)
            browser.close()
            shutil.rmtree(temp_dir)
            return None, None

def worker(domains, locale, b_locale):
    results = []

    for domain in domains:
        print(f"\n--- Processing: {domain} ---")
        if domain.startswith("http"):
            urls = [domain]
        else:
            urls = generate_urls(domain)
        final_html = None
        working_url = None
        url_after_redirect = None

        for url in urls:
            print(f"Trying: {url}")
            html, current_url = try_connect(url, b_locale)
            if html:
                print(f"Connected successfully: {url}")
                final_html = html
                working_url = url
                url_after_redirect = current_url
                break

        if not final_html:
            print(f"No working URL found for {domain}")
            results.append((domain, None, None, locale, b_locale, None, None))
            continue

        ft_summary, cld3_summary = analyze_text_segments([final_html])

        print(f"fastText top languages: {ft_summary}")
        print(f"CLD3 summary: {cld3_summary}")

        results.append((domain, working_url, url_after_redirect, locale, b_locale, ft_summary, cld3_summary))

    return results

def parallel_filter(domains, locale, b_locale, workers=7, chunk_size=5):
    chunks = [domains[i:i + chunk_size] for i in range(0, len(domains), chunk_size)]
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_chunk = {executor.submit(worker, chunk, locale, b_locale): chunk for chunk in chunks}
        for future in as_completed(future_to_chunk):
            try:
                results.extend(future.result())
            except Exception as e:
                print(f"[THREAD ERROR] {e}")
    return results

def random_desktop_ua():
    return random.choice(DESKTOP_UAS)

def normalize_uri(uri: str) -> str:
    uri = uri.strip()
    if not re.match(r'^[a-zA-Z]+://', uri):
        uri = 'http://' + uri
    parsed = urlparse(uri)
    host = parsed.hostname or ''
    host = re.sub(r'^www\.', '', host, flags=re.IGNORECASE)
    return host

def load_domains(csv_path, maxx, rand, start=0):
    domains = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2:
                domains.append(normalize_uri(row[1].strip()))
    if rand:
        return random.sample(domains, maxx)
    else:
        return domains[start:maxx]

def load_int_filter(filter_dim, whitelist, start=0):
    domains = {}
    files = os.listdir(CSV_DIR)
    for file in files:
        if file.endswith("_crux_only.csv") and any(file.endswith(f"{c}_crux_only.csv") for c in whitelist):
            domains[file.split("_")[-3]] = load_domains(CSV_DIR + '/' + file, filter_dim, False, start)
    return domains

def save_gt(file, gt):
    with open(file, "w") as f:
        f.write(f'url,country\n')
        for c in gt:
            for url in gt[c]:
                f.write(f'{url},{c}\n')

def url_to_ip(url):
    hostname = urlparse(url).netloc or url
    if hostname:
        try:
            ip = socket.gethostbyname(hostname)
            return ip
        except:
            return ""
    else:
        return ""

def get_url_location_info(url):
    ip = url_to_ip(url)
    print(f"Found ip corresponding to {url}: {ip}")
    if ip:
        try:
            url = f"https://api.ipinfo.io/lite/{ip}?token={IPINFO_TOKEN}"
            response = requests.get(url, verify=False, timeout=300)
            data = response.json()
            return data
        except Exception as e:
            print(f"Could not retrieve ip location data for {ip}: {e}")
            return {}
    else:
        return {}

def country_to_continent(country_alpha2):
    continent_code = pc.country_alpha2_to_continent_code(country_alpha2.upper())
    return continent_code

def is_cc_tld(dom):
    tld = dom.split(".")[-1].lower()
    return len(tld) == 2 and tld.isalpha()

def domain_check_playwright(domain):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu"
            ]
        )
        page = browser.new_page(ignore_https_errors=True, user_agent=random_desktop_ua())
        try:
            page.set_default_timeout(30000)
            page.set_default_navigation_timeout(30000)
            response = page.goto(domain, timeout=30000)
            if response is None:
                browser.close()
                return False
            status = response.status
            if status >= 400:
                browser.close()
                return False
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            content = page.content()
            browser.close()
            return '<html' in content.lower() or '<!doctype html' in content.lower()
        except Exception as e:
            print(f"[ERROR] {e}")
            browser.close()
            return False

def filter_unreachable_urls(lst):
    result = []
    for domain in lst:
        if domain_check_playwright(f"https://www.{domain}"):
            result.append(f"https://www.{domain}")
            print(f"Successfully connected to https://www.{domain}")
        elif domain_check_playwright(f"http://www.{domain}"):
            result.append(f"http://www.{domain}")
            print(f"Successfully connected to http://www.{domain}")
        elif domain_check_playwright(f"https://{domain}"):
            result.append(f"https://{domain}")
            print(f"Successfully connected to https://{domain}")
        elif domain_check_playwright(f"http://{domain}"):
            result.append(f"http://{domain}")
            print(f"Successfully connected to http://{domain}")
        else:
            print(f"[WARN] No URL found for domain {domain}")
    return result

def parallel_int_filter(domains, workers=10, chunk_size=5):
    chunks = [domains[i:i + chunk_size] for i in range(0, len(domains), chunk_size)]
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_chunk = {executor.submit(filter_unreachable_urls, chunk): chunk for chunk in chunks}
        for future in as_completed(future_to_chunk):
            try:
                results.extend(future.result())
            except Exception as e:
                print(f"[THREAD ERROR] {e}")
    return results

def process_results(results, k, threshold, max_len, international="", log_f="new_tranco_lists_filtered"):
    logger_dct = {}
    filtered_domains = []
    for domain, url, url_after_redirect, loc, b_locale, ft_res, cld3_res in results:
        logger_dct[domain] = {}
        logger_dct[domain]['url'] = url
        logger_dct[domain]['final_url'] = url_after_redirect
        logger_dct[domain]['locale'] = loc
        logger_dct[domain]['browser_locale'] = b_locale
        logger_dct[domain]['fastText_result'] = ft_res
        logger_dct[domain]['CLD3_result'] = cld3_res
        if ft_res is None:
            ft_ress = []
        else:
            ft_ress = ft_res
        if cld3_res is None:
            cld3_ress = []
        else:
            cld3_ress = cld3_res
        url_location_info = get_url_location_info(url_after_redirect)
        url_continent = url_location_info.get("continent_code", "")
        print(f"Found continent corresponding to {url_after_redirect}: {url_continent}")
        locale_continent = country_to_continent(k)
        logger_dct[domain]['ip_country'] = url_location_info.get("country_code", "")
        logger_dct[domain]['ip_continent'] = url_continent
        logger_dct[domain]['locale_continent'] = locale_continent
        logger_dct[domain]['tld'] = domain.split(".")[-1].lower()
        if not is_cc_tld(domain):
            if any(k == key and v >= threshold for key, v in ft_ress) and url_continent == locale_continent:
                filtered_domains.append(domain)
                logger_dct[domain]["domain_loaded_in_correct_language"] = True
            elif any(k == key and v.get("mean_prob", 0) >= threshold for key, v in cld3_ress) and url_continent == locale_continent:
                filtered_domains.append(domain)
                logger_dct[domain]["domain_loaded_in_correct_language"] = True
            else:
                logger_dct[domain]["domain_loaded_in_correct_language"] = False
        else:
            if any(k == key and v >= threshold for key, v in ft_ress):
                filtered_domains.append(domain)
                logger_dct[domain]["domain_loaded_in_correct_language"] = True
            elif any(k == key and v.get("mean_prob", 0) >= threshold for key, v in cld3_ress):
                filtered_domains.append(domain)
                logger_dct[domain]["domain_loaded_in_correct_language"] = True
            else:
                logger_dct[domain]["domain_loaded_in_correct_language"] = False
    os.makedirs(log_f, exist_ok=True)
    with open(f"{log_f}/{international}{k}_top_{max_len}_filtered.json", "w") as log_out:
        json.dump(logger_dct, log_out, indent=4)
    return filtered_domains

def new_raw_int_domains_list(dct):
    intersect = list(set.intersection(*(set(dct[k]) for k in COMPLETE_COUNTRIES_WHITELIST_GT if k in dct)))
    return intersect

def new_raw_cc_domains_list(dct, filter_dct):
    result = {}
    for k in COMPLETE_COUNTRIES_WHITELIST_GT:
        result[k] = []
        for domain in dct[k]:
            discard = False
            for k_filter in COMPLETE_COUNTRIES_WHITELIST_GT:
                if not k_filter == k:
                    if domain in filter_dct[k_filter]:
                        discard = True
            if not discard:
                result[k].append(domain)
    return result

def collect_raw_data(max_len, max_len_inter, threshold, workers, chunk_size):
    countries_lists = load_int_filter(max_len, COMPLETE_COUNTRIES_WHITELIST_GT)
    countries_lists_filter = load_int_filter(max_len_inter, COMPLETE_COUNTRIES_WHITELIST_GT)
    inter = new_raw_int_domains_list(countries_lists)
    unfiltered_gt = new_raw_cc_domains_list(countries_lists, countries_lists_filter)
    unfiltered_gt['int'] = inter
    gt = {}
    for k in unfiltered_gt:
        if k == 'int':
            for locale in INT_LOCALES:
                filtered_results = parallel_filter(unfiltered_gt[k], locale, locale, workers=workers, chunk_size=chunk_size)
                filtered_domains = process_results(filtered_results, locale.split("-")[1].lower(), threshold, max_len, international="int_")
                gt[f"{k}_{locale}"] = filtered_domains
        else:
            locale = REGION_TO_BCP47.get(k.lower())
            results = parallel_filter(unfiltered_gt[k], locale, "en-US", workers=workers, chunk_size=chunk_size)
            filtered_domains = process_results(results, k, threshold, max_len)
            gt[k] = filtered_domains
    return gt

if __name__ == "__main__":
    _ = collect_raw_data(50000, 100000, 0.9, 7, 5)
