import threading
import serial.tools.list_ports
import struct
import threading
import time

import cv2
import numpy as np

#FUKY LOCATOR的基础
#更多注释会在后面添加
#暂时没有添加自动区分左右镜头的功能，暂时确定img_data1是左边，img_data2是右边，如果重启电脑或插拔位置不对，就会改变
#还有一些小bug



class FUKY_deviceBase():
    
    def __init__(self):
        self.device_port1 = None
        self.device_port2 = None
        self.serial_ser1 = None
        self.serial_ser2 = None
        self.serial_IsConnect = False
        self.img_data1 = None
        self.img_data2 = None
        
        self.TARGET_VID = 0x2333
        self.TARGET_PID = 0x6666
        self.baudrate = 926100
        

        #FUKY主线程
        self.FUKY_Device_MainThread = threading.Thread(target=self.FUKY_Device_Main)
        #用来获取设备引用，最先开始进入的支线程，其他进程发现出问题后就会断开连接，然后重新进入该线程
        self.FindingDevice_thread = threading.Thread(target=self.Finding_Device)
        #两个用来交叉获取图像数据的线程，当找到设备并验证通讯后就会开始，退出条件是通讯断开
        self.Cam1_thread = threading.Thread(target=self.getport1_image_Asyn)
        self.Cam2_thread = threading.Thread(target=self.getport2_image_Asyn)
        #全局线程事件
        self.Stop_Cam_event = threading.Event()
        self.Close_event = threading.Event()
        self.img1_Data_event = threading.Event()
        self.img2_Data_event = threading.Event()
        #线程锁，防止其他异步执行的逻辑读取到出错的图像
        self.FukyWriting_lock_1 = threading.Lock()
        self.FukyWriting_lock_2 = threading.Lock()

        # ---------- 设备连接线程 ----------

    def Finding_Device(self):
        self.Clear_Connect()
        time.sleep(1)
        print("搜索FUKY LOCATOR设备...")
        while self.device_port1 == None or self.device_port2 == None:
            self.find_fuky_locator_port()
            time.sleep(1)
        while not self.serial_IsConnect:
            self.get_ser_test_connect()      

    def find_fuky_locator_port(self):
        """查找设备并返回端口""" 
        # 获取所有串口设备
        ports = serial.tools.list_ports.comports()
        for port in ports:
            # 检查VID/PID
            if port.vid == self.TARGET_VID and port.pid == self.TARGET_PID:
                print(f"找到匹配VID/PID的设备: {port.device}")
                if self.device_port1 == None:
                    self.device_port1 = port.device
                elif self.device_port2 == None:
                    self.device_port2 = port.device
                else: print("不可能有三个摄像头")
    
    def get_ser_test_connect(self):
        if not self.device_port1 and self.device_port2:
            raise Exception("设备未连接，需要两个摄像头")
        try:
            # 打开串口连接，设置适当的参数
            self.serial_ser1 = serial.Serial(self.device_port1, self.baudrate, timeout=1)
            self.serial_ser2 = serial.Serial(self.device_port2, self.baudrate, timeout=1)
            print(f"已连接到 {self.serial_ser1}和{self.serial_ser2}，正在发送测试数据...")
            if self.test_connect(self.serial_ser1) and self.test_connect(self.serial_ser2):
                self.serial_IsConnect = True
                self.start_stream_command()
                return True
        except serial.SerialException as e:
            print(f"连接失败: {e}")
            return False
    
        except serial.SerialException as e:
            print(f"串口通讯错误: {e}")
            return False  
        except Exception as e:
            print(f"发生意外错误: {e}")
            return False  

    def test_connect(self,ser):
        try:
            # 发送测试命令
            test_data = "233"
            ser.write(test_data.encode('utf-8'))
            response = ser.readline().decode('utf-8').strip()
            
            if response == test_data:
                print("初始化成功")
                return True
            else:
                print(f"响应异常: {response}")
                return False
        except Exception as e:
            print(f"连接失败: {str(e)}")
            return False
              
        # ---------- 主线程 ----------
    
    def FUKY_Device_Main(self):
        """主进程"""
        while not self.Close_event.is_set():
            if not self.FindingDevice_thread.is_alive():
                self.FindingDevice_thread.start()
                self.FindingDevice_thread.join()
                self.Cam1_thread.start()
                self.Cam2_thread.start()
                self.Cam1_thread.join()
                self.Cam2_thread.join()
                time.sleep(5)
                self.Clear_And_Restart()

        # ---------- 数据读取线程 ----------

    def getport1_image_Asyn(self):
        print("开始接收来自cam1的数据...")
        # 等待帧头0xAA 0x55
        while not self.Stop_Cam_event.is_set():
            try:
                while not self.Stop_Cam_event.is_set():
                    header1 = self.serial_ser1.read(1)
                    if not header1:
                        continue
                    if ord(header1) == 0xAA:
                        header2 = self.serial_ser1.read(1)
                        if header2 and ord(header2) == 0x55:
                            break
                # 读取图像长度（4字节）
                len_bytes = self.serial_ser1.read(4)
                if len(len_bytes) != 4:
                    print("Error: 无法读取完整长度信息")
                    continue
                img_len = struct.unpack('<I', len_bytes)[0]  # 小端格式解包
                # 读取图像数据
                imgdata = self.serial_ser1.read(img_len)
                if len(imgdata) != img_len:
                    print(f"Error: 数据不完整，期望 {img_len} 字节，实际收到 {len(self.imgdata)} 字节")
                    continue
                
                # 检查帧尾0x55 0xAA
                footer1 = self.serial_ser1.read(1)
                footer2 = self.serial_ser1.read(1)
                if not footer1 or not footer2 or ord(footer1) != 0x55 or ord(footer2) != 0xAA:
                    print("Error: 帧尾不匹配")
                    continue
                with self.FukyWriting_lock_1:
                    self.img_data1 = imgdata
                self.img1_Data_event.set()
            except Exception as e:
                print("\n已断开连接")
                break

    def getport2_image_Asyn(self):
        # 等待帧头0xAA 0x55
        print("开始接收来自cam2的数据...")
        while not self.Stop_Cam_event.is_set():
            try:
                while not self.Stop_Cam_event.is_set():
                    header1 = self.serial_ser2.read(1)
                    if not header1:
                        continue
                    if ord(header1) == 0xAA:
                        header2 = self.serial_ser2.read(1)
                        if header2 and ord(header2) == 0x55:
                            break
                # 读取图像长度（4字节）
                len_bytes = self.serial_ser2.read(4)
                if len(len_bytes) != 4:
                    print("Error: 无法读取完整长度信息")
                    continue
                img_len = struct.unpack('<I', len_bytes)[0]  # 小端格式解包
                # 读取图像数据
                imgdata = self.serial_ser2.read(img_len)
                if len(imgdata) != img_len:
                    print(f"Error: 数据不完整，期望 {img_len} 字节，实际收到 {len(self.imgdata)} 字节")
                    continue
                
                # 检查帧尾0x55 0xAA
                footer1 = self.serial_ser2.read(1)
                footer2 = self.serial_ser2.read(1)
                if not footer1 or not footer2 or ord(footer1) != 0x55 or ord(footer2) != 0xAA:
                    print("Error: 帧尾不匹配")
                    continue
                with self.FukyWriting_lock_2:
                    self.img_data2 = imgdata
                self.img2_Data_event.set()
            except Exception as e:
                print("已断开连接")
                break
       
        # ---------- 断连重启 ----------
    
    def create_newthread(self):
        # 创建新线程实例
        self.FindingDevice_thread = threading.Thread(target=self.Finding_Device)
        self.Cam1_thread = threading.Thread(target=self.getport1_image_Asyn)
        self.Cam2_thread = threading.Thread(target=self.getport2_image_Asyn)
   
    def is_physically_connected(self, port_name):
        """检查端口是否真实存在"""
        return any(p.device == port_name for p in serial.tools.list_ports.comports())


        # ---------- 数据流控制 ----------
    def start_stream_command(self):
        """启动视频流"""
        return self._send_command(1)

    def stop_stream_command(self):
        """停止视频流"""
        return self._send_command(0)

    def _send_command(self, code: int):
        """内部方法：发送控制命令"""
        if not self.serial_IsConnect:
            return False
        try:
            self.serial_ser1.write([code])
            self.serial_ser2.write([code])
            return True
        except serial.SerialException:
            return False
        
        # ---------- 清理关闭 ----------
        
    def Clear_And_Restart(self):
        """停止所有正在进行的摄像机数据读取进程"""
        """安全断开所有串口连接"""
        """重置所有事件"""
        """新建新的进程"""
        self.stop_stream_command()
        self.Stop_Cam_event.set()
        #self.Close_event.set()
        self.Cam1_thread.join()
        self.Cam2_thread.join()
        
        if self.serial_ser1 != None or self.serial_ser2 != None:
            if self.serial_ser1 or self.serial_ser1.is_open:
                self.serial_ser1.close()
                self.serial_ser1 = None
            if self.serial_ser2 or self.serial_ser2.is_open:
                self.serial_ser2.close()
                self.serial_ser2 = None
            print("关闭串口")
        self.device_port1 = None
        self.device_port2 = None
        self.serial_IsConnect = False

        self.Stop_Cam_event.clear()
        self.img1_Data_event.clear()
        self.img2_Data_event.clear()
        print("关闭端口和清理事件")
        self.create_newthread()
        print("已经重启设备搜索线程")


    def Close_FUKY_Device(self):
        self.Stop_Cam_event.set()
        self.Close_event.set()
        
    def Clear_Connect(self):
        """如果有正在运行的读取线程就停止，并新建新的进程"""
        """安全断开所有串口连接"""
        """重置所有事件"""
        if(self.Cam1_thread.is_alive() or self.Cam2_thread.is_alive()):
            self.stop_stream_command()
            self.Stop_Cam_event.set()
            self.Cam1_thread.join()
            self.Cam2_thread.join()
            self.create_newthread()
        if self.serial_ser1 != None or self.serial_ser2 != None:
            if self.serial_ser1 or self.serial_ser1.is_open:
                self.serial_ser1.flush()
                self.serial_ser1.close()
                self.serial_ser1 = None
            if self.serial_ser2 or self.serial_ser2.is_open:
                self.serial_ser2.flush()
                self.serial_ser2.close()
                self.serial_ser2 = None
        self.device_port1 = None
        self.device_port2 = None
        self.serial_IsConnect = False

        self.Stop_Cam_event.clear()
        self.img1_Data_event.clear()
        self.img2_Data_event.clear()

        # ---------- 测试显示 ----------
    def _show_images(self):
        """OpenCV图像显示线程"""
        cv2.namedWindow('Camera 1', cv2.WINDOW_NORMAL)
        cv2.namedWindow('Camera 2', cv2.WINDOW_NORMAL)
        
        while not self.Close_event.is_set():
            try:
                # 获取并显示摄像头1图像
                with self.FukyWriting_lock_1:
                    data1 = self.img_data1
                if data1:
                    img1 = cv2.imdecode(np.frombuffer(data1, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img1 is not None:
                        cv2.imshow('Camera 1', img1)
                
                # 获取并显示摄像头2图像
                with self.FukyWriting_lock_2:
                    data2 = self.img_data2
                if data2:
                    img2 = cv2.imdecode(np.frombuffer(data2, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img2 is not None:
                        cv2.imshow('Camera 2', img2)
                
                # 检测退出按键
                if cv2.waitKey(25) & 0xFF == ord('q'):
                    self.Close_FUKY_Device()
                    break
            except Exception as e:
                print(f"显示异常: {str(e)}")
                break
                
        cv2.destroyAllWindows()          
                
          

if __name__ == "__main__":

    fukydevice = FUKY_deviceBase()
    FUKY_Device_Thread = threading.Thread(target=fukydevice.FUKY_Device_Main)
    img_test_Thread = threading.Thread(target=fukydevice._show_images)
    FUKY_Device_Thread.start()
    img_test_Thread.start()


    
    
    