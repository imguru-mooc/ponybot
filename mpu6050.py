# mpu6050.py
# ESP32 MicroPython용 MPU6050(자이로/가속도) 라이브러리
# 교재와 동일한 사용법:  imu = mpu6050.accel(i2c, 0x69)  /  imu.get_values()
#   반환 키: AcX, AcY, AcZ, Tmp, GyX, GyY, GyZ

class accel():
    def __init__(self, i2c, addr=0x68):
        self.iic = i2c
        self.addr = addr
        # 슬립 해제 (PWR_MGMT_1 = 0)
        self.iic.writeto(self.addr, bytearray([107, 0]))

    def get_raw_values(self):
        # 0x3B부터 14바이트: AcX,AcY,AcZ, Temp, GyX,GyY,GyZ
        return self.iic.readfrom_mem(self.addr, 0x3B, 14)

    def get_ints(self):
        b = self.get_raw_values()
        return [self.bytes_toint(b[i], b[i + 1]) for i in range(0, len(b), 2)]

    def bytes_toint(self, msb, lsb):
        if not msb & 0x80:
            return msb << 8 | lsb
        return -(((msb ^ 255) << 8) | (lsb ^ 255) + 1)

    def get_values(self):
        raw = self.get_ints()
        return {
            'AcX': raw[0],
            'AcY': raw[1],
            'AcZ': raw[2],
            'Tmp': round(raw[3] / 340.00 + 36.53, 2),  # ℃
            'GyX': raw[4],
            'GyY': raw[5],
            'GyZ': raw[6],
        }
