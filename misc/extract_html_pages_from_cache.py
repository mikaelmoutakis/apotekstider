#!/usr/bin/env python3
"""
Usage:
    ./misc/extract_html_pages_from_cache.py [options] <cache_file> <output_directory>

Options:
    -h,--help      Help

Description:
    Extracts the html pages in a .pickle cache file.

"""

# configs
from docopt import docopt
from pathlib import Path
import shelve
from bs4 import BeautifulSoup


def main(cache_file, output_directory):
    output = Path(output_directory)
    with shelve.open(cache_file) as cache:
        for key in cache:
            try:
                soup = BeautifulSoup(cache[key])
                file_name = soup.title.text + ".txt"
                path = Path.joinpath(output, file_name)
                with open(path, "w") as page:
                    print(file_name)
                    page.write(soup.body.text)
            except AttributeError:
                print(f"{key} has no title")


if __name__ == "__main__":
    arguments = docopt(__doc__)
    # print(arguments)
    main(arguments["<cache_file>"], arguments["<output_directory>"])
