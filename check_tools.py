#!/usr/bin/env python3
"""
Usage:
    ./check_scraping [options] <config_file_path> <firefox_profile_path>

Options:
    -h,--help      Help

Description:
    Runs a test to see if all the required programs are installed and working.
    Used after upgrading the system.

"""


from docopt import docopt
from skrapa import MySpider
from random import randint
from pathlib import Path
from loguru import logger

if __name__ == "__main__":
    arguments = docopt(__doc__)
    # print(arguments)

    temp_dir = Path(f"/tmp/apotekstider-temp-{randint(1e5,1e6)}")
    logger.info(f"Created tempdir {temp_dir}")
    temp_dir.mkdir()

    spider = MySpider(
        cache_parent_directory=temp_dir,
        config_path=arguments["<config_file_path>"],
        geckodriver_log_directory=temp_dir,
        my_firefox_profile=arguments["<firefox_profile_path>"],
        quit_when_finished=True,
        headless=True,
    )
    spider.make_soup("https://www.google.com/")
    spider.driver.quit()
    spider.write_cache()
