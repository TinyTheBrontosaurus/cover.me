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


template = {
    # The name of this configuration (for logging purposes)
    'name': str,
    # True to use cache instead of the servers
    "use_cache": bool,
}

class LogLayout:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.cache = CacheLayout(root / "cache")


class CacheLayout:
    def __init__(self, root: pathlib.Path):
        self.root = root

    @property
    def quotes(self) -> pathlib.Path:
        return self.root / "quotes"


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

    # Load the symbols

    # Cache miss
    symbols = coverme_config['symbols'].get()
    dest_cache_layout = LogLayout(conguru.LogFolder.folder).cache
    dest_cache_layout.quotes.mkdir(parents=True, exist_ok=True)

    # Populate cache, either from the last run (cache hit) or from the servers (cache miss)
    use_cache = coverme_config['use_cache'].get()
    src_cache_layout = LogLayout(conguru.LogFolder.latest_log_folder).cache
    hits = 0
    misses = 0
    for symbol in symbols:
        src_filename = src_cache_layout.quotes / f"{symbol}.json"
        dst_filename = dest_cache_layout.quotes / f"{symbol}.json"
        if use_cache and src_filename.is_file():
            # Cache hit!
            shutil.copy(str(src_filename), str(dst_filename))
            hits += 1
        else:
            # Cache miss -- hit the server
            quote = market_api.quote(symbol)
            with dst_filename.open('w') as f:
                json.dump(quote, f)
            misses += 1
    logger.info(f"Cache: {hits} hits, {misses} misses")

    # Load from the now-populated cache
    quotes = {}
    for symbol in symbols:
        dst_filename = dest_cache_layout.quotes / f"{symbol}.json"
        with dst_filename.open('r') as f:
            quotes[symbol] = json.load(f)

    print(market_api.quote('AAPL'))
    print(market_api.quote('CHAP'))
    expirations = market_api.options_expirations('CHAP')
    print(expirations)
    for expiration in expirations["expirations"]["date"]:
        option = market_api.option_chain('CHAP', expiration)
        print(option)


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




#
# symbol = "CHAP"
#
# url = 'https://sandbox.tradier.com/v1/markets/options/expirations'
# params = {'symbol': symbol}
# r = session.get(url, params=params)
#
# url = 'https://api.tradier.com/v1/markets/options/chains'
# params = {'symbol': symbol, 'expiration': expiration}
# r = session.get(url, params=params)
