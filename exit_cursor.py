import psutil  # 导入进程操作模块，用于获取和控制系统进程
from logger import logging  # 导入日志模块，用于记录程序运行状态
import time  # 导入时间模块，用于实现超时等待功能

def ExitCursor(timeout=5):
    """
    温和地关闭 Cursor 进程
    
    此函数会尝试优雅地关闭所有运行中的Cursor进程，首先使用温和的终止信号，
    然后等待一段时间让进程自然结束，避免强制终止可能带来的数据丢失风险。
    
    Args:
        timeout (int): 等待进程自然终止的超时时间（秒），默认为5秒
    Returns:
        bool: 是否成功关闭所有进程，成功返回True，否则返回False
    """
    try:
        # 记录开始退出的日志信息
        logging.info("开始退出Cursor...")
        # 初始化一个空列表用于存储找到的Cursor进程
        cursor_processes = []
        
        # 遍历系统中所有进程，收集所有Cursor相关进程
        for proc in psutil.process_iter(['pid', 'name']):  # 只获取进程ID和名称信息以提高效率
            try:
                # 检查进程名称是否为Cursor（考虑不同操作系统下的命名差异）
                if proc.info['name'].lower() in ['cursor.exe', 'cursor']:
                    cursor_processes.append(proc)  # 将找到的Cursor进程添加到列表中
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # 捕获并忽略进程不存在或无权限访问的异常
                # 这些异常可能在遍历过程中出现，因为进程状态可能随时变化
                continue

        # 如果没有找到任何Cursor进程，记录信息并返回成功
        if not cursor_processes:
            logging.info("未发现运行中的 Cursor 进程")
            return True

        # 对每个找到的Cursor进程发送温和的终止信号
        for proc in cursor_processes:
            try:
                # 确认进程仍在运行中（防止在操作前进程已经结束）
                if proc.is_running():
                    proc.terminate()  # 发送终止信号，比kill()更温和，允许进程清理资源
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # 忽略进程已不存在或无权限终止的情况
                continue

        # 记录当前时间作为等待开始时间点
        start_time = time.time()
        
        # 在超时时间内循环检查进程是否已经终止
        while time.time() - start_time < timeout:
            # 用于存储仍在运行的进程
            still_running = []
            
            # 检查每个进程的状态
            for proc in cursor_processes:
                try:
                    # 如果进程仍在运行，则添加到still_running列表
                    if proc.is_running():
                        still_running.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # 忽略进程已不存在或无权限访问的情况
                    continue
            
            # 如果没有仍在运行的进程，表示所有进程已经成功关闭
            if not still_running:
                logging.info("所有 Cursor 进程已正常关闭")
                return True
                
            # 短暂等待后再次检查，减少CPU使用率并给进程时间结束
            time.sleep(0.5)
            
        # 如果超时后仍有进程在运行，记录未能关闭的进程ID并返回失败
        if still_running:
            # 将进程ID列表转换为字符串，用逗号分隔
            process_list = ", ".join([str(p.pid) for p in still_running])
            logging.warning(f"以下进程未能在规定时间内关闭: {process_list}")
            return False
            
        # 如果代码执行到这里（理论上不会），意味着所有进程已关闭
        return True

    except Exception as e:
        # 捕获并记录任何未预期的异常
        logging.error(f"关闭 Cursor 进程时发生错误: {str(e)}")
        return False

# 当脚本作为主程序直接运行时执行
if __name__ == "__main__":
    # 直接调用ExitCursor函数关闭所有Cursor进程
    ExitCursor()
