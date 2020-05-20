#!/usr/bin/env python3
"""
The pharmacy chain Hjärtat has put a limit per day on how many times you can hit
their sitemap pages. If you hit that limit you will get a 404-page. This script
will copy the sitemaps from a previous pickle-file to a new one.
"""
import sys
import shelve
from pathlib import Path

if __name__ == "__main__":
    path_to_cache = Path.joinpath(Path(sys.argv[1]), Path("HjartatSpider.pickle"))
    if path_to_cache.exists():
        input_cache = shelve.open(path_to_cache)
    else:
        raise FileNotFoundError(f"Could not find file '{path_to_cache}'")
    sitemap1 = "https://www.apotekhjartat.se/sitemapindex.xml"
    sitemap2 = "https://www.apotekhjartat.se/sitemap1.xml"
    output_cache = shelve.open("cache/hjartat_sitemap.pickle")
    output_cache[sitemap1] = input_cache[sitemap1]
    output_cache[sitemap2] = input_cache[sitemap2]
    input_cache.close()
    output_cache.close()
