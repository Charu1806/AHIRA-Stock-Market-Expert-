import os
import sys
from typing import Literal

try:
    from pydantic_settings import BaseSettings
    from pydantic import Field

    class Settings(BaseSettings):
        GROQ_API_KEY: str = Field(default="", env="GROQ_API_KEY")
        GEMINI_API_KEY: str = Field(default="", env="GEMINI_API_KEY")
        TELEGRAM_BOT_TOKEN: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
        TELEGRAM_CHAT_ID: str = Field(default="", env="TELEGRAM_CHAT_ID")

        NEWS_SOURCES: dict = {
            "us": {
                "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
                "cnbc_markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
                "bloomberg_technology": "https://feeds.bloomberg.com/technology/news.rss",
                "wsj": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
                "ft": "https://www.ft.com/rss/home/us",
            },
            "india": {
                "economic_times_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                "moneycontrol": "https://www.moneycontrol.com/rss/MCtopnews.xml",
                "mint": "https://www.livemint.com/rss/markets",
            },
        }

        PERIODS: dict = {"today": 1, "week": 7, "month": 30}

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"

        def get_active_sources(self, filter: Literal["all", "us", "india", "global"] = "all") -> dict:
            if filter == "us":
                return self.NEWS_SOURCES["us"]
            if filter == "india":
                return self.NEWS_SOURCES["india"]
            # "all" and "global" return everything
            combined = {}
            for region_sources in self.NEWS_SOURCES.values():
                combined.update(region_sources)
            return combined

except ImportError:
    # Fallback: plain dotenv-based Settings
    from dotenv import load_dotenv

    load_dotenv()

    class Settings:  # type: ignore[no-redef]
        def __init__(self):
            self.GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
            self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
            self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
            self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
            self.NEWS_SOURCES = {
                "us": {
                    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
                    "cnbc_markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
                    "bloomberg_technology": "https://feeds.bloomberg.com/technology/news.rss",
                    "wsj": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
                    "ft": "https://www.ft.com/rss/home/us",
                },
                "india": {
                    "economic_times_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
                    "moneycontrol": "https://www.moneycontrol.com/rss/MCtopnews.xml",
                    "mint": "https://www.livemint.com/rss/markets",
                },
            }
            self.PERIODS = {"today": 1, "week": 7, "month": 30}

        def get_active_sources(self, filter="all"):
            if filter == "us":
                return self.NEWS_SOURCES["us"]
            if filter == "india":
                return self.NEWS_SOURCES["india"]
            combined = {}
            for region_sources in self.NEWS_SOURCES.values():
                combined.update(region_sources)
            return combined


settings = Settings()

_REQUIRED_VARS = {
    "GROQ_API_KEY": settings.GROQ_API_KEY,
    "GEMINI_API_KEY": settings.GEMINI_API_KEY,
    "TELEGRAM_BOT_TOKEN": settings.TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": settings.TELEGRAM_CHAT_ID,
}

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _print_banner():
    width = 52
    print(f"\n{CYAN}{BOLD}{'=' * width}{RESET}")
    print(f"{CYAN}{BOLD}{'  ARIA STOCK AGENT — Config Loader':^{width}}{RESET}")
    print(f"{CYAN}{BOLD}{'=' * width}{RESET}\n")

    loaded, missing = [], []
    for var, val in _REQUIRED_VARS.items():
        if val and not val.endswith("..."):
            loaded.append(var)
        else:
            missing.append(var)

    if loaded:
        print(f"  {GREEN}{BOLD}Loaded:{RESET}")
        for v in loaded:
            print(f"    {GREEN}✔  {v}{RESET}")

    if missing:
        print(f"\n  {RED}{BOLD}Missing / placeholder:{RESET}")
        for v in missing:
            print(f"    {RED}✘  {v}{RESET}")

    all_sources = settings.get_active_sources("all")
    print(f"\n  {CYAN}News sources configured: {len(all_sources)}{RESET}")
    print(f"  {CYAN}Periods: {list(settings.PERIODS.keys())}{RESET}")
    print(f"\n{CYAN}{'=' * width}{RESET}\n")

    if missing:
        print(f"  {RED}⚠  Copy .env.example → .env and fill in missing keys.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    _print_banner()
