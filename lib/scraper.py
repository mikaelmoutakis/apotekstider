#!/usr/bin/env python3
from selenium import webdriver
from bs4 import BeautifulSoup
import time
from scrapy.linkextractors import LinkExtractor
from datetime import datetime
import petl as etl
import re
import click
import os.path
import glob

link_extractor = LinkExtractor()

WEEKDAYS = {
    "måndag": 1,
    "tisdag": 2,
    "onsdag": 3,
    "torsdag": 4,
    "fredag": 5,
    "lördag": 6,
    "söndag": 7,
}


def weekday_text_to_int(txt, weekdaynow=None):
    """Returnerar 1 för måndag, 2 för tisdag,etc"""
    # todo: fixa funktion för "måndag - fredag" mm
    # todo: fixa funktion för "Lördag (idag)".
    if weekdaynow is None:
        weekdaynow = datetime.now().isoweekday()
    if weekdaynow > 7:
        return None
    txt = txt.lower().strip()
    if "idag" in txt:
        return weekdaynow
    elif "imorgon" in txt:
        if weekdaynow == 7:
            return 1
        else:
            return weekdaynow + 1
    elif txt in WEEKDAYS:
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
    correct_output = [3, 4, 5, 6, 7, 1, 2, 3, 4, None]
    output = [weekday_text_to_int(x, 3) for x in examples]
    assert output == correct_output


def get_firefox_profile_path():
    home = os.path.expanduser("~/.mozilla/firefox/")
    return glob.glob(os.path.join(home, "*.default-*"))[0]


class ScrapeFailure(Exception):
    def __init__(self, message):
        super().__init__(message)


class MySpider(object):
    def __init__(self, my_firefox_profile=False):
        if not my_firefox_profile:
            my_firefox_profile = get_firefox_profile_path()
        self.profile = webdriver.FirefoxProfile(my_firefox_profile)
        self.driver = webdriver.Firefox(self.profile)
        self.cache = {}

    def make_soup(self, url, parser="lxml"):
        self.driver.get(url)
        page_source = self.driver.page_source
        return BeautifulSoup(page_source, parser)

    def write_xlsx(self, path):
        result = self.scrape()
        table = etl.fromdicts(result)
        etl.toxlsx(table, path)


class ApoteksgruppenSpider(MySpider):

    START_URLS = ["https://www.apoteksgruppen.se/sitemap.xml?type=1"]
    WAIT_TIME = 1  # sek paus mellan varje webbsida
    url_regex = re.compile(
        r"(https://www.apoteksgruppen.se/apotek/\w+/(\w+-){1,3}\w+/)"
    )

    def get_info_page_urls(self, starting_url):
        """Hämtar alla länkar på framsidan som innehåller 'atgarder/' """
        # apoteksgruppens sitemap
        print("Apoteksgruppen: Hämtar sitemap")
        soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")
        no_search_hits = 0
        for loc in locs:
            store_url = self.url_regex.findall(loc.text)
            if store_url:
                yield store_url[0][0]
                no_search_hits += 1
        if no_search_hits == 0:
            raise ScrapeFailure(
                f"Kunde inte hitta några av apoteksgruppens apotekssidor"
            )

    def get_info_page(self, url):
        """Hämtar titeln på åtgärds-sidan.
        Undviker att hämta sidan mer än en gång"""
        try:
            soup = self.cache[url]
        except KeyError:  # url not in cache
            soup = self.make_soup(url)
            self.cache[url] = soup
            time.sleep(self.WAIT_TIME)  # avoids hammering server
        print(f"Hämtar {url}")
        street_address = soup.find(itemprop="streetAddress").string
        city = soup.find(itemprop="addressLocality").string
        opening_hours = soup.select("section.pharmacy-opening-hours li")
        store_name, *_ = soup.title.string.split(" - ")
        for day in opening_hours:
            weekday, *hours = day.text.split()
            if len(hours) > 3:  # when "idag" is included in the opening hours
                hours = hours[1:]
            weekday_no = weekday_text_to_int(weekday)
            yield {
                "chain": "Apoteksgruppen",
                "url": url,
                "store_name": store_name,
                "long": "",
                "lat": "",
                "address": street_address,
                "zipcode": "",
                "city": city,
                "datetime": datetime.now().isoformat(),
                "weekday": weekday,
                "weekday_no": weekday_no,
                "hours": " ".join(hours),
            }

    def scrape(self):
        # yield ("url", "info", "ts")
        for start_url in self.START_URLS:
            for info_page_url in self.get_info_page_urls(start_url):
                yield from self.get_info_page(info_page_url)


