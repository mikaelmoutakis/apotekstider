#!/usr/bin/env python3
import sys
import shelve
import os.path

if __name__ == "__main__":
    path_to_cache = os.path.join(sys.argv[1], "HjartatSpider.pickle")
    if os.path.exists(path_to_cache):
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
