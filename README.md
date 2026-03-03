# LLM-Assisted-Web-Measurements-Artifacts

**Note: Due to an ongoing issue affecting Anonymous GitHub access, files in some repositories may not display correctly in the browser. As a workaround, you can download the repository as a ZIP archive and inspect the files locally. The files are present; however, they may not render correctly online.**

This repository contains the prompts, code, generated datasets, and LLM results presented in our paper ‘LLM-Assisted Web Measurements’.

## Dependencies

To run the scripts, at least Python 3.10.0 is required. You can find all the necessary python packages along with their versions in the `requirements.txt` file.

1. [Linux Debian based distros] Install gcld3 dependencies:
    ```
    sudo apt install protobuf-compiler python3.12-dev build-essential
    ```
    For other operating systems, please refer to the online repository: https://github.com/google/cld3.

2. Install all Python dependencies by running `pip install -r requirements.txt` from the root of the project.
3. Install Playwright dependencies by running `playwright install`.
4. Install fastText (https://fasttext.cc/docs/en/support.html):
    ```
    git clone https://github.com/facebookresearch/fastText.git
    cd fastText
    make
    ```
    This will produce the main binary `fasttext`. Add it to your `PATH` system variable so that it is available from any working directory.
    
    Next download the language identification model from https://fasttext.cc/docs/en/language-identification.html (it's the file called `lid.176.bin`) and place it inside the `/scripts/groundtruth_dataset_generation/countries/` folder.
5. Download the "I Still Don't Care About Cookies" extension by cloning the repository (https://github.com/OhMyGuus/I-Still-Dont-Care-About-Cookies) and copy the contents of the `src` folder (so the source code of the extension) into a folder named `I-Still-Dont-Care-About-Cookies-1.1.9` placed inside the `/scripts/groundtruth_dataset_generation/countries/` folder. Finally, rename the file `manifest_v3.json` to `manifest.json`.
6. [OPTIONAL] Generate a free ipinfo API token here: https://ipinfo.io/dashboard/token after creating a free account and assign it to the `IPINFO_TOKEN` variable inside the `/scripts/groundtruth_dataset_generation/countries/collect_raw_country_data.py` script.
7. Install Ollama: https://ollama.com/download. For Linux users:
    ```
    curl -fsSL https://ollama.com/install.sh | sh
    ```
    Download the models you would like to use using the `ollama pull` command, for example:
    ```
    ollama pull gpt-oss:20b
    ```
    If you install ollama in a different machine or you change its default network port, then you also have to update the URL at line 237 of the `/scripts/query_llm.py` script, according to your setup.
8. Download the datasets from the HomePage2Vec repository (https://figshare.com/articles/dataset/Curlie_Dataset_-_Language-agnostic_Website_Embedding_and_Classification/19406693), extract the `curlie_filtered.csv.gz` file and place the `test_uid.txt` and the extracted `curlie_filtered.csv` files inside the `/scripts/groundtruth_dataset_generation/categories/` folder.

## Groundtruth Datasets

The groundtruth datasets presented in Section 4 of our paper can be found inside the `/datasets/groundtruth/` folder. The datasets have been generated using the following scripts:

- **Countries**:
    1. Collect raw language and location data for each website in the initial datasets (one for each country) using the `/scripts/groundtruth_dataset_generation/countries/collect_raw_country_data.py` script. The first parameter of the `collect_raw_data` function determines the length of the subset of the country specific Tranco lists (starting from the top) which will be used as initial datasets. The second parameter, instead, determines the length of the subset of the country specific Tranco lists to consider when checking whether each website only appears in a specific country list or not.
    2. Parse the collected raw data and generate the final dataset using the `/scripts/groundtruth_dataset_generation/countries/build_groundtruth.py` script.

- **Categories**:
    1. Collect raw data from curlie by using the `/scripts/groundtruth_dataset_generation/categories/curlie_scraper.py` script. The third parameter of the `scrape_curlie` function sets the size of the dataset, so the total number of websites to be scraped from Curlie. These websites are randomly sampled from HomePage2Vec's test set.
    2. Parse the collected raw data by using the `/scripts/groundtruth_dataset_generation/categories/raw_curlie_categories_parser.py` script. This will assign to each website its new label(s).
    3. Filter the generated dataset as to only keep those URLs that are reachable and have at least one category assigned to them by using the `/scripts/groundtruth_dataset_generation/categories/build_groundtruth.py` script. This will generate the final dataset.

For the governmental dataset we downloaded the datasets from https://govcookies.github.io/ and https://github.com/uw-ictd/GovHTTPS-Data. We first computed the intersection of these two datasets. We then expanded this set by including additional websites from the first dataset (https://govcookies.github.io/) that were manually labeled as governmental, were not part of the intersection, and did not use a governmental top-level domain (TLD). Finally, we further extended the dataset by randomly sampling websites from the Tranco list that did not use a governmental TLD.

## LLM Prompts, Results, and Scripts

All of the prompts which were used can be found in the `\prompts\` folder.<br>
The `llms_results` folder contains the results for all models in both the "only urls" and "live website access" configurations over all of the groundtruth datasets.<br>
The models were queried using the `\scripts\query_llm.py` script. By changing the value of the `DISABLE_TOOLS` variable, one can switch between the two configurations: when `DISABLE_TOOLS` is set to `True` the LLM will only have access to the URL, when `DISABLE_TOOLS` is set to `False` the model has live access to the website through Playwright. The `\scripts\query_llm.py` script also save time logs, which we used to perform our scalability analysis (Section 6.3).

## Web Measurement

### Datasets

- **Governmental**: we used the two datasets from the literature, https://govcookies.github.io/ and https://github.com/uw-ictd/GovHTTPS-Data, and we generated a dataset by filtering the Tranco top 50k and bottom 50k websites keeping only those websites that gpt-oss categorized as governmental, using the `\scripts\query_llm.py` script with the `\prompts\prompt_government.txt` prompt.<br>
The baseline dataset, instead, was built by:
    1. Executing the `/scripts/web_measurement_dataset_generation/governmental/build_raw_tld_filtered_dataset.py` script to filter Tranco in order to only keep the domains with a governmental TLD.
    2. Executing the `/scripts/web_measurement_dataset_generation/governmental/dataset_reachability_filter.py` script to filter out unreachable URLs and generate the final baseline.
The final dataset and baseline can be found at `/datasets/web_measurements/tranco_top_and_bot_50k_governmental_gpt_oss_filtered.csv` and `/datasets/web_measurements/tranco_top_and_bot_50k_governmental_tld_filtered.csv`, respectively.

- **Pornographic**: we reconstructed the dataset from Vallina et al. (https://doi.org/10.1145/3355369.3355583), using the following scripts:
    1. `/scripts/web_measurement_dataset_generation/pornographic/build_raw_vallina_dataset.py`, which scrapes three aggregator websites to collect pornographic domains and identifies additional pornographic websites from the top and bottom 50k entries of the Tranco list using a keyword-based filtering approach, following Vallina et al.'s methodology as closely as possible.
    2. `/scripts/web_measurement_dataset_generation/pornographic/dataset_reachability_filter.py`, which filters out unreachable URLs and generates the final dataset.

    We then filtered the reconstructed dataset to create the baseline by only keeping the websites that appear in the Tranco top 50k or bottom 50k. The reconstructed dataset, along with the baseline, can be found at `/datasets/web_measurements/vallina_reconstructed_dataset.csv` and `/datasets/web_measurements/vallina_reconstructed_dataset_baseline.csv`, respectively.

    Finally, we built the gpt-oss filtered dataset by keeping the domains that gpt-oss categorized as pornographic in the Tranco top and bottom 50k. This was done by using the `\scripts\query_llm.py` script with the `\prompts\prompt_categories_porno.txt` prompt. The dataset can be found at `/datasets/web_measurements/tranco_top_and_bot_50k_pornographic_gpt_oss_filtered.csv`.

### Measurement

The tool (and source code) used for the experiments carried out in section 6 is available at: https://bitbucket.org/srdjanmatic/websci_govcookies/src/master/. For the study on governmental websites, we executed the tool over these datasets: https://govcookies.github.io/, https://github.com/uw-ictd/GovHTTPS-Data, and our gpt-oss filtered dataset (`/datasets/web_measurements/tranco_top_and_bot_50k_governmental_gpt_oss_filtered.csv`). For the study on pornographic websites, instead, we executed the tool over these datasets: the reconstructed dataset (`/datasets/web_measurements/vallina_reconstructed_dataset.csv`), and our gpt-oss filtered dataset (`/datasets/web_measurements/tranco_top_and_bot_50k_pornographic_gpt_oss_filtered.csv`). 

Using the tool’s output, we computed the percentage of websites that set third-party tracking cookies. Since the tool stores all cookies associated with each visited URL, we identified third-party trackers by checking whether the cookie domains matched entries in the Disconnect list. Similarly, since the code also saves the source code of each visited URL, we extracted all `<script>` tags from the body of the HTML documents and checked whether they appeared in the Disconnect list to identify first-party trackers. Finally, we quantified and compared the number, diversity, and popularity of the trackers, both those detected via third-party cookies and those identified in scripts, across the different datasets and their respective subsets.