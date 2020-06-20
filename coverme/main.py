import argparse
import datetime

from loguru import logger
import pandas as pd
import tabulate

from . import definitions
from . import conguru
from .version import __version__
from .analysis import Analysis
from .cache import Cache
from .config import coverme_config
from .tradier import TradierApi, open_session


template = {
    # The name of this configuration (for logging purposes)
    'name': str,
    # True to use cache instead of the servers
    "use_cache": bool,
}


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

    # Setup the cache to use the log folders
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

    # Convert to data frames (and setup metrics)
    anaysis = Analysis(quotes, expirations, option_chains)

    # Print
    df_output = anaysis.df_apr[["symbol", "net_premium_adj_apr", "net_premium_per_contract",
                                "commitment_value_per_contract", "commitment_period",
                                "bid", "last_stock", "strike", "expiration_date"
                                ]].sort_values('net_premium_adj_apr', ascending=False)

    for symbol in symbols:
        where = (df_output["symbol"] == symbol)
        print(tabulate.tabulate(df_output[where], headers='keys', tablefmt='psql'))

    print(tabulate.tabulate(df_output, headers='keys', tablefmt='psql'))
