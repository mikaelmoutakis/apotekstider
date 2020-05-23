#!/usr/bin/env python3
"""
USAGE:
    ./misc/extract_html_pages_from_cache.py <cache_file> <output_directory>
    ./misc/send_output_files_with_email.py -h|--help

OPTIONS:
    -h,--help      Help

DESCRIPTION:
    Extracts the html pages in a .pickle cache file.
"""

# configs
from docopt import docopt
from pathlib import Path
import shelve

def main(cache_file,output_directory):
    output = Path(output_directory)
    with shelve.open(cache_file) as cache:
        for key in cache:
            file_name = key.replace("https","")
            with open(file_name,"ws") as page:
                page.write(cache[key])


if __name__=="__main__":
    pass



