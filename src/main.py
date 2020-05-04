import sys, os
import sqlite3
from datetime import datetime, timedelta
import time
import threading
from queue import Queue
import logging
import random
import argparse
import colorama
import serial
from serial.tools import list_ports


CONSOLE_LEVEL_FORE_COLOR_TAB = {
    'debug': colorama.Fore.RESET,
    'info' : colorama.Fore.GREEN,
    'warning': colorama.Fore.YELLOW,
    'error': colorama.Fore.RED
}

PARITY_DICT = {'None': serial.PARITY_NONE, 'Even': serial.PARITY_EVEN,
               'Odd': serial.PARITY_ODD, 'Mask': serial.PARITY_MARK,
               'Space': serial.PARITY_SPACE}

STOPBITS_DIT = {'1' : serial.STOPBITS_ONE,
                '1.5' : serial.STOPBITS_ONE_POINT_FIVE,
                '2' : serial.STOPBITS_TWO}

def get_portlist_names():
    ports = []
    for comport in list_ports.comports():
        print(comport)
        port = comport[0]
        if (port.startswith('/dev/ttyACM') or port.startswith('/dev/ttyUSB') or
                port.startswith('COM') or
                port.startswith('/dev/cu.')):
            ports.append(port)
    return ports

def get_serial_port(portname, baud, bytesize, parity, stopbits):
    port = None
    port = serial.Serial(port=port,
                baudrate=baud,
                bytesize=bytesize,
                stopbits=stopbits,
                parity=PARITY_DICT[parity],
                timeout=0)
    return port

def get_time_diff_seconds(t1, t2):
    diff = t1 - t2;
    return diff.total_seconds()

def get_time_diff_milliseconds(t1, t2):
    diff = t1 - t2;
    return diff.total_seconds() * 1000

def datetime_test():
    delta = timedelta(days=50, seconds=27, microseconds=10, milliseconds=29000, minutes=5, hours=8, weeks=2)
    print(delta, delta.total_seconds())

def console_print(level, msg, fore_col=None):
    col = CONSOLE_LEVEL_FORE_COLOR_TAB.get(level, colorama.Fore.RED)
    if fore_col:
        col = fore_col
    print(col + msg + colorama.Style.RESET_ALL)

class PortRecvRecord(object):
    def __init__(self, echo=True, echo_coding='utf-8', new_line=b'\n'):
        self.__file_name = None
        self.__file_obj = None
        self.__echo = echo
        self.__echo_coding = echo_coding
        self.__new_line = new_line
        # print('PortRecvRecord Init')

    def write(self, data):
        if data:
            if self.__echo:
                print(data.decode(self.__echo_coding, errors='ignore'))
            if self.__file_obj:
                self.__file_obj.write(data + self.__new_line)

    def open(self, file_name=None):
        self.__file_name = file_name
        if not file_name:
            self.__file_name = datetime.now().strftime('%Y-%m-%d %H_%M_%S.log')
            print(self.__file_name)
        self.__file_obj = open(self.__file_name, 'wb') # 如果为'w', 则write() argument must be str, not bytes

    def close(self):
        self.__file_obj.close()
        self.__file_obj = None

class LineParse(object):
    def __init__(self, new_line=b'\n'):
        self.__remain = b'' # None
        self.__new_line = new_line
        #print('LineParse Init')

    def parse(self, data, force=False):
        dt_all = b'' # None
        if self.__remain:
            dt_all = self.__remain
            self.__remain = b''
        if data:
            dt_all += data
        
        if dt_all:
            dt_all = bytes(dt_all)
        else:
            return b'' # None
        
        lines = dt_all.split(self.__new_line)
        if force:
            return lines
        else:
            if len(lines) == 1:
                self.__remain = lines[0]
                return b''
            else:
                if lines[-1]:
                    self.__remain = lines[-1]
                    return lines[0:-1]
                else:
                    return lines


    def reset(self):
        self.__remain = b'' # None


