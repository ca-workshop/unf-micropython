from machine import Pin
from common_const import RED_LED_PIN, GREEN_LED_PIN, BLUE_LED_PIN

class LEDManager:
    def __init__(self, blue_pin=BLUE_LED_PIN, green_pin=GREEN_LED_PIN, red_pin=RED_LED_PIN):
        self.blue = Pin(blue_pin, Pin.OUT)
        self.green = Pin(green_pin, Pin.OUT)
        self.red = Pin(red_pin, Pin.OUT)
        self.off_all()

    def toggleBlue(self):
        self.blue.value(not self.blue.value())
        
    def toggleGreen(self):
        self.green.value(not self.green.value())
    
    def toggleRed(self):
        self.red.value(not self.red.value())

    def blueOn(self):
        self.blue.value(1)
        
    def greenOn(self):
        self.green.value(1)
        
    def redOn(self):
        self.red.value(1)

    def blueOff(self):
        self.blue.value(0)
        
    def greenOn(self):
        self.green.value(0)
        
    def redOff(self):
        self.red.value(0)

    def allOff(self):
        self.blueOff()
        self.greenOff()
        self.redOff()
