import requests
from requests.adapters import HTTPAdapter

import argparse
import pathlib
from coverme.config import coverme_config
from loguru import logger
from coverme import definitions
from coverme import conguru
from coverme.version import __version__
import json
import shutil
from typing import Callable
import pandas as pd


template = {
    # The name of this configuration (for logging purposes)
    'name': str,
    # True to use cache instead of the servers
    "use_cache": bool,
}


class Cache:
    def __init__(self, src_root: pathlib.Path, dst_root: pathlib.Path, use_cache=True):
        self.src_root = src_root
        self.dst_root = dst_root
        self.hits = 0
        self.misses = 0
        self.use_cache = use_cache


    def load(self, name: str, miss_callback: Callable, params: tuple) -> object:
        """
        Attempt to load from cache. On a miss load direct. Updates statistics based upon hit/miss
        :param name: The name of the service. Used as part 1/2 of a hash for future cache loads
        :param miss_callback: The callback to call on a cache miss to load directly
        :param params: The parameters to the callback. Used as part 2/2 of a hash for future cache loads.
        :return: The loaded data
        """
        dst_folder = self.dst_root / name
        dst_folder.mkdir(parents=True, exist_ok=True)

        # Populate cache, either from the last run (cache hit) or from the servers (cache miss)
        src_folder = self.src_root / name

        src_filename = src_folder / f"{params}.json"
        dst_filename = dst_folder / f"{params}.json"
        if self.use_cache and src_filename.is_file():
            # Cache hit!
            shutil.copy(str(src_filename), str(dst_filename))
            self.hits += 1
        else:
            # Cache miss -- hit the server
            result = miss_callback(*params)
            with dst_filename.open('w') as f:
                json.dump(result, f)
            self.misses += 1

        # Always load from the now-populated cache to minimize testable code paths
        with dst_filename.open('r') as f:
            return json.load(f)


def main(argv):
    parser = argparse.ArgumentParser(description="Tool for covered calls")
    conguru.add_argument(parser, definitions.CONFIG_DIR / "config.yml")
    parser.add_argument("--cache", dest="use_cache", action="store_true",
                        help="Force to use locally cached data")
    args = parser.parse_args(argv)

    # Conguru -- parse config and setup logging
    conguru.init(args, argv, coverme_config, template, definitions.LOG_DIR, __version__)

    # Setup the session
    session = open_session(
        coverme_config['tradier']['key'].get()
    )
    base_url = coverme_config['tradier']['base_url'].get()
    market_api = TradierApi(session, base_url)

    use_cache = coverme_config['use_cache'].get()
    cache = Cache(src_root=conguru.LogFolder.latest_log_folder / "cache",
                  dst_root=conguru.LogFolder.folder / "cache",
                  use_cache=use_cache)

    # Load the symbols' quotes
    symbols = coverme_config['symbols'].get()
    quotes = {
        symbol: cache.load("quotes", market_api.quote, (symbol,))
        for symbol in symbols
    }

    # Load option expirations
    expirations = {
        symbol: cache.load("expiration", market_api.options_expirations, (symbol,))
        for symbol in symbols
    }

    # Load option chains
    option_chains = {
        symbol: {
            expiration: cache.load("optionchains", market_api.option_chain, (symbol, expiration))
            for expiration in expirations[symbol]['expirations']['date']
        }
        for symbol in symbols
    }

    logger.info(f"Cache: {cache.hits} hits, {cache.misses} misses")

    # Make a big ass table

    # But start with the quotes table
    last_prices = [quotes[symbol]['quotes']['quote']['last'] for symbol in symbols]
    df_quote = pd.DataFrame({
        'symbol': symbols,
        'last': last_prices
    })

    # Then the option chains table
    to_grab = ["underlying", "ask", "asksize", "bid", "bidsize", "last", "strike", "expiration_date"]
    table = {x: [] for x in to_grab}
    for option_chain in option_chains.values():
        for expiration_chain in option_chain.values():
            for contract in expiration_chain['options']['option']:
                # Only tracking calls
                if contract['option_type'] == "put":
                    continue
                for key in to_grab:
                    table[key].append(contract[key])
    df_options_chain = pd.DataFrame(table)

    foo = 1




def open_session(api_key: str) -> requests.Session:
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=1))
    session.headers.update({'Authorization': 'Bearer ' + api_key, 'Accept': 'application/json'})

    return session

class TradierApi:
    def __init__(self, session: requests.Session, base_url: str):
        """
        https://documentation.tradier.com/brokerage-api/overview/market-data
        """
        self.session = session
        self.base_url = base_url

    def quote(self, symbol: str):
        # URL for the API endpoint
        url = self.base_url + f"/v1/markets/quotes"
        params = {"symbols": symbol}
        return self._get(url, params)

    def options_expirations(self, symbol: str):
        # URL for the API endpoint
        url = self.base_url + f"/v1/markets/options/expirations"
        params = {"symbol": symbol}
        return self._get(url, params)

    def option_chain(self, symbol: str, expiration: str):
        url = self.base_url + f"/v1/markets/options/chains"
        params = {"symbol": symbol, "expiration": expiration}
        return self._get(url, params)

    def _get(self, url, params):
        # Make API call for GET request
        response = self.session.get(url, params=params)

        if response is not None and response.status_code == 200:
            return response.json()
        else:
            raise IOError(f"Bad response: {response.text}")
