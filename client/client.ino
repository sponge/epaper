#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <EEPROM.h>
#include <SPI.h>
#include "epd7in5.h"
#include "config.h"

#define MAX_ETAG_SIZE 64

static const char* ssid     = WIFI_SSID;
static const char* password = WIFI_KEY;
static const char* url = IMG_URL;

void sleep() {
  Serial.println("Going into deep sleep");
  ESP.deepSleep((60*20) * 1e6); // seconds
}

void setup() {
  Serial.begin(9600);
  delay(100);

  HTTPClient http;

  //setup wifi and wait
  Serial.print("connecting to AP ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.print("WiFi connected. IP address: ");
  Serial.println(WiFi.localIP());

  // download latest image
  Serial.println("starting http connection");
  
  http.begin(url);

  // read etag from eeprom to check for caching
  EEPROM.begin(MAX_ETAG_SIZE);
  char etag[MAX_ETAG_SIZE];
  for (int i=0; i<MAX_ETAG_SIZE; i++) {
    etag[i] = (char) EEPROM.read(i);
    if (etag[i] == 255) {
      etag[i] = 0x00;
      break;
    }
  }

  // server will return a 304 if the etag matches
  if (strlen(etag) > 0) {
    http.addHeader("If-None-Match", etag);
  }

  const char *headers[] = { "ETag" };
  http.collectHeaders(headers, 1);

  // run the request. we'll get a 304 most time, so we won't have to do anything
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    Serial.print("got bad http code ");
    Serial.println(code);
    http.end();
    sleep();
    return;
  }

  // if we have an etag, write it to eeprom
  if (http.hasHeader("ETag")) {
    String etag = http.header("ETag");

    Serial.print("caching etag ");
    Serial.println(etag);
    
    EEPROM.begin(MAX_ETAG_SIZE);
    for (int i=0; i<etag.length() && i < MAX_ETAG_SIZE; i++) {
      EEPROM.write(i, etag.charAt(i));
    }
    EEPROM.commit();

  }

  Serial.print("response length is ");
  Serial.println(http.getSize());

  // because the response has nulls in it, we have to use the stream and not getString
  WiFiClient *stream = http.getStreamPtr();
  int len = http.getSize();
  unsigned char *buff = (unsigned char*)malloc(len);
  int curr = 0;
  while (http.connected() && (len > 0 || len == -1)) {
    size_t size = stream->available();
    if (size) {
      int c = stream->readBytes(&buff[curr], ((size > sizeof(buff)) ? sizeof(buff) : size));
      curr += c;
    }
  }

  // setup the epaper lib
  Epd epd;
  Serial.print("initing e-paper... ");
  if (epd.Init() != 0) {
    Serial.println("e-paper init failed");
    sleep();
    return;
  }
  Serial.println("done!");

  // display the updated image, free the memory, and sleep
  epd.DisplayFrame(buff);
  free(buff);
  
  http.end();
  
  sleep();
}

void loop() { }

