from langchain_community.tools.playwright.base import BaseBrowserTool
from langchain_community.tools.playwright.extract_text import ExtractTextToolInput
from pydantic import BaseModel, model_validator
from langchain_community.tools.playwright.utils import get_current_page
import langchain_community.tools.playwright.navigate
import langchain_community.agent_toolkits.playwright.toolkit
from typing import Any, Optional, Type
from langchain_core.callbacks import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)

######################################## LangChain Overrides #############################################

async def patched_aget_current_page(browser):
    if not browser.contexts:
        context = await browser.new_context(ignore_https_errors=True)
        return await context.new_page()
    context = browser.contexts[0]
    if not context.pages:
        return await context.new_page()
    return context.pages[-1]

class PatchedExtractTextTool(BaseBrowserTool):
    """Tool for extracting all the text on the current webpage."""

    name: str = "extract_text"
    description: str = "Extract all the text on the current webpage"
    args_schema: Type[BaseModel] = ExtractTextToolInput

    @model_validator(mode="before")
    @classmethod
    def check_acheck_bs_importrgs(cls, values: dict) -> Any:
        """Check that the arguments are valid."""
        try:
            from bs4 import BeautifulSoup  # noqa: F401
        except ImportError:
            raise ImportError(
                "The 'beautifulsoup4' package is required to use this tool."
                " Please install it with 'pip install beautifulsoup4'."
            )
        return values

    def _run(self, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        """Use the tool."""
        # Use Beautiful Soup since it's faster than looping through the elements
        from bs4 import BeautifulSoup

        if self.sync_browser is None:
            raise ValueError(f"Synchronous browser not provided to {self.name}")

        page = get_current_page(self.sync_browser)
        html_content = page.content()

        # Parse the HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, "lxml")
        k = 2000
        result = " ".join(text for text in soup.stripped_strings)
        if len(result) >= (2 * k):
            result = result[:k] + result[-k:]

        return result

    async def _arun(
        self, run_manager: Optional[AsyncCallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        if self.async_browser is None:
            raise ValueError(f"Asynchronous browser not provided to {self.name}")
        # Use Beautiful Soup since it's faster than looping through the elements
        from bs4 import BeautifulSoup

        page = await patched_aget_current_page(self.async_browser)
        html_content = await page.content()

        # Parse the HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, "lxml")
        k = 2000
        result = " ".join(text for text in soup.stripped_strings)
        if len(result) >= (2 * k):
            result = result[:k] + result[-k:]

        return result

langchain_community.tools.playwright.navigate.aget_current_page = patched_aget_current_page
langchain_community.agent_toolkits.playwright.toolkit.ExtractTextTool = PatchedExtractTextTool

#########################################################################################################



from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain.agents.middleware import ToolCallLimitMiddleware
import os
import asyncio
from playwright.async_api import async_playwright
import csv
import json
import logging
from datetime import datetime

GROUNDTRUTH_FILE = "../datasets/groundtruth/governmental.csv"
PROMPT_FILE = "../prompts/prompt_government.txt"
TEMPERATURE = 0
DISABLE_TOOLS = False
TOOL_CALL_LIMIT = 2
TOOL_ACTIONS_LIMIT = True
TOOL_ACTIONS = ["navigate_browser", "extract_text"]
OLLAMA_MODELS = ['gpt-oss:20b',
                 #'llama3.3:70b', 
                 #'mistral-small3.2:24b', 
                 #'phi4-mini:3.8b', 
                 #'qwen3:32b'
                 ]
LOG_FOLDERS = ['llm_logs/governmental/gpt_20/logs_ollama_gpt_20_gov_website_access',
               #'llm_logs/governmental/llama3-3_70/logs_ollama_llama3-3_70_gov_website_access',
               #'llm_logs/governmental/mistral-small3-2_24/logs_ollama_mistral-small3-2_24_gov_website_access',
               #'llm_logs/governmental/phi4-mini_3-8/logs_ollama_phi4-mini_3-8_gov_website_access',
               #'llm_logs/governmental/qwen3_32/logs_ollama_qwen3_32_gov_website_access'
               ]

for folder in LOG_FOLDERS:
    os.makedirs(folder, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

async def process_chunk(llm, urls, prompt_file, log_folder, semaphore, thread):
    async with semaphore:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=browser)
        if TOOL_ACTIONS_LIMIT:
            tools = [t for t in toolkit.get_tools() if t.name in TOOL_ACTIONS]
        else:
            tools = toolkit.get_tools()

        if DISABLE_TOOLS:
            agent = create_agent(
                model=llm
            )
        else:
            agent = create_agent(
                tools=tools,
                model=llm,
                middleware=[limiter]
            )

        with open(prompt_file, "r") as f:
            query_template = f.read()
        query = query_template.format(urls=urls)

        try:
            with open(f"{log_folder}/log_thread_{thread}_time.txt", "w") as f:
                f.write("Start time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f") + "\n")
            results = await agent.ainvoke(
                {"messages": [{"role": "user", "content": query}]}
            )
            with open(f"{log_folder}/log_thread_{thread}_time.txt", "a") as f:
                f.write("End time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f") + "\n")

            ans = ''
            for item in results['messages'][-1]:
                if item[0] == 'content':
                    ans = item[1]

            await browser.close()
            await playwright.stop()

            with open(f"{log_folder}/log_thread_{thread}.txt", "w") as log_out:
                log_out.write(str(results))
                log_out.write("\n\n\n")
                log_out.write(f"[ANSWER] {ans}")

            return ans
        except Exception as e:
            await browser.close()
            await playwright.stop()
            with open(f"{log_folder}/log_thread_{thread}_time.txt", "a") as f:
                f.write("End time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f") + "\n")
            with open(f"{log_folder}/log_thread_{thread}.txt", "w") as log_out:
                log_out.write(f"The LLM failed to categorize the following urls: {urls}\n")
                log_out.write(f"\n{e}")
            return ''

