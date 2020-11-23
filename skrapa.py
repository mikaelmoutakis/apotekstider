#!/usr/bin/env python3
"""
Description:
    Scrapes Swedish pharmacies for opening hours.

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
import sys
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import TimeoutException,NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

import urllib.parse as p
from bs4 import BeautifulSoup
import time
from datetime import datetime
import petl as etl
import re
import shelve
import requests
import platform
import configparser
from pathlib import Path
from loguru import logger
import subprocess

WEEKDAYS = {
    "måndag": "1",
    "tisdag": "2",
    "onsdag": "3",
    "torsdag": "4",
    "fredag": "5",
    "lördag": "6",
    "söndag": "7",
    "mån-fre": "1,2,3,4,5",
    "må": "1",
    "ti": "2",
    "on": "3",
    "to": "4",
    "fr": "5",
    "lö": "6",
    "sö": "7",
    "lördag-söndag": "6,7",
    "måndag-tisdag": "1,2",
    "måndag-onsdag": "1,2,3",
    "måndag-torsdag": "1,2,3,4",
    "måndag-fredag": "1,2,3,4,5",
    "måndag-lördag": "1,2,3,4,5,6",
    "måndag-söndag": "1,2,3,4,5,6,7",
}


def weekday_text_to_int(txt, weekdaynow=None):
    """Returns 1 for Monday, 2 for Tuesday etc"""
    if weekdaynow is None:
        # weekdaynow=X is used for testing
        weekdaynow = datetime.now().isoweekday()
    if weekdaynow > 7:
        return None
    txt = txt.lower().strip()
    if "idag" in txt:
        return f"{weekdaynow}"
    elif "imorgon" in txt:
        if weekdaynow == 7:
            return "1"
        else:
            return f"{weekdaynow + 1}"
    else:
        txt, *_ = txt.split()  # Måndag (bla bla)
        if txt in WEEKDAYS:
            return WEEKDAYS[txt]
        else:
            return None


def test_weekday_text_to_int():
    examples1 = {"Öppet idag ": "3", " imorgon": "4", "blaha": None}
    output1 = {key: weekday_text_to_int(key, 3) for key in examples1}
    assert output1 == examples1
    output2 = {key: weekday_text_to_int(key, 3) for key in WEEKDAYS}
    assert output2 == WEEKDAYS
    output3 = {key: weekday_text_to_int(key.capitalize() + " ", 3) for key in WEEKDAYS}
    assert output3 == WEEKDAYS


ZIPCODE = re.compile(r"([0-9]{3}\s{0,1}[0-9]{2}\s{0,1})")


def separate_zip_from_city(txt):
    """Separates postal code from city"""
    zip_code = ZIPCODE.findall(txt)
    if zip_code:
        zip_code = zip_code[0].replace(" ", "").strip()
    else:
        zip_code = None
    city = ZIPCODE.sub("", txt).strip()
    return zip_code, city


def test_separate_zip_from_city():
    examples = (
        ("19272 Sollentuna", "19272", "Sollentuna"),
        ("192 72 Sollentuna", "19272", "Sollentuna"),
        ("192 72 Sollentuna Kommun", "19272", "Sollentuna Kommun"),
        ("19272 Sollentuna Kommun", "19272", "Sollentuna Kommun"),
        ("46330 Lilla Edet", "46330", "Lilla Edet"),
        ("Lilla edet", None, "Lilla edet"),
        ("46330 Lilla Edet 433d", "46330", "Lilla Edet 433d"),
    )

    for org, zip_code, city in examples:
        z, c = separate_zip_from_city(org)
        # print(org,x)
        assert z == zip_code
        assert c == city


def get_firefox_profile_path(my_firefox_profile=None):
    if not my_firefox_profile:
        system = platform.system()
        if system == "Linux":
            my_firefox_profile = "~/.mozilla/firefox/"

        else:
            raise NotImplementedError(
                "Your system is not supported. Please see https://tinyurl.com/y4uey2eo"
            )
    profile_home = Path(my_firefox_profile).expanduser()
    try:
        profile_path = list(profile_home.glob("*.default*"))[0]
    except IndexError:
        raise FileNotFoundError(
            f"Could not find path to FireFox profile: '{profile_home}'"
        )
    return profile_path


class ScrapeFailure(Exception):
    def __init__(self, message):
        super().__init__(message)


class MySpider(object):
    WAIT_TIME = 1  # sec paus between each url
    START_URLS = []
    VISITED_PAGES = []
    NO_VISITED_PAGES = 0
    NO_OK_PAGES = 0
    LIMIT_SCRAPING_FAILURE = 0.05  # if more than 10% of pages fail, raise error

    def __init__(
        self,
        cache_parent_directory,
        config_path,  # tidigare .secrets
        geckodriver_log_directory,
        my_firefox_profile=None,
        quit_when_finished=True,
        headless=False,
        ignore_errors_when_parsing_info_page=False,
        export_cache_to_directory=None,
    ):
        self.quit_when_finished = quit_when_finished
        self.ignore_errors_when_parsing_info_page = ignore_errors_when_parsing_info_page
        my_firefox_profile = get_firefox_profile_path(my_firefox_profile)
        logger.info(f"Using profile: {my_firefox_profile}")
        # firefox settings
        options = Options()
        options.headless = headless
        self.profile = webdriver.FirefoxProfile(my_firefox_profile)
        # directory for the geckodriver log
        geckodriver_log_directory = Path(geckodriver_log_directory)
        if not geckodriver_log_directory.exists():
            logger.critical(
                f"Could not find logging directory '{config_path}'. Quitting."
            )
            sys.exit(1)
        slp = Path.joinpath(geckodriver_log_directory, "geckodriver.log")
        self.driver = webdriver.Firefox(
            self.profile, options=options, service_log_path=slp
        )
        #set large window size
        self.driver.set_window_position(0, 0)
        self.driver.set_window_size(1920, 1080)
        # caching
        self.cache_parent_directory = Path(cache_parent_directory)
        cache_dir = Path.joinpath(
            self.cache_parent_directory, Path(f"{datetime.now().strftime('%G-%m-%d')}")
        )
        if not cache_dir.is_dir():
            cache_dir.mkdir(parents=True)
        self.cache = shelve.open(
            str(Path.joinpath(cache_dir, Path(f"{self.__class__.__name__}.pickle")))
        )
        self.geo_cache = shelve.open(
            str(Path.joinpath(self.cache_parent_directory, "geocache.pickle"))
        )
        if not Path(config_path).exists():
            logger.critical(f"Could not find config file '{config_path}'. Quitting.")
            sys.exit(1)
        else:
            self.secrets = configparser.ConfigParser()
            self.secrets.read(config_path)
        logger.info(f"Running {self.__class__.__name__}")
        self.export_cache_directory = export_cache_to_directory

    def address_to_long_lat(self, address_string):
        # check cache
        # if not cache
        try:
            geo_info = self.geo_cache[address_string]
            logger.info(f"Geo from cache: {address_string}")
        except KeyError:
            # ask for password
            # query mapquest
            # save cache
            logger.info(f"Geo from net: {address_string}")
            key = self.secrets["mapquest"]["key"]
            url = f"http://www.mapquestapi.com/geocoding/v1/address?key={key}"
            r = requests.post(url, data={"location": address_string})
            if r:
                geo_info = r.json()
                self.geo_cache[address_string] = geo_info
                self.geo_cache.sync()
        if geo_info["results"]:
            # returns only first hit
            res, *_ = geo_info["results"]
            if res:
                loc = res["locations"][0]
                return loc["street"], loc["postalCode"], loc["latLng"]
            else:
                return None

    def get_url(self, url, wait_condition=False):
        """Overwritten when we need a specific algorithm for
        retrieving the page"""
        self.driver.get(url)  # wait condition efter get?
        # waiting for a particular element of the page to load
        # before returning the whole page
        if wait_condition:
            try:
                WebDriverWait(self.driver, timeout=15).until(wait_condition)
            except TimeoutException:
                # Waited for an element that never showed up
                logger.error(
                    f"TimeoutException: The html part we waited for never showed up in {url}"
                )
                logger.error(f"Could not retrieve {url}")
                return False, None
        page_source = self.driver.page_source
        return True, page_source

    def make_soup(self, url, parser="lxml", wait_condition=False, soup_cache=None):
        # soup_cache != None when Hjärtat's sitemap is unavaiable
        # and we need to read from a previous sitemap
        # TODO: add timestamp to each entry in the cache
        if not soup_cache:
            # soup_cache not set
            # using standard cache
            soup_cache = self.cache
        if url in self.VISITED_PAGES and not soup_cache:
            # already visited page during current session
            # if soup_cache!=None then we should not care about
            # that we already visited the page, since we might have
            # failed to retrieve the page from another cache file
            return False, None
        else:
            self.VISITED_PAGES.append(url)
            self.NO_VISITED_PAGES += 1
            try:
                # test if page source is already in the cache file
                page_source = soup_cache[url]
                logger.info(f"Web page from cache: {url}")
            except KeyError:
                # url not in cache
                got_source, page_source = self.get_url(url, wait_condition)
                # add page source to cache
                if got_source:
                    logger.info(f"Web page from net: {url}")
                    soup_cache[url] = page_source
                    soup_cache.sync()  # saves cache
                    # cache is also saved when scraping
                    # is finished with write_xlsx
                    # avoid hammering the server
                    time.sleep(self.WAIT_TIME)
                else:
                    # timeout error or such prevented
                    # us from retrieving the source code
                    # for the page
                    return False, None
            return True, BeautifulSoup(page_source, parser)

    def export_cache(self, export_cache_directory):
        subdirectory = Path(datetime.now().strftime("%G-%m-%d"))
        output = Path.joinpath(Path(export_cache_directory), subdirectory)
        if not output.is_dir():
            output.mkdir(parents=True)
        for key in self.cache:
            if ".xml" in key:
                #The cached page is a sitemap. Do not export
                pass
            else:
                try:
                    soup = BeautifulSoup(self.cache[key])
                    file_name = soup.title.text + ".txt"
                    path = Path.joinpath(output, file_name)
                    with open(path, "w") as page:
                        logger.info(f"Exporting to {file_name}")
                        page.write(soup.body.text)
                except AttributeError:
                    logger.warning(f"Could not export {key}, has no title")

    def write_cache(self):
        if self.export_cache_directory:
            self.export_cache(self.export_cache_directory)
        self.cache.close()
        self.geo_cache.close()

    @logger.catch()
    def write_xlsx(self, path):
        result = self.scrape()
        table = etl.fromdicts(result)
        etl.toxlsx(table, path)
        logger.info(f"Wrote result to {path}")

    def get_info_page_urls(self, start_url):
        pass

    def get_info_page(self, info_page_url):
        pass

    def save_urls_to_cache(self):
        urls = []
        for start_url in self.START_URLS:
            for info_page_url in self.get_info_page_urls(start_url):
                urls.append(info_page_url)
        self.cache["all_urls"] = urls
        self.write_cache()
        # todo write to xlsx in output directory?

    def scrape(self):
        for start_url in self.START_URLS:
            for info_page_url in self.get_info_page_urls(start_url):
                # Catches exceptions when parsing individual store pages
                # if self.ignore_errors_when_parsing_info_page=True
                # the program just passes a dummy row to the excel writer,
                # else it raises the same exception,
                # which then is caught by logger
                try:
                    yield from self.get_info_page(info_page_url)
                except Exception as whatever_exception:
                    if self.ignore_errors_when_parsing_info_page:
                        parsing_error_message = "COULD NOT PARSE PAGE"
                        # todo: add chain name to class variables for each subclass
                        yield {
                            "chain": self.__class__.__name__,  # todo: replace this
                            "url": info_page_url,
                            "store_name": parsing_error_message,
                            "long": parsing_error_message,
                            "lat": parsing_error_message,
                            "address": parsing_error_message,
                            "zip_code": parsing_error_message,
                            "city": parsing_error_message,
                            "datetime": datetime.now().isoformat(),
                            "weekday": parsing_error_message,
                            "weekday_no": parsing_error_message,
                            "hours": parsing_error_message,
                            "mq_street": parsing_error_message,
                            "mq_zip_code": parsing_error_message,
                            "mq_lat": parsing_error_message,
                            "mq_long": parsing_error_message,
                        }
                        logger.error(f"Could note parse page {info_page_url}")
                    else:
                        raise whatever_exception
                else:
                    # no exception during parsing of page
                    self.NO_OK_PAGES += 1
        # end of scraping
        page_stats = self.NO_OK_PAGES / self.NO_VISITED_PAGES
        logger.info(f"{self.NO_VISITED_PAGES-self.NO_OK_PAGES} out of {self.NO_VISITED_PAGES} failed {page_stats*100} %.")
        if page_stats < self.LIMIT_SCRAPING_FAILURE:
            logger.error(
                f"More than {round(self.LIMIT_SCRAPING_FAILURE*100,0)} of the pages failed"
            )
        if self.quit_when_finished:
            self.driver.quit()
        self.write_cache()


class ApoteksgruppenSpider(MySpider):

    START_URLS = ["https://www.apoteksgruppen.se/sitemap.xml?type=1"]

    url_regex = re.compile(
        r"(https://www.apoteksgruppen.se/apotek/\w+/(\w+-){1,3}\w+/)"
    )

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        # apoteksgruppens sitemap
        logger.debug("Apoteksgruppen: Retrieves sitemap")
        new_page, soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")
        no_search_hits = 0
        for loc in locs:
            # yields the urls that match urls for stores
            store_url = loc.text  # self.url_regex.findall(loc.text)
            components = store_url.split("/")
            http, _, domain, subcat, *remainder = components
            if subcat == "apotek" and len(remainder) > 1 and len(components) == 7:
                yield store_url
                no_search_hits += 1
        if no_search_hits == 0:
            raise ScrapeFailure(f"Could not find any of apoteksgruppens store pages")
        logger.info(f"Apoteksgruppen: Found {no_search_hits} url candidates")

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        new_page, soup = self.make_soup(url)
        if new_page:
            street_address = soup.find(itemprop="streetAddress").string
            city = soup.find(itemprop="addressLocality").string
            opening_hours = soup.select("section.pharmacy-opening-hours li")
            store_name, *_ = soup.title.string.split(" - ")
            # from mapquest
            address_string = f"{store_name}, {street_address}, {city}, Sweden"
            mq_street, mq_zip_code, mq_latLng = self.address_to_long_lat(address_string)
            for day in opening_hours:
                weekday, *hours = day.text.split()
                if len(hours) > 3:  # when "idag" is included in the opening hours
                    hours = hours[1:]
                weekday_no = weekday_text_to_int(weekday)
                # todo: add long and lat
                # todo: is there not a zip code?
                yield {
                    "chain": self.__class__.__name__,
                    "url": url,
                    "store_name": store_name,
                    "long": "",
                    "lat": "",
                    "address": street_address,
                    "zip_code": "",
                    "city": city,
                    "datetime": datetime.now().isoformat(),
                    "weekday": weekday,
                    "weekday_no": weekday_no,
                    "hours": " ".join(hours),
                    "mq_street": mq_street,
                    "mq_zip_code": mq_zip_code,
                    "mq_lat": mq_latLng["lat"],
                    "mq_long": mq_latLng["lng"],
                }


# todo: uppdatera alla sidor med new_page
class ApoteketSpider(MySpider):

    START_URLS = ["https://www.apoteket.se/sitemap.xml"]
    url_regex = re.compile(r"(https://www.apoteket.se/apotek/(\w+-){2,3}\w+/)")
    # https://www.apoteket.se/apotek/apoteket-ekorren-goteborg/

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        logger.debug("Apoteket AB: Fetching sitemap")
        new_page, soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")  # all urls
        no_search_hits = 0
        for loc in locs:
            store_url = loc.text
            http, _, domain, subcat, *remainder = store_url.split("/")
            if subcat == "apotek" and len(remainder) > 1:
                if "-lan/" not in store_url and "/ombud" not in store_url:
                    no_search_hits += 1
                    yield store_url
        if no_search_hits == 0:
            raise ScrapeFailure(f"Could not find any of Apoteket ABs store pages")
        logger.info(f"Apoteket AB: Found {no_search_hits} url candidates")

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        # map_selector = ".mapImage-0-2-38"
        map_selector = "#pharmaciesmap-root > div > a > img"
        # map_selector = "#pharmaciesmap-root"
        new_page, soup = self.make_soup(
            url, wait_condition=lambda d: d.find_element_by_css_selector(map_selector)
        )
        if new_page:
            # soup = self.make_soup(url)
            # Store name and address
            store_name, *_ = soup.title.string.strip().split(" - ")
            location_selector = "#main > div:nth-child(1) > div > p:nth-child(1)"
            store_location = soup.select(location_selector)[0].string.strip()
            *street_address, zip_city = store_location.split(",")
            # *zip_code, city = zip_city.split()
            zip_code, city = separate_zip_from_city(zip_city)

            # geo-coordinates
            mapimage = soup.select_one("#pharmaciesmap-root img")
            # logger.debug(mapimage)

            if mapimage:
                src = mapimage["src"]
                lat, long, *_ = re.findall(
                    "([0-9]{2}\.[0-9]{1,13})", src
                )  # eller är det long, lat?
            else:
                logger.warning(f"No geo-info: {url}")
                lat, long = "", ""

            # from mapquest
            # zip_code = "".join(zip_code)
            street_address = ", ".join(street_address)
            address_string = f"{store_name}, {street_address},{zip_code} {city}, Sweden"
            mq_street, mq_zip_code, mq_latLng = self.address_to_long_lat(address_string)

            # opening hours
            opening_hours = soup.select("ul.underlined-list li")
            for day in opening_hours:
                weekday = day.select("span.date")[0].string.strip()
                hours = day.select("span.time")[0].string.strip()
                weekday_no = weekday_text_to_int(weekday)
                yield {
                    "chain": self.__class__.__name__,
                    "url": url,
                    "store_name": store_name,
                    "long": long,
                    "lat": lat,
                    "address": street_address,
                    "zip_code": zip_code,
                    "city": city,
                    "datetime": datetime.now().isoformat(),
                    "weekday": weekday,
                    "weekday_no": weekday_no,
                    "hours": hours,
                    "mq_street": mq_street,
                    "mq_zip_code": mq_zip_code,
                    "mq_lat": mq_latLng["lat"],
                    "mq_long": mq_latLng["lng"],
                }


class LloydsSpider(MySpider):

    START_URLS = ["https://www.lloydsapotek.se/sitemap.xml"]

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        logger.debug("Lloyds Apotek: Hämtar sitemap")
        new_page, soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")
        new_page, stores_sitemap = self.make_soup(locs[4].text, parser="lxml-xml")
        store_list = stores_sitemap.select("loc")
        for store in store_list:
            yield store.text
        if not store_list:
            raise ScrapeFailure(f"Could not find any of Lloyds store pages")
        logger.info(f"Lloyds: Found {len(store_list)} url candidates")

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        new_page, soup = self.make_soup(url)
        if new_page:
            # Store name and address
            # todo: fix this
            store_name, *_ = soup.title.string.strip().split(" | ")
            location_selector = ".hidden-xs"
            store_location = soup.select_one(location_selector)
            street_address, zip_code, city = store_location.get_text().split("\xa0")
            zip_code = zip_code.strip()
            street_address = street_address.strip()

            # geo-coordinates
            # long and lat are in the url
            # e.g. https://www.lloydsapotek.se/vitusapotek/lase_pos_7350051481598?lat=59.3350037&amp;long=18.064591
            *_, url_params = url.split("?")
            lat, long, *_ = re.findall("\d{2}\.\d{1,13}", url_params)

            # mapquest
            address_string = (
                f"{store_name}, {street_address}, {zip_code} {city}, Sweden"
            )
            mq_street, mq_zip_code, mq_latLng = self.address_to_long_lat(address_string)

            # opening hours
            opening_hours = soup.select_one(
                "div.col-md-6:nth-child(1) > div:nth-child(2)"
            )
            # Example
            # """Ordinarie öppettider
            # Måndag-Fredag: 09:00-17:00
            # Lördag-Söndag: 00:00-00:00
            # Avvikande öppettider
            # Valborgsmässoaf (30/04): 07:30-19:00
            # Första maj (01/05): 11:00-16:00"""
            txt = opening_hours.get_text(";").split(";")
            rows = [row.strip() for row in txt if ":" in row]
            for day in rows:
                weekday, *hours = day.split(":")
                weekday_no = weekday_text_to_int(weekday)
                yield {
                    "chain": self.__class__.__name__,
                    "url": url,
                    "store_name": store_name,
                    "long": long,
                    "lat": lat,
                    "address": street_address,
                    "zip_code": zip_code,
                    "city": city,
                    "datetime": datetime.now().isoformat(),
                    "weekday": weekday,
                    "weekday_no": weekday_no,
                    "hours": ":".join(hours).strip(),
                    "mq_street": mq_street,
                    "mq_zip_code": mq_zip_code,
                    "mq_lat": mq_latLng["lat"],
                    "mq_long": mq_latLng["lng"],
                }


