import os
import glob
import json
import re
import argparse
from urllib.parse import urlparse
from nltk.stem.snowball import SnowballStemmer
from collections import Counter

STEM = SnowballStemmer("english")
INCLUDE_CATEGORIES_EXTRACTED_FROM_DESCRIPTION = False

CATEGORIES = [
    "Arts", "Business", "Computers", "Games", "Health", "Home", "News",
    "Recreation", "Reference", "Science", "Shopping", "Society", "Sports"
]
CATEGORIES_LOWER = {c.lower(): c for c in CATEGORIES}

DESC_KEYWORDS = {
    "Arts": {"art", "music", "radio", "artist", "gallery", "theatre", "theater", "film", "cinema", "movie", "photography", "literature", "museum"},
    "Business": {"company", "business", "finance", "organization", "distribution"},
    "Computers": {"computer", "software", "server", "internet", "network", "voip", "hardware"},
    "Games": {"game", "multiplayer", "gaming", "rpg", "videogame", "arcade"},
    "Health": {"health", "medical", "clinical", "medicine", "disease", "patient", "hospital", "clinic", "physician"},
    "Home": {"home", "family", "recipes", "garden", "parenting", "baby", "cooking"},
    "News": {"news", "breaking", "journalist", "newspaper", "coverage", "article", "magazine"},
    "Recreation": {"recreation", "travel", "tourism", "hobby", "outdoor", "camping"},
    "Reference": {"maps", "library", "encyclopedia", "dictionary", "reference"},
    "Science": {"science", "university", "institute", "biology", "laboratory"},
    "Shopping": {"shop", "store", "buy", "cart", "retail", "ecommerce", "e-commerce", "sell", "items", "product"},
    "Society": {"society", "government", "ngo", "rights", "policy", "civic", "association"},
    "Sports": {"sport", "team", "league", "match", "tournament", "athlete"},
}

WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

def tokenize(text):
    if not text:
        return set()
    toks = [m.group(0).lower() for m in WORD_RE.finditer(text)]
    result = set(STEM.stem(t) for t in toks if len(t) >= 2)
    return result


def normalize_host(netloc):
    return netloc.split("@")[-1].split(":")[0].lower().strip(".")


def normalize_path(p):
    return p if p else "/"


def extract_candidates_from_entry(obj):
    candidates = set()
    categories_tokens = {x: cat for lower, cat in CATEGORIES_LOWER.items() for x in tokenize(lower)}

    raw_path = obj.get("raw_category_path", "") or ""
    prefix = raw_path.split("/", 1)[0].strip()
    if prefix:
        p = prefix.lower()
        if p in categories_tokens:
            candidates.add(categories_tokens[p])

    tree = obj.get("category_tree", [])
    if isinstance(tree, list):
        for node in tree:
            if not isinstance(node, str):
                continue
            toks = tokenize(node)
            for t in toks:
                if t in categories_tokens:
                    candidates.add(categories_tokens[t])

    return candidates


def confirm_candidates_for_entry(dom, candidates, description):
    desc_tokens = tokenize(description if isinstance(description, str) else "")
    confirmed = []
    for cat in sorted(candidates):
        kws = DESC_KEYWORDS.get(cat, set())
        kw_set = set(x for kw in kws for x in tokenize(kw))
        if desc_tokens & kw_set:
            confirmed.append(cat)
    return confirmed


