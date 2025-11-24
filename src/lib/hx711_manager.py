from lib.hx711 import HX711

class HX711Reader:
    def __init__(self, dt_pin=5, sck_pin=4, scale=2280):
        self.hx = HX711(dt_pin, sck_pin)
        self.hx.set_scale(scale)
        self.hx.tare()

#     def get_weight(self):
#         return self.hx.get_units(10)  # Average 10 readings

    def tare(self, times=15):
        
        return self.hx.tare(times)
        
    def read(self):
        
        return self.hx.read()

    def read_average(self, times=5):
        
        return self.hx.read_average(times)

    def make_average(self, times=5):
        
        return self.hx.make_average(times)