async def main_parallel(llm, urls, prompt_file, log_folder, chunk_size=20, max_workers=10):
    chunks = [urls[i:i+chunk_size] for i in range(0, len(urls), chunk_size)]
    semaphore = asyncio.Semaphore(max_workers)
    tasks = [process_chunk(llm, chunk, prompt_file, log_folder, semaphore, i) for i, chunk in enumerate(chunks)]
    ans = await asyncio.gather(*tasks)
    return ans

def load_dataset(file):
    dataset = []
    with open(file, newline='', encoding='utf-8') as f:
        if file.endswith(".csv"):
            reader = csv.DictReader(f)
            for row in reader:
                if "url" in row:
                    url = row["url"].strip()
                    dataset.append(url)
                if "domain" in row:
                    url = row["domain"].strip()
                    dataset.append(url)
        if file.endswith(".json"):
            data = json.load(f)
            dataset = list(data.keys())
    return dataset

def save_answers(file, answers, log_folder):
    error = []
    with open(file, "w") as out:
        out.write("url,gov\n")
        for dct in answers:
            try:
                dct.replace("'", '"')
                parsed_dct = json.loads(dct)
                for url in parsed_dct:
                    out.write(f"{url},{parsed_dct[url]['gov_site']}\n")
            except:
                if dct:
                    logger.info(f"Could not parse the following dictionary:", dct)
                    error.append(dct)
    with open(f"{log_folder}/log_save_answers_errors.txt", 'w') as log_out:
        log_out.write(str(error))
        log_out.write(f"\n{len(error)}")

if __name__ == "__main__":
    for i, model in enumerate(OLLAMA_MODELS):
        llm = ChatOllama(
            base_url="http://localhost:11434",
            model=model,
            temperature=TEMPERATURE,
            timeout=1800,
            max_retries=2,
            format="json"
        )
        limiter = ToolCallLimitMiddleware(
            run_limit=TOOL_CALL_LIMIT,
            exit_behavior="continue"
        )
        urls = load_dataset(GROUNDTRUTH_FILE)
        print("Number of URLs to process:", len(urls))
        with open(f"{LOG_FOLDERS[i]}/time_log.txt", "a") as f:
            f.write("Start time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        answers = asyncio.run(main_parallel(llm, urls, PROMPT_FILE, LOG_FOLDERS[i], chunk_size=1, max_workers=1))
        with open(f"{LOG_FOLDERS[i]}/time_log.txt", "a") as f:
            f.write("End time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        logger.info("DONE!")
