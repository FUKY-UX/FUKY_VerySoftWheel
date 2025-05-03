"""
测试BLE设备处理进程
模拟主进程，验证标志位是否能被正常读取，以及数据是否能被正常传输
"""
import asyncio
import sys
import time
# 导入FUKY_BleDeviceBase类
from fuky_device_BleData import FUKY_BleDeviceBase

async def main():
    """主函数 - 模拟主进程"""
    print("BLE设备处理进程测试程序")
    print("=" * 40)

    # 创建BLE设备对象
    ble_device_base = FUKY_BleDeviceBase()
    
    # 启动BLE设备处理进程
    ble_device_base.start_ble_process()
    
    # 等待设备被找到
    print("主进程正在等待BLE设备被找到...")
    try:
        # 每秒检查一次标志位
        for i in range(30):  # 最多等待30秒
            found = ble_device_base.is_device_found()
            print(f"检查标志位 ({i+1}/30): {found}")
            
            if found:
                print("\n成功: BLE设备已找到！标志位已被设置为True")
                print("这证明多进程通信正常工作，子进程能够成功通知主进程")
                break
                
            await asyncio.sleep(1)
        else:
            print("\n超时: 30秒内未找到BLE设备")
            return
        
        # 如果找到设备，开始从队列中读取数据
        if ble_device_base.is_device_found():
            print("\n开始从队列中读取数据...")
            count = 0
            max_count = 60  # 最多等待60秒
            
            while count < max_count:
                # 非阻塞方式检查队列
                data = ble_device_base.get_data(block=False)
                if data is not None:
                    print(f"收到数据: {data.hex()}")
                
                await asyncio.sleep(0.5)  # 每0.5秒检查一次
                count += 1
                
                # 每10秒打印一次状态
                if count % 20 == 0:
                    print(f"等待数据中... {count//2}秒/{max_count//2}秒")
            
            print("\n数据接收测试完成")
    
    except KeyboardInterrupt:
        print("\n程序被用户中断")
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
