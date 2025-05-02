"""
蓝牙设备检测程序
使用Windows WinRT库检测并打印连接到Windows的蓝牙设备名称
支持多进程运行和进程间通信
"""
import asyncio
import sys
import multiprocessing
import time
import ctypes  # 用于定义共享内存中的布尔类型
import struct  # 用于解析二进制数据

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
        self.HID_SERVICE_UUID = "00001812-0000-1000-8000-00805f9b34fb"
        self.SCALE_Q14 = 1.0 / (1 << 14)
        self.SCALE_Q8 = 1.0 / (1 << 8)
        
        # 多进程共享变量
        self.device_found_flag = multiprocessing.Value(ctypes.c_bool, False)
        self.data_queue = multiprocessing.Queue()  # 用于传输BLE设备返回的数据
        self.ble_process = None
        
        # BLE设备对象（仅在BLE进程中有效）
        self.FUKY_Mouse_Device = None
        self.characteristic = None
        
    def start_ble_process(self):
        """启动BLE设备处理进程"""
        if self.ble_process is not None and self.ble_process.is_alive():
            print("BLE进程已经在运行中")
            sys.stdout.flush()
            return
        
        # 创建并启动进程
        self.ble_process = multiprocessing.Process(
            target=self.ble_process_function, 
            args=(self.device_found_flag, self.data_queue)
        )
        self.ble_process.daemon = True  # 设置为守护进程，主进程退出时自动结束
        self.ble_process.start()
        
        print(f"已启动BLE设备处理进程，PID: {self.ble_process.pid}")
        sys.stdout.flush()
    
    def is_device_found(self):
        """检查是否找到BLE设备"""
        return self.device_found_flag.value
    
    def get_data(self, block=False, timeout=None):
        """从数据队列中获取数据
        
        Args:
            block: 是否阻塞等待数据
            timeout: 超时时间（秒）
            
        Returns:
            数据，如果没有数据则返回None
        """
        try:
            if block:
                return self.data_queue.get(block=True, timeout=timeout)
            else:
                return self.data_queue.get_nowait()
        except:
            return None
    
    def stop_ble_process(self):
        """停止BLE设备处理进程"""
        if self.ble_process is not None and self.ble_process.is_alive():
            self.ble_process.terminate()
            self.ble_process.join(timeout=1.0)
            print("已停止BLE设备处理进程")
            sys.stdout.flush()
            self.ble_process = None
    
    @staticmethod
    def ble_process_function(device_found_flag, data_queue):
        """BLE设备处理进程的主函数
        
        Args:
            device_found_flag: 多进程共享的标志位，表示是否找到设备
            data_queue: 多进程共享的队列，用于传输BLE设备返回的数据
        """
        # 创建一个新的FUKY_BleDeviceBase实例，用于BLE进程
        ble_handler = FUKY_BleDeviceBase()
        # 使用传入的共享变量替换实例中的变量
        ble_handler.device_found_flag = device_found_flag
        ble_handler.data_queue = data_queue
        
        # 运行异步主函数
        if sys.platform == "win32":
            asyncio.run(ble_handler.async_main())
        else:
            print("错误: 此程序仅支持Windows平台")
            sys.stdout.flush()
    
    async def async_main(self):
        """BLE设备处理进程的异步主函数"""
        print("BLE设备处理进程已启动")
        sys.stdout.flush()
        
        # 获取蓝牙适配器
        adapter = await self.get_bluetooth_adapter()
        if adapter is None:
            print("无法获取蓝牙适配器，进程退出")
            sys.stdout.flush()
            return
        
        print("蓝牙适配器已找到")
        print(f"蓝牙地址: {adapter.bluetooth_address}")
        sys.stdout.flush()
        
        # 检查蓝牙是否开启
        if not adapter.is_central_role_supported:
            print("警告: 此蓝牙适配器不支持中央角色，可能无法扫描设备")
            sys.stdout.flush()
        
        # 获取已连接的BLE设备
        self.FUKY_Mouse_Device = await self.get_connected_ble_devices()
        if self.FUKY_Mouse_Device is None:
            print("未找到目标BLE设备，进程退出")
            sys.stdout.flush()
            return
        
        # 订阅特征值通知
        success = await self.subscribe_to_characteristic()
        if not success:
            print("订阅特征值通知失败，进程退出")
            sys.stdout.flush()
            return
        
        # 保持进程运行，处理特征值通知
        print("BLE设备已找到并订阅特征值通知，进程继续运行...")
        sys.stdout.flush()
        while True:
            await asyncio.sleep(1)
    
    async def get_bluetooth_adapter(self):
        """获取默认蓝牙适配器"""
        try:
            adapter = await BluetoothAdapter.get_default_async()
            if adapter is None:
                print("错误: 未找到蓝牙适配器")
                sys.stdout.flush()
                return None
            return adapter
        except Exception as e:
            print(f"获取蓝牙适配器时出错: {e}")
            sys.stdout.flush()
            return None
    
    async def get_connected_ble_devices(self):
        """获取已连接的蓝牙低功耗(BLE)设备"""
        print("\n正在获取已连接的BLE设备...")
        sys.stdout.flush()
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
                sys.stdout.flush()
                return None
            
            print(f"\n找到 {devices_info.size} 个已连接的BLE设备:")
            sys.stdout.flush()
            
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
                    sys.stdout.flush()
                    
                    # 尝试获取更多BLE设备信息
                    try:
                        # 从设备ID创建BluetoothLEDevice对象
                        ble_device = await BluetoothLEDevice.from_id_async(device_id)
                        if ble_device:
                            print(f"   蓝牙地址: {ble_device.bluetooth_address}")
                            print(f"   连接状态: {'已连接' if ble_device.connection_status == BluetoothConnectionStatus.CONNECTED else '未连接'}")
                            sys.stdout.flush()
                            
                            # 尝试获取GATT服务信息
                            try:
                                services = await ble_device.get_gatt_services_async()
                                if services.status == 0:  # 成功
                                    print(f"   GATT服务数量: {services.services.size}")
                                    sys.stdout.flush()
                                    # 设置标志位，通知主进程已找到设备
                                    self.device_found_flag.value = True
                                    print("   已设置设备找到标志位")
                                    sys.stdout.flush()
                                    
                                    return ble_device
                            except Exception as e:
                                print(f"   获取GATT服务时出错: {e}")
                                sys.stdout.flush()
                    except Exception as e:
                        print(f"   获取BLE设备详细信息时出错: {e}")
                        sys.stdout.flush()
            
            return None
        except Exception as e:
            print(f"获取已连接BLE设备时出错: {e}")
            sys.stdout.flush()
            return None
    
    async def subscribe_to_characteristic(self):
        """订阅BLE设备的特征值通知"""
        if self.FUKY_Mouse_Device is None:
            print("错误: 未找到BLE设备，无法订阅特征值")
            sys.stdout.flush()
            return False
        
        try:
            print(f"\n正在查找服务: {self.SERVICE_UUID}")
            sys.stdout.flush()
            
            # 获取目标服务
            services_result = await self.FUKY_Mouse_Device.get_gatt_services_async()
            if services_result.status != 0:
                print(f"获取服务失败，状态码: {services_result.status}")
                sys.stdout.flush()
                return False
            
            target_service = None
            for service in services_result.services:
                if str(service.uuid).lower() == self.SERVICE_UUID.lower():
                    target_service = service
                    print(f"找到目标服务: {service.uuid}")
                    sys.stdout.flush()
                    break
            
            if target_service is None:
                print(f"未找到目标服务: {self.SERVICE_UUID}")
                sys.stdout.flush()
                return False
            
            # 获取目标特征值
            characteristics_result = await target_service.get_characteristics_async()
            if characteristics_result.status != 0:
                print(f"获取特征值失败，状态码: {characteristics_result.status}")
                sys.stdout.flush()
                return False
            
            target_characteristic = None
            for characteristic in characteristics_result.characteristics:
                if str(characteristic.uuid).lower() == self.CHARACTERISTIC_UUID.lower():
                    target_characteristic = characteristic
                    print(f"找到目标特征值: {characteristic.uuid}")
                    sys.stdout.flush()
                    break
            
            if target_characteristic is None:
                print(f"未找到目标特征值: {self.CHARACTERISTIC_UUID}")
                sys.stdout.flush()
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
                        
                        # 将buffer中的数据复制到字节数组中
                        for i in range(buffer.length):
                            data[i] = buffer.get_byte(i)
                        
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
                            sys.stdout.flush()
                            
                            # 将数据放入队列，供主进程使用
                            self.data_queue.put(imu_data)
                            print("已将解析后的IMU数据放入队列")
                            sys.stdout.flush()
                        except Exception as e:
                            print(f"解析IMU数据时出错: {e}")
                            sys.stdout.flush()
                            # 如果解析失败，仍然将原始数据放入队列
                            self.data_queue.put({'raw_data': data.hex()})
                    else:
                        if buffer:
                            print(f"收到数据长度不正确: {buffer.length}字节")
                        else:
                            print("收到空buffer")
                        sys.stdout.flush()
                        
                except Exception as e:
                    print(f"处理特征值通知时出错: {e}")
                    sys.stdout.flush()
            
            # 添加事件处理函数
            target_characteristic.add_value_changed(value_changed_handler)
            
            # 开启通知
            config_result = await target_characteristic.write_client_characteristic_configuration_descriptor_async(
                GattClientCharacteristicConfigurationDescriptorValue.NOTIFY
            )
            
            if config_result == 0:  # 成功
                print("成功订阅特征值通知")
                sys.stdout.flush()
                return True
            else:
                print(f"订阅特征值通知失败，状态码: {config_result}")
                sys.stdout.flush()
                return False
            
        except Exception as e:
            print(f"订阅特征值时出错: {e}")
            sys.stdout.flush()
            return False

