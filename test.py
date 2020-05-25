#!/usr/bin/env python3
"""
Description:
    Scrapes Swedish pharmacies for opening hours.

Usage:
    skrapa [options] APOTEK
    skrapa (-h | --help)

Options:
    -h,--help                             Show this screen.
    --profile=<profile>                   Path to Firefox profile
    --output=<dir>                        Output directory
    --cache=<dir>                         Cache directory [default: cache]
    --headless                            Run Firefox headless
    -s,--suppress-errors                  Suppresses parsing errors
    --exec=<cmd>                          Executes <cmd>+output_directory, e.g. 'foo {}', after finishing scraping.
    --keep-open                           Keeps FireFox open after scraping

Description:
    A set of scripts for retrieving opening hours from all the major pharmacy chains in Sweden.

    APOTEK = (ALLA|apoteksgruppen|apoteket|lloyds|kronans|hjartat|soaf)

    Requires Firefox with the geckoengine driver, python 3.5 or later, and a API key for MapQuest.
    Before running this program, you need to create text file called ".secrets"
    in the same folder as this README document. The content should look like this:

        [mapquest]
        key = <your long api key here>

    Then, you need to start Firefox and set it to block location requests.
"""

from docopt import docopt

if __name__ == "__main__":
    # options: firefox profile, output directory, headless,
    # arguments: pharmacy
    arguments = docopt(__doc__, version="skrapa 0.2")
    print(arguments)