class AppSerial(object):
    def __init__(self, recv_handle = None, baudrate=9600, bytesize=8, parity='None', stopbits='1'):
        self.__recv_handle = recv_handle
        self.__mutex = threading.Lock()
        self.__io_exception = False
        self.__read_thread_obj = None
        self.__line_queue = Queue() # 线程安全

        self.sport_obj = serial.Serial()
        self.sport_obj.baudrate = baudrate
        self.sport_obj.bytesize = bytesize
        self.sport_obj.parity = PARITY_DICT[parity]
        self.sport_obj.stopbits = STOPBITS_DIT[stopbits]
        self.sport_obj.timeout = None
        # print('AppSerial init')

    def open(self, port_name):
        if(self.sport_obj.isOpen()):
            cur_port_name = self.sport_obj.name
            if(cur_port_name.upper() == port_name.upper()):
                return True
            else:
                self.close() # release port opened
        try:
            self.sport_obj.port = port_name
            self.sport_obj.timeout = 0 # noblock read 
            self.sport_obj.port.open()
        except Exception as ex_msg:
            return False
        return True
    
    def close(self):
        self.sport_obj.close()

    def write(self, data):
        try:
            self.sport_obj.write(data)
        except Exception as ex_msg:
            self.sport_obj.close()
            return False
        return True

    def read(self):
        try:
            data = self.sport_obj.read()
        except Exception as ex_msg:
            return None, False
        return data, True

    def _recv_task(self):
        try:
            while True:
                if self.__recv_handle:
                    dat = self.sport_obj.read()
                    self.__recv_handle(dat)
                else:
                    dat = self.sport_obj.readline()
                    self.__line_queue.put(dat)
        except Exception as ex_msg:
            self.__io_exception = True;

    def mopen(self, port_name):
        if(self.sport_obj.isOpen()):
            cur_port_name = self.sport_obj.name
            if(cur_port_name.upper() == port_name.upper()):
                return True
            else:
                self.mclose() # release port opened
        try:
            self.sport_obj.port = port_name
            self.sport_obj.timeout =None # block read 
            self.sport_obj.port.open()
            self.__io_exception = False
            self.__read_thread_obj = threading.Thread(target=self._recv_task, name="reveive handle")
            self.__read_thread_obj.setDaemon(True) # 设置为后台线程
            self.__read_thread_obj.start()
        except Exception as ex_msg:
            self.__read_thread_obj = None
            return False
        return True

    def mclose(self):
        self.sport_obj.close()
        if self.__read_thread_obj:
            self.__read_thread_obj.join() # 等待线程结束
            self.__read_thread_obj = None
        self.__io_exception = False

    def mwrite(self, data):
        return self.write(data)

    def mread(self):
        if self.__io_exception:
            self.mclose()
        if not self.sport_obj.isOpen():
            return None, False
        data = None
        if not self.__line_queue.empty: 
            data = self.__line_queue.get()
        return data, False
    

def list_serial_device():
    lp = list_ports.comports()
    if lp:
        for comport in lp:
            console_print('info', str(comport))
    else:
       console_print('info', 'no device') 

def arg_parse_setup(args=None):
    Version = '0.0.1'
    epi = ""
    parser = argparse.ArgumentParser(description='serial helper utility', epilog=epi)
    parser.add_argument('-v','--version', action='version', version=Version)
    parser.add_argument('-l', '--list', dest='list', action="store_true", help="list the current serial device of the system")
    parser.add_argument("-p", '--port', metavar='COMxx', dest='port', default=None, help="specify communication serial port name, such as COM1")
    parser.add_argument('-e', '--echo', dest='echo', action="store_true", help="echo enable")

    if args:
        return parser.parse_args(args.split())
    else:
        return parser.parse_args() 

def task_run():
    AT_COMMAND_CTRL = [
        [b'at+rmsgadv=112233445566,5,1600', 5000, 1500 * 1000],
        [b'at+rmsghex=0027001f,8,0204', 5000, 1000],
        [b'at+rmsghex=0048002c,8,0204', 5000, 1000],
        [b'at+rmsghex=0037002d,8,0204', 5000, 1000],
        [b'at+rmsghex=0040004a,8,0204', 5000, 1000],
        [b'at+rmsghex=003b0026,8,0204', 5000, 1000],
        [b'at+rmsghex=004b0035,8,0204', 5000, 1000],
        [b'at+rmsghex=0042001b,8,0204', 5000, 1000],
        [b'at+rmsghex=002f002b,8,0204', 5000, 1000],
        [b'at+rmsghex=003A003C,8,0204', 5000, 1000],
        [b'at+rmsghex=003f0031,8,0204', 5000, 1000],
    ]

    args = arg_parse_setup()

    if args.list:
        list_serial_device()
    if not args.port:
        return

    sport_read_line_parse = LineParse()

    # sport = AppSerial()
    # if not sport.open(args.port):
    #     console_print('error', 'port open fail')
    #     return

    sport_read_recorder= PortRecvRecord(echo = args.echo)
    sport_read_recorder.open()

    cmd_list_inx = 0
    cmd_sta = 0

    try:
        while True:
            # 如串口数据并记录
            data, sta = b'abcd\nef', True # sport.read()
            if sta:
                lines = sport_read_line_parse.parse(data)
                for l in lines: 
                    sport_read_recorder.write(l)
            else:
                # sport.close()
                sport_read_recorder.close()

            # if cmd_sta == 0:
            #     sport.write(b'\xFF\xFF' + AT_COMMAND_CTRL[cmd_list_inx] + b'\r\n')
            

            time.sleep(0.1)
    except Exception as ex_msg:
        print('err', ex_msg)
    except KeyboardInterrupt:
        print('err', 'KeyboardInterrupt')
    finally:
        # sport.close()
        sport_read_recorder.close()


if __name__ == '__main__':
    colorama.init()
    # datetime_test()

    task_run()


