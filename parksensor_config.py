from waviotmodem import WaviotModem
from appJar import gui
import re
from time import sleep
from binascii import hexlify
import threading
from serial_ports import serial_ports

class flasher():

    retry_limit = 10

    def __init__(self, dongle, filename, block_size=64):

        if filename == None:
            return

        self.file = open(filename, 'rb')
        self.fw_size = self.getSize(self.file)# - 2048
        self.file = open(filename, 'rb')

        self.block_size = block_size
        # for i in range(32):
        #     buff = self.file.read(self.block_size)

        self.fw_block_it = 1

        self.dongle = dongle
        self.crc = 0
        self.fw_uploaded_size = 0

        self.window = gui()
        self.window.setFont(12)
        self.window.addMessage("mess", "flashing...")
        self.window.addMeter("progress")
        # self.thr = threading.Thread(target=self.upload_firmware)
        self.window.registerEvent(self.upload_progress)
        self.window.setPollTime(100)
        # self.thr.start()
        self.window.go()
        # self.thr.join()
        # self.window.stop()

    def getSize(self, fileobject):
        fileobject.seek(0,2) # move the cursor to the end of the file
        size = fileobject.tell()
        return size

    def upload_progress(self):

        # while self.fw_uploaded_size < self.fw_size:
            self.window.setMeter("progress", float(self.fw_uploaded_size) / float(self.fw_size) * 100)
            buff = self.file.read(self.block_size)

            if len(buff) < self.block_size:
                while len(buff) != self.block_size:
                    buff = buff + chr(0xFF)

            for i in range(self.block_size):
                self.crc = 0xFFFF & (self.crc >> 8) | (self.crc << 8)
                self.crc ^= 0xFFFF & ord(buff[i])
                self.crc ^= 0xFFFF & (self.crc & 0xff) >> 4
                self.crc ^= 0xFFFF & self.crc << 12
                self.crc ^= (self.crc & 0xff) << 5

            acked, id, num = None, None, None
            for i in range(self.retry_limit):
                acked, id, num = self.broadcast_cmd([0x03, (self.fw_block_it >> 8) & 0xFF, self.fw_block_it & 0xFF], buff)
                if acked:
                    break
                print("Retry")

            if not acked:
                if id:
                    print("flashing modem " + hexlify(id) + " failed on block " + str(self.fw_block_it))
                else:
                    print("nobody acked")
                self.window.stop()
                return

            print (hexlify(id) + ' acked on ' + str(self.fw_block_it))

            self.fw_block_it += 1

            self.fw_uploaded_size += self.block_size

            if self.fw_uploaded_size >= self.fw_size:
                self.dongle.transmit(chr(0x02) + chr((self.crc >> 8) & 0xFF) + chr(self.crc & 0xFF))
                self.window.unregisterEvent(self.upload_progress)
                self.window.stop()

    def upload_firmware(self):

        while self.fw_uploaded_size < self.fw_size:
            buff = self.file.read(self.block_size)

            if len(buff) < self.block_size:
                while len(buff) != self.block_size:
                    buff = buff + chr(0xFF)

            for i in range(self.block_size):
                self.crc = 0xFFFF & (self.crc >> 8) | (self.crc << 8)
                self.crc ^= 0xFFFF & ord(buff[i])
                self.crc ^= 0xFFFF & (self.crc & 0xff) >> 4
                self.crc ^= 0xFFFF & self.crc << 12
                self.crc ^= (self.crc & 0xff) << 5

            acked, id, num = None, None, None
            for i in range(self.retry_limit):
                acked, id, num = self.broadcast_cmd([0x03, (self.fw_block_it >> 8) & 0xFF, self.fw_block_it & 0xFF], buff)
                if acked:
                    break
                print("Retry")

            if not acked:
                if id:
                    print("flashing modem " + hexlify(id) + " failed on block " + str(self.fw_block_it))
                else:
                    print("nobody acked")
                self.window.stop()
                return

            print (hexlify(id) + ' acked on ' + str(self.fw_block_it))

            self.fw_block_it += 1

            self.fw_uploaded_size += self.block_size

        if self.fw_uploaded_size >= self.fw_size:
            self.dongle.transmit(chr(0x02) + chr((self.crc >> 8) & 0xFF) + chr(self.crc & 0xFF))
            self.window.unregisterEvent(self.upload_progress)
            self.window.stop()

    def broadcast_cmd(self, cmdlist, data=None, WATRANSMIT=0.1, WFRETRY=0.1):
        buffer = ''
        for cmd in cmdlist:
            buffer += chr(cmd)
        buffer += data

        self.dongle.transmit(buffer)
        sleep(WATRANSMIT)
        acked = False
        id = None
        num = None

        for i in range(3):
            sleep(WFRETRY)
            msg = self.dongle.receive_downlink()
            if msg and len(msg) > 12:
                id = msg[1:4]
                ack = msg[6:11]
                num = msg[12:]
                if ack == 'PKTOK':
                    acked = True
                    break

        return acked, id, num

