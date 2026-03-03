import csv

GOV_DOMAINS = [
    # United States
    ".gov", ".mil",

    # United Kingdom
    ".gov.uk", ".mod.uk", ".nhs.uk",

    # France
    ".gouv.fr",

    # Mexico
    ".gob.mx",

    # Canada
    ".gc.ca", ".canada.ca",

    # Australia
    ".gov.au",

    # Germany
    ".bund.de",

    # Italy
    ".gov.it",

    # Spain
    ".gob.es",

    # India
    ".gov.in", "nic.in",

    # New Zealand
    ".govt.nz", ".parliament.nz",

    # Singapore
    ".gov.sg",

    # South Africa
    ".gov.za",

    # Brazil
    ".gov.br",

    # China
    ".gov.cn",

    # Japan
    ".go.jp",

    # Chile
    ".gob.cl",

    # Argentina
    ".gob.ar",

    # Colombia
    ".gov.co",

    # Peru
    ".gob.pe",

    # Philippines
    ".gov.ph",

    # Portugal
    ".gov.pt",

    # Belgium
    ".fgov.be", ".belgium.be",

    # Netherlands
    ".rijksoverheid.nl", ".overheid.nl",

    # Sweden
    ".gov.se",

    # Norway
    ".gov.no",

    # Denmark
    ".gov.dk",

    # Finland
    ".gov.fi",

    # Ireland
    ".gov.ie",

    # Austria
    ".gv.at",

    # Switzerland
    ".admin.ch",

    # Poland
    ".gov.pl",

    # Czech Republic
    ".gov.cz",

    # Hungary
    ".gov.hu",

    # Slovakia
    ".gov.sk",

    # Romania
    ".gov.ro",

    # Bulgaria
    ".government.bg",

    # Greece
    ".gov.gr",

    # Turkey
    ".gov.tr",

    # Russia
    ".gov.ru",

    # Ukraine
    ".gov.ua",

    # Dominican Republic
    ".gob.do",

    # Ecuador
    ".gob.ec",

    # Venezuela
    ".gob.ve",

    # Panama
    ".gob.pa",

    # Honduras
    ".gob.hn",

    # Guatemala
    ".gob.gt",

    # El Salvador
    ".gob.sv",

    # Nicaragua
    ".gob.ni",

    # Bolivia
    ".gob.bo",

    # Paraguay
    ".gob.py",

    # Uruguay
    ".gub.uy",

    # Costa Rica
    ".gob.cr",

    # Cuba
    ".gob.cu",

    # Jamaica
    ".gov.jm",

    # Kenya
    ".go.ke",

    # Tanzania
    ".go.tz",

    # Uganda
    ".go.ug",

    # Egypt
    ".gov.eg",

    # Saudi Arabia
    ".gov.sa",

    # United Arab Emirates
    ".gov.ae",

    # Pakistan
    ".gov.pk",

    # Bangladesh
    ".gov.bd",

    # Sri Lanka
    ".gov.lk",

    # Malaysia
    ".gov.my",

    # Indonesia
    ".go.id",

    # Thailand
    ".go.th",

    # Vietnam
    ".gov.vn",

    # South Korea
    ".go.kr",

    # North Korea
    ".gov.kp",

    # Singapore
    ".gov.sg",

    # Taiwan
    ".gov.tw",

    # Hong Kong
    ".gov.hk",

    # Macao
    ".gov.mo",

    # Australia territories
    ".act.gov.au", ".nsw.gov.au", ".nt.gov.au", ".qld.gov.au", ".sa.gov.au",
    ".tas.gov.au", ".vic.gov.au", ".wa.gov.au",
]

def is_gov_url(url: str) -> bool:
    url = url.lower().strip()
    for pattern in GOV_DOMAINS:
        if url.endswith(pattern) or ".gov." in url or ".gob." in url or ".gouv." in url or ".gc." in url or ".nic." in url or ".go." in url:
            return True
    return False

def tranco_subset(input_file, start, end, disable_filter):
    subset = []
    with open(input_file, newline='') as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)
        for i, row in enumerate(reader, start=1):
            if start <= i <= end:
                domain = row[1]
                if disable_filter:
                    subset.append(domain)
                else:
                    if is_gov_url(domain):
                        subset.append(domain)
            elif i > end:
                break
    return subset

def save_to_csv(file, lst):
    with open(file, "w") as out:
        out.write(f"domain\n")
        for domain in lst:
            out.write(f"{domain}\n")

if __name__ == "__main__":
    tranco_top_50k_filtered = tranco_subset("../../../tranco.csv", 0, 50000, False)
    tranco_bot_50k_filtered = tranco_subset("../../../tranco.csv", 950000, 1000000, False)
    save_to_csv("tranco_top_50k_only_gov_tld.csv", tranco_top_50k_filtered)
    save_to_csv("tranco_bot_50k_only_gov_tld.csv", tranco_bot_50k_filtered)
