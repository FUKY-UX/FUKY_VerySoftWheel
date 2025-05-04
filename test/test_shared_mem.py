import mmap
import struct
import time

def read_shared_memory():
    # 共享内存配置（必须与写入端一致）
    SHMEM_NAME = "FUKY_Locator_Memory"
    SHMEM_SIZE = 12  # 3个float32 = 12字节

    try:
        # 打开共享内存
        with mmap.mmap(-1, SHMEM_SIZE, SHMEM_NAME, access=mmap.ACCESS_READ) as shm:
            print("成功连接到共享内存，开始读取数据...")
            print("按 Ctrl+C 停止")
            
            while True:
                try:
                    # 读取数据
                    shm.seek(0)
                    data = shm.read(SHMEM_SIZE)
                    
                    # 解包数据
                    x, y, z = struct.unpack('<3f', data)  # 小端序，3个float
                    
                    # 打印结果
                    print(f"\rX: {x:.4f} | Y: {y:.4f} | Z: {z:.4f}", end='', flush=True)
                    time.sleep(0.1)  # 降低读取频率
                    
                except KeyboardInterrupt:
                    print("\n用户中断，停止读取")
                    break
                    
    except FileNotFoundError:
        print(f"错误：找不到共享内存 '{SHMEM_NAME}'，请先启动主程序")
    except Exception as e:
        print(f"发生错误: {str(e)}")

if __name__ == "__main__":
    read_shared_memory()