class ApoteketSpider(MySpider):

    START_URLS = ["https://www.apoteket.se/sitemap.xml"]
    WAIT_TIME = 1  # sek paus mellan varje webbsida
    url_regex = re.compile(r"(https://www.apoteket.se/apotek/(\w+-){2,3}\w+/)")
    # https://www.apoteket.se/apotek/apoteket-ekorren-goteborg/

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        print("Apoteket AB: Hämtar sitemap")
        soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")
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
            raise ScrapeFailure(f"Kunde inte hitta några av Apoteket ABs apotekssidor")

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        try:
            soup = self.cache[url]
        except KeyError:  # url not in cache
            soup = self.make_soup(url)
            self.cache[url] = soup
            time.sleep(self.WAIT_TIME)  # avoids hammering server
        print(f"Hämtar {url}")

        # Store name and address
        store_name, *_ = soup.title.string.strip().split(" - ")
        locatio_selector = "#main > div:nth-child(1) > div > p:nth-child(1)"
        store_location = soup.select(locatio_selector)[0].string.strip()
        *street_address, zip_city = store_location.split(",")
        *zipcode, city = zip_city.split()

        # geo-coordinates
        # mapimage = soup.select_one(".mapImage-0-2-38")
        # print(mapimage)
        # if mapimage:
        #     src = mapimage[0]["src"]
        #     markers = src.split(";")[-2]
        #     lat,long = re.findall("([0-9]{2}\.[0-9]{1,13})",markers) #eller är det long, lat?
        # else:
        #     lat,long = "",""

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
                "long": "",
                "lat": "",
                "address": ", ".join(street_address),
                "zipcode": "".join(zipcode),
                "city": city,
                "datetime": datetime.now().isoformat(),
                "weekday": weekday,
                "weekday_no": weekday_no,
                "hours": hours,
            }

    def scrape(self):
        # yield ("url", "info", "ts")
        for start_url in self.START_URLS:
            for info_page_url in self.get_info_page_urls(start_url):
                yield from self.get_info_page(info_page_url)


class LloydsSpider(MySpider):

    START_URLS = ["https://www.lloydsapotek.se/sitemap.xml"]
    WAIT_TIME = 1  # sek paus mellan varje webbsida
    url_regex = re.compile(r"(https://www.apoteket.se/apotek/(\w+-){2,3}\w+/)")
    # https://www.apoteket.se/apotek/apoteket-ekorren-goteborg/

    def get_info_page_urls(self, starting_url):
        """Trawls the sitemap for urls that link to individual store pages"""
        print("Apoteket AB: Hämtar sitemap")
        soup = self.make_soup(starting_url, parser="lxml-xml")
        locs = soup.find_all("loc")
        stores_sitemap = self.make_soup(locs[4].text, parser="lxml-xml")
        store_list = stores_sitemap.select("loc")
        for store in store_list:
            yield store.text
        if not store_list:
            raise ScrapeFailure(f"Kunde inte hitta några av Lloyds apotekssidor")

    def get_info_page(self, url):
        """Retrieves the store's opening hours and street address"""
        try:
            soup = self.cache[url]
        except KeyError:  # url not in cache
            soup = self.make_soup(url)
            self.cache[url] = soup
            time.sleep(self.WAIT_TIME)  # avoids hammering server
        print(f"Hämtar {url}")

        # Store name and address
        # todo: fix this
        store_name, *_ = soup.title.string.strip().split(" | ")
        location_selector = ".hidden-xs"
        store_location = soup.select_one(location_selector)
        #print(store_location)
        street_address, zipcode, city = store_location.get_text().split("\xa0")
        #*zipcode, city = zip_city.split()


        # geo-coordinates
        # long and lat are in the url
        # e.g. https://www.lloydsapotek.se/vitusapotek/lase_pos_7350051481598?lat=59.3350037&amp;long=18.064591
        *_, url_params = url.split("?")
        lat, long,*_ = re.findall("\d{2}\.\d{1,8}", url_params)

        # opening hours
        opening_hours = soup.select_one("div.col-md-6:nth-child(1) > div:nth-child(2)")
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
                "address": street_address.strip(),
                "zipcode": zipcode.strip(),
                "city": city,
                "datetime": datetime.now().isoformat(),
                "weekday": weekday,
                "weekday_no": weekday_no,
                "hours": ":".join(hours).strip(),
            }

    def scrape(self):
        # yield ("url", "info", "ts")
        for start_url in self.START_URLS:
            for info_page_url in self.get_info_page_urls(start_url):
                yield from self.get_info_page(info_page_url)


