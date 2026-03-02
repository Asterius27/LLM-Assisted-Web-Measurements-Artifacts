import os
import json
from collect_raw_country_data import is_cc_tld, normalize_uri, save_gt

def save_logs(file, dct):
    with open(file, 'w') as f:
        json.dump(dct, f, indent=4)

def load_filtered_int_urls(folder, threshold):
    result = []
    result_log = {}
    for file in os.listdir(folder):
        if file.startswith("int_"):
            with open(f"{folder}/{file}", "r") as f:
                data = json.load(f)
            for domain in data:
                domain_after_redirect = normalize_uri(data[domain]["final_url"] or "")
                if domain_after_redirect and (not is_cc_tld(domain_after_redirect)):
                    expected_lang = data[domain]["locale"].split("-")[0]
                    fasttext = data[domain]["fastText_result"] or []
                    cld3 = data[domain]["CLD3_result"] or []
                    result_log.setdefault(domain, {})
                    result_log[domain].setdefault("url", data[domain]["url"])
                    result_log[domain].setdefault("final_urls", []).append(data[domain]["final_url"])
                    result_log[domain][expected_lang] = {}
                    result_log[domain][expected_lang]["fasttext_predicted_langs"] = [key for key, v in fasttext if v >= threshold]
                    result_log[domain][expected_lang]["cld3_predicted_langs"] = [key for key, v in cld3 if v.get("mean_prob", 0) >= threshold]
    for domain in result_log:
        matching_langs = []
        not_matching_langs = []
        for expected_lang in result_log[domain]:
            if not (expected_lang == "fr"):
                if not expected_lang == "url" and not expected_lang == "final_urls":
                    found = False
                    for key in result_log[domain][expected_lang]["fasttext_predicted_langs"]:
                        if expected_lang == key and not found:
                            matching_langs.append(expected_lang)
                            found = True
                    for key in result_log[domain][expected_lang]["cld3_predicted_langs"]:
                        if expected_lang == key and not found:
                            matching_langs.append(expected_lang)
                            found = True
                    if not found:
                        found1 = False
                        for key in result_log[domain][expected_lang]["fasttext_predicted_langs"]:
                            if "en" == key and not found1:
                                not_matching_langs.append("en")
                                found1 = True
                        for key in result_log[domain][expected_lang]["cld3_predicted_langs"]:
                            if "en" == key and not found1:
                                not_matching_langs.append("en")
                                found1 = True
        if len(matching_langs) >= 3:
            result.append((result_log[domain]["url"], result_log[domain]["final_urls"]))
            result_log[domain]["keep"] = True
        else:
            result_log[domain]["keep"] = False
    print(f"Number of URLs for int: {len(result)}")
    return result, result_log

def load_country_urls(folder, threshold):
    result = {}
    result_log = {}
    for file in os.listdir(folder):
        if not file.startswith("int_"):
            country = file.split("_")[0]
            result[country] = []
            result_log[country] = {}
            with open(f"{folder}/{file}", "r") as f:
                file_dct = json.load(f)
            for domain in file_dct:
                domain_after_redirect = normalize_uri(file_dct[domain]["final_url"] or "")
                if domain_after_redirect:
                    result_log[country][domain] = {}
                    fasttext = file_dct[domain]["fastText_result"] or []
                    cld3 = file_dct[domain]["CLD3_result"] or []
                    expected_lang = file_dct[domain]["locale"].split("-")[0]
                    result_log[country][domain]["expected_lang"] = expected_lang
                    if not is_cc_tld(domain_after_redirect):
                        result_log[country][domain]["int_tld"] = True
                        result_log[country][domain]["ip_continent"] = file_dct[domain]["ip_continent"]
                        result_log[country][domain]["locale_continent"] = file_dct[domain]["locale_continent"]
                        result_log[country][domain]["fasttext_predicted_langs"] = [key for key, v in fasttext if v >= threshold]
                        result_log[country][domain]["cld3_predicted_langs"] = [key for key, v in cld3 if v.get("mean_prob", 0) >= threshold]
                        if any(expected_lang == key and v >= threshold for key, v in fasttext) and file_dct[domain]["ip_continent"] == file_dct[domain]["locale_continent"]:
                            result[country].append((file_dct[domain]["url"], file_dct[domain]["final_url"]))
                            result_log[country][domain]["keep"] = True
                        elif any(expected_lang == key and v.get("mean_prob", 0) >= threshold for key, v in cld3) and file_dct[domain]["ip_continent"] == file_dct[domain]["locale_continent"]:
                            result[country].append((file_dct[domain]["url"], file_dct[domain]["final_url"]))
                            result_log[country][domain]["keep"] = True
                        else:
                            result_log[country][domain]["keep"] = False
                    else:
                        result_log[country][domain]["int_tld"] = False
                        if domain_after_redirect.split(".")[-1].lower() == country and file_dct[domain]["final_url"]:
                            result_log[country][domain]["keep"] = True
                            result[country].append((file_dct[domain]["url"], file_dct[domain]["final_url"]))
                        else:
                            result_log[country][domain]["keep"] = False
            print(f"Number of URLs for {country}: {len(result[country])}")
    return result, result_log

if __name__ == "__main__":
    int_urls_list, int_log_dct = load_filtered_int_urls("new_tranco_lists_filtered", 0.9)
    gt_dct, gt_log_dct = load_country_urls("new_tranco_lists_filtered", 0.9)
    gt_dct["int"] = int_urls_list
    save_logs("filtered_int_domains_logs.json", int_log_dct)
    save_logs("filtered_country_domains_logs.json", gt_log_dct)
    save_gt("new_groundtruth.csv", {k: [x for x, _ in v] for k, v in gt_dct.items()})
