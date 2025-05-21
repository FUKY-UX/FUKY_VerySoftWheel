# FUKY驱动的架构 因为还在开发所以相对混乱
#⨠FUKYWindow(协调用的Main程序)，它会作为主进程启动整个程序
#⨠带有一个处理图像数据的支线程，并且会启动两个支进程，一个负责读取蓝牙数据，另一个负责处理数据发送的回调

# 主进程 UI + 视觉定位: FUKY_deviceBase(摄像头的底层通信类) - FUKY_DataHandler(摄像头的立体坐标计算类)            
# 支进程 FUKY_BleDeviceBase(处理蓝牙的IMU数据，避免处理图像造成的延迟)
# 支进程 FUKY_PipeServer(命名管道，向应用层提供数据时使用，相对独立) 
#
import multiprocessing
from fuky_data_Processing import FUKY_DataHandler
# from fuky_device_BleData import FUKY_BleDeviceBase
from fuky_ble_base import FUKY_BleBase
import threading
import cv2
import mmap
import os
import ctypes
from ctypes import wintypes

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QSystemTrayIcon, QMenu, 
                            QAction,QWidget,QSplitter,QVBoxLayout,QTextEdit,QMessageBox,QLabel)
from PyQt5.QtGui import QIcon,QPixmap,QImage
from PyQt5.QtCore import Qt,QTimer

class FUKYWindow(QMainWindow):
    
    
    def __init__(self):
        super().__init__()
        self.initUI()
        self.initTray()
        #self.initShareMem() #共享内存让各自进程线程自己创建即可
        # 图像处理线程，我暂时还没有利用更多的进程来处理，所以图像处理和UI更新都是在一个进程中更新
        # 这样效率相对低一些，但是算是历史遗留问题
        self.ImgDataHandler = FUKY_DataHandler()
        self.ImgDataHandler_Thread = threading.Thread(target=self.ImgDataHandler.FUKY_Data_Main)

        # 蓝牙处理的进程，利用多核CPU，提高效率，避免高频的IMU数据与低频的图像数据相互影响

        
        # 创建一个关闭事件对象
        self.close_event = multiprocessing.Event()
        
        # 实例化BLE基类
        self.ble_base = FUKY_BleBase(self.close_event)