async def main():
    """主函数 - 用于测试"""
    print("FUKY_BleDeviceBase测试程序")
    print("=" * 40)
    sys.stdout.flush()
    
    # 创建BLE设备对象
    ble_device_base = FUKY_BleDeviceBase()
    
    # 启动BLE设备处理进程
    ble_device_base.start_ble_process()
    
    # 等待设备被找到
    print("等待BLE设备被找到...")
    sys.stdout.flush()
    try:
        while not ble_device_base.is_device_found():
            print("检查标志位: ", ble_device_base.is_device_found())
            sys.stdout.flush()
            await asyncio.sleep(1)
        
        print("BLE设备已找到！标志位已设置为True")
        sys.stdout.flush()
        
        # 从队列中读取数据
        print("\n开始从队列中读取数据...")
        sys.stdout.flush()
        count = 0
        max_count = 30  # 最多等待30秒
        
        while count < max_count:
            # 非阻塞方式检查队列
            data = ble_device_base.get_data(block=False)
            if data is not None:
                if isinstance(data, dict):
                    if 'accel' in data and 'quat' in data:
                        print(f"收到IMU数据:")
                        print(f"  原始数据: {data.get('raw_data', 'N/A')}")
                        print(f"  加速度 (g): {data['accel']}")
                        print(f"  四元数: {data['quat']}")
                    else:
                        print(f"收到原始数据: {data.get('raw_data', 'N/A')}")
                else:
                    print(f"收到数据: {data}")
                sys.stdout.flush()
            
            await asyncio.sleep(1)
            count += 1
            
            # 每5秒打印一次状态
            if count % 5 == 0:
                print(f"等待数据中... {count}/{max_count}")
                sys.stdout.flush()
    
    except KeyboardInterrupt:
        print("程序被用户中断")
        sys.stdout.flush()
    finally:
        # 停止BLE设备处理进程
        ble_device_base.stop_ble_process()
        print("\n测试完成")
        sys.stdout.flush()

if __name__ == "__main__":
    # 运行异步主函数
    if sys.platform == "win32":
        asyncio.run(main())
    else:
        print("错误: 此程序仅支持Windows平台")
        sys.stdout.flush()