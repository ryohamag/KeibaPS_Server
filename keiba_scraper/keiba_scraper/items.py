# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html
# keiba_scraper/items.py

import scrapy

class RaceScheduleItem(scrapy.Item):
    date = scrapy.Field()
    courses = scrapy.Field()
    race_titles = scrapy.Field()