# ---------- 初始化 ----------

    def initUI(self):
        # 添加定时器（主线程中运行）
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_images)
        self.timer.start(30)  # 约33帧/秒
        
        
        # 窗口基础设置
        self.showMaximized()
        self.setWindowTitle("FUKY_DRIVER")
        self.setGeometry(300, 300, 800, 600)
        self.setWindowIcon(QIcon("logo_PNG.png"))
        
        # 主窗口设置
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        
        # =====左侧内容区域（占2/3）========
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #f0f0f0;")
        left_splitter = QSplitter(Qt.Vertical)
        # 上半部分控件
        # === 上半部分：图片显示区 ===
        image_splitter = QSplitter(Qt.Horizontal)  # 水平分割器
        
        # 左图显示区域
        self.img_left = QLabel()
        self.img_left.setStyleSheet("background-color: #ffffff; border: 2px solid #999;")
        self.img_left.setAlignment(Qt.AlignCenter)
        self.img_left.setText("左图显示区域")
        
        # 右图显示区域
        self.img_right = QLabel()
        self.img_right.setStyleSheet("background-color: #ffffff; border: 2px solid #999;")
        self.img_right.setAlignment(Qt.AlignCenter)
        self.img_right.setText("右图显示区域")
        
        # 设置图片区比例（各占50%）
        image_splitter.addWidget(self.img_left)
        image_splitter.addWidget(self.img_right)
        image_splitter.setSizes([400, 400])  # 初始宽度根据主窗口大小调整
        # 下半部分控件
        bottom_widget = QWidget()
        bottom_widget.setStyleSheet("background-color: #ccffcc;")  # 测试用颜色
        # 将上下部分加入分割器
        left_splitter.addWidget(image_splitter)
        left_splitter.addWidget(bottom_widget)
        # 设置分割比例（示例：上半部40%，下半部60%）
        left_splitter.setSizes([int(left_widget.height()*0.4), int(left_widget.height()*0.6)])
        # 将分割器加入左侧主布局
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(left_splitter)
        # 右侧边栏（占1/3）
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.text_output.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #d0d0d0;
                font-family: "SimHei", "黑体", sans-serif;
                font-size: 24px;
            }
        """)
        self.text_output.append("程序启动...")
        right_layout.addWidget(self.text_output)
        
        # 设置左右部件比例 (2:1)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([self.width()*2//3, self.width()*1//3])
        
        # 主布局
        main_layout = QVBoxLayout(main_widget)
        main_layout.addWidget(splitter)

    def initTray(self):
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("logo_PNG.png"))  # 替换为你的图标路径
        self.tray_icon.show()  # 必须显式调用show()显示托盘图标
        # 创建托盘菜单
        tray_menu = QMenu()
        restore_action = QAction("恢复窗口", self)
        exit_action = QAction("退出", self)
        
        restore_action.triggered.connect(self.showNormal)
        exit_action.triggered.connect(self.quitApp)
        
        tray_menu.addAction(restore_action)
        tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)
        
        # 绑定双击事件
        self.tray_icon.activated.connect(self.trayDoubleClick)


# ---------- 更新视频显示 ----------

    def update_images(self):
        """更新图像显示"""
        try:
            # 安全获取图像数据
            with self.ImgDataHandler.imgProcessing_lock:
                process_img1 = self.ImgDataHandler.Process_img1
                process_img2 = self.ImgDataHandler.Process_img2
            
            # 更新左图
            if process_img1 is not None:
                try:
                    # 编码为JPEG字节流
                    _, jpeg_bytes1 = cv2.imencode('.jpg', process_img1, [cv2.IMWRITE_JPEG_QUALITY, 100])
                    
                    # 从字节数据创建QImage
                    qimage1 = QImage.fromData(jpeg_bytes1.tobytes())
                    
                    # 从QImage创建QPixmap
                    pixmap1 = QPixmap.fromImage(qimage1)
                    
                    # 设置图像
                    self.img_left.setPixmap(pixmap1)
                except Exception as e:
                    print(f"左图更新错误: {str(e)}")
            
            # 更新右图
            if process_img2 is not None:
                try:
                    # 编码为JPEG字节流
                    _, jpeg_bytes2 = cv2.imencode('.jpg', process_img2, [cv2.IMWRITE_JPEG_QUALITY, 100])
                    
                    # 从字节数据创建QImage
                    qimage2 = QImage.fromData(jpeg_bytes2.tobytes())
                    
                    # 从QImage创建QPixmap
                    pixmap2 = QPixmap.fromImage(qimage2)
                    
                    # 设置图像
                    self.img_right.setPixmap(pixmap2)
                except Exception as e:
                    print(f"右图更新错误: {str(e)}")
        except Exception as e:
            print(f"图像更新总错误: {str(e)}")
        
# ---------- 托盘功能 ----------

    def trayDoubleClick(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()

# ---------- 退出应用 ----------

    def quitApp(self):
        reply = QMessageBox.question(self, '确认退出', '确定要退出吗？',QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:   
                # ==========关闭共享内存==========  
                self.Mouse_Mem.close()
                self.Locator_Mem.close()#清理共享内存
                self.timer.stop()# 停止定时器
                # ==========关闭图像处理线程==========
                self.ImgDataHandler.Close_fuky_data_processing()
                # 等待图像处理线程结束（最多等待6秒）
                if self.ImgDataHandler_Thread.is_alive():
                    self.ImgDataHandler_Thread.join(timeout=6)
                    if self.ImgDataHandler_Thread.is_alive():
                        print("警告：图像处理线程未能正常终止")
                # ==========关闭蓝牙进程==========  
                # 终止蓝牙进程（如果启用）
                #self.close_event.set()
                if self.ble_base.ble_process and self.ble_base.ble_process.is_alive():
                    self.ble_base.ble_process.terminate()
                    self.ble_base.ble_process.join()
                # if hasattr(self.BleFukyDataHandler, 'is_alive'):
                #     if self.BleFukyDataHandler.is_alive():
                #         self.BleFukyDataHandler.terminate()
                #         self.BleFukyDataHandler.join(timeout=6)
                # ==========销毁系统托盘==========  
                self.tray_icon.hide()
                self.tray_icon.deleteLater()  # 延迟删除对象
                QApplication.processEvents()  # 处理未完成的事件
                # ==========退出应用==========  
                QApplication.quit()
                self.close()  # 确保主窗口关闭
                # ==========退出Python后台==========  
                sys.exit(0)  # 确保Python进程终止
            except Exception as e:
                print(f"退出时发生错误: {str(e)}")
                os._exit(1)  # 强制终止
        
# ---------- 共享内存管理 ----------
    
    def _setup_shared_memory_apis(self):
        """初始化Windows共享内存相关API"""
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        
        # 定义OpenFileMappingW函数
        self.OpenFileMappingW = self.kernel32.OpenFileMappingW
        self.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        self.OpenFileMappingW.restype = wintypes.HANDLE
        
        # 定义CloseHandle函数
        self.CloseHandle = self.kernel32.CloseHandle
        self.CloseHandle.argtypes = [wintypes.HANDLE]
        self.CloseHandle.restype = wintypes.BOOL
        
        # 定义所需常量
        self.FILE_MAP_ALL_ACCESS = 0xF001F  # 完全访问权限

    def _force_remove_shared_memory(self, mem_name):
        """强制删除已存在的共享内存"""
        try:
            # 将内存名称转换为Windows API需要的宽字符串格式
            mem_name_wide = ctypes.create_unicode_buffer(mem_name)
            
            # 尝试打开现有的共享内存
            h_map = self.OpenFileMappingW(
                self.FILE_MAP_ALL_ACCESS,  # 访问权限
                False,                     # 不继承句柄
                ctypes.byref(mem_name_wide) # 内存名称
            )
            
            # 如果成功获取到句柄（不等于0和INVALID_HANDLE_VALUE）
            if h_map not in (0, wintypes.HANDLE(-1).value):
                print(f"找到已存在的共享内存 {mem_name}，正在强制删除...")
                if self.CloseHandle(h_map):
                    print(f"成功关闭共享内存句柄: {mem_name}")
                else:
                    print(f"关闭句柄失败，错误代码: {ctypes.get_last_error()}")
        except Exception as e:
            print(f"删除共享内存时发生异常: {str(e)}")

    def initShareMem(self):
        self.Mouse_Mem_name="FUKY_Mouse_Memory"
        self.MouseSize = 32
        self.Locator_Mem_name="FUKY_Locator_Memory"
        self.LocatorSize = 12

       # 强制删除可能残留的共享内存
        self._force_remove_shared_memory(self.Mouse_Mem_name)
        self._force_remove_shared_memory(self.Locator_Mem_name)

        # 创建Mouse共享内存（带异常处理）
        try:
            self.Mouse_Mem = mmap.mmap(
                -1,                       # 匿名映射
                self.MouseSize,           # 内存大小
                tagname=self.Mouse_Mem_name,  # 内存标签名
                access=mmap.ACCESS_WRITE  # 写权限
            )
            self.ClearMemory(self.Mouse_Mem, self.MouseSize)
            print(f"成功创建Mouse共享内存: {self.Mouse_Mem_name}")
        except mmap.error as e:
            print(f"创建Mouse共享内存失败: {e}")
            # 这里可以添加重试逻辑或抛出异常

        # 创建Locator共享内存（带异常处理）
        try:
            self.Locator_Mem = mmap.mmap(
                -1,
                self.LocatorSize,
                tagname=self.Locator_Mem_name,
                access=mmap.ACCESS_WRITE
            )
            self.ClearMemory(self.Locator_Mem, self.LocatorSize)
            print(f"成功创建Locator共享内存: {self.Locator_Mem_name}")
        except mmap.error as e:
            print(f"创建Locator共享内存失败: {e}")
            # 这里可以添加重试逻辑或抛出异常


    def ClearMemory(self, Target, size):
        # 清空内存区域
        Target.seek(0)
        Target.write(b'\x00' * size)
        

        

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("系统托盘不可用")
        sys.exit(1)
    # 先创建窗口再启动线程
    window = FUKYWindow()
    window.show()
    # 初始化数据处理线程
    window.ImgDataHandler_Thread.start()
    window.ble_base.start_ble_process()
    sys.exit(app.exec_())

if __name__ == "__main__":
    # 确保只有一个实例运行
    import ctypes
    import win32event
    import win32api
    import winerror
    
    # 创建一个互斥体，确保只有一个实例运行
    mutex_name = "FUKY_DRIVER_MUTEX"
    mutex = win32event.CreateMutex(None, 1, mutex_name)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        # 如果互斥体已存在，说明已经有一个实例在运行
        print("程序已经在运行中，不允许多个实例同时运行")
        sys.exit(0)
    
    # 如果互斥体不存在，说明这是第一个实例，继续运行
    main()