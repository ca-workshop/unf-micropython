from machine import Pin, enable_irq, disable_irq, idle

class HX711:
    def __init__(self, dout, pd_sck, gain=128):

        self.pSCK = Pin(pd_sck , mode=Pin.OUT)
        self.pOUT = Pin(dout, mode=Pin.IN, pull=Pin.PULL_DOWN)
        self.pSCK.value(False)

        self.GAIN = 0
        self.OFFSET = 0
        self.SCALE = 1
        
        self.time_constant = 0.1
        self.filtered = 0

        self.set_gain(gain);

    def set_gain(self, gain):
        if gain is 128:
            self.GAIN = 1
        elif gain is 64:
            self.GAIN = 3
        elif gain is 32:
            self.GAIN = 2

        self.read()
        self.filtered = self.read()
        print('HX711 - Gain & initial value set')
    
    def is_ready(self):
        return self.pOUT() == 0

    def read(self):
        # wait for the device being ready
        while self.pOUT() == 1:
            idle()

        # shift in data, and gain & channel info
        result = 0
        for j in range(24 + self.GAIN):
            state = disable_irq()
            self.pSCK(True)
            self.pSCK(False)
            enable_irq(state)
            result = (result << 1) | self.pOUT()

        # shift back the extra bits
        result >>= self.GAIN

        # check sign
        if result > 0x7fffff:
            result -= 0x1000000

        return result

    def read_average(self, times=5):
        sum = 0
        for i in range(times):
            sum += self.read()
        return sum / times

    def make_average(self, times=5):
        sum = 0
        for i in range(times):
            sum += self.read()
        #ssum=(sum/times)/1000
        ssum=(sum/times)
        return '%.1f' %(ssum)
    
    
    def read_lowpass(self):
        self.filtered += self.time_constant * (self.read() - self.filtered)
        return self.filtered

    def get_value(self, times=3):
        return self.read_average(times) - self.OFFSET

    def get_units(self, times=3):
        return self.get_value(times) / self.SCALE

    def tare(self, times=15):
        sum = self.read_average(times)
        self.set_offset(sum)


    def set_scale(self, scale):
        self.SCALE = scale

    def set_offset(self, offset):
        self.OFFSET = offset

    def set_time_constant(self, time_constant = None):
        if time_constant is None:
            return self.time_constant
        elif 0 < time_constant < 1.0:
            self.time_constant = time_constant

    def power_down(self):
        self.pSCK.value(False)
        self.pSCK.value(True)

    def power_up(self):
        self.pSCK.value(False)
        
        
        
        
    #     def calibrate(self, known_weight = 2000): # 1 kilo
    #         
    #        # """Calibrate the scale using a known reference weight."""
    #        # print("Starting calibration... Place the known weight on the scale.")
    #         
    #        # raw_data = self.hx_mgr711.read_raw()  # Read raw data with the known weight on the scale
    #        # print(f"Raw data with reference weight: {raw_data}")
    # 
    #        # Calculate the calibration factor
    #        # self.calibration_factor = raw_data / known_weight
    #        # print(f"Calibration factor set to: {self.calibration_factor}")
    #         
    #                 
    #         self.empty_weight = self.read_average(10)
    #         
    #         time.sleep(2)  # Wait for the user to place the known weight
    #         
    #         self.reading_weight = self.read_average(10)
    #         
    #         raw_diff = self.reading_weight - self.empty_weight
    #         
    #         self.calibration_factor = raw_diff / known_weight  
    #         
    # 
    #     def getWeightInGrams(self):
    #         
    #         raw = self.read_average(times=10)
    #         return (raw - self.empty_weight) / self.calibration_factor
    #     
    #     def getWeightInKillo(self):
    #         
    #         calibrate()
    #         raw = self.read_average(times=10)
    #         return (raw - self.empty_weight) / self.calibration_factor