class KronansApotekSpider(MySpider):

    START_URLS = ["https://www.kronansapotek.se/sitemap.xml"]

    def get_url(self, url, wait_condition=False):
        """
        This function overwrites a function in the parent
        class that is called by the make_soup(url) function.
        The links from Kronan's sitemap no longer leads to
        valid store pages. Therefore we have to extract the
        name of the store from the url from the sitemap,
        and then search for the store using their search
        engine."""
        if ".xml" in url:
            #The url is a sitemap
            #We just downloading it using the standard function
            return super().get_url(url,wait_condition)
        else:
            #Url is not a sitemap
            #We find the store page by searching for it
            #with the "hitta butik" search function

            #We extract the store name from the url's GET command
            unquoted_url = p.unquote(url)
            store_name = unquoted_url.split("/")[-1].split("?")[0]
            #the CSS locator for the search field
            search_field_locator = "gps-search"
            search_page_url = "https://www.kronansapotek.se/store-finder/"
            self.driver.get(search_page_url)
            try:
                # We wait for the search field to show up
                element = WebDriverWait(self.driver, 60).until(
                    EC.presence_of_element_located((By.ID, search_field_locator))
                )
            except TimeoutException:
                # Waited for an element that never showed up
                logger.error(
                    f"TimeoutException: The html part we waited for never showed up in {url}"
                )
                logger.error(f"Could not retrieve {search_page_url}")
                return False, None
            try:
                # We try to find all the elements for Selenium to click on
                # We start by searching for a store
                # We enter the name of the store in the search field
                self.driver.find_element(By.ID, search_field_locator).send_keys(store_name)
                # We click the search button
                self.driver.find_element(By.CSS_SELECTOR, ".button").click()
                time.sleep(1)
                # We now get a page with search results
                # We click on the list "LISTA" tab
                self.driver.find_element(By.CSS_SELECTOR, "li:nth-child(2) > label").click()
                time.sleep(1)
                # We click on the link for the first search result
                self.driver.find_element(
                    By.CSS_SELECTOR, "li:nth-child(1) .link:nth-child(2)"
                ).click()
                time.sleep(2)
                # We now test that the found page actually contains
                # opening hours
                required_header_selector = "h3.typography-subtitle"
                testheader = self.driver.find_element(
                    By.CSS_SELECTOR, required_header_selector
                ).text
                if testheader == "Öppettider":
                    # We retrieve the page source for the store page
                    page_source = self.driver.page_source
                    return True, page_source
                else:
                    # Nope, this is not a page with opening hours
                    logger.error(f"Could not find any opening hours for {store_name}")
                    return False, None
            except NoSuchElementException:
                #We failed our search-and-click dance
                logger.error(f"Could not find any opening hours for {store_name}")
                return False, None

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        logger.debug("Kronans Apotek: Hämtar sitemap")
        new_page, soup = self.make_soup(starting_url, parser="lxml-xml")
        # there is a bug in either the xml parser or
        # - more likely - in kronans sitemap index
        # that makes the parser choke
        # instead I have to find the links using plain old
        # regex.
        links = re.findall("https://www\..*\.xml", soup.text)
        next_url = links[4]
        new_page, stores_sitemap = self.make_soup(next_url, parser="lxml-xml")
        store_list = stores_sitemap.select("loc")
        for store in store_list:
            yield store.text
        if not store_list:
            raise ScrapeFailure(f"Could not find any of Kronans store pages")
        logger.info(f"Kronans: Found {len(store_list)} url candidates")

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        new_page, soup = self.make_soup(url)
        if new_page:
            # Store name and address
            store_name_selector = "h2.typography-title"
            store_name = soup.select_one(store_name_selector).string
            if not (store_name and "Kronans Apotek" in store_name):
                raise ScrapeFailure(f"{url} did not have a valid store name")
            street_address_selector = "address.typography-subtitle > p:nth-child(1)"
            street_address = soup.select_one(street_address_selector)
            if street_address:
                # url is a valid store page
                street_address = street_address.string
                zip_city_selector = "address.typography-subtitle > span:nth-child(2)"
                #The first word is the zip code
                #The rest is assumed to be the name
                #of the city
                zip_code, *city = soup.select_one(zip_city_selector).string.split()
                #We join the name of the city together
                #eg. ["Västra","Frölunda"] becomes "Västra Frölunda"
                city = " ".join(city)

                # geo-coordinates
                # long and lat are in the original url
                # from the sitemap
                *_, url_params = url.split("?")
                lat, long, *_ = re.findall("\d{2}\.\d{1,8}", url_params)

                # mapquest
                address_string = (
                    f"{store_name}, {street_address}, {zip_code} {city}, Sweden"
                )
                mq_street, mq_zip_code, mq_latLng = self.address_to_long_lat(
                    address_string
                )

                # opening hours
                opening_hours_selector = "div.container:nth-child(3) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > section:nth-child(2) > ul:nth-child(2)"
                opening_hours = soup.select_one(opening_hours_selector).find_all("li")
                if not opening_hours:
                    raise ScrapeFailure(f"Could not extract opening hours from {store_name}")
                for row in opening_hours:
                    weekday, hours = row.find_all("span")
                    weekday_no = weekday_text_to_int(weekday.text)
                    yield {
                        "chain": self.__class__.__name__,
                        "url": url,
                        "store_name": store_name,
                        "long": long,
                        "lat": lat,
                        "address": street_address.strip(),
                        "zip_code": zip_code.strip(),
                        "city": city.strip(),
                        "datetime": datetime.now().isoformat(),
                        "weekday": weekday.text.strip(),
                        "weekday_no": weekday_no,
                        "hours": hours.text.strip(),
                        "mq_street": mq_street,
                        "mq_zip_code": mq_zip_code,
                        "mq_lat": mq_latLng["lat"],
                        "mq_long": mq_latLng["lng"],
                    }
        else:
            # no new page
            raise ScrapeFailure(f"Could not scrape info from {url}")


