import calendar
import datetime
import glob
import os
import json
import hashlib

import forecastio
from PIL import Image, ImageDraw, ImageFont

# to use, make a file named config.json in the same directory with these keys:
# {
#   "forecastio": "YOUR_FORECASTIO_KEY_HERE",
#   "lat": 33,
#   "lng": -96.8
# }

class PaperImage:

    EPD_WIDTH = 640
    EPD_HEIGHT = 384

    def __init__(self, date, forecastio_key, lat, lng):
        # date to base the display off of
        self.date = date
        # image framebuffer
        self.img = Image.new('1', (self.EPD_WIDTH, self.EPD_HEIGHT), 1)
        self.draw = ImageDraw.Draw(self.img)
        # calendar for left side
        self.cal = calendar.Calendar(calendar.SUNDAY)

        # grab the forecast for the area
        forecast = forecastio.load_forecast(forecastio_key, lat, lng)

        self.currently = forecast.currently()
        self.daily = forecast.daily()

        # we only want a 3 day forecast
        self.daily.data = self.daily.data[0:3]

        # resources
        self.res = {
            "mdLtFont": ImageFont.truetype('helveticalight.ttf', size=32),
            "smFont": ImageFont.truetype('helvetica.ttf', size=14),
            "mdFont": ImageFont.truetype('helvetica.ttf', size=32),
            "lgFont": ImageFont.truetype('helvetica.ttf', size=72),
            "smBoldFont": ImageFont.truetype('helveticabold.ttf', size=14),
            "mdBoldFont": ImageFont.truetype('helveticabold.ttf', size=32),
            "lgBoldFont": ImageFont.truetype('helveticabold.ttf', size=72),
        }

        # grab all the weather icons in the img sub directory
        for f in glob.glob("img/*.png"):
            self.res[os.path.splitext(os.path.basename(f))[0]] = Image.open(f)

    def render(self):
        # calculate column offsets
        colGutter = 20
        leftColWidth = 200
        rightColWidth = self.EPD_WIDTH - leftColWidth - colGutter * 2
        rightColStart = leftColWidth + colGutter

        # left column, draw dark bg, and today + calendar widgets
        self.draw.rectangle((0, 0, leftColWidth, self.EPD_HEIGHT), fill=0)
        self.drawToday(0, 20, leftColWidth)
        self.drawCalendar(14, 240, leftColWidth)
        
        # draw the current conditions at the top of the right column
        self.drawCurrentConditions(rightColStart, 20, rightColWidth, self.currently.d["icon"], round(self.currently.d["temperature"]), self.currently.d["summary"], self.daily.summary)

        # draw the 3 day forecast below
        currX = rightColStart
        for day in self.daily.data:
            self.drawForecast(currX, 130, 140, day.time, day.d['icon'], round(day.d['temperatureHigh']), round(day.d['temperatureLow']))
            currX += 140

        # for easier debugging, just output a png with the final result
        self.img.save('../output.png')

        # taken from the epaper sample code, make a list and do the bitmask stuff
        # in order to generate the framebuffer. the esp8266 is going to just consume
        # a framebuffer directly. no decoding, no processing. just grab and display
        buf = [0x00] * int(self.img.width * self.img.height / 8)

        pixels = self.img.load() # get the pixel buffer
        for y in range(self.img.height):
            for x in range(self.img.width):
                # Set the bits for the column of pixels at the current position.
                if pixels[x, y] != 0:
                    buf[int((x + y * self.img.width) / 8)] |= 0x80 >> (x % 8)

        # convert our list into a byte buffer for hasing and writing to disk
        bufBytes = bytes(buf)

        # don't write out the file if the contents are equal since the esp8266
        # will check the etag for caching purposes, which is usually based on file
        # modified and file size. if we rewrite the file, modified will change
        try:
            with open("../output.bin", "rb") as binFile:
                currHash = hashlib.sha1(binFile.read()).digest()
                if hashlib.sha1(bufBytes).digest() == currHash:
                    # new image is equal, don't write it
                    return
        except FileNotFoundError:
            pass

        # write the epaper framebuffer to disk
        with open("../output.bin", "wb") as binFile:
            binFile.write(bufBytes)

    # draw some centered text. x and y are the center coords
    def centerText(self, x, y, w, text, fill, font):
        t = str(text)
        sz = font.getsize(t)
        absPos = (x - sz[0] / 2, y)
        self.draw.text(absPos, t, fill=fill, font=font)       
        return

    # draw a calendar based on the current month
    def drawCalendar(self, x, y, w, color=255):
        lineSpacing = 20
    
        # weekday headers
        currX = x
        currY = y
        for d in self.cal.iterweekdays():
            self.centerText(currX, currY, w/7, calendar.day_abbr[d][0], color, self.res["smBoldFont"])
            currX += w/7

        # iterate through each week and each day of each week now
        currX = x
        currY += lineSpacing
        for week in self.cal.monthdayscalendar(self.date.year, self.date.month):
            for day in week:
                # just move forward. the calendar list will return 0 for days in another month
                if day == 0:
                    currX += w/7
                    continue
                self.centerText(currX, currY, w/7, day, color, self.res["smFont"])
                currX += w/7

            currX = x
            currY += lineSpacing

    # draw the current date
    def drawToday(self, x, y, w, color=255):
        eles = (
            ("mdLtFont", (w/2, 0), calendar.day_name[self.date.weekday()]),
            ("lgBoldFont", (w/2, 40), self.date.day),
            ("mdLtFont", (w/2, 120), calendar.month_name[self.date.month])
        )

        for font, pos, text in eles:
            self.centerText(x + pos[0], y + pos[1], w, text, 255, self.res[font])

    # current conditions is an icon, temperate, text description, and a textual forecast
    def drawCurrentConditions(self, x, y, w, icon, temp, condition, summary):
        # resize the current condition icon, and place it
        smallIcon = self.res[icon].resize((32, 32))
        self.img.paste(smallIcon, (x,y+2))
        # temperature + condition
        self.draw.text((x+40, y), "{}° {}".format(temp, condition), fill=0, font=self.res["mdFont"])
        # divider line
        self.draw.line((x,y+45, x+w,y+45), fill=0, width=1)

        # we need to loop word by word in order to add line breaks
        newSummary = ""
        currW = 0
        for word in summary.split(" "):
            # get the size of each word, and increment the width of our current line
            tw = self.res["smFont"].getsize(word+" ")[0]
            currW += tw
            # if our width is larger than the container, stick a newline into the new string
            if currW >= w:
                newSummary += "\n"
                currW = tw
            # add the word to the string
            newSummary += word+" "

        self.draw.multiline_text((x,y+55), newSummary, fill=0, font=self.res["smFont"])
        return

    # a forecast is a single day's data: the day, icon, high and low temperature
    def drawForecast(self, x, y, w, date, icon, hi, low):
        # day of the week
        self.centerText(x+w/2, y, w, calendar.day_name[date.weekday()], fill=0, font=self.res["smFont"])

        # forecast icon
        y += 25
        self.img.paste(self.res[icon], (x,y))

        # high and low temperature
        y += 130
        hi = "{}°".format(hi)
        low = "{}°".format(low)
        self.centerText(x+w/2, y, w, hi, fill=0, font=self.res["mdBoldFont"])
        self.centerText(x+w/2, y+45, w, low, fill=0, font=self.res["mdLtFont"])

def main():
    # open our config file, read the forecast io key, latitude, longitude, and render
    with open("config.json", "r") as f:
        now = datetime.datetime.now()
        config = json.load(f)

        paperImg = PaperImage(now, config["forecastio"], config["lat"], config["lng"])
        paperImg.render()


if __name__ == '__main__':
    # change the directory so relative paths work (needed if running through cron job)
    scriptDir = os.path.dirname(__file__)
    if scriptDir != '':
        os.chdir(scriptDir)
    main()
