"""
蓝牙设备检测程序
使用Windows WinRT库检测并打印连接到Windows的蓝牙设备名称
支持多进程运行和进程间通信
"""
import asyncio
import sys
import multiprocessing
import time
import mmap
import ctypes  # 用于定义共享内存中的布尔类型
import struct  # 用于解析二进制数据
from winrt.windows.storage.streams import DataReader
from winrt.windows.devices.bluetooth import BluetoothAdapter, BluetoothDevice, BluetoothLEDevice
from winrt.windows.devices.bluetooth import BluetoothConnectionStatus
from winrt.windows.devices.enumeration import DeviceInformation, DeviceInformationKind
from winrt.windows.devices.bluetooth.genericattributeprofile import GattCharacteristic, GattClientCharacteristicConfigurationDescriptorValue

# 添加Spyder兼容性处理
if 'ipykernel' in sys.modules:
    import nest_asyncio
    nest_asyncio.apply()

class FUKY_BleDeviceBase:
    """FUKY的蓝牙设备数据底层"""
    
    def __init__(self):
        """初始化蓝牙设备扫描器"""
        self.DEVICE_NAME = "FUKY_MOUSE"
        self.SERVICE_UUID = "0000f233-0000-1000-8000-00805f9b34fb"
        self.ACCESS_SERVICE_UUID = "00001800-0000-1000-8000-00805f9b34fb"
        self.CHARACTERISTIC_UUID = "0000f666-0000-1000-8000-00805f9b34fb"
        self.CHARACTERISTIC_UUID = "0000f667-0000-1000-8000-00805f9b34fb"
        self.CHARACTERISTIC_UUID = "0000f668-0000-1000-8000-00805f9b34fb"
        self.HID_SERVICE_UUID = "00001812-0000-1000-8000-00805f9b34fb"
        self.SCALE_Q14 = 1.0 / (1 << 14)
        self.SCALE_Q8 = 1.0 / (1 << 8)
        
        # 进程共享变量
        self.device_found_flag = multiprocessing.Value(ctypes.c_bool, False)
        self.ble_process = None
        
        # BLE设备对象（仅在BLE进程中有效）
        self.FUKY_Mouse_Device = None
        self.characteristic = None
        
        # 共享内存配置，主进程中创建的
        self.Mouse_Mem_name = "FUKY_Mouse_Memory"
        self.MouseSize = 32
        self.Mouse_Mem = None  # 共享内存对象
        
    def init_shared_memory(self):
        """在子进程中打开主进程创建的共享内存"""
        try:
            self.Mouse_Mem = mmap.mmap(
                -1,
                self.MouseSize,
                tagname=self.Mouse_Mem_name,
                access=mmap.ACCESS_WRITE
            )
            print("成功连接共享内存")
        except Exception as e:
            print(f"共享内存连接失败: {e}")
            self.Mouse_Mem = None
        
    def start_ble_process(self):
        """启动BLE设备处理进程"""
        if self.ble_process is not None and self.ble_process.is_alive():
            print("BLE进程已经在运行中")
            
            return
        
        # 创建并启动进程
        self.ble_process = multiprocessing.Process(
            target=self.ble_process_function, 
            args=(self.device_found_flag,)
        )
        self.ble_process.daemon = True  # 设置为守护进程，主进程退出时自动结束
        self.ble_process.start()
        
        print(f"已启动BLE设备处理进程，PID: {self.ble_process.pid}")
    
    def is_device_found(self):
        """检查是否找到BLE设备"""
        return self.device_found_flag.value
    
    def stop_ble_process(self):
        """停止BLE设备处理进程"""
        if self.ble_process is not None and self.ble_process.is_alive():
            self.ble_process.terminate()
            self.ble_process.join(timeout=1.0)
            print("已停止BLE设备处理进程")
            
            self.ble_process = None
    
    def ble_process_function(self, device_found_flag):
        """BLE设备处理进程的主函数
        
        Args:
            device_found_flag: 多进程共享的标志位，表示是否找到设备
            data_queue: 多进程共享的队列，用于传输BLE设备返回的数据
        """
        # 在子进程中创建蓝牙处理实例
        ble_handler = FUKY_BleDeviceBase()

        # 使用传入的共享变量替换实例中的变量
        ble_handler.device_found_flag = device_found_flag
        # 初始化子进程中蓝牙处理实例的共享内存，以便后面可以向其写入数据
        ble_handler.init_shared_memory()  # 初始化共享内存
        
        
        # 运行异步主函数
        if sys.platform == "win32":
            asyncio.run(ble_handler.async_main())
        else:
            print("错误: 此程序仅支持Windows平台")
            
    
    async def async_main(self):
        """BLE设备处理进程的异步主函数"""
        print("BLE设备处理进程已启动")
        
        
        # 获取蓝牙适配器
        adapter = await self.get_bluetooth_adapter()
        if adapter is None:
            print("无法获取蓝牙适配器，进程退出")
            
            return
        
        print("蓝牙适配器已找到")
        print(f"蓝牙地址: {adapter.bluetooth_address}")
        
        
        # 检查蓝牙
        if not adapter.is_central_role_supported:
            print("警告: 此蓝牙适配器不支持中央角色，可能无法扫描设备")
            
        
        # 获取已连接的BLE设备
        self.FUKY_Mouse_Device = await self.get_connected_ble_devices()
        if self.FUKY_Mouse_Device is None:
            print("未找到目标BLE设备，进程退出")
            return
        
        while True:  # 添加循环，持续尝试连接
            # 获取已连接的BLE设备
            self.FUKY_Mouse_Device = await self.get_connected_ble_devices()
            if self.FUKY_Mouse_Device is None:
                print("未找到目标BLE设备，等待重试...")
                await asyncio.sleep(5)  # 等待5秒后重试
                continue
            break
        
        # 订阅特征值通知
        success = await self.subscribe_to_characteristic()
        if not success:
            print("订阅特征值通知失败，进程退出")
            
            return
        
        # 保持进程运行，处理特征值通知
        print("BLE设备已找到并订阅特征值通知，进程继续运行...")
        
        while True:
            await asyncio.sleep(1)
    
    async def get_bluetooth_adapter(self):
        """获取默认蓝牙适配器"""
        try:
            adapter = await BluetoothAdapter.get_default_async()
            if adapter is None:
                print("错误: 未找到蓝牙适配器")
                
                return None
            return adapter
        except Exception as e:
            print(f"获取蓝牙适配器时出错: {e}")
            
            return None
    
    async def get_connected_ble_devices(self):
        """获取已连接的蓝牙低功耗(BLE)设备"""
        print("\n正在获取已连接的BLE设备...")
        
        try:
            # 使用BluetoothLEDevice的get_device_selector_from_connection_status方法获取已连接BLE设备的选择器
            selector = BluetoothLEDevice.get_device_selector_from_connection_status(BluetoothConnectionStatus.CONNECTED)
            
            # 定义要获取的额外属性
            additional_properties = ["System.Devices.Aep.DeviceAddress", 
                                    "System.Devices.Aep.IsConnected", 
                                    "System.Devices.Aep.IsPaired",
                                    "System.ItemNameDisplay"]
            
            # 查找符合选择器的设备
            devices_info = await DeviceInformation.find_all_async(selector, additional_properties)
            
            if devices_info.size == 0:
                print("未找到已连接的BLE设备")
                
                return None
            
            print(f"\n找到 {devices_info.size} 个已连接的BLE设备:")
            
            
            # 遍历并打印设备信息
            for i, device_info in enumerate(devices_info):
                # 获取设备名称
                device_name_found = device_info.name or "未知设备"
                # 检查是否是我们要找的设备
                if device_name_found == self.DEVICE_NAME:
                    print(f"   找到目标设备: {self.DEVICE_NAME}")

                # 获取设备ID
                    device_id = device_info.id
                    
                    # 打印基本设备信息
                    print(f"{i+1}. 名称: {device_name_found}")
                    print(f"   设备ID: {device_id}")
                    
                    
                    # 尝试获取更多BLE设备信息
                    try:
                        # 从设备ID创建BluetoothLEDevice对象
                        ble_device = await BluetoothLEDevice.from_id_async(device_id)
                        if ble_device:
                            print(f"   蓝牙地址: {ble_device.bluetooth_address}")
                            print(f"   连接状态: {'已连接' if ble_device.connection_status == BluetoothConnectionStatus.CONNECTED else '未连接'}")
                            
                            
                            # 尝试获取GATT服务信息
                            try:
                                services = await ble_device.get_gatt_services_async()
                                if services.status == 0:  # 成功
                                    print(f"   GATT服务数量: {services.services.size}")
                                    
                                    # 设置标志位，通知主进程已找到设备
                                    self.device_found_flag.value = True
                                    print("   已设置设备找到标志位")
                                    
                                    return ble_device
                            except Exception as e:
                                print(f"   获取GATT服务时出错: {e}")
                                
                    except Exception as e:
                        print(f"   获取BLE设备详细信息时出错: {e}")
                        
            
            return None
        except Exception as e:
            print(f"获取已连接BLE设备时出错: {e}")
            
            return None
    
    async def subscribe_to_characteristic(self):
        """订阅BLE设备的特征值通知"""
        if self.FUKY_Mouse_Device is None:
            print("错误: 未找到BLE设备，无法订阅特征值")
            
            return False
        
        try:
            print(f"\n正在查找服务: {self.SERVICE_UUID}")
            
            
            # 获取目标服务
            services_result = await self.FUKY_Mouse_Device.get_gatt_services_async()
            if services_result.status != 0:
                print(f"获取服务失败，状态码: {services_result.status}")
                
                return False
            
            target_service = None
            for service in services_result.services:
                if str(service.uuid).lower() == self.SERVICE_UUID.lower():
                    target_service = service
                    print(f"找到目标服务: {service.uuid}")
                    
                    break
            
            if target_service is None:
                print(f"未找到目标服务: {self.SERVICE_UUID}")
                
                return False
            
            # 获取目标特征值
            characteristics_result = await target_service.get_characteristics_async()
            if characteristics_result.status != 0:
                print(f"获取特征值失败，状态码: {characteristics_result.status}")
                
                return False
            
            target_characteristic = None
            for characteristic in characteristics_result.characteristics:
                if str(characteristic.uuid).lower() == self.CHARACTERISTIC_UUID.lower():
                    target_characteristic = characteristic
                    print(f"找到目标特征值: {characteristic.uuid}")
                    
                    break
            
            if target_characteristic is None:
                print(f"未找到目标特征值: {self.CHARACTERISTIC_UUID}")
                
                return False
            
            # 保存找到的特征值对象
            self.characteristic = target_characteristic
            
            # 注册特征值通知事件处理函数
            def value_changed_handler(sender, args):
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
                            accel_float = tuple(v * self.SCALE_Q8 for v in lin_accel)
                            quat_float = tuple(v * self.SCALE_Q14 for v in quat)
                            
                            # 创建IMU数据字典
                            imu_data = {
                                'accel': accel_float,
                                'quat': quat_float,
                                'raw_data': data.hex()
                            }
                            
                            # 打印解析后的数据
                            print(f"收到IMU数据:")
                            print(f"  原始数据: {data.hex()}")
                            print(f"  加速度 (g): {accel_float}")
                            print(f"  四元数: {quat_float}")
                            
                            
                            # 将数据写入共享内存
                            if self.Mouse_Mem is not None:
                                try:
                            # 打包数据为二进制格式 (7个float: 3个加速度 + 4个四元数)
                                    packed_data = struct.pack(
                                        '<7f',  # 小端序，7个float32
                                        accel_float[0], accel_float[1], accel_float[2],
                                        quat_float[0], quat_float[1], quat_float[2], quat_float[3]
                                    )
                                    # 直接写入共享内存
                                    self.Mouse_Mem.seek(0)
                                    self.Mouse_Mem.write(packed_data)
                                    self.Mouse_Mem.flush()
                                    print("已将IMU数据写入共享内存")
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
                    
            
            # 添加事件处理函数
            target_characteristic.add_value_changed(value_changed_handler)
            
            # 开启通知
            config_result = await target_characteristic.write_client_characteristic_configuration_descriptor_async(
                GattClientCharacteristicConfigurationDescriptorValue.NOTIFY
            )
            
            if config_result == 0:  # 成功
                print("成功订阅特征值通知")
                return True
            else:
                print(f"订阅特征值通知失败，状态码: {config_result}")
                return False
        except Exception as e:
            print(f"订阅特征值时出错: {e}")
            return False