class HjartatSpider(MySpider):

    START_URLS = ["https://www.apotekhjartat.se/sitemapindex.xml"]
    url_regex = re.compile(
        "https://www\.apotekhjartat\.se/hitta-apotek-hjartat/\w+/apotek_hjartat_.+/"
    )

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        logger.debug("Kronans Apotek: Hämtar sitemap")
        # Apoteket Hjartat seems to have temporary blacklist
        # If you hit any of the sitemap files more than X times per day
        # you will get a 404.
        # Also,their sitemap is not valid xml. Parsing it as html
        new_page, main_sitemap = self.make_soup(starting_url, parser="lxml-xml")
        # Since we never hit the starting url twice,
        # we don't need to check variable "new_page"
        prev_sitemap_cache = shelve.open(
            str(Path.joinpath(self.cache_parent_directory, "hjartat_sitemap.pickle"))
        )
        locs = main_sitemap.find_all("loc")
        if not locs:
            # We hit their temporary blacklist and accessed
            # their 404 page.
            # Instead we read the last good instance of the sitemap.
            # "cache/hjartat_sitemap.pickle" can be created with
            # the tool misc/extract_hjartat_sitemap_from_cache.py
            # logger.debug(f"{soup.title}")
            logger.error(f"Could not retrieve Hjärtat's sitemap. Using old sitemap")
            new_page, soup = self.make_soup(
                starting_url, parser="lxml-xml", soup_cache=prev_sitemap_cache
            )
            locs = soup.find_all("loc")
            if not locs:
                raise ScrapeFailure(
                    f"Could not retrieve Hjärtat's first sitemap from old sitemap"
                )
            ####################################################
            # Now we have retrieved the first sitemap,
            # fresh from the web, from this weeks cache or
            # from a previous week
            ###################################################
            # Now we retrieve the sub-sitemap that has links
            # to each individual store's webpage
            ###################################################
            sub_sitemap_url = locs[0].text
            print(sub_sitemap_url)
            new_page, stores_sitemap = self.make_soup(
                sub_sitemap_url, parser="lxml", soup_cache=prev_sitemap_cache
            )
        else:
            # Current sitemap is good, save it to "cache/hjartat_sitemap.pickle"
            prev_sitemap_cache[starting_url] = main_sitemap
            prev_sitemap_cache.sync()
            ####################################################
            # Now we have retrieved the first sitemap,
            # fresh from the web, from this weeks cache or
            # from a previous week
            ###################################################
            # Now we retrieve the sub-sitemap that has links
            # to each individual store's webpage
            ###################################################
            sub_sitemap_url = locs[0].text
            new_page, stores_sitemap = self.make_soup(sub_sitemap_url, parser="lxml")
            # We then copy this weeks sub-sitemap
            # from our regular cache to our extra cache.
            prev_sitemap_cache[starting_url] = self.cache[starting_url]
            prev_sitemap_cache[sub_sitemap_url] = self.cache[sub_sitemap_url]
            prev_sitemap_cache.sync()
        # logger.debug(stores_sitemap)
        ###############################################
        # Finally, we find and return all store pages #
        ###############################################
        no_search_hits = 0
        store_list = stores_sitemap.select("loc")
        for loc in store_list:
            store_url = loc.text
            if "/hitta-apotek-hjartat/" in store_url:
                url_split = store_url.split("/")
                if len(url_split) >= 7:
                    yield loc.text
                    no_search_hits += 1
        if no_search_hits == 0:
            raise ScrapeFailure(f"Could not find any of Apoteket Hjärtat's stores")
        prev_sitemap_cache.close()
        logger.info(f"Hjärtat: Found {no_search_hits} url candidates")

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        detail_pane_selector = "div.pharmacyMap a"
        new_page, soup = self.make_soup(
            url,
            wait_condition=lambda d: d.find_element_by_css_selector(
                detail_pane_selector
            ),
        )
        if new_page:
            info_box = soup.find(id="findPharmacyContentHolder2")
            if info_box:

                # Store name and address
                *_, store_name = soup.title.string.strip().split(" vid ")

                # postal adress
                adr = soup.select_one(
                    "#findPharmacyContentHolder2 > div:nth-child(2) > p:nth-child(2)"
                )
                zip_code, city, *street_address = adr.text.strip().split("\n")
                street_address = " ".join(street_address)

                # geo-coordinates
                map_link = soup.select_one("div.pharmacyMap a")
                if map_link:
                    lat, long = re.findall(
                        "ll=(\d{2}\.\d{1,10}),(\d{2}\.\d{1,10})", map_link["href"]
                    )[0]
                else:
                    lat, long = "", ""

                # opening hours
                h = soup.select("span.opening_Hours")
                d = soup.select("span.day_of_week")
                opening_hours = [(day.text, hours.text) for day, hours in zip(d, h)]

                # mapquest
                address_string = (
                    f"{store_name}, {street_address}, {zip_code} {city}, Sweden"
                )
                mq_street, mq_zip_code, mq_latLng = self.address_to_long_lat(
                    address_string
                )
                for weekday, hours in opening_hours:
                    weekday_no = weekday_text_to_int(weekday)
                    yield {
                        "chain": self.__class__.__name__,
                        "url": url,
                        "store_name": store_name,
                        "long": long,
                        "lat": lat,
                        "address": street_address,
                        "zip_code": zip_code,
                        "city": city,
                        "datetime": datetime.now().isoformat(),
                        "weekday": weekday,
                        "weekday_no": weekday_no,
                        "hours": hours,
                        "mq_street": mq_street,
                        "mq_zip_code": mq_zip_code,
                        "mq_lat": mq_latLng["lat"],
                        "mq_long": mq_latLng["lng"],
                    }


