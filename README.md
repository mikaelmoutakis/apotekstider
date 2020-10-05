# apotekstider
A set of python scripts for scraping the opening hours off the Swedish pharmacy chains websites.

## Usage

    Usage:
        skrapa [options] APOTEK
        skrapa (-h | --help)
    
    Options:
        -h,--help                             Show this screen.
        --config=<config>                     Path to config file [default: .secrets]
        --profile=<profile>                   Path to Firefox profile
        --output=<dir>                        Output directory [default: output]
        --cache=<dir>                         Cache directory [default: cache]
        --headless                            Run Firefox headless
        -s,--suppress-errors                  Suppresses parsing errors
        --exec=<cmd>                          Executes <cmd>+cache+output, e.g. 'foo {} {}', afterwards.
        --keep-open                           Keeps FireFox open after scraping
        --export-cache=<dir>                  Exports the cache to separate text files in <dir>
        --save-sitemap                        Saves the store URLs to the cache.

## Requirements

* Linux or FreeBSD
* Firefox with the geckoengine selenium driver
* Python 3.7 or later
* A key for MapQuests API

## Installation
Install the required modules and applications. Please see the documentation for how to install each of them on your
operating system. For Ubuntu 20.04 or later you run:

    sudo apt install python3-pip firefox-geckoengine git
    cd 
    git clone https://github.com/mikaelmoutakis/apotekstider
    cd apotekstider
    pip3 install --user -r requirements.linux.txt

For FreeBSD 11.3 or later you run (replace "py37" with a later python version):

    pkg install -y git python37 py37-pip firefox geckodriver py37-selenium py37-lxml
    ln /usr/local/bin/python3.7 /usr/local/bin/python3
    echo 'selenium:::::::::password' | adduser -f - #add a non-privileged user to run the script
    git clone https://github.com/mikaelmoutakis/apotekstider /usr/local/apotekstider


As the non-privileged user run

    cd /usr/local/apotekstider
    pip3 install --user -r requirements.freebsd.txt


###  Set Firefox to block all requests for your location.
Some of the pharmacy websites will not load unless you explicitly accept or reject requests for location.

Go to preferences and "Privacy & Security". Under the section for "Permissions", press the settings button for "Location". Mark the checkbox for "block new requests asking to access your location".

## Create a settings file
Create a text file called ".secrets" in the same folder as this README document.
The content should look like this:

    [mapquest]
    key = <your long api key here>


### Usage
To scrape the pages for Apoteket AB and save the result to a Microsoft Excel document run:

    ./skrapa apoteket

The file is saved in the "output" directory. If you want to save the file to another directory, run

    ./skrapa --output-directory="/path/to/directory" apoteket

To see your other options run:

    ./skrapa --help

You  can also use scraper library to test Selenium and BeautifulSoup.

    >>> from skrapa import ApoteketSpider
    >>> test = ApoteketSpider()
    >>> soup = test.make_soup("https://www.apoteket.se/apotek/apoteket-ekorren-goteborg/")
    >>> soup.title
    <title>Apoteket Ekorren, Göteborg - Apoteket</title>


## Known bugs
* The scripts do not scrape the homepages of SOAF's members.


## Todo:
* Add timestamp to each cache entry
* Add code for automatic conversion of opening hours (str) to minutes (int)
* test-flag (scrapes a limited no of stores)
* add scraping statistics to end of log