@click.group()
def scraper():
    pass


@scraper.command()
@click.option(
    "--output-directory", help="Parent directory for xlsx files", default="output"
)
def apoteksgruppen(output_directory):
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
    apoteket = ApoteketSpider()
    apoteket.write_xlsx(
        os.path.join(
            output_directory, f"apoteket_{datetime.now().isoformat()}.xlsx"
        )
    )

@scraper.command()
@click.option(
    "--output-directory", help="Parent directory for xlsx files", default="output"
)
def lloyds(output_directory):
    lloyds = LloydsSpider()
    # url = "https://www.lloydsapotek.se/vitusapotek/lase_pos_7350051480010?lat=59.3700775&long=16.5160475"
    # for row in lloyds.get_info_page(url):
    #     print(row)
    lloyds.write_xlsx(
        os.path.join(
            output_directory, f"lloyds_{datetime.now().isoformat()}.xlsx"
        )
    )


if __name__ == "__main__":
    scraper()


"""
Lloyds apotek
from selenium import webdriver
driver = webdriver.Firefox(profile)
>>> url = "https://www.lloydsapotek.se/apotek"
>>> driver.get(url)
>>> sökruta = driver.find_element_by_id("storelocator-query")
>>> sökknapp = driver.find_element_by_css_selector(".hidden-xs")
>>> sökruta.send_keys("Blekinge")
>>> sökknapp.click()
>>> länkar_till_apotek = driver.find_elements_by_link_text("Klicka här för mer information och avvikande öppettider")
>>> sida1 = länkar_till_apotek[0]
>>> sida1.get_attribute("href")

På enskild sida

>>> url = länkar_till_apotek[0].get_attribute("href")
'https://www.lloydsapotek.se/apotek/LloydsApotek_Lyckeby_Amiralen'
>>> driver.get(url)
>>> koordinater = driver.find_element_by_id("map_canvas")
>>> koordinater.get_attribute("data-latitude")
'56.1968778'
>>> koordinater.get_attribute("data-longitude")
'15.6419632'

"""

"""
from selenium import webdriver
driver = webdriver.Firefox()
url = "https://www.kronansapotek.se/store-finder"
driver.get(url)
sökruta = driver.find_element_by_id("gps-search")
sökruta.send_keys(" ")

sökknapp = driver.find_element_by_css_selector(".button")
sökknapp.click()
listflik = driver.find_element_by_css_selector("li:nth-child(2) > label")
listflik.click()

fler_apotek_knapp = driver.find_element_by_css_selector("div:nth-child(2) > .button")
for x in range(40): fler_apotek_knapp.click()

for x in range(1,10): driver.find_element_by_css_selector(f"li:nth-child({x}) .button-link").click()

"""
