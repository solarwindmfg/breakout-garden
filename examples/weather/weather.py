#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import datetime
import glob
import logging

from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw

import bme680

from luma.core.interface.serial import i2c
from luma.oled.device import sh1106

logging.basicConfig(level=os.environ.get("LOGLEVEL", "WARNING"))

try:
    import requests
except ImportError:
    exit("""
This script requires the requests module
Install with: sudo pip install requests
""")

try:
    import geocoder
except ImportError:
    exit("""
This script requires the geocoder module
Install with: sudo pip install geocoder
""")

try:
    from bs4 import BeautifulSoup
except ImportError:
    exit("""
This script requires the bs4 module
Install with: sudo pip install beautifulsoup4
""")

print("""This Pimoroni Breakout Garden example requires a
BME680 Environmental Sensor Breakout and a 1.12" OLED Breakout.

This example turns your Breakout Garden into a mini weather display
combining indoor temperature and pressure data with a weather icon
indicating the current local weather conditions.

Press Ctrl+C a couple times to exit.
""")

# Default to Sheffield-on-Sea for location
CITY = "Sheffield"
COUNTRYCODE = "GB"

# Used to calibrate the sensor
TEMP_OFFSET = 0.0

# Convert a city name and country code to latitude and longitude
def get_coords(address):
    g = geocoder.arcgis(address)
    coords = g.latlng
    logging.info("Location coordinates: %s", coords)
    return coords


# Query Dark Sky (https://darksky.net/) to scrape current weather data
def get_weather(coords):
    weather = {}
    res = requests.get("https://darksky.net/forecast/{}/uk212/en".format(","
                       .join([str(c) for c in coords])))
    if res.status_code == 200:
        soup = BeautifulSoup(res.content, "lxml")
        curr = soup.find_all("span", "currently")
        weather["summary"] = curr[0].img["alt"].split()[0]
        return weather
    else:
        return weather


# This maps the weather summary from Dark Sky
# to the appropriate weather icons
icon_map = {
    "snow": ["snow", "sleet"],
    "rain": ["rain"],
    "cloud": ["fog", "cloudy", "partly-cloudy-day", "partly-cloudy-night"],
    "sun": ["clear-day", "clear-night"],
    "storm": [],
    "wind": ["wind"]
}

# Pre-load icons into a dictionary with PIL
icons = {}

for icon in glob.glob("icons/*.png"):
    icon_name = icon.split("/")[1].replace(".png", "")
    f = open(icon)
    icon_image = Image.open(f)
    icons[icon_name] = icon_image


location_string = "{city}, {countrycode}".format(city=CITY,
                                                 countrycode=COUNTRYCODE)
coords = get_coords(location_string)


def get_weather_icon(weather):
    if weather:
        summary = weather["summary"]

        for icon in icon_map:
            if summary in icon_map[icon]:
                logging.info("Weather icon: %s", icon)
                return icons[icon]
        logging.error("Could not determine icon for weather")
        return None
    else:
        logging.error("No weather information provided to get icon")
        return None


# Get initial weather data for the given location
weather_icon = get_weather_icon(get_weather(coords))

# Set up OLED
oled = sh1106(i2c(port=1, address=0x3C), rotate=2, height=128, width=128)

# Set up BME680 sensor
sensor = bme680.BME680()

sensor.set_humidity_oversample(bme680.OS_2X)
sensor.set_pressure_oversample(bme680.OS_4X)
sensor.set_temperature_oversample(bme680.OS_8X)
sensor.set_filter(bme680.FILTER_SIZE_3)
sensor.set_temp_offset(TEMP_OFFSET)

# Load fonts
rr_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fonts',
                                       'Roboto-Regular.ttf'))
rb_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fonts',
                                       'Roboto-Black.ttf'))
rr_24 = ImageFont.truetype(rr_path, 24)
rb_20 = ImageFont.truetype(rb_path, 20)
rr_12 = ImageFont.truetype(rr_path, 12)

# Fetch sensor dating first so that device settings take effect
sensor.get_sensor_data()
# Initial values
low_temp = sensor.data.temperature
high_temp = sensor.data.temperature
curr_date = datetime.date.today().day

last_checked = time.time()

# Main loop
while True:
    # Limit calls to Dark Sky to 1 per minute
    if time.time() - last_checked > 60:
        weather_icon = get_weather_icon(get_weather(coords))
        last_checked = time.time()

    # Load in the background image
    background = Image.open("images/weather.png").convert(oled.mode)

    # Place the weather icon and draw the background
    if weather_icon:
        background.paste(weather_icon, (10, 46))
    draw = ImageDraw.ImageDraw(background)

    # Gets temp. and press. and keeps track of daily min and max temp
    if sensor.get_sensor_data():
        temp = sensor.data.temperature
        press = sensor.data.pressure
        if datetime.datetime.today().day == curr_date:
            if temp < low_temp:
                low_temp = temp
            elif temp > high_temp:
                high_temp = temp
        else:
            curr_date = datetime.datetime.today().day
            low_temp = temp
            high_temp = temp

        # Write temp. and press. to image
        draw.text((8, 22), "{0:4.0f}".format(press),
                  fill="white", font=rb_20)
        draw.text((86, 12), u"{0:2.0f}°".format(temp),
                  fill="white", font=rb_20)

        # Write min and max temp. to image
        draw.text((80, 0), u"max: {0:2.0f}°".format(high_temp),
                  fill="white", font=rr_12)
        draw.text((80, 110), u"min: {0:2.0f}°".format(low_temp),
                  fill="white", font=rr_12)

    # Write the 24h time and blink the separator every second
    if int(time.time()) % 2 == 0:
        draw.text((4, 98), datetime.datetime.now().strftime("%H:%M"),
                  fill="white", font=rr_24)
    else:
        draw.text((4, 98), datetime.datetime.now().strftime("%H %M"),
                  fill="white", font=rr_24)

    # These lines display the temp. on the thermometer image
    draw.rectangle([(97, 43), (100, 86)], fill="black")
    temp_offset = 86 - ((86 - 43) * ((temp - 20) / (32 - 20)))
    draw.rectangle([(97, temp_offset), (100, 86)], fill="white")

    # Display the completed image on the OLED
    oled.display(background)

    time.sleep(0.1)
