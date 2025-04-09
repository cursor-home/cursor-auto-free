import os  # 导入操作系统模块，用于文件路径操作
import sys  # 导入系统模块，用于获取平台信息
import json  # 导入JSON模块，用于读写配置文件
import uuid  # 导入UUID模块，用于生成唯一标识符
import hashlib  # 导入哈希库，用于生成安全的哈希值
import shutil  # 导入文件操作模块，用于文件复制等操作
from colorama import Fore, Style, init  # 导入colorama模块，用于终端彩色输出

# 初始化colorama，使终端支持彩色输出
init()

# 定义emoji和颜色常量，用于美化终端输出
EMOJI = {
    "FILE": "📄",  # 文件图标
    "BACKUP": "💾",  # 备份图标
    "SUCCESS": "✅",  # 成功图标
    "ERROR": "❌",  # 错误图标
    "INFO": "ℹ️",  # 信息图标
    "RESET": "🔄",  # 重置图标
}


class MachineIDResetter:
    """
    Cursor机器标识重置工具类
    用于重置Cursor应用的机器ID，以重新获取免费使用额度
    """
    def __init__(self):
        """
        初始化函数，根据不同操作系统确定配置文件路径
        """
        # 判断当前操作系统类型并设置相应的配置文件路径
        if sys.platform == "win32":  # Windows系统
            appdata = os.getenv("APPDATA")  # 获取Windows的APPDATA环境变量
            if appdata is None:
                raise EnvironmentError("APPDATA 环境变量未设置")  # 环境变量不存在时抛出异常
            # 设置Windows系统下Cursor配置文件的完整路径
            self.db_path = os.path.join(
                appdata, "Cursor", "User", "globalStorage", "storage.json"
            )
        elif sys.platform == "darwin":  # macOS系统
            # 设置macOS系统下Cursor配置文件的完整路径
            self.db_path = os.path.abspath(
                os.path.expanduser(
                    "~/Library/Application Support/Cursor/User/globalStorage/storage.json"
                )
            )
        elif sys.platform == "linux":  # Linux和其他类Unix系统
            # 设置Linux系统下Cursor配置文件的完整路径
            self.db_path = os.path.abspath(
                os.path.expanduser("~/.config/Cursor/User/globalStorage/storage.json")
            )
        else:
            # 不支持的操作系统类型抛出异常
            raise NotImplementedError(f"不支持的操作系统: {sys.platform}")

    def generate_new_ids(self):
        """
        生成新的机器标识ID
        
        返回:
            dict: 包含所有需要更新的机器标识的字典
        """
        # 生成新的UUID作为设备ID
        dev_device_id = str(uuid.uuid4())  # 生成随机UUID字符串

        # 生成新的machineId (使用SHA-256生成64个字符的十六进制)
        machine_id = hashlib.sha256(os.urandom(32)).hexdigest()  # 使用随机32字节数据生成哈希值

        # 生成新的macMachineId (使用SHA-512生成128个字符的十六进制)
        mac_machine_id = hashlib.sha512(os.urandom(64)).hexdigest()  # 使用随机64字节数据生成哈希值

        # 生成新的sqmId (服务质量监控ID，使用大写的UUID并用花括号包围)
        sqm_id = "{" + str(uuid.uuid4()).upper() + "}"

        # 返回包含所有新生成ID的字典
        return {
            "telemetry.devDeviceId": dev_device_id,    # 开发设备ID
            "telemetry.macMachineId": mac_machine_id,  # MAC机器ID
            "telemetry.machineId": machine_id,         # 机器ID
            "telemetry.sqmId": sqm_id,                 # 服务质量监控ID
        }

    def reset_machine_ids(self):
        """
        重置机器ID并输出结果
        
        返回:
            bool: 操作是否成功
        """
        try:
            # 打印开始检查配置文件的提示信息
            print(f"{Fore.CYAN}{EMOJI['INFO']} 正在检查配置文件...{Style.RESET_ALL}")

            # 检查配置文件是否存在
            if not os.path.exists(self.db_path):
                # 文件不存在时打印错误信息并返回失败
                print(
                    f"{Fore.RED}{EMOJI['ERROR']} 配置文件不存在: {self.db_path}{Style.RESET_ALL}"
                )
                return False

            # 检查配置文件的读写权限
            if not os.access(self.db_path, os.R_OK | os.W_OK):
                # 没有读写权限时打印错误信息
                print(
                    f"{Fore.RED}{EMOJI['ERROR']} 无法读写配置文件，请检查文件权限！{Style.RESET_ALL}"
                )
                # 提示可能是由于使用了go-cursor-help工具导致文件只读
                print(
                    f"{Fore.RED}{EMOJI['ERROR']} 如果你使用过 go-cursor-help 来修改 ID; 请修改文件只读权限 {self.db_path} {Style.RESET_ALL}"
                )
                return False

            # 读取现有配置文件
            print(f"{Fore.CYAN}{EMOJI['FILE']} 读取当前配置...{Style.RESET_ALL}")
            with open(self.db_path, "r", encoding="utf-8") as f:
                config = json.load(f)  # 将JSON配置文件加载为Python字典

            # 生成新的机器标识
            print(f"{Fore.CYAN}{EMOJI['RESET']} 生成新的机器标识...{Style.RESET_ALL}")
            new_ids = self.generate_new_ids()  # 调用方法生成新的ID

            # 使用新生成的ID更新配置字典
            config.update(new_ids)

            # 将更新后的配置保存回文件
            print(f"{Fore.CYAN}{EMOJI['FILE']} 保存新配置...{Style.RESET_ALL}")
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)  # 将更新后的配置写入文件，使用4空格缩进美化JSON

            # 打印成功信息
            print(f"{Fore.GREEN}{EMOJI['SUCCESS']} 机器标识重置成功！{Style.RESET_ALL}")
            # 打印新的机器标识信息
            print(f"\n{Fore.CYAN}新的机器标识:{Style.RESET_ALL}")
            for key, value in new_ids.items():
                print(f"{EMOJI['INFO']} {key}: {Fore.GREEN}{value}{Style.RESET_ALL}")

            return True  # 返回成功标志

        except PermissionError as e:
            # 捕获权限错误异常
            print(f"{Fore.RED}{EMOJI['ERROR']} 权限错误: {str(e)}{Style.RESET_ALL}")
            # 提示用户以管理员身份运行
            print(
                f"{Fore.YELLOW}{EMOJI['INFO']} 请尝试以管理员身份运行此程序{Style.RESET_ALL}"
            )
            return False  # 返回失败标志
        except Exception as e:
            # 捕获其他所有异常
            print(f"{Fore.RED}{EMOJI['ERROR']} 重置过程出错: {str(e)}{Style.RESET_ALL}")
            return False  # 返回失败标志


# 当脚本直接运行时执行的代码块
if __name__ == "__main__":
    # 打印分隔线和标题
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{EMOJI['RESET']} Cursor 机器标识重置工具{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")

    # 创建重置器对象并执行重置操作
    resetter = MachineIDResetter()
    resetter.reset_machine_ids()

    # 打印结束分隔线并等待用户按键退出
    print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    input(f"{EMOJI['INFO']} 按回车键退出...")
