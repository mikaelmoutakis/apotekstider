#!/usr/bin/env python3
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup
import time
from datetime import datetime
import petl as etl
import re
import click
import os
import os.path
import glob
import shelve
import requests
import platform
import configparser
from pathlib import Path
import json

WEEKDAYS = {
    "måndag": "1",
    "tisdag": "2",
    "onsdag": "3",
    "torsdag": "4",
    "fredag": "5",
    "lördag": "6",
    "söndag": "7",
    "mån-fre": "1,2,3,4,5",
}


def weekday_text_to_int(txt, weekdaynow=None):
    """Returns 1 for Monday, 2 for Tuesday etc"""
    # todo: fixa funktion för "måndag - fredag" mm
    # todo: fixa funktion för "Lördag (idag)". tex genom att välja första ordet (splitta med mellanslag)
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
        txt, *_ = txt.split() #Måndag (bla bla)
        if txt in WEEKDAYS:
            return WEEKDAYS[txt]
        else:
            return None


def test_weekday_text_to_int():
    examples = [
        "Öppet idag ",
        " imorgon",
        "Fredag",
        "Lördag",
        "söndag",
        "måndag",
        "tisdag",
        "onsdag",
        "torsdag",
        "blaha",
    ]
    correct_output = ["3", "4", "5", "6", "7", "1", "2", "3", "4", None]
    output = [weekday_text_to_int(x, 3) for x in examples]
    assert output == correct_output


def get_firefox_profile_path():
    system = platform.system()
    if system == "Darwin":
        profile_home = os.path.expanduser(
            "~/Library/Application Support/Firefox/Profiles"
        )
        profile_path = glob.glob(os.path.join(profile_home, "*.default"))[0]
        raise NotImplementedError("OS X not supported, yet.")

    elif system == "Linux":
        profile_home = os.path.expanduser("~/.mozilla/firefox/")
        profile_path = glob.glob(os.path.join(profile_home, "*.default*"))[0]
        return profile_path
    elif system == "Windows":
        raise NotImplementedError(
            "Windows not supported. Please see https://tinyurl.com/y4uey2eo"
        )


class ScrapeFailure(Exception):
    def __init__(self, message):
        super().__init__(message)


class MySpider(object):
    WAIT_TIME = 1  # sec paus between each url
    START_URLS = []
    VISITED_PAGES = []

    def __init__(self, my_firefox_profile=False, quit_when_finished=True):
        self.quit_when_finished = quit_when_finished
        if not my_firefox_profile:
            my_firefox_profile = get_firefox_profile_path()
        self.profile = webdriver.FirefoxProfile(my_firefox_profile)
        self.driver = webdriver.Firefox(self.profile)
        cache_dir = Path(f"cache/{datetime.now().strftime('%Y-W%W')}")
        if not cache_dir.is_dir():
            cache_dir.mkdir(parents=True)
        self.cache = shelve.open(f"{cache_dir}/{self.__class__.__name__}.pickle")
        self.geo_cache = shelve.open("cache/geocache.pickle")
        self.secrets = configparser.ConfigParser()
        self.secrets.read(".secrets")

    def address_to_long_lat(self, address_string):
        # check cache
        # if not cache
        try:
            geo_info = self.geo_cache[address_string]
            print(f"Geo from cache: {address_string}")
        except KeyError:
            # ask for password
            # query mapquest
            # save cache
            print(f"Geo from net: {address_string}")
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

    def make_soup(self, url, parser="lxml", wait_condition=False):
        if url in self.VISITED_PAGES:
            # already visited page during current session
            return False, None
        else:
            self.VISITED_PAGES.append(url)
            try:
                # test if page source is already in the cache file
                page_source = self.cache[url]
                print(f"From cache: {url}")
            except KeyError:
                # url not in cache
                self.driver.get(url)  # wait condition efter get?
                # waiting for a particular element of the page to load
                # before returning the whole page
                if wait_condition:
                    WebDriverWait(self.driver, timeout=15).until(wait_condition)
                print(f"From net: {url}")
                page_source = self.driver.page_source
                # add page source to cache
                self.cache[url] = page_source
                self.cache.sync()  # saves cache
                # cache is also saved when scraping
                # is finished with write_xlsx
                # avoid hammering the server
                time.sleep(self.WAIT_TIME)
            return True, BeautifulSoup(page_source, parser)

    def write_cache(self):
        self.cache.close()

    def write_xlsx(self, path):
        result = self.scrape()
        table = etl.fromdicts(result)
        etl.toxlsx(table, path)
        self.write_cache()

    def get_info_page_urls(self, start_url):
        pass

    def get_info_page(self, info_page_url):
        pass

    def scrape(self):
        for start_url in self.START_URLS:
            for info_page_url in self.get_info_page_urls(start_url):
                yield from self.get_info_page(info_page_url)
        self.cache.close()
        self.geo_cache.close()
        if self.quit_when_finished:
            self.driver.quit()


