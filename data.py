    def _notification_handler(self, data):
        """处理IMU数据通知"""
        try:
            if len(data) == 14:
                # 解析原始数据
                lin_accel = struct.unpack('<3h', data[0:6])
                quat = struct.unpack('<4h', data[6:14])

                # 转换为浮点数
                imu_data = {
                    'accel': tuple(v * self.SCALE_Q8 for v in lin_accel),
                    'quat': tuple(v * self.SCALE_Q14 for v in quat)
                }
                self._shared['imu_data'] = imu_data
        except Exception as e:
            print(f"Data parsing error: {e}")

    DEVICE_NAME = "FUKY_MOUSE"
    SERVICE_UUID = "0000f233-0000-1000-8000-00805f9b34fb"
    CHARACTERISTIC_UUID = "0000f666-0000-1000-8000-00805f9b34fb"
    SCALE_Q14 = 1.0 / (1 << 14)
    SCALE_Q8 = 1.0 / (1 << 8)
    
    
    备份：
    """
    蓝牙设备检测程序
    使用Windows WinRT库检测并打印连接到Windows的蓝牙设备名称
    """
    import asyncio
    import sys
    from winrt.windows.devices.bluetooth import BluetoothAdapter, BluetoothDevice, BluetoothLEDevice # 导入WinRT库
    from winrt.windows.devices.bluetooth import BluetoothConnectionStatus
    from winrt.windows.devices.enumeration import DeviceInformation, DeviceInformationKind


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
        
        async def get_paired_devices(self):
            """获取已配对的蓝牙设备，不考虑该方法，因为我们设备是BLE设备"""
            print("\n正在获取已配对的蓝牙设备...")
            try:
                # 使用选择器字符串获取已配对的蓝牙设备
                # 这里使用BluetoothDevice的get_device_selector_from_pairing_state方法获取已配对设备的选择器
                selector = BluetoothDevice.get_device_selector_from_pairing_state(True)
                
                # 定义要获取的额外属性
                additional_properties = ["System.Devices.Aep.DeviceAddress", 
                                        "System.Devices.Aep.IsConnected", 
                                        "System.Devices.Aep.IsPaired",
                                        "System.ItemNameDisplay"]
                
                # 使用DeviceInformationKind.ASSOCIATION_ENDPOINT作为设备信息类型
                # 这是蓝牙设备通常使用的类型
                devices_info = await DeviceInformation.find_all_async(
                    selector, 
                    additional_properties, 
                    DeviceInformationKind.ASSOCIATION_ENDPOINT
                )
                
                if devices_info.size == 0:
                    print("未找到已配对的蓝牙设备")
                    return
                
                print(f"\n找到 {devices_info.size} 个已配对的蓝牙设备:")
                
                # 遍历并打印设备信息
                for i, device_info in enumerate(devices_info):
                    # 获取设备名称
                    device_name = device_info.name or "未知设备"
                    
                    # 获取设备ID
                    device_id = device_info.id
                    
                    # 获取设备地址（如果可用）
                    device_address = "未知"
                    if "System.Devices.Aep.DeviceAddress" in device_info.properties:
                        device_address = device_info.properties["System.Devices.Aep.DeviceAddress"]
                    
                    # 检查设备是否已连接
                    is_connected = False
                    if "System.Devices.Aep.IsConnected" in device_info.properties:
                        is_connected = device_info.properties["System.Devices.Aep.IsConnected"]
                    
                    # 打印设备信息
                    print(f"{i+1}. 名称: {device_name}")
                    print(f"   设备ID: {device_id}")
                    print(f"   设备地址: {device_address}")
                    print(f"   连接状态: {'已连接' if is_connected else '未连接'}")
                    print()
                    
                    # 如果设备已连接，尝试获取更多信息
                    if is_connected:
                        try:
                            # 尝试从设备ID创建BluetoothDevice对象
                            bluetooth_device = await BluetoothDevice.from_id_async(device_id)
                            if bluetooth_device:
                                print(f"   蓝牙地址: {bluetooth_device.bluetooth_address}")
                                print(f"   设备类型: {bluetooth_device.class_of_device.major_device_class}")
                                print()
                        except Exception as e:
                            print(f"   获取设备详细信息时出错: {e}")
                            print()
                
            except Exception as e:
                print(f"获取已配对设备时出错: {e}")
        
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
                    return
                
                print(f"\n找到 {devices_info.size} 个已连接的BLE设备:")
                
                # 遍历并打印设备信息
                for i, device_info in enumerate(devices_info):
                    # 获取设备名称
                    device_name = device_info.name or "未知设备"
                    
                    # 获取设备ID
                    device_id = device_info.id
                    
                    # 打印基本设备信息
                    print(f"{i+1}. 名称: {device_name}")
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
                                    return ble_device
                            except Exception as e:
                                print(f"   获取GATT服务时出错: {e}")
                    except Exception as e:
                        print(f"   获取BLE设备详细信息时出错: {e}")
                    
                    print()
                
            except Exception as e:
                print(f"获取已连接BLE设备时出错: {e}")

    async def main():
        """主函数"""
        print("FUKY_BleDeviceBase检测程序")
        print("=" * 40)
        
        scanner = FUKY_BleDeviceBase()
        
        # 获取蓝牙适配器信息
        adapter = await scanner.get_bluetooth_adapter()
        if adapter:
            # 注意：BluetoothAdapter没有name属性，只打印蓝牙地址
            print(f"蓝牙适配器已找到")
            print(f"蓝牙地址: {adapter.bluetooth_address}")
            
            # 检查蓝牙是否开启
            if not adapter.is_central_role_supported:
                print("警告: 此蓝牙适配器不支持中央角色，可能无法扫描设备")
            
            # 获取已连接的BLE设备
            await scanner.get_connected_ble_devices()
        else:
            print("无法获取蓝牙适配器信息，请确保蓝牙已开启")

    if __name__ == "__main__":
        # 运行异步主函数
        if sys.platform == "win32":
            asyncio.run(main())
        else:
            print("错误: 此程序仅支持Windows平台")
    