import threading
from fuky_device_base import FUKY_deviceBase
import numpy as np
import cv2
import struct
import mmap

class FUKY_DataHandler():

    def __init__(self, share_mem=None):
        self.share_mem = share_mem
        self.fuky_deivce_base = FUKY_deviceBase()
        self.imgProcessing_lock = threading.Lock()  # 新增线程锁，用户层希望获取图像数据时用到
        # ---------- 线程 ----------
        self.Device_Threading = threading.Thread(target=self.fuky_deivce_base.FUKY_Device_Main)# 硬件通讯底层
        self.Data_Threading = threading.Thread(target=self.FUKY_Data_Main)# 数据处理层


        # ---------- 数据处理层的关闭事件 ----------
        self.Close_event = threading.Event()
        # ---------- 参数 ----------
        #图像
        self.prev_frame1 = None        #帧差计算用的帧缓存
        self.prev_frame2 = None
        self.left_frame1 = None        #准备定位用的帧缓存
        self.right_frame2 = None
        self.Process_img1 = None       #调试用图像，调试输出
        self.Process_img2 = None
        


        self.threshold_value = 127        # 二分阈值
        # 计算坐标用的参数
        stereo_params_path = "./stereo_params_game.npz"
        params = np.load(stereo_params_path)        # 加载立体标定参数
        
        # 打印参数内容 -------------------------------------------------
        # 设置numpy打印格式：保留4位小数
        np.set_printoptions(precision=4, suppress=True)
        
        print("\nLoaded parameters from", stereo_params_path)
        print("--------------------------------------------------")
        for param_name in params:  # 遍历npz文件中的所有参数
            print(f"[{param_name}]:")  # 打印参数名称
            print(params[param_name])  # 打印参数值
            print("---")
        
        # 恢复默认numpy打印设置（避免影响程序其他部分的输出）
        np.set_printoptions()
        
        self.Left_Ready = False  # 控制画面同步的机制，只有处理了两帧图像后才会触发计算，(小概率同摄像头反复更新导致bug)
        self.Right_Ready = False
        self.Left_spot = None
        self.Right_spot = None
        self.K1 = params['K1']
        self.D1 = params['D1']
        self.K2 = params['K2']
        self.D2 = params['D2']
        self.R = params['R']
        self.T = params['T']
        self.image_size = (800, 600)   # 立体校正参数计算（只需执行一次）这里根据实际图像尺寸修改
        self.R1, self.R2, self.P1, self.P2, self.Q, _, _ = cv2.stereoRectify(
            self.K1, self.D1,
            self.K2, self.D2,
            self.image_size, self.R, self.T,
            flags=cv2.CALIB_ZERO_DISPARITY,
            alpha=0.9
        )
        self.left_mapx, self.left_mapy = cv2.initUndistortRectifyMap(
            self.K1, self.D1, self.R1, self.P1,
            self.image_size, cv2.CV_32FC1
        )        # 生成校正映射（用于原始图像坐标转换）
        self.right_mapx, self.right_mapy = cv2.initUndistortRectifyMap(
            self.K2, self.D2, self.R2, self.P2,
            self.image_size, cv2.CV_32FC1
        )
        
        self.Cam_Coord_Data = None        #最后得出的数据
        
        # ---------- 共享内存的配置 ----------
        self.Locator_Mem_name = "FUKY_Locator_Memory"
        self.Locator_Size = 12
        self.Locator_Mem = None  # 共享内存对象
        
        cv2.setUseOptimized(True)  # 启用优化
        cv2.setNumThreads(4)       # 设置线程数

        # ---------- 初始化共享内存 ----------

    def init_shared_memory(self):
        """在子进程中打开主进程创建的共享内存"""
        try:
            self.Locator_Mem = mmap.mmap(
                -1,
                self.Locator_Size,
                tagname=self.Locator_Mem_name,
                access=mmap.ACCESS_WRITE
            )
            print("成功连接共享内存")
        except Exception as e:
            print(f"共享内存连接失败: {e}")
            self.Locator_Mem = None
        # ---------- 异步处理图像主线程 ----------
    def FUKY_Data_Main(self):
        self.init_shared_memory()
        self.Device_Threading.start()
        print("开始处理图像数据")
        while not self.Close_event.is_set():

            while self.fuky_deivce_base.serial_IsConnect:
                # 预处理部分
                if self.fuky_deivce_base.img1_Data_event.wait():
                    encode_gray_img1 = self.fuky_encode(self.fuky_deivce_base.img_data1)
                    with self.imgProcessing_lock:
                        self.left_frame1 = self.fuky_processing1(encode_gray_img1)
                        self.fuky_deivce_base.img1_Data_event.clear()
                        self.Left_Ready = True
                if self.fuky_deivce_base.img2_Data_event.wait():
                    encode_gray_img2 = self.fuky_encode(self.fuky_deivce_base.img_data2)
                    with self.imgProcessing_lock:
                        self.right_frame2 = self.fuky_processing2(encode_gray_img2)
                        self.fuky_deivce_base.img2_Data_event.clear()
                        self.Right_Ready = True
                if self.Right_Ready and self.Left_Ready:
                    self.fuky_detect_point()
                    self.fuky_Cal_point()
                
        
    def fuky_encode(self,img_data):
        """解码图像，转换为灰度图"""
        img_np = np.frombuffer(img_data, dtype=np.uint8)
        img = cv2.imdecode(img_np, cv2.IMREAD_GRAYSCALE)
        return img

        # ---------- 预处理 ----------
    def fuky_processing1(self,gray_imgdata):
        """调整图像的对比度和曝光度，减去上一帧图像，留下运动中的光斑，参数暂时硬编码到了代码中"""
        # 1. 调整对比度和曝光度
        adjusted_gray_img = cv2.convertScaleAbs(gray_imgdata, 1, 10)

        # 2. 模糊，去掉莫名其妙的高频噪声 
        blurred_diff = cv2.blur(adjusted_gray_img, (5,5))  
        # 3. 二值化
        _, binary_img1 = cv2.threshold(blurred_diff, self.threshold_value, 255, cv2.THRESH_BINARY)
        # 4. 帧差
        if self.prev_frame1 is None:
            #进行膨胀处理
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
            dilated_prev = cv2.dilate(binary_img1, kernel, iterations=1)
            self.prev_frame1 = dilated_prev
            return binary_img1
        frame_diff1 = cv2.subtract(binary_img1,self.prev_frame1)# 现在这个帧不再是上一帧，而是摄像头没捕捉到红点的前一帧画面
        return frame_diff1

    def fuky_processing2(self,gray_imgdata):
        """调整图像的对比度和曝光度，减去上一帧图像，留下运动中的光斑,参数暂时硬编码到了代码中"""
        # 1. 调整对比度和曝光度
        adjusted_gray_img = cv2.convertScaleAbs(gray_imgdata, 1, 10)

        # 2. 模糊，去掉莫名其妙的高频噪声 （均值滤波）
        blurred_diff = cv2.blur(adjusted_gray_img, (5,5))  
        # 3. 二值化
        _, binary_img2 = cv2.threshold(blurred_diff, self.threshold_value, 255, cv2.THRESH_BINARY)
        # 4. 帧差
        if self.prev_frame2 is None:
            #进行膨胀处理
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
            dilated_prev = cv2.dilate(binary_img2, kernel, iterations=1)
            self.prev_frame2 = dilated_prev
            return binary_img2

        frame_diff2 = cv2.subtract(binary_img2,self.prev_frame2)# 现在这个帧不再是上一帧，而是摄像头没捕捉到红点的前一帧画面
        return frame_diff2
        # ---------- 算法部分(全是opencv的功劳，不要看我) ----------

    def fuky_detect_point(self):
        self.Process_img1,Local_Left_spot ,IsDetected1 = self.detect_spot_centroids(self.left_frame1)
        self.Process_img2,Local_Right_spot ,IsDetected2 = self.detect_spot_centroids(self.right_frame2)
            
        self.Right_Ready = False
        self.Left_Ready = False
        if(Local_Left_spot is not None):
            self.Left_spot = Local_Left_spot.copy()
        if(Local_Right_spot is not None):
            self.Right_spot = Local_Right_spot.copy()
        
    def fuky_Cal_point(self):
        if self.Left_spot is not None and self.Right_spot is not None:
            calibrated_l,calibrated_r = self.rectify_points(self.Left_spot,self.Right_spot)
            self.triangulate(calibrated_l,calibrated_r)

    def detect_spot_centroids(self, binary_img, min_area=15,max_area=600):
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            binary_img.astype(np.uint8), 
            connectivity=4
        )
        
        result_img = cv2.cvtColor(binary_img, cv2.COLOR_GRAY2BGR)
        
        if num_labels > 1:
            # 提取所有连通域信息（排除背景）
            areas = stats[1:, cv2.CC_STAT_AREA]
            valid_indices = np.where((areas >= min_area) & (areas <= max_area))[0]
            
            
            if valid_indices.size > 0:
                # 获取符合条件的最大连通域
                max_area_idx = np.argmax(areas[valid_indices])
                selected_idx = valid_indices[max_area_idx] + 1  # 补偿背景索引偏移
                
                # 提取坐标信息
                max_centroid = centroids[selected_idx].astype(np.float32)
                x, y = max_centroid
                
                # 绘制标记
                cv2.circle(result_img, 
                          (int(round(x)), int(round(y))), 
                          radius=3, color=(0, 0, 255), thickness=-1)
                #print(f"发现有效连通域，面积：{areas[valid_indices[max_area_idx]]}")
                return result_img, max_centroid, True        
        return result_img, None, False
            
    
    
    def rectify_points(self, left_pts, right_pts):
        """将原始像素坐标转换到校正后坐标系"""
        # 输入格式：Nx2 的 numpy 数组
        left_pts = left_pts.astype(np.float32).reshape(-1, 1, 2)
        right_pts = right_pts.astype(np.float32).reshape(-1, 1, 2)
        # 坐标校正
        left_rect = cv2.undistortPoints(left_pts, self.K1, self.D1, R=self.R1, P=self.P1)
        right_rect = cv2.undistortPoints(right_pts, self.K2, self.D2, R=self.R2, P=self.P2)
        return left_rect, right_rect

    def triangulate(self, left_pixel, right_pixel):
        """
        输入：左右图像中的像素坐标 (x,y)
        输出：三维坐标 (X,Y,Z) in meters
        """
        # 转换为校正坐标系坐标
        left_rect, right_rect = self.rectify_points(
            np.array([left_pixel]),
            np.array([right_pixel])
        )
        
        # 三角测量
        points_4d = cv2.triangulatePoints(
            self.P1, self.P2,
            left_rect.reshape(2, 1),  # 需要 (2xN) 格式
            right_rect.reshape(2, 1)
        )
        
        # 转换为三维坐标 (齐次坐标转笛卡尔坐标)
        point_3d = cv2.convertPointsFromHomogeneous(points_4d.T)
        #print(f"3D点: {point_3d}")
        # 将3D坐标写入共享内存
        if self.Locator_Mem is not None:
            try:
                # 获取坐标值
                x, y, z = point_3d[0][0].tolist()
                # 打包为二进制格式
                packed_data = struct.pack('<3f', x, y, z)  # 小端序，3个float32
                # 直接写入共享内存
                self.Locator_Mem.seek(0)
                self.Locator_Mem.write(packed_data)
                self.Locator_Mem.flush()
                #print("已将3D数据写入共享内存")
            except Exception as e:
                print(f"写入共享内存失败: {e}")
        
        # ---------- 调试用显示图像 ----------

    def show_images(self):
        """OpenCV图像显示线程"""
        cv2.namedWindow('Camera 1', cv2.WINDOW_AUTOSIZE)
        cv2.namedWindow('Camera 2', cv2.WINDOW_AUTOSIZE)
        
        while not self.Close_event.is_set():
            try:
                # 获取并显示1图像
                if self.Process_img1 is not None:
                    cv2.imshow('Camera 1', self.Process_img1)
                
                # 获取并显示2图像
                if self.Process_img2 is not None:
                    cv2.imshow('Camera 2', self.Process_img2)
                
                # 检测退出按键
                if cv2.waitKey(25) & 0xFF == ord('q'):
                    self.Close_fuky_data_processing()
                    break
                    
            except Exception as e:
                print(f"显示异常: {str(e)}")
                break
                
        cv2.destroyAllWindows()          

        # ---------- 关闭函数 ----------
    def Close_fuky_data_processing(self):
        """安全关闭所有数据处理的资源"""
        try:
            print("[DataHandler] 开始关闭数据处理...")
            
            # ========== 阶段1：设置关闭标志 ==========
            self.Close_event.set()
            
            # ========== 阶段2：停止设备通信 ==========
            if hasattr(self.fuky_deivce_base, 'Close_FUKY_Device'):
                self.fuky_deivce_base.Close_FUKY_Device()
            
            # ========== 阶段3：停止子线程 ==========
            # 停止设备通信线程
            if self.Device_Threading.is_alive():
                print("[DataHandler] 等待设备线程停止...")
                self.Device_Threading.join(timeout=6)
                if self.Device_Threading.is_alive():
                    print("[DataHandler] 警告：设备线程未正常终止！")
    
            # 停止数据处理线程
            if self.Data_Threading.is_alive():
                print("[DataHandler] 等待数据处理线程停止...")
                self.Data_Threading.join(timeout=6)
                if self.Data_Threading.is_alive():
                    print("[DataHandler] 警告：数据处理线程未正常终止！")
    
            # ========== 阶段4：释放OpenCV资源 ==========
            print("[DataHandler] 释放OpenCV资源...")
            cv2.destroyAllWindows()
            
            # 显式释放摄像头资源（如果设备层未释放）
            if hasattr(self.fuky_deivce_base, 'cap1'):
                if self.fuky_deivce_base.cap1.isOpened():
                    self.fuky_deivce_base.cap1.release()
            if hasattr(self.fuky_deivce_base, 'cap2'):
                if self.fuky_deivce_base.cap2.isOpened():
                    self.fuky_deivce_base.cap2.release()
    
            # ========== 阶段5：清理内存资源 ==========
            print("[DataHandler] 清理共享内存...")
            if self.Locator_Mem:
                self.Locator_Mem.close()
                self.Locator_Mem = None
    
            # ========== 阶段6：重置状态变量 ==========
            with self.imgProcessing_lock:
                self.prev_frame1 = None
                self.prev_frame2 = None
                self.left_frame1 = None
                self.right_frame2 = None
                self.Process_img1 = None
                self.Process_img2 = None
    
            print("[DataHandler] 资源释放完成")
    
        except Exception as e:
            print(f"[DataHandler] 关闭时发生异常: {str(e)}")
        finally:
            # 最终保障：强制清空OpenCV线程池
            cv2.destroyAllWindows()
            cv2.setNumThreads(0)
        

        

if __name__ == "__main__":
    
    
    TestDataProcess = FUKY_DataHandler()
    show_Threading = threading.Thread(target=TestDataProcess.show_images)
    Processing_Threading = threading.Thread(target=TestDataProcess.FUKY_Data_Main)
    
    show_Threading.start()
    Processing_Threading.start()