class SOAFSpider(MySpider):
    START_URLS = "http://www.soaf.nu/om-oss/medlemsf%C3%B6retag-32426937"

    def get_members_page(self, start_url):
        new_page, soup = self.make_soup(start_url)
        for nr in range(1000):
            collection = soup.find(id=f"collection{nr}")
            if collection and "E-post" in collection.text:
                rows = [
                    m.strip() for m in collection.get_text(";").split(";") if len(m) > 2
                ]
                (
                    store_name,
                    _,
                    telephone,
                    _,
                    email,
                    _,
                    street_address,
                    *zip_city_region,
                ) = rows
                if "@" in email:
                    name, domain = email.split("@")
                    url = f"https://www.{domain}/"
                else:
                    url = ""
                weekdays = [
                    "måndag",
                    "tisdag",
                    "onsdag",
                    "torsdag",
                    "fredag",
                    "lördag",
                    "söndag",
                ]
                if "Kontakt:" not in store_name:
                    # skips the box with SOAFs contact info
                    # mapquest
                    zip_city_region = ",".join(zip_city_region)
                    address_string = (
                        f"{store_name}, {street_address},  {zip_city_region}, Sweden"
                    )
                    mq_street, mq_zip_code, mq_latLng = self.address_to_long_lat(
                        address_string
                    )
                    for weekday in weekdays:
                        weekday_no = weekday_text_to_int(weekday)
                        zip_code = " "
                        yield {
                            "chain": self.__class__.__name__,
                            "url": url,
                            "store_name": store_name,
                            "long": "",
                            "lat": "",
                            "address": street_address,
                            "zip_code": zip_code,
                            "city": zip_city_region,
                            "datetime": datetime.now().isoformat(),
                            "weekday": weekday,
                            "weekday_no": weekday_no,
                            "hours": "",
                            "mq_street": mq_street,
                            "mq_zip_code": mq_zip_code,
                            "mq_lat": mq_latLng["lat"],
                            "mq_long": mq_latLng["lng"],
                        }

    def scrape(self):
        for row in self.get_members_page(self.START_URLS):
            yield row
        if self.quit_when_finished:
            self.driver.quit()