async def main():
    """主函数 - 用于测试"""
    print("FUKY_BleDeviceBase测试程序")
    print("=" * 40)
    
    
    # 创建BLE设备对象
    ble_device_base = FUKY_BleDeviceBase()
    
    # 启动BLE设备处理进程
    ble_device_base.start_ble_process()
    
    # 等待设备被找到
    print("等待BLE设备被找到...")
    
    try:
        while not ble_device_base.is_device_found():
            print("检查标志位: ", ble_device_base.is_device_found())
            
            await asyncio.sleep(1)
        
        print("BLE设备已找到！标志位已设置为True")
        
        
        # 从队列中读取数据
        print("\n开始从队列中读取数据...")
        
        count = 0
        max_count = 30  # 最多等待30秒
        
        while count < max_count:
            await asyncio.sleep(1)
            count += 1
            
            # 每5秒打印一次状态
            if count % 5 == 0:
                print(f"等待数据中... {count}/{max_count}")
                
    
    except KeyboardInterrupt:
        print("程序被用户中断")
        
    finally:
        # 停止BLE设备处理进程
        ble_device_base.stop_ble_process()
        print("\n测试完成")
        

if __name__ == "__main__":
    # 运行异步主函数
    if sys.platform == "win32":
        asyncio.run(main())
    else:
        print("错误: 此程序仅支持Windows平台")