def additional_candidates_for_entry(description):
    desc_tokens = tokenize(description if isinstance(description, str) else "")
    confirmed = []
    for cat in DESC_KEYWORDS:
        kws = DESC_KEYWORDS[cat]
        kw_set = set(x for kw in kws for x in tokenize(kw))
        if len(desc_tokens & kw_set) >= 1:
            confirmed.append(cat)
    return confirmed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default="raw_curlie_categories_intersect_tranco_top_100k")
    ap.add_argument("--pattern", default="*.jsonl", help="Glob pattern (default: *.jsonl)")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.folder, args.pattern)))
    if not files:
        print("No file found.")
        return

    result = {}
    dropped_no_confirm = 0
    dropped_too_many_candidates = 0
    dropped_inconsistent = 0
    dropped_no_www_root = 0
    processed = 0
    kept = 0

    for path in files:
        processed += 1
        domain = os.path.basename(path)
        if domain.lower().endswith(".jsonl"):
            domain = domain[:-6]

        result[domain.lower()] = ""
        www_host = "www." + domain.lower()

        lines = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    lines.append(obj)
        except OSError:
            continue

        baseline_candidates = set()
        baseline_entries = []
        considered_urls = []
        descriptions = []
        for obj in lines:
            site_url = obj.get("site_url", "")
            if not isinstance(site_url, str) or not site_url:
                continue
            u = urlparse(site_url)
            host = normalize_host(u.netloc)
            p = normalize_path(u.path)

            host_parts = set(host.lower().split("."))
            domain_parts = set(domain.lower().split("."))
            if not (len(domain_parts) == len(host_parts.intersection(domain_parts))):
                continue

            if ((host == www_host) or (host == domain.lower())) and p == "/":
                baseline_entries.append(obj)
                considered_urls.append(site_url)
                descriptions.append(obj.get("description", ""))
                baseline_candidates |= extract_candidates_from_entry(obj)

        if not baseline_entries or not baseline_candidates:
            if not baseline_entries:
                result[domain.lower()] = {
                    "res": "No baseline URL found",
                    "baseline_urls": considered_urls,
                    "candidates": list(baseline_candidates)
                }
            else:
                if not baseline_candidates:
                    result[domain.lower()] = {
                        "res": "No baseline candidates found",
                        "baseline_urls": considered_urls,
                        "candidates": list(baseline_candidates)
                    }
            dropped_no_www_root += 1
            continue

        inconsistent = False
        inconsistent_cats = []
        consistent_cats = []
        other_urls = []
        other_descriptions = []
        for obj in lines:
            site_url = obj.get("site_url", "")
            if not isinstance(site_url, str) or not site_url:
                continue
            u = urlparse(site_url)
            host = normalize_host(u.netloc)
            p = normalize_path(u.path)

            host_parts = set(host.lower().split("."))
            domain_parts = set(domain.lower().split("."))
            if not (len(domain_parts) == len(host_parts.intersection(domain_parts))):
                continue

            is_baseline_entry = (((host == www_host) or (host == domain.lower())) and p == "/")
            if is_baseline_entry:
                continue

            other_urls.append(site_url)
            other_descriptions.append(obj.get("description", ""))
            other_candidates = extract_candidates_from_entry(obj)
            if not other_candidates:
                continue

            if baseline_candidates.isdisjoint(other_candidates):
                inconsistent_cats.append(list(other_candidates))
                inconsistent = True
            else:
                consistent_cats.append(list(other_candidates))

        if inconsistent:
            dropped_inconsistent += 1
            result[domain.lower()] = {
                "res": "Found inconsistent categories",
                "baseline_urls": considered_urls,
                "related_urls": other_urls,
                "candidates": list(baseline_candidates),
                "conflicting candidates from related urls": inconsistent_cats,
                "non-conflicting candidates from related urls": consistent_cats,
                "descriptions": descriptions,
                "related urls descriptions": other_descriptions
            }
            continue

        if len(baseline_candidates) > 3:
            dropped_too_many_candidates += 1
            result[domain.lower()] = {
                "res": "Found too many categories",
                "baseline_urls": considered_urls,
                "related_urls": other_urls,
                "candidates": list(baseline_candidates),
                "conflicting candidates from related urls": inconsistent_cats,
                "non-conflicting candidates from related urls": consistent_cats,
                "descriptions": descriptions,
                "related urls descriptions": other_descriptions
            }
            continue

        confirmed_for_domain = set()
        
        for obj in baseline_entries:
            entry_candidates = baseline_candidates
            confirmed = confirm_candidates_for_entry(domain, entry_candidates, obj.get("description", ""))
            if INCLUDE_CATEGORIES_EXTRACTED_FROM_DESCRIPTION:
                additional = additional_candidates_for_entry(obj.get("description", ""))
                confirmed = list(set(confirmed).union(set(additional)))
            confirmed_for_domain.update(confirmed)

        if not confirmed_for_domain:
            dropped_no_confirm += 1
            result[domain.lower()] = {
                "res": "No matching between candidate categories and site description found",
                "baseline_urls": considered_urls,
                "related_urls": other_urls,
                "candidates": list(baseline_candidates),
                "conflicting candidates from related urls": inconsistent_cats,
                "non-conflicting candidates from related urls": consistent_cats,
                "descriptions": descriptions,
                "related urls descriptions": other_descriptions
            }
            continue

        kept += 1
        result[domain.lower()] = {
            "res": "Kept Domains (>=1 confirmed categories)",
            "baseline_urls": considered_urls,
            "related_urls": other_urls,
            "candidates": list(baseline_candidates),
            "conflicting candidates from related urls": inconsistent_cats,
            "non-conflicting candidates from related urls": consistent_cats,
            "descriptions": descriptions,
            "related urls descriptions": other_descriptions,
            "confirmed": list(confirmed_for_domain)
        }

    string_counter = Counter()

    for value in result.values():
        if isinstance(value["res"], str):
            string_counter[value["res"]] += 1

    print("\n--- Summary ---")
    print("Processed Files:", processed)
    for key, count in string_counter.items():
        print(f"{key}: {count}")

    if INCLUDE_CATEGORIES_EXTRACTED_FROM_DESCRIPTION:
        with open("new_unfiltered_extended_groundtruth_from_scrape.json", "w") as f:
            json.dump(result, f, indent=4)
    else:
        with open("new_unfiltered_groundtruth_from_scrape.json", "w") as f:
            json.dump(result, f, indent=4)

if __name__ == "__main__":
    main()