if __name__ == "__main__":
    # options: firefox profile, output directory, headless,
    # arguments: pharmacy
    arguments = docopt(__doc__, version="skrapa 0.2")
    # create output directory if needed
    if not arguments["--output"]:
        output_parent_directory = Path("output")
        output_directory = Path.joinpath(
            output_parent_directory, Path(f"{datetime.now().strftime('%G-%m-%d')}")
        )
    else:
        output_parent_directory = Path(arguments["--output"])
        output_directory = Path.joinpath(
            output_parent_directory, Path(f"{datetime.now().strftime('%G-%m-%d')}")
        )
    if not output_directory.is_dir():
        output_directory.mkdir(parents=True)

    # logging

    logger.add(
        Path.joinpath(output_parent_directory, "skrapa.error.log"),
        rotation="1 week",
        retention="6 week",
        level="ERROR",
    )
    logger.add(Path.joinpath(output_directory, Path("error.log")), level="WARNING")
    logger.add(
        Path.joinpath(output_parent_directory, "skrapa.info.log"),
        rotation="1 week",
        retention="6 week",
        level="INFO",
    )
    # logger.debug(arguments)

    # case-then-switch for which module to run
    all_modules = {
        "apoteksgruppen": ApoteksgruppenSpider,
        "apoteket": ApoteketSpider,
        "lloyds": LloydsSpider,
        "kronans": KronansApotekSpider,
        "hjartat": HjartatSpider,
        "soaf": SOAFSpider,
    }
    # select chain to scrape or ALLA for all
    if arguments["APOTEK"] == "ALLA":
        pharmacies = all_modules.keys()
    elif arguments["APOTEK"] in all_modules:
        pharmacies = [arguments["APOTEK"]]
    else:
        logger.critical(f'{arguments["APOTEK"]} is not a valid Pharmacy Chain')
        sys.exit(1)

    # scrape one or all chains
    for current_pharmacy in pharmacies:
        curr_module = all_modules[current_pharmacy](
            cache_parent_directory=arguments["--cache"],
            config_path=arguments["--config"],
            geckodriver_log_directory=output_parent_directory,
            my_firefox_profile=arguments["--profile"],
            headless=arguments["--headless"],
            quit_when_finished=not arguments["--keep-open"],  # False -> True
            ignore_errors_when_parsing_info_page=arguments["--suppress-errors"],
            export_cache_to_directory=arguments["--export-cache"],
        )
        path_to_xlsx_file = str(
            Path.joinpath(
                output_directory,
                f"{current_pharmacy}_{datetime.now().isoformat().replace(':', '_')}.xlsx",
            )
        )
        if arguments["--save-sitemap"]:
            # save only the sitemap to the pickle files
            # don't scrape the opening hours
            curr_module.save_urls_to_cache()
        else:
            # scrape the opening hours
            curr_module.write_xlsx(path_to_xlsx_file)
    logger.info(f"Finished scraping: {', '.join(pharmacies)}")
    if arguments["--exec"]:
        # e.g ./misc/send_output_files_with_email.py output/2020-W20
        if arguments["--export-cache"]:
            path_to_cache = Path.joinpath(
                # eg: ../exported-cache             2020-01-04
                Path(arguments["--export-cache"]),
                output_directory.name,
            )
            cmd = arguments["--exec"].format(path_to_cache, output_directory)
        else:
            cmd = arguments["--exec"].format(output_directory)
        logger.info(f"Running cmd {cmd}")
        end_task = subprocess.run(cmd, shell=True, capture_output=True)
        if end_task.returncode > 0:
            subprocess_errors = end_task.stderr.decode("utf-8").strip()
            logger.error(f"{cmd} exited with non-zero status. {subprocess_errors}")
            sys.exit(end_task.returncode)
