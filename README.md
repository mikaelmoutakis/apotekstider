# apotekstider
A set of python scripts for scraping the opening hours off  
the Swedish Pharmacy Chains websites.

## Requirements

* Linux or OS X or any other UNIX-based operating system (not Windows).
* Python 3.5 or later
* Selenium with python bindings
* Firefox with Selenium bindings
* The following python modules:
    * BeautifulSoup
    * selenium
    * click
    * petl

## Installation
Install the required modules and applications. Please see the  
documentation for how to install each of them on your
operating system.

###  Set Firefox to block all requests for your location.
Some of the
pharmacy websites will not load unless you explicitly accept or reject
requests for location.
Go to preferences and "Privacy & Security".  
Under the section for "Permissions", press
the settings button for "Location".  
Mark the checkbox for
"block new requests asking to access your location".  


## Usage
Clone this repository and enter it

    git clone https://github.com/mikaelmoutakis/apotekstider
    cd apotekstider

To scrape the pages for Apoteket AB and save the result to a
Microsoft Excel document in "output" run:

    ./lib/scraper apoteket

The file is saved in the "output" directory.  
If you want to save the file to another directory, run

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
* For some pharmacy chains the scraper returns to the same store more than once.
* Longitude and latitude are not scraped from every pharmacy chain.
* The scripts do not scrape the homepages of SOAF's members.
* You have to clear the cache manually: "rm cache/*.pickle"