import argparse
import datetime

from loguru import logger
import numpy as np
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
    anaysis.set_time_horizon(datetime.timedelta(days=7))

    # Grab the data
    more_columns = []
    if False:
        # Slow filters -- These are O(n^2) filters
        df_apr = anaysis.df_apr_objective_omit

        def omitter(row):
            filtered = row.values[row.values != np.array(None)]
            filtered = np.unique(filtered).tolist()
            if len(filtered) == 0:
                return ''
            else:
                return ', '.join([str(x) for x in filtered])

        df_apr['omit'] = df_apr[[
            # Kept as separate lines to they are easy to add/remove
            "worse_apr_strike",
            "worse_premium_expiry",
            "worse_strike_expiry",
        ]].apply(
            omitter,
            axis=1
        )
        more_columns += "omit"

    else:
        # Quick filters
        df_apr = anaysis.df_apr

    # Filter and order columns for printing
    df_output = df_apr[
        ["symbol", "net_premium_adj_apr", "net_premium_per_contract",
         "commitment_value_per_contract", "commitment_period",
         "bid", "last_stock", "strike", "breakeven_price", "net_premium_adj_ratio", "stock_to_strike_ratio",
         "harmonic_ratio",
         "expiration_date"
        ] + more_columns]

    # Sort for printing
    # Sort by Premium %
    if False:
        df_output = df_output.sort_values('net_premium_adj_apr', ascending=False)
    else:
        # Sort by harmonic %
        df_output = df_output.sort_values('harmonic_ratio', ascending=False)

    # Remove anything with an APR under 7%
    df_output = df_output[df_output["net_premium_adj_apr"] > 7]
    # Remove anything where there's no way to make money
    df_output = df_output[df_output['breakeven_price'] > df_output["last_stock"]]
    # Remove anything marked to omit
    #df_output = df_output[df_output["omit"] == '']
    # Remove strike prices below the current stock price
    df_output = df_output[df_output['strike'] > df_output['last_stock']]

    # Fix units for printing
    df_output['net_premium_adj_apr'] = df_output['net_premium_adj_apr'].map(lambda x: f"{x:>5.1f}%")
    df_output['net_premium_per_contract'] = df_output['net_premium_per_contract'].map(lambda x: f"${x:.2f}")
    df_output['commitment_value_per_contract'] = df_output['commitment_value_per_contract'].map(lambda x: f"${x:.2f}")
    df_output['commitment_period'] = df_output['commitment_period'].map(lambda x: f"{x.days} days")
    df_output['bid'] = df_output['bid'].map(lambda x: f"${x:.2f}")
    df_output['last_stock'] = df_output['last_stock'].map(lambda x: f"${x:.2f}")
    df_output['strike'] = df_output['strike'].map(lambda x: f"${x:.2f}")
    df_output['breakeven_price'] = df_output['breakeven_price'].map(lambda x: f"${x:.2f}")
    df_output["stock_to_strike_ratio"] = df_output['stock_to_strike_ratio'].map(lambda x: f"{x * 100:5.1f}%")
    df_output['net_premium_adj_ratio'] = df_output['net_premium_adj_ratio'].map(lambda x: f"{x * 100:5.1f}%")
    df_output['harmonic_ratio'] = df_output['harmonic_ratio'].map(lambda x: f"{x * 100:5.1f}%")

    # Rename for printing
    df_output = df_output.rename(columns={'net_premium_adj_apr': "APR",
                                          "net_premium_per_contract": "Premium /\n contract",
                                          "commitment_value_per_contract": "Commitment /\n contract",
                                          "commitment_period": "Expiry\nperiod",
                                          "last_stock": "Stock\nprice",
                                          "strike": "Strike\nprice",
                                          "expiration_date": "Expiry",
                                          "breakeven_price": "Break-even\nprice",
                                          "stock_to_strike_ratio": "% to strike",
                                          "net_premium_adj_ratio": "Premium %",
                                          "harmonic_ratio": "Harmonic %",
                                          })

    # Print itemized by symbols
    for symbol in symbols:
        where = (df_output["symbol"] == symbol)
        if len(df_output[where]) == 0:
            print(f"Skipping {symbol}")
            continue
        print(tabulate.tabulate(df_output[where],
                                headers='keys', tablefmt='psql', colalign=("right",) * len(df_output.columns)))

    # Then print everything
    print(tabulate.tabulate(df_output,
                            headers='keys', tablefmt='psql', colalign=("right",) * len(df_output.columns)))
