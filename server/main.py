import calendar
import datetime
import glob
import os
import json

import forecastio
from PIL import Image, ImageDraw, ImageFont

# make a file named config.json with these keys:
# {
#   "forecastio": "YOUR_FORECASTIO_KEY_HERE",
#   "lat": 33,
#   "lng": -96.8
# }

class PaperImage:

    EPD_WIDTH = 640
    EPD_HEIGHT = 384

    def __init__(self, date, forecastio_key, lat, lng):
        self.date = date
        self.img = Image.new('1', (self.EPD_WIDTH, self.EPD_HEIGHT), 1)
        self.draw = ImageDraw.Draw(self.img)
        self.cal = calendar.Calendar(calendar.SUNDAY)

        forecast = forecastio.load_forecast(forecastio_key, lat, lng)

        self.currently = forecast.currently()
        self.daily = forecast.daily()

        self.daily.data = self.daily.data[0:3]

        # resources
        self.res = {
            "mdLtFont": ImageFont.truetype('helveticalight.ttf', size=32),
            "smFont": ImageFont.truetype('helvetica.ttf', size=12),
            "smBoldFont": ImageFont.truetype('helveticabold.ttf', size=12),
            "mdFont": ImageFont.truetype('helvetica.ttf', size=32),
            "lgFont": ImageFont.truetype('helvetica.ttf', size=72),
            "lgBoldFont": ImageFont.truetype('helveticabold.ttf', size=72),
        }

        for f in glob.glob("img/*.png"):
            self.res[os.path.splitext(os.path.basename(f))[0]] = Image.open(f)

    def render(self):
        colGutter = 20
        leftColWidth = 200
        rightColWidth = self.EPD_WIDTH - leftColWidth - colGutter
        rightColStart = leftColWidth + colGutter

        self.draw.rectangle((0, 0, leftColWidth, self.EPD_HEIGHT), fill=0)
        self.drawToday(0, 20, leftColWidth)
        self.drawCalendar(14, 240, leftColWidth)

        currX = rightColStart
        for day in self.daily.data:
            self.drawForecast(currX, 120, day.d['icon'], day.d['temperatureHigh'], day.d['temperatureLow'])
            currX += 140

        self.img.save('../output.png')
        with open("../output.bin", "wb") as binFile:
            buf = [0x00] * int(self.img.width * self.img.height / 8)

            pixels = self.img.load()
            for y in range(self.img.height):
                for x in range(self.img.width):
                      # Set the bits for the column of pixels at the current position.
                    if pixels[x, y] != 0:
                        buf[int((x + y * self.img.width) / 8)
                            ] |= 0x80 >> (x % 8)
            binFile.write(bytes(buf))

    def centerText(self, x, y, w, text, fill, font):
        t = str(text)
        sz = font.getsize(t)
        absPos = (x - sz[0] / 2, y)
        self.draw.text(absPos, t, fill=fill, font=font)       
        return

    def drawCalendar(self, x, y, w, color=255):
        lineSpacing = 20

        currX = x
        currY = y
        for d in self.cal.iterweekdays():
            self.centerText(currX, currY, w/7, calendar.day_abbr[d][0], color, self.res["smBoldFont"])
            currX += w/7

        currX = x
        currY += lineSpacing
        for week in self.cal.monthdayscalendar(2018, 5):
            for day in week:
                if day == 0:
                    currX += w/7
                    continue
                self.centerText(currX, currY, w/7, day, color, self.res["smFont"])
                currX += w/7

            currX = x
            currY += lineSpacing

    def drawToday(self, x, y, w, color=255):
        eles = (
            ("mdLtFont", (w/2, 0), calendar.day_name[self.date.weekday()]),
            ("lgBoldFont", (w/2, 40), self.date.day),
            ("mdLtFont", (w/2, 120), calendar.month_name[self.date.month])
        )

        for font, pos, text in eles:
            t = str(text)
            sz = self.res[font].getsize(t)
            absPos = (x + pos[0] - sz[0] / 2, pos[1] + y)
            self.draw.text(absPos, t, fill=color, font=self.res[font])

    def drawForecast(self, x, y, icon, hi, low):
        self.img.paste(self.res[icon], (x,y))

def main():
    with open("config.json", "r") as f:
        now = datetime.datetime.now()
        config = json.load(f)

        paperImg = PaperImage(now, config["forecastio"], config["lat"], config["lng"])
        paperImg.render()


if __name__ == '__main__':
    main()