class searcher():

    def __init__(self, dongle, retries = 20):
        self.dongle = dongle
        self.discover_percent = 0
        self.id = None

        self.retries = retries
        self.maxretries = retries

        self.window = gui('Search for available sensors...')
        self.window.setGeometry(200, 100)
        self.window.addMeter("modem_discover")
        self.window.registerEvent(self.refresh_modems)
        self.window.setPollTime(1500)
        self.run = True
        self.window.go()

    def refresh_modems(self):
        self.dongle.transmit(chr(0x04))
        self.window.setMeter("modem_discover", (1.0 - float(self.retries) / float(self.maxretries)) * 100.0)
        s = self.dongle.receive_downlink()
        if s:
            id = s[1:4]
            answer = s[6:]
            if answer == 'FWUPD':
                self.window.infoBox("Notification", 'Found {}'.format(hexlify(id)))
                if self.run:
                    self.run = False
                    self.window.unregisterEvent(self.refresh_modems)
                    self.id = id
                    self.window.stop()
        elif self.retries:
            self.retries -= 1
        elif self.run:
            self.window.infoBox("Notification", 'No parksensors found')
            self.run = False
            self.window.unregisterEvent(self.refresh_modems)
            self.window.stop()

class parksensor_config_app():

    def __init__(self):
        self.pre_main = gui()
        self.popup = gui()

        self.firmware_path = None
        self.fw_uploaded_size = 0
        self.discover_percent = 0
        self.crc = 0
        self.dongle = None

        self.main = gui()
        self.main.setGeometry(500, 300)
        self.main.addLabel("fw_path", self.display_path(self.firmware_path, 20), 0, 0)

        self.main.addMenuList("Firmware", ["Open firmware"], self.file_menu)

        self.main.addMenuList("Dongle connection", serial_ports(), self.connect_to_dongle)

        self.main.addMenuList("Flash", ["Connect to sensor", "-", "Flash firmware", "Read settings", "Write settings"], self.flash_menu)

        self.main.addLabelSpinBoxRange("Angle average window size", 1, 50)
        self.main.setSpinBox("Angle average window size", 5, callFunction=False)

        self.main.addLabelSpinBoxRange("Angle derivative threshold", 10, 500)
        self.main.setSpinBox("Angle derivative threshold", 100, callFunction=False)

        self.main.addLabelSpinBoxRange("Angle derivative window size", 1, 50)
        self.main.setSpinBox("Angle derivative window size", 10, callFunction=False)

        self.main.addLabelSpinBoxRange("Angle zero derivative threshold", 1, 200)
        self.main.setSpinBox("Angle zero derivative threshold", 10, callFunction=False)

        self.main.addLabelSpinBoxRange("Flags", 0, 65535)
        self.main.setSpinBox("Flags", 65535, callFunction=False)

        self.main.addLabelSpinBoxRange("IIR average window size", 10, 500)
        self.main.setSpinBox("IIR average window size", 200, callFunction=False)

        self.main.addLabelSpinBoxRange("Calibration time", 0, 500)
        self.main.setSpinBox("Calibration time", 200, callFunction=False)

        self.main.addLabelSpinBoxRange("Parking time", 10, 200)
        self.main.setSpinBox("Parking time", 60, callFunction=False)

        self.main.addLabelSpinBoxRange("Threshold high", 10, 20000)
        self.main.setSpinBox("Threshold high", 1000, callFunction=False)

        self.main.addLabelSpinBoxRange("Threshold low", 10, 2000)
        self.main.setSpinBox("Threshold low", 600, callFunction=False)

        self.main.addLabelSpinBoxRange("Threshold zero", 10, 1000)
        self.main.setSpinBox("Threshold zero", 200, callFunction=False)

        self.main.go()

    def read_params(self):
        self.dongle.transmit(chr(0x10))
        mes = self.dongle.receive_downlink()
        while not mes or len(mes) != 28:
            mes = self.dongle.receive_downlink()
        print hexlify(mes)
        self.main.setSpinBox("Angle average window size", (ord(mes[6]) << 8) + ord(mes[7]), callFunction=False)
        self.main.setSpinBox("Angle derivative threshold", (ord(mes[8]) << 8) + ord(mes[9]), callFunction=False)
        self.main.setSpinBox("Angle derivative window size", (ord(mes[10]) << 8) + ord(mes[11]), callFunction=False)
        self.main.setSpinBox("Angle zero derivative threshold", (ord(mes[12]) << 8) + ord(mes[13]), callFunction=False)
        self.main.setSpinBox("Flags", (ord(mes[14]) << 8) + ord(mes[15]), callFunction=False)
        self.main.setSpinBox("IIR average window size", (ord(mes[16]) << 8) + ord(mes[17]), callFunction=False)
        self.main.setSpinBox("Calibration time", (ord(mes[18]) << 8) + ord(mes[19]), callFunction=False)
        self.main.setSpinBox("Parking time", (ord(mes[20]) << 8) + ord(mes[21]), callFunction=False)
        self.main.setSpinBox("Threshold high", (ord(mes[22]) << 8) + ord(mes[23]), callFunction=False)
        self.main.setSpinBox("Threshold low", (ord(mes[24]) << 8) + ord(mes[25]), callFunction=False)
        self.main.setSpinBox("Threshold zero", (ord(mes[26]) << 8) + ord(mes[27]), callFunction=False)

    def write_params(self):
        aaws = int(self.main.getSpinBox("Angle average window size"))
        adt = int(self.main.getSpinBox("Angle derivative threshold"))
        adws = int(self.main.getSpinBox("Angle derivative window size"))
        azdt = int(self.main.getSpinBox("Angle zero derivative threshold"))
        f = int(self.main.getSpinBox("Flags"))
        iaws = int(self.main.getSpinBox("IIR average window size"))
        ct = int(self.main.getSpinBox("Calibration time"))
        pt = int(self.main.getSpinBox("Parking time"))
        th = int(self.main.getSpinBox("Threshold high"))
        tl = int(self.main.getSpinBox("Threshold low"))
        tz = int(self.main.getSpinBox("Threshold zero"))
        self.dongle.transmit(chr(0x0F) +
                             chr((aaws >> 8) & 0xFF) + chr(aaws & 0xFF) +
                             chr((adt >> 8) & 0xFF) + chr(adt & 0xFF) +
                             chr((adws >> 8) & 0xFF) + chr(adws & 0xFF) +
                             chr((azdt >> 8) & 0xFF) + chr(azdt & 0xFF) +
                             chr((f >> 8) & 0xFF) + chr(f & 0xFF) +
                             chr((iaws >> 8) & 0xFF) + chr(iaws & 0xFF) +
                             chr((ct >> 8) & 0xFF) + chr(ct & 0xFF) +
                             chr((pt >> 8) & 0xFF) + chr(pt & 0xFF) +
                             chr((th >> 8) & 0xFF) + chr(th & 0xFF) +
                             chr((tl >> 8) & 0xFF) + chr(tl & 0xFF) +
                             chr((tz >> 8) & 0xFF) + chr(tz & 0xFF))
        sleep(1)
        self.read_params()

    def flash_menu(self, btnName):
        if btnName == 'Flash firmware':
            if self.firmware_path:
                flasher(self.dongle, self.firmware_path)
            else:
                self.main.infoBox('Notification', 'choose firmware file')

        if btnName == 'Connect to sensor':
            if self.dongle:
                self.modem = searcher(self.dongle).id
            else:
                self.main.infoBox('Notification', 'dongle not connected')

        if btnName == 'Write settings':
            self.write_params()

        if btnName == 'Read settings':
            self.read_params()


    def file_menu(self, btnName):
        if btnName == 'Open firmware':
            self.firmware_path = self.main.openBox(title="Choose the firmware", dirName=None,
                                                   fileTypes=[('binary', '*.bin'), ('binary', '*.hex')], asFile=False)
            self.main.setLabel("fw_path", self.display_path(self.firmware_path, 20))


    def display_path(self, path, length):
        if path and len(path) > length:
            halflen = (length - 3)/2
            return path[0:halflen] + '...' + path[-halflen:len(path)]
        return path


    def apply_settings(self, btnName):
        global waviot, popup, main
        waviot.transmit(chr(0x10))
        while 1:
            print hexlify(waviot.port.read(1000))
        # mesg = waviot.receive()
        # if mesg:
        #     print hexlify(mesg)
        #     main.stop()
        #     break

    def connect_to_dongle(self, portName):
        if self.dongle and self.dongle.port.port == portName:
            self.pre_main.infoBox("Connection", 'Already connected to dongle on {}'
                                  .format(portName))
        self.dongle = WaviotModem(portName)
        self.dongle.set_fastDL()
        self.pre_main.infoBox("Connection", 'Successfully connected to dongle on {}'
                              .format(portName))

parksensor_config_app()