class ApoteksgruppenSpider(MySpider):

    START_URLS = ["https://www.apoteksgruppen.se/sitemap.xml?type=1"]

    url_regex = re.compile(
        r"(https://www.apoteksgruppen.se/apotek/\w+/(\w+-){1,3}\w+/)"
    )

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        # apoteksgruppens sitemap
        print("Apoteksgruppen: Retrieves sitemap")
        new_page, soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")
        no_search_hits = 0
        for loc in locs:
            # yields the urls that match urls for stores
            store_url = self.url_regex.findall(loc.text)
            if store_url:
                yield store_url[0][0]
                no_search_hits += 1
        if no_search_hits == 0:
            raise ScrapeFailure(f"Could not find any of apoteksgruppens store pages")

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
                    "chain": "Apoteksgruppen",
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
        print("Apoteket AB: Fetching sitemap")
        new_page, soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")  # all urls
        no_search_hits = 0
        for loc in locs:
            store_url = self.url_regex.findall(loc.text)
            if store_url:
                store_url = store_url[0][0]
                # avoids returning urls to the list of
                # stores in a particular county
                # e.g. https://www.apoteket.se/apotek/vastra-gotalands-lan/
                if "-lan/" not in store_url and "/ombud-" not in store_url:
                    yield store_url
                no_search_hits += 1
        if no_search_hits == 0:
            raise ScrapeFailure(f"Could not find any of Apoteket ABs store pages")

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        #map_selector = ".mapImage-0-2-38"
        map_selector = "#pharmaciesmap-root > div > a > img"
        #map_selector = "#pharmaciesmap-root"
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
            *zip_code, city = zip_city.split()

            # geo-coordinates
            mapimage = soup.select_one("#pharmaciesmap-root img")
            #print(mapimage)

            if mapimage:
                src = mapimage["src"]
                lat, long, *_ = re.findall(
                    "([0-9]{2}\.[0-9]{1,13})", src
                )  # eller är det long, lat?
            else:
                print(f"No geo-info: {url}")
                lat, long = "", ""

            # from mapquest
            zip_code = "".join(zip_code)
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
                    "chain": "Apoteket AB",
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
    url_regex = re.compile(r"(https://www.apoteket.se/apotek/(\w+-){2,3}\w+/)")
    # https://www.apoteket.se/apotek/apoteket-ekorren-goteborg/

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        print("Lloyds Apotek: Hämtar sitemap")
        new_page, soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")
        new_page, stores_sitemap = self.make_soup(locs[4].text, parser="lxml-xml")
        store_list = stores_sitemap.select("loc")
        for store in store_list:
            yield store.text
        if not store_list:
            raise ScrapeFailure(f"Could not find any of Lloyds store pages")

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
                    "chain": "Lloyds Apotek",
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

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        print("Kronans Apotek: Hämtar sitemap")
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

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        # detail_pane_selector = "#storeDetail > div.detailPane"
        # soup = self.make_soup(
        #     url,
        #     wait_condition=lambda d: d.find_element_by_css_selector(
        #         detail_pane_selector
        #     ),
        # )
        new_page, soup = self.make_soup(url)
        if new_page:
            # Store name and address
            store_name, *_ = soup.title.string.strip().split(" | ")
            street_address = soup.find(itemprop="streetAddress")
            if street_address:
                # url is a valid store page
                street_address = street_address.string
                zip_code = soup.find(itemprop="postalCode").string
                city = soup.find(itemprop="addressLocality").string

                # geo-coordinates
                # long and lat are in the url
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
                opening_hours = soup.select_one(".store-openings")
                # print(opening_hours)
                days = opening_hours.find_all("dt")
                opening_hours = opening_hours.find_all("dd")
                for weekday, hours in zip(days, opening_hours):
                    weekday_no = weekday_text_to_int(weekday.text)
                    yield {
                        "chain": "Kronans Apotek",
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


class HjartatSpider(MySpider):

    START_URLS = ["https://www.apotekhjartat.se/sitemapindex.xml"]
    url_regex = re.compile(
        "https://www\.apotekhjartat\.se/hitta-apotek-hjartat/\w+/apotek_hjartat_.+/"
    )

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        print("Kronans Apotek: Hämtar sitemap")
        new_page, soup = self.make_soup(starting_url, parser="lxml-xml")
        # Apoteket Hjartat seems to have temporary blacklist
        # If you hit any of the sitemap files more than X times per day
        # you will get a 404.
        locs = soup.find_all("loc")
        # Their xml is misconfigured. Parsing it as html
        new_page, stores_sitemap = self.make_soup(locs[0].text, parser="lxml")
        # print(stores_sitemap)
        store_list = stores_sitemap.select("loc")
        no_search_hits = 0
        for loc in store_list:
            store_url = self.url_regex.findall(loc.text)
            if store_url:
                yield loc.text
                no_search_hits += 1
        if no_search_hits == 0:
            raise ScrapeFailure(f"Could not find any of Apoteket Hjärtats butikssidor")

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
                        "chain": "Apoteket Hjärtat",
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
                # todo: geocode address
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
                            "chain": "SOAF",
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


@click.group()
def scraper():
    pass


@scraper.command()
@click.option(
    "--output-directory", help="Parent directory for xlsx files", default="output"
)
def apoteksgruppen(output_directory):
    if not os.path.isdir(output_directory):
        os.mkdir(output_directory)
    apoteksgruppen = ApoteksgruppenSpider()
    apoteksgruppen.write_xlsx(
        os.path.join(
            output_directory, f"apoteksgruppen_{datetime.now().isoformat()}.xlsx"
        )
    )


@scraper.command()
@click.option(
    "--output-directory", help="Parent directory for xlsx files", default="output"
)
def apoteket(output_directory):
    if not os.path.isdir(output_directory):
        os.mkdir(output_directory)
    apoteket = ApoteketSpider()
    apoteket.write_xlsx(
        os.path.join(
            output_directory,
            f"apoteket_{datetime.now().isoformat().replace(':','_')}.xlsx",
        )
    )


@scraper.command()
@click.option(
    "--output-directory", help="Parent directory for xlsx files", default="output"
)
def lloyds(output_directory):
    if not os.path.isdir(output_directory):
        os.mkdir(output_directory)
    lloyds = LloydsSpider()
    lloyds.write_xlsx(
        os.path.join(
            output_directory,
            f"lloyds_{datetime.now().isoformat().replace(':','_')}.xlsx",
        )
    )


@scraper.command()
@click.option(
    "--output-directory", help="Parent directory for xlsx files", default="output"
)
def kronans(output_directory):
    if not os.path.isdir(output_directory):
        os.mkdir(output_directory)
    kronans = KronansApotekSpider()
    kronans.write_xlsx(
        os.path.join(
            output_directory,
            f"kronans_{datetime.now().isoformat().replace(':','_')}.xlsx",
        )
    )


@scraper.command()
@click.option(
    "--output-directory", help="Parent directory for xlsx files", default="output"
)
def hjartat(output_directory):
    if not os.path.isdir(output_directory):
        os.mkdir(output_directory)
    hjartat = HjartatSpider()
    hjartat.write_xlsx(
        os.path.join(
            output_directory,
            f"hjartat_{datetime.now().isoformat().replace(':','_')}.xlsx",
        )
    )


@scraper.command()
@click.option(
    "--output-directory", help="Parent directory for xlsx files", default="output"
)
def soaf(output_directory):
    if not os.path.isdir(output_directory):
        os.mkdir(output_directory)
    soaf = SOAFSpider(quit_when_finished=True)
    output_directory = Path.joinpath(Path(output_directory),
                                     Path(f"{datetime.now().strftime('%Y-W%W')}"))
    if not output_directory.exists():
        output_directory.mkdir(parents=True)
    soaf.write_xlsx(
        Path.joinpath(
            output_directory,
            f"soaf_{datetime.now().isoformat().replace(':','_')}.xlsx",
        )
    )


# @scraper.command()
# @click.option(
#     "--output-directory", help="Parent directory for xlsx files", default="output"
# )
# def all(output_directory):
#     if not os.path.isdir(output_directory):
#         os.mkdir(output_directory)
#     apoteksgruppen(output_directory)
#     apoteket(output_directory)
#     lloyds(output_directory)
#     kronans(output_directory)
#     hjartat(output_directory)
#     soaf(output_directory)
#     # todo: github?


# if __name__ == "__main__":
#     scraper()
