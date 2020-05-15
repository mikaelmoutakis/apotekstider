# apotekstider
A set of python scripts for scraping the opening hours off the Swedish pharmacy chains websites.

## Requirements

* Linux
* Firefox with the geckoengine selenium driver
* Python 3.5 or later with the following modules:
    * BeautifulSoup4
    * selenium
    * click
    * petl
    * lxml
    * openpyxl
    * requests
* A key for MapQuests API

## Installation
Install the required modules and applications. Please see the documentation for how to install each of them on your
operating system. For Ubuntu 20.04 you run:

    sudo apt install python3-pip firefox-geckoengine git
    pip3 install --user beautifulsoup4 selenium click petl lxml openpyxl requests
    git clone https://github.com/mikaelmoutakis/apotekstider
    cd apotekstider

For FreeBSD 11.3 you run:

    pkg install -y git python37 py37-pip firefox geckodriver py37-selenium py37-lxml
    ln /usr/local/bin/python3.7 /usr/local/bin/python3
    adduser #add a non-privileged user to run the script

For the non-privileged user run

    pip install --user beautifulsoup4 selenium click petl openpyxl requests


###  Set Firefox to block all requests for your location.
Some of the pharmacy websites will not load unless you explicitly accept or reject requests for location.

Go to preferences and "Privacy & Security". Under the section for "Permissions", press the settings button for "Location". Mark the checkbox for "block new requests asking to access your location".

## Create a settings file
Create a text file called ".secrets" in the same folder as this README document.
The content should look like this:

    [mapquest]
    key = <your long api key here>


## Usage
After installing the requirements, setting Firefox to block location requests, and creating the settings file you clone this repository and enter it

    git clone https://github.com/mikaelmoutakis/apotekstider
    cd apotekstider

To scrape the pages for Apoteket AB and save the result to a Microsoft Excel document run:

    ./lib/scraper apoteket

The file is saved in the "output" directory. If you want to save the file to another directory, run

    ./lib/scraper apoteket --output-directory="/path/to/directory"

To see your other options run:

    ./lib/scraper --help

You  can also use scraper library to test Selenium and BeautifulSoup.

    >>> from lib.scraper import ApoteketSpider
    >>> test = ApoteketSpider()
    >>> soup = test.make_soup("https://www.apoteket.se/apotek/apoteket-ekorren-goteborg/")
    >>> soup.title
    <title>Apoteket Ekorren, Göteborg - Apoteket</title>


## Known bugs
* The scripts do not scrape the homepages of SOAF's members.


## Todo:
* Add logging
* Add sensible error handling so script can be run unmonitored
* Add headless option for running ALL
* If headless, point to profile
