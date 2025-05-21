import mmap
import struct

def check_shared_memory():
    try:
        # 检查按钮内存
        with mmap.mmap(-1, 1, "BTN_Memory") as btn_mem:
            print(f"当前按钮状态: {btn_mem[0]}")
            
        # 检查IMU内存
        with mmap.mmap(-1, 28, "IMU_Memory") as imu_mem:  # 7个float×4字节=28
            data = struct.unpack('<7f', imu_mem.read(28))
            print(f"IMU数据: {data}")
            
    except Exception as e:
        print(f"验证失败: {str(e)}")

if __name__ == "__main__":
    while True:
        input("按回车键检查共享内存...")
        check_shared_memory()