import mmap

class FUKY_SharedMemory:

    def __init__(self):
        """
        初始化Windows共享内存
        :param name: 共享内存标识名
        :param size: 内存区域大小(字节)
        """
        self.Mouse_Mem_name="FUKY_Mouse_Memory"
        self.MouseSize = 32
        self.Locator_Mem_name="FUKY_Locator_Memory"
        self.LocatorSize = 12
        # 创建Mouse共享内存
        self.Mouse_Mem = mmap.mmap(
            -1,  # 使用匿名映射
            self.MouseSize,
            self.Mouse_Mem_name,
            access=mmap.ACCESS_WRITE
        )
        self.ClearMemory(self.Mouse_Mem,self.MouseSize)
        # 创建Locator共享内存
        self.Locator_Mem = mmap.mmap(
            -1,  # 使用匿名映射
            self.LocatorSize,
            self.Locator_Mem_name,
            access=mmap.ACCESS_WRITE
        )
        self.ClearMemory(self.Locator_Mem,self.LocatorSize)
        
    def ClearMemory(self, Target, size):
        # 清空内存区域
        Target.seek(0)
        Target.write(b'\x00' * size)

    def Mouse_Write(self,packed_data):
        """
        创建共享内存并写入数据
        :注意写入的数据大小必须是28字节，每个是占两字节的float\n
        :--4字节--4字节---4字节---4字节---4字节---4字节---4字节--4字节\n
        :加速度X-加速度y-加速度z---QX------QY------QZ------QW----PRESS 
        """
        try:            
            self.Mouse_Mem.seek(0)
            self.Mouse_Mem.write(packed_data)
            self.Mouse_Mem.flush()

        except Exception as e:
            raise RuntimeError(f"Failed to create shared memory: {str(e)}")

    def Locator_Write(self,packed_data):
        """
        创建共享内存并写入数据
        :注意写入的数据大小必须是28字节，每个是占两字节的float\n
        :4字节---4字节---4字节\n
        :坐标X---坐标y---坐标z 
        """
        try:            
            self.Locator_Mem.seek(0)
            self.Locator_Mem.write(packed_data)
            self.Locator_Mem.flush()

        except Exception as e:
            raise RuntimeError(f"Failed to create shared memory: {str(e)}")

    def __del__(self):
        """自动清理资源"""
        if self.Mouse_Mem:
            self.Mouse_Mem.close()
        if self.Locator_Mem:
            self.Locator_Mem.close()

# 使用示例
if __name__ == "__main__":
    shm = FUKY_SharedMemory()
    shm.create_and_write()
    input("Press Enter to exit and release memory...")
