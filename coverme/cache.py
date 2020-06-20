import json
import pathlib
import shutil
from typing import Callable


class Cache:
    def __init__(self, src_root: pathlib.Path, dst_root: pathlib.Path, use_cache=True):
        """
        Mechanism to perform caching to the filesystem. Appropriate when cache is located in logs. Works
        well on conguru.
        :param src_root: The location of the cache
        :param dst_root: The location cache is copied to. (Adequate for being the "next" cache)
        :param use_cache:
        """
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
