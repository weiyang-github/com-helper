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
    diff = t1 - t2
    return diff.total_seconds()

def get_time_diff_milliseconds(t1, t2):
    diff = t1 - t2
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
            self.sport_obj.open()
        except Exception as ex_msg:
            print('sport open err', ex_msg)
            return False
        return True
    
    def close(self):
        self.sport_obj.close()

    def write(self, data):
        try:
            self.sport_obj.write(data)
        except Exception as ex_msg:
            print('sport write err', ex_msg)
            self.sport_obj.close()
            return False
        return True

    def read(self):
        try:
            data = self.sport_obj.read(1000)
        except Exception as ex_msg:
            print('sport read err', ex_msg)
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
            self.__io_exception = True

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
            self.sport_obj.open()
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
    parser.add_argument("-c", '--count', metavar='', dest='count', default=None, help="specify the count of command list executing")
    parser.add_argument('-e', '--echo', dest='echo', action="store_true", help="echo enable")

    if args:
        return parser.parse_args(args.split())
    else:
        return parser.parse_args() 

    
class CmdSendCtrl(object):
    def __init__(self):
        super().__init__() # 一定要显示调用父类初始化方法(也就是构造方法)，python不会自动调用
        self.STA_IDLE, self.STA_SEND_CMD, self.SEND_DELAY = range(3)
        self.__index = 0
        self.__sta = self.STA_IDLE
        self.__cnt_max = 0
        self.__cnt = 0
        self.__ctrl_tab = None
        self.__ctrl_tab_len = 0
        self.__cmd_wr_if = None
        self.__cmd_send_delay = 0

        self.__tmst = datetime.now()
        self.__inject_cmd = None
        self.__inject_cmd_ongoing = False
        
    def start(self, ctrl_tab, cmd_wr_if, loop_cnt):
        self.__sta = self.STA_IDLE
        self.__cnt = 0
        self.__cnt_max = loop_cnt
        self.__index = 0
        self.__ctrl_tab = ctrl_tab
        self.__ctrl_tab_len = 0
        self.__cmd_wr_if = cmd_wr_if
        if self.__ctrl_tab:
            self.__ctrl_tab_len = len(self.__ctrl_tab)
        if (self.__ctrl_tab_len > 0) and self.__cmd_wr_if:
            self.__sta = self.STA_SEND_CMD
            return True
        else:
            return False

    def inject_cmd_put(self, cmd):
        self.__inject_cmd = cmd

    def run(self):
        ret = True
        if self.__sta == self.STA_IDLE:
            pass
        elif self.__sta == self.STA_SEND_CMD:
            if self.__inject_cmd:
                msg = b'\xFF\xFF' + self.__inject_cmd[0] + b'\r\n'
                self.__cmd_send_delay = self.__inject_cmd[1]
                self.__inject_cmd = None
                self.__inject_cmd_ongoing = True
            else:
                msg = b'\xFF\xFF' + self.__ctrl_tab[self.__index][0] + b'\r\n'
                self.__cmd_send_delay = self.__ctrl_tab[self.__index][1]

            ret = self.__cmd_wr_if(msg)
            self.__tmst = datetime.now() # 记录发送时间戳
            self.__sta = self.SEND_DELAY

            print(self.__tmst, '->', msg)
        elif self.__sta == self.SEND_DELAY:
            if get_time_diff_milliseconds(datetime.now(), self.__tmst) > self.__cmd_send_delay:
                self.__sta = self.STA_SEND_CMD
                if self.__inject_cmd_ongoing:
                    self.__inject_cmd_ongoing = False
                else:
                    self.__index += 1
                    if self.__index >= self.__ctrl_tab_len:
                        self.__index = 0
                        self.__cnt += 1
                        if (self.__cnt_max > 0) and (self.__cnt >= self.__cnt_max):
                            self.__sta = self.STA_IDLE
                            ret = False
        else:
            self.__sta = self.STA_IDLE

        return ret

def task_run():
    AT_COMMAND_CTRL2 = [
        [b'at+rmsghex=0027001f,8,0204', 6000, 0],
        [b'at+rmsghex=0048002c,8,0204', 6000, 0],
        [b'at+rmsghex=0037002d,8,0204', 6000, 0],
        [b'at+rmsghex=0040004a,8,0204', 6000, 0],
        [b'at+rmsghex=003b0026,8,0204', 6000, 0],
        [b'at+rmsghex=004b0035,8,0204', 6000, 0],
        [b'at+rmsghex=0042001b,8,0204', 6000, 0],
        [b'at+rmsghex=002f002b,8,0204', 6000, 0],
        [b'at+rmsghex=003A003C,8,0204', 6000, 0],
        [b'at+rmsghex=003f0031,8,0204', 6000, 0],
    ]

    AT_COMMAND_CTRL2 = []
    cmd_addr_rand_tab = random.sample(range(1, 0xFFFFFFFF), 2)
    for cmd_addr in cmd_addr_rand_tab:
        cmd_port = 8
        cmd_data = '0204'
        cmd_all = 'at+rmsghex={:08x},{},{}'.format(cmd_addr, cmd_port, cmd_data)
        cmd_item = [bytes(cmd_all, encoding='utf-8'), 6000, 0]
        # print(cmd_item)
        AT_COMMAND_CTRL2.append(cmd_item)

    args = arg_parse_setup()
    print(args)

    if args.list:
        list_serial_device()
    if not args.port:
        return

    if not args.count:
        args.count = 0
    else:
        args.count = int(args.count)
    print('args.count', args.count)

    sport_read_line_parse = LineParse()

    sport = AppSerial()
    if not sport.open(args.port):
        args.port = args.port.upper()
        console_print('error', '{} open fail'.format(args.port))
        return

    sport_read_recorder= PortRecvRecord(echo = args.echo)
    sport_read_recorder.open()

    inject_cmd = [b'at+rmsgadv=112233445566,5,1600', 8000, 1500 * 1000]
    send_ctrl = CmdSendCtrl()
    send_ctrl.inject_cmd_put(inject_cmd)
    inject_cmd_put_tmst = datetime.now()
    inject_cmd_delay = inject_cmd[2]
    ret = send_ctrl.start(AT_COMMAND_CTRL2, sport.write, args.count)
    if not ret:
        print('send_ctrl start fail')
        return
    try:
        while True:
            # 读串口数据并记录
            data, sta = sport.read()#b'abcd\nef', True # 
            if sta:
                lines = sport_read_line_parse.parse(data)
                for l in lines: 
                    sport_read_recorder.write(l)
            else:
                # sport.close()
                # sport_read_recorder.close()
                return

            if not send_ctrl.run():
                print('send_ctrl run fail')
                # sport.close()
                # sport_read_recorder.close()
                return # return 在try finally语句中时仍会执行finally内容

            if get_time_diff_milliseconds(datetime.now(), inject_cmd_put_tmst) > inject_cmd_delay:
                send_ctrl.inject_cmd_put(inject_cmd)
                inject_cmd_put_tmst = datetime.now()
            
            time.sleep(1)
    except Exception as ex_msg:
        print('err main', ex_msg)
    except KeyboardInterrupt: # Exception 不能捕获KeyboardInterrupt
        print('err main', 'KeyboardInterrupt')
    finally:
        sport.close()
        sport_read_recorder.close()
        print('test complete')


if __name__ == '__main__':
    colorama.init()
    # datetime_test()

    task_run()


