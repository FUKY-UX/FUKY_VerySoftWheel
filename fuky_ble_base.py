import asyncio
import sys
import multiprocessing
import threading
import fuky_WinAPI_base

import time
import mmap
import ctypes  # 用于定义共享内存中的布尔类型
import struct  # 用于解析二进制数据
from winrt.windows.storage.streams import DataReader
from winrt.windows.devices.bluetooth import BluetoothAdapter, BluetoothDevice, BluetoothLEDevice
from winrt.windows.devices.bluetooth import BluetoothConnectionStatus
from winrt.windows.devices.enumeration import DeviceInformation, DeviceInformationKind
from winrt.windows.devices.bluetooth.genericattributeprofile import GattCharacteristic, GattClientCharacteristicConfigurationDescriptorValue
from winrt.windows.devices.bluetooth.genericattributeprofile import GattSession

# 添加Spyder兼容性处理
if 'ipykernel' in sys.modules:
    import nest_asyncio
    nest_asyncio.apply()
    
class FUKY_BleBase:
    
    def __init__(self,Close_Event):
        """初始化蓝牙设备信息，事件必须是跨进程事件，用于关闭进程""" 
        # 进程共享变量
        self.Is_device_found = multiprocessing.Value(ctypes.c_bool, False)
        self.close_event = Close_Event
        self.ble_process =None
    def start_ble_process(self):
        """启动蓝牙处理进程"""
        self.ble_process = multiprocessing.Process(target=self.ble_process_Active,args=(self.Is_device_found, self.close_event))
        self.ble_process.start()
        
        print("蓝牙处理进程已启动")
        return self.ble_process

    def stop_ble_process(self):
        """停止蓝牙处理进程"""
        if self.ble_process and self.ble_process.is_alive():
            self.close_event.set()
            self.ble_process.join(timeout=5)
            print("蓝牙进程已停止")

    def ble_process_Active(self, is_device_found, close_event):
        # 运行异步主函数
        if sys.platform == "win32":
            try:
                asyncio.run(self.ble_process_function(is_device_found,close_event))
            except Exception as e:
                print(f"发生未预期错误: {str(e)}")
            finally:
                # 仅在打包为 EXE 时添加等待
                if hasattr(sys, '_MEIPASS'):
                    print("\n程序执行完毕，按任意键退出...")
                    import msvcrt
                    msvcrt.getch()
        else:
            print("错误: 此程序仅支持Windows平台")        
       

        
    async def ble_process_function(self, Is_device_found,Close_Event):
        print("BLE设备处理进程已启动")
        DEVICE_NAME = "FUKY_MOUSE"
        SERVICE_UUID = "0000f233-0000-1000-8000-00805f9b34fb"
        IMU_CHAR_UUID = "0000f666-0000-1000-8000-00805f9b34fb"
        PRESS_CHAR_UUID = "0000f667-0000-1000-8000-00805f9b34fb"
        BTN_CHAR_UUID = "0000f668-0000-1000-8000-00805f9b34fb"

        #转换浮点数的参数
        SCALE_Q14 = 1.0 / (1 << 14)
        SCALE_Q8 = 1.0 / (1 << 8)
        

        Local_close_event = Close_Event
        # 连接共享内存对象，需要在主进程中创建
        
        IMU_Mem_name = "IMU_Memory"
        MemSize = 32
        IMU_Mem = None 
        try:
            IMU_Mem = mmap.mmap(
                -1,
                MemSize,
                tagname=IMU_Mem_name,
                access=mmap.ACCESS_WRITE
            )
            print("成功连接共享内存")
        except Exception as e:
            print(f"共享内存连接失败: {e},读取到的数据将不会传入应用")
            IMU_Mem = None
        # 按钮共享内存配置
        BTN_Mem_name = "BTN_Memory"
        BTN_MemSize = 1  # 只需要1字节存储按钮状态
        BTN_Mem = None
        try:
            BTN_Mem = mmap.mmap(
                -1,
                BTN_MemSize,
                tagname=BTN_Mem_name,
                access=mmap.ACCESS_WRITE
            )
            print("成功连接按钮共享内存")
        except Exception as e:
            print(f"按钮共享内存连接失败: {e}")
        # 按钮共享内存配置
        PRESS_Mem_name = "PRESS_Memory"
        PRESS_MemSize = 2  # 只需要2字节存储压力
        PRESS_Mem = None
        try:
            PRESS_Mem = mmap.mmap(
                -1,
                PRESS_MemSize,
                tagname=PRESS_Mem_name,
                access=mmap.ACCESS_WRITE
            )
            print("创建了压力共享内存")
        except Exception as e:
            print(f"按钮共享内存连接失败: {e}")
        # 创建Window事件对象
        BleWindowEventHandler = fuky_WinAPI_base.FUKY_WindowAPIHandler();
        imu_event = BleWindowEventHandler.Creat_WinEvent("IMU_DataRev",DontAutoReset=False,OriginSet=False)
        btn_event = BleWindowEventHandler.Creat_WinEvent("Btn_DataRev",DontAutoReset=False,OriginSet=False)
        press_event = BleWindowEventHandler.Creat_WinEvent("Press_DataRev",DontAutoReset=False,OriginSet=False)

        
        
        # 蓝牙适配器
        adapter = None
        selector = BluetoothLEDevice.get_device_selector_from_connection_status(BluetoothConnectionStatus.CONNECTED)
        additional_properties = ["System.Devices.Aep.DeviceAddress", 
                                "System.Devices.Aep.IsConnected", 
                                "System.Devices.Aep.IsPaired",
                                "System.ItemNameDisplay"]
        # 目标设备的信息
        FUKY_Device_info = None
        # 目标设备实例
        FUKY_Device = None
        
        #三个蓝牙传输的数据特征值
        imu_char = None
        btn_char = None
        press_char = None
        
        #特征值通知处理函数注册状态令牌
        imu_event_token = None
        btn_event_token = None
        press_event_token = None
        
        while(not Local_close_event.is_set()):
            # ======尝试获得蓝牙适配器======
            if(adapter == None):
                for count in range(10):
                    # 获取蓝牙适配器
                    try:
                        adapter = await BluetoothAdapter.get_default_async()
                        if adapter is None:
                            print(f"无法获取蓝牙适配器，尝试 {count + 1}/10...")
                            if count < 9:  # 如果不是最后一次尝试
                                await asyncio.sleep(1)
                                count = count+1
                            continue
                        print("蓝牙适配器已找到")
                        print(f"蓝牙地址: {adapter.bluetooth_address}")
                        break # 获取到就打破循环即可                        
                    except Exception as e:
                        print(f"获取蓝牙适配器出错(尝试 {count + 1}/10): {str(e)}")
                        if count < 9:
                            await asyncio.sleep(1)
                            count = count+1
                            continue
                    print("达到最大重试次数仍无法获得蓝牙适配器，蓝牙处理进程启动失败")
                    return
                

            # ======尝试获得目标设备======
            while(FUKY_Device == None):
                # 查找符合选择器的设备
                AllBleDevices = await DeviceInformation.find_all_async(selector, additional_properties)
                if AllBleDevices.size == 0:
                    print("未找到任何BLE设备，继续查找")
                    await asyncio.sleep(5)
                    continue
                    print(f"\n找到 {AllBleDevices.size} 个已连接的BLE设备:")
                
                for i, device_info in enumerate(AllBleDevices):
                    # 获取设备名称
                    device_name_found = device_info.name or "未知设备"
                    # 检查是否是我们要找的设备
                    if device_name_found == DEVICE_NAME:
                        print(f"找到目标设备: {DEVICE_NAME}")
                        FUKY_Device_info = device_info
                        # 打印基本设备信息
                        print(f"名称: {FUKY_Device_info.name}")
                        print(f"设备ID: {FUKY_Device_info.id}")
                        # 从设备ID创建BluetoothLEDevice对象
                        FUKY_Device = await BluetoothLEDevice.from_id_async(FUKY_Device_info.id)
                        if FUKY_Device:
                            print(f"设备实例蓝牙地址: {FUKY_Device.bluetooth_address}")
                            print(f"设备实例连接状态: {'已连接' if FUKY_Device.connection_status == BluetoothConnectionStatus.CONNECTED else '未连接'}")
                        
                        else:
                            print("从设备信息生成BLE设备实例时出错:重新尝试")
                            adapter == None
                            FUKY_Device = None
                            FUKY_Device_info = None
                            break # 清空进度,重新获取
                AllBleDevices = None
            # ======尝试获得三个特征值======
            while(FUKY_Device and (imu_char == None or btn_char == None or press_char == None)):
                target_service = None
                services_result = await FUKY_Device.get_gatt_services_async()
                if services_result.status == 0:  # 成功
                    print(f"GATT服务数量: {services_result.services.size}")
                    for service in services_result.services:
                        if str(service.uuid).lower() == SERVICE_UUID.lower():
                            target_service = service
                            print(f"找到目标服务: {service.uuid}")
                            # 获取目标特征值
                            characteristics_result = await target_service.get_characteristics_async()
                            if characteristics_result.status == 0:
                                for characteristic in characteristics_result.characteristics:
                                    if str(characteristic.uuid).lower() == IMU_CHAR_UUID.lower():
                                        imu_char = characteristic
                                        print(f"找到目标特征值: {characteristic.uuid}")
                                    elif str(characteristic.uuid).lower() == BTN_CHAR_UUID.lower():
                                        btn_char = characteristic
                                        print(f"找到目标特征值: {characteristic.uuid}")
                                    elif str(characteristic.uuid).lower() == PRESS_CHAR_UUID.lower():
                                        press_char = characteristic
                                        print(f"找到目标特征值: {characteristic.uuid}")
                            else:
                                print(f"获取特征值失败，重新尝试，状态码: {characteristics_result.status}")                    
                                # ********重置进度**********
                                adapter == None
                                FUKY_Device = None
                                FUKY_Device_info = None
                                await asyncio.sleep(1)  # 等待1秒再重试
                                break # 清空进度,重新获取
                            # 注册IMU特征值通知事件处理函数
                            def IMU_Data_handler(sender, args):
                                try:
                                    # 获取特征值数据
                                    buffer = args.characteristic_value
                                    
                                    # 将buffer转换为字节数组
                                    if buffer and buffer.length == 14:  # 确保数据长度正确
                                        # 创建一个字节数组来存储数据
                                        data = bytearray(buffer.length)
                                        
                                        # 将buffer转换为字节数组
                                        if buffer and buffer.length == 14:  # 确保数据长度正确
                                            # 使用DataReader读取buffer数据
                                            reader = DataReader.from_buffer(buffer)
                                            data_bytes = reader.read_bytes(buffer.length)
                                            data = bytearray(data_bytes)
                                        
                                        # 解析IMU数据
                                        try:
                                            # 解析加速度数据 (前6个字节)
                                            lin_accel = struct.unpack('<3h', data[0:6])
                                            
                                            # 解析四元数数据 (后8个字节)
                                            quat = struct.unpack('<4h', data[6:14])
                                            
                                            # 转换为浮点数
                                            accel_float = tuple(v * SCALE_Q8 for v in lin_accel)
                                            quat_float = tuple(v * SCALE_Q14 for v in quat)
                                            

                                            
                                            # 打印解析后的数据
                                            # print("收到IMU数据:")
                                            #print(f"  原始数据: {data.hex()}")
                                            #print(f"  加速度 (g): {accel_float}")
                                            #print(f"  四元数: {quat_float}")
                                            
                                            
                                            # 将数据写入共享内存
                                            if IMU_Mem is not None:
                                                try:
                                            # 打包数据为二进制格式 (7个float: 3个加速度 + 4个四元数)
                                                    packed_data = struct.pack(
                                                        '<7f',  # 小端序，7个float32
                                                        accel_float[0], accel_float[1], accel_float[2],
                                                        quat_float[0], quat_float[1], quat_float[2], quat_float[3]
                                                    )
                                                    # 直接写入共享内存
                                                    IMU_Mem.seek(0)
                                                    IMU_Mem.write(packed_data)
                                                    IMU_Mem.flush()
                                                    #print("已将IMU数据写入共享内存")
                                                    # 触发事件
                                                    BleWindowEventHandler.set_event(imu_event)
                                                except Exception as e:
                                                    print(f"写入共享内存失败: {e}")
                                            
                                        except Exception as e:
                                            print(f"解析IMU数据时出错: {e}")
                                    else:
                                        if buffer:
                                            print(f"收到数据长度不正确: {buffer.length}字节")
                                        else:
                                            print("收到空buffer")
                                except Exception as e:
                                    print(f"处理特征值通知时出错: {e}")
            
                            # 注册btn特征值通知事件处理函数
                            def BTN_Data_handler(sender, args):
                                try:
                                    # 获取特征值数据
                                    buffer = args.characteristic_value
                                    
                                    # 验证数据长度（应为一个字节）
                                    if buffer and buffer.length == 1:
                                        reader = DataReader.from_buffer(buffer)
                                        data_byte = reader.read_byte()
                                        
                                        # 解析按钮状态
                                        button_state = data_byte
                                        
                                        # 按位解析按钮状态
                                        # left_pressed = bool(button_state & 0x01)    # 第0位：左键
                                        # right_pressed = bool(button_state & 0x02)   # 第1位：右键
                                        # middle_pressed = bool(button_state & 0x04)  # 第2位：中键
                                        
                                        # 打印按钮状态
                                        # print("\n按钮状态更新：")
                                        # print(f"  左键: {'按下' if left_pressed else '释放'}")
                                        # print(f"  右键: {'按下' if right_pressed else '释放'}")
                                        # print(f"  中键: {'按下' if middle_pressed else '释放'}")
                                        
                                        # 写入共享内存（单个字节）
                                        if BTN_Mem is not None:
                                            try:
                                                BTN_Mem.seek(0)
                                                BTN_Mem.write_byte(button_state)
                                                BTN_Mem.flush()
                                                #print("按钮状态已写入共享内存")
                                            except Exception as e:
                                                print(f"写入按钮共享内存失败: {e}")
                                        
                                        # 触发事件
                                        BleWindowEventHandler.set_event(btn_event)
                                        
                                    else:
                                        err_msg = f"无效按钮数据长度: {buffer.length if buffer else 'None'}"
                                        print(err_msg)
                                        
                                except Exception as e:
                                    print(f"处理按钮数据时发生错误: {str(e)}")
                                
                            # 注册press特征值通知事件处理函数
                            def Press_Data_handler(sender, args):
                                try:
                                    buffer = args.characteristic_value
                                    
                                    # 验证数据长度（应为两个字节）
                                    if buffer and buffer.length == 2:
                                        reader = DataReader.from_buffer(buffer)
                                        # 读取小端字节序的16位无符号整数（uint16_t）
                                        pressure_value = reader.read_uint16()
                                        
                                        # 打印压力百分比值
                                        #print(f"  压力百分比: {pressure_value} (0x{pressure_value:04X})")
                                        
                                        # 写入共享内存（两个字节）
                                        if PRESS_Mem is not None:
                                            try:
                                                PRESS_Mem.seek(0)
                                                # 将16位值拆分为两个字节写入
                                                PRESS_Mem.write_byte(pressure_value & 0xFF)         # 低字节
                                                PRESS_Mem.write_byte((pressure_value >> 8) & 0xFF) # 高字节
                                                PRESS_Mem.flush()
                                                #print("压力值已写入共享内存")
                                            except Exception as e:
                                                print(f"写入压力共享内存失败: {e}")
                                        
                                        # 触发压力更新事件
                                        BleWindowEventHandler.set_event(press_event)
                                    else:
                                        err_msg = f"无效压力数据长度: {buffer.length if buffer else 'None'}"
                                        print(err_msg)
                                        
                                except Exception as e:
                                    print(f"处理压力数据时发生错误: {str(e)}")
                            
                            # 注册回调函数
                            btn_event_token = btn_char.add_value_changed(BTN_Data_handler)
                            imu_event_token = imu_char.add_value_changed(IMU_Data_handler)  
                            press_event_token = press_char.add_value_changed(Press_Data_handler)
                            # 开启通知
                            imu_config_result = await imu_char.write_client_characteristic_configuration_descriptor_async(
                                GattClientCharacteristicConfigurationDescriptorValue.NOTIFY
                            )
                            if imu_config_result == 0:  # 成功
                                print("成功订阅IMU征值通知")
                            btn_config_result = await btn_char.write_client_characteristic_configuration_descriptor_async(
                                GattClientCharacteristicConfigurationDescriptorValue.NOTIFY
                            )
                            if btn_config_result == 0:  # 成功
                                print("成功订阅按钮特征值通知")
                            pre_config_result = await press_char.write_client_characteristic_configuration_descriptor_async(
                                GattClientCharacteristicConfigurationDescriptorValue.NOTIFY
                            )
                            if pre_config_result == 0:  # 成功
                                print("成功订阅压力特征值通知")
                        else:                      
                            print("{service.uuid}不是fx233服务,继续查找")
                        
                else:                      
                    print("获取GATT服务时出错,重新尝试")
                    # ********重置进度**********
                    FUKY_Device = None
                    FUKY_Device_info = None
                    break # 清空进度,重新获取     
                if FUKY_Device and not Is_device_found.value:
                    with Is_device_found.get_lock():
                        Is_device_found.value = True
                    print("设备已标记为找到状态")
                break    
        
        print("工作完毕，释放所有蓝牙资源")
        if imu_event_token is not None:
            print("已尝试移除回调函数")
            imu_char.remove_value_changed(imu_event_token)
            btn_char.remove_value_changed(btn_event_token)
            press_char.remove_value_changed(press_event_token)
            
            if imu_char:
                print("关闭IMU数据订阅")
                await imu_char.write_client_characteristic_configuration_descriptor_async(
                    GattClientCharacteristicConfigurationDescriptorValue.NONE
                )
            if btn_char:
                print("关闭按钮数据订阅")
                await btn_char.write_client_characteristic_configuration_descriptor_async(
                    GattClientCharacteristicConfigurationDescriptorValue.NONE
                )
            if press_char:
                print("关闭压力数据订阅")
                await press_char.write_client_characteristic_configuration_descriptor_async(
                    GattClientCharacteristicConfigurationDescriptorValue.NONE
                )

        adapter == None
        FUKY_Device = None
        FUKY_Device_info = None
        print("测试完毕")
        return




                
                    
            # ======订阅特征并添加回调函数======
            
        

                    
# 测试代码
# 主进程
if __name__ == "__main__":
    close_event = multiprocessing.Event()
    ble_controller = FUKY_BleBase(close_event)
    
    try:
        # 启动蓝牙进程
        ble_controller.start_ble_process()
        
        # 主循环监控状态
        while True:
            if ble_controller.Is_device_found.value:
                print("设备已连接")
            else:
                print("等待设备连接...")
            time.sleep(1)
            
    except KeyboardInterrupt:
        # 停止蓝牙进程
        ble_controller.stop_ble_process()        
