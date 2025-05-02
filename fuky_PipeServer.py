import threading
import win32pipe
import win32file
import struct
import time
import numpy as np

class FUKY_PipeServer:
    def __init__(self):
        self.pipe_name = r'\\.\pipe\Fuky_DataPipe'
        self.pipe_handle = None
        self.isconnected = False
        self.Create_New_Pipe()
        self.Close_event = threading.Event()
        self.PipeManager_Threading = threading.Thread(target=self.PipeManager)
        self.Pipe_lock = threading.Lock()  # 发送数据锁
        
    def PipeManager(self):
        while not self.Close_event.is_set():
            if self.isconnected :
                time.sleep(1)
                #PipeServer.send_point_3d([1,1,1])
            else:
               self. wait_connection()
        self.close()

        
    def Create_New_Pipe(self):
        """创建新的管道实例"""
        if self.pipe_handle:
            win32file.CloseHandle(self.pipe_handle)
        self.pipe_handle = win32pipe.CreateNamedPipe(
            self.pipe_name,
            win32pipe.PIPE_ACCESS_DUPLEX,  # 双向通信更稳定
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_WAIT,
            1, 65536, 65536, 0, None)
    
    def wait_connection(self):
        """等待客户端连接"""
        print("等待客户端连接...")
        win32pipe.ConnectNamedPipe(self.pipe_handle, None)
        self.isconnected = True
        print("客户端已连接")
        return True

    
    def close(self):
        if self.pipe_handle:
            win32file.CloseHandle(self.pipe_handle)
            win32pipe.DisconnectNamedPipe(self.pipe_handle)
            self.pipe_handle = None
            
            
    def send_point_3d(self, point_3d):
        """
        发送三维坐标数据 (单位：毫米)
        :param point_3d: 三维坐标列表/数组 [X, Y, Z]
        """
        with self.Pipe_lock:
            if not self.isconnected:
                print("未连接客户端")
                return False
    
            try:
                # 确保数据格式正确
                if isinstance(point_3d, (np.ndarray, list)):
                    # 如果是OpenCV返回的3D点结构 (1,1,3)
                    if isinstance(point_3d, np.ndarray) and point_3d.ndim == 3:
                        x_mm = point_3d[0,0,0]   # 转换为毫米
                        y_mm = point_3d[0,0,1]
                        z_mm = point_3d[0,0,2]
                    else:  # 普通列表/数组
                        x_mm, y_mm, z_mm = [float(n)*1000 for n in point_3d[:3]]
                else:
                    raise TypeError("坐标数据格式错误，应为数组或列表")
    
                # 转换为米（根据Unity协议）
                x = x_mm / 1000.0
                y = y_mm / 1000.0
                z = z_mm / 1000.0
    
                # 小端字节序打包
                header = struct.pack('<I', 0xDEADBEEF)
                data = struct.pack('<3f', x, y, z)
                
                print(f"发送坐标：X={x_mm:.1f}mm Y={y_mm:.1f}mm Z={z_mm:.1f}mm")
                
                # 发送数据
                win32file.WriteFile(self.pipe_handle, header + data)
                return True
                
            except Exception as e:
                print(f"发送失败: {str(e)}")
                self._safe_close()
                return False
            
if __name__ == "__main__":
    PipeServer = FUKY_PipeServer()# 数据传输层
    PipeServer.PipeManager_Threading.start()

    