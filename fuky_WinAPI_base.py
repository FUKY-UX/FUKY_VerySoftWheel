import ctypes
import ctypes.wintypes
import threading
#每个进程都有一个该类用于处理window事件对象
#在关闭进程的时候记得调用
#自己的FUKY_WindowAPIHandler类中的destroy_all_events

class FUKY_WindowAPIHandler:
    
    def __init__(self):
        # 定义 Windows API 函数
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        
        # 函数原型声明
        self.CreateEvent = self.kernel32.CreateEventW
        self.CreateEvent.argtypes = [
            ctypes.wintypes.LPVOID,  # 安全属性（通常为 NULL）
            ctypes.wintypes.BOOL,    # 手动重置（True）或自动重置（False）
            ctypes.wintypes.BOOL,    # 初始状态（True 为已触发）
            ctypes.wintypes.LPCWSTR  # 事件对象名称
        ]
        self.CreateEvent.restype = ctypes.wintypes.HANDLE
        
        # 关闭事件句柄的函数
        self.CloseHandle = self.kernel32.CloseHandle
        self.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        self.CloseHandle.restype = ctypes.wintypes.BOOL
        
        self.AllFukyEvent = []
        self.EmptySlotIndex = 0
    
    def Creat_WinEvent(self, Event_Name, Security=None, DontAutoReset=True, OriginSet=False):
        """返回创建的命名事件对象"""
        # 全局命名空间需前缀 "Global\\"
        event_name = f"Global\\FukyDeviceEvent_{Event_Name}"
        
        # 创建事件
        event_handle = self.CreateEvent(
            Security,       # 默认安全属性
            DontAutoReset,  # 手动重置（True 表示需手动调用 ResetEvent）
            OriginSet,      # 初始状态为未触发
            event_name      # 事件名称
        )
        
        if not event_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        
        # 确保列表足够大
        if self.EmptySlotIndex >= len(self.AllFukyEvent):
            self.AllFukyEvent.append(event_handle)
        else:
            self.AllFukyEvent[self.EmptySlotIndex] = event_handle
            
        self.EmptySlotIndex += 1
        print(f"事件对象已创建，句柄: {event_handle}, 事件名: {event_name}")
        return event_handle
    
    def set_event(self, event_handle):
        """触发事件"""
        self.kernel32.SetEvent(event_handle)
    
    def reset_event(self, event_handle):
        """重置事件"""
        self.kernel32.ResetEvent(event_handle)
    
    def destroy_all_events(self):
        """销毁所有创建的事件对象"""
        for handle in self.AllFukyEvent:
            if handle:
                self.CloseHandle(handle)
        self.AllFukyEvent = []
        self.EmptySlotIndex = 0
        print("所有事件对象已销毁")
    
    def __del__(self):
        """析构函数，确保资源释放"""
        self.destroy_all_events()
        
if __name__ == "__main__":
    import time
    import sys
    
    def test_event_communication():
        handler = FUKY_WindowAPIHandler()
        
        try:
            # Create a named event
            event_name = "UnityTestEvent"
            event_handle = handler.Creat_WinEvent(event_name)
            
            print("\nPython Event Controller")
            print("----------------------")
            print("1. Trigger event (SetEvent)")
            print("2. Reset event")
            print("3. Exit")
            
            while True:
                choice = input("\nEnter choice (1-3): ")
                
                if choice == "1":
                    handler.set_event(event_handle)
                    print("Event triggered! Unity should detect this.")
                elif choice == "2":
                    handler.reset_event(event_handle)
                    print("Event reset. Unity can wait for it again.")
                elif choice == "3":
                    break
                else:
                    print("Invalid choice")
        
        finally:
            handler.destroy_all_events()
    
    test_event_communication()