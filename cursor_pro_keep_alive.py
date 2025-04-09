import os  # 导入操作系统相关功能，用于文件路径操作和环境变量设置
import platform  # 导入平台模块，用于获取系统平台信息
import json  # 导入JSON模块，用于处理配置文件
import sys  # 导入系统模块，用于系统级操作和退出程序
from colorama import Fore, Style  # 导入终端彩色输出模块
from enum import Enum  # 导入枚举类型，用于定义有限状态集合
from typing import Optional  # 导入类型提示功能，支持可选类型

# 导入自定义模块
from exit_cursor import ExitCursor  # 导入Cursor进程退出处理模块
import go_cursor_help  # 导入Cursor助手模块
import patch_cursor_get_machine_id  # 导入修补Cursor机器ID获取功能的模块
from reset_machine import MachineIDResetter  # 导入机器ID重置器

# 设置环境变量，关闭Python和PyInstaller的详细输出
os.environ["PYTHONVERBOSE"] = "0"  # 禁用Python详细日志
os.environ["PYINSTALLER_VERBOSE"] = "0"  # 禁用PyInstaller详细日志

import time  # 导入时间模块，用于延时和计时功能
import random  # 导入随机模块，用于生成随机值和模拟人工操作
from cursor_auth_manager import CursorAuthManager  # 导入Cursor认证管理器
import os  # 重复导入(可能是代码疏忽)
from logger import logging  # 导入日志模块
from browser_utils import BrowserManager  # 导入浏览器管理工具
from get_email_code import EmailVerificationHandler  # 导入邮箱验证码处理器
from logo import print_logo  # 导入徽标打印功能
from config import Config  # 导入配置模块
from datetime import datetime  # 导入日期时间模块

# 定义 EMOJI 字典，用于在日志中显示不同类型的信息图标
EMOJI = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}


class VerificationStatus(Enum):
    """
    验证状态枚举
    用于标识用户在验证流程中的不同阶段状态
    包含密码页面、验证码页面和账户设置页面三种状态
    """

    PASSWORD_PAGE = "@name=password"  # 密码输入页面的标识符
    CAPTCHA_PAGE = "@data-index=0"  # 验证码输入页面的标识符
    ACCOUNT_SETTINGS = "Account Settings"  # 账户设置页面的标识符


class TurnstileError(Exception):
    """
    Turnstile 验证相关异常
    当处理Cloudflare Turnstile人机验证出现问题时抛出
    """
    pass


def save_screenshot(tab, stage: str, timestamp: bool = True) -> None:
    """
    保存页面截图
    
    在处理Turnstile验证过程中的不同阶段保存浏览器页面截图，用于调试和记录验证过程
    
    Args:
        tab: 浏览器标签页对象，用于获取当前页面的截图
        stage: 截图阶段标识，标记当前截图对应的验证流程阶段
        timestamp: 是否添加时间戳，默认为True，用于区分同一阶段的多次截图
    """
    try:
        # 创建 screenshots 目录，用于存储截图文件
        screenshot_dir = "screenshots"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)  # 如果目录不存在则创建

        # 生成文件名，根据是否需要时间戳来决定文件名格式
        if timestamp:
            filename = f"turnstile_{stage}_{int(time.time())}.png"  # 添加Unix时间戳
        else:
            filename = f"turnstile_{stage}.png"  # 不添加时间戳的简单文件名

        # 构建完整的文件保存路径
        filepath = os.path.join(screenshot_dir, filename)

        # 使用浏览器标签对象的方法保存当前页面截图
        tab.get_screenshot(filepath)
        logging.debug(f"截图已保存: {filepath}")  # 记录截图保存成功的日志
    except Exception as e:
        # 捕获并记录截图过程中的任何异常
        logging.warning(f"截图保存失败: {str(e)}")


def check_verification_success(tab) -> Optional[VerificationStatus]:
    """
    检查验证是否成功
    
    通过检查页面元素判断Turnstile验证是否成功，并确定当前所处的页面状态
    
    Args:
        tab: 浏览器标签页对象，用于检查页面元素
        
    Returns:
        VerificationStatus: 验证成功时返回对应状态（密码页、验证码页或账户设置页），失败返回 None
    """
    # 遍历所有可能的验证状态
    for status in VerificationStatus:
        # 检查页面是否包含对应状态的元素标识
        if tab.ele(status.value):
            # 找到匹配元素，记录验证成功的日志，并返回对应状态
            logging.info(f"验证成功 - 已到达{status.name}页面")
            return status
    # 未找到任何匹配元素，表示验证可能未成功
    return None


def handle_turnstile(tab, max_retries: int = 2, retry_interval: tuple = (1, 2)) -> bool:
    """
    处理 Turnstile 验证
    
    处理Cloudflare的Turnstile人机验证，包括定位验证框、点击验证、检查结果等完整流程
    
    Args:
        tab: 浏览器标签页对象，用于交互操作验证元素
        max_retries: 最大重试次数，默认为2次
        retry_interval: 重试间隔时间范围(最小值, 最大值)，单位为秒，默认为(1, 2)
        
    Returns:
        bool: 验证是否成功，成功返回True，失败返回False
        
    Raises:
        TurnstileError: 验证过程中出现严重异常时抛出
    """
    logging.info("正在检测 Turnstile 验证...")  # 记录开始处理验证的日志
    save_screenshot(tab, "start")  # 保存验证开始前的页面截图

    retry_count = 0  # 初始化重试计数器

    try:
        # 在最大重试次数范围内尝试验证
        while retry_count < max_retries:
            retry_count += 1
            logging.debug(f"第 {retry_count} 次尝试验证")  # 记录当前尝试次数

            try:
                # 定位验证框元素，使用复杂的选择器链定位到具体的输入元素
                challenge_check = (
                    tab.ele("@id=cf-turnstile", timeout=2)  # 首先找到验证框容器，设置超时为2秒
                    .child()  # 获取子元素
                    .shadow_root.ele("tag:iframe")  # 通过影子DOM找到iframe
                    .ele("tag:body")  # 在iframe中找到body
                    .sr("tag:input")  # 在body中找到input标签
                )

                if challenge_check:
                    logging.info("检测到 Turnstile 验证框，开始处理...")
                    # 随机延时后点击验证，模拟真实用户操作
                    time.sleep(random.uniform(1, 3))  # 随机等待1-3秒
                    challenge_check.click()  # 点击验证元素
                    time.sleep(2)  # 等待验证响应

                    # 保存点击验证后的页面截图
                    save_screenshot(tab, "clicked")

                    # 检查验证结果，如果成功则直接返回
                    if check_verification_success(tab):
                        logging.info("Turnstile 验证通过")  # 记录验证通过日志
                        save_screenshot(tab, "success")  # 保存验证成功的截图
                        return True

            except Exception as e:
                # 捕获当前尝试中的异常，记录但继续下一次尝试
                logging.debug(f"当前尝试未成功: {str(e)}")

            # 再次检查是否已经验证成功（可能无需点击就已通过）
            if check_verification_success(tab):
                return True

            # 当前尝试未成功，随机延时后继续下一次尝试
            time.sleep(random.uniform(*retry_interval))  # 在指定范围内随机等待

        # 超出最大重试次数，验证失败
        logging.error(f"验证失败 - 已达到最大重试次数 {max_retries}")
        logging.error(
            "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
        )
        save_screenshot(tab, "failed")  # 保存验证失败的截图
        return False

    except Exception as e:
        # 捕获整个验证过程中的严重异常
        error_msg = f"Turnstile 验证过程发生异常: {str(e)}"
        logging.error(error_msg)  # 记录错误日志
        save_screenshot(tab, "error")  # 保存错误状态的截图
        raise TurnstileError(error_msg)  # 抛出验证错误异常


def get_cursor_session_token(tab, max_attempts=3, retry_interval=2):
    """
    获取Cursor会话token，带有重试机制
    
    从浏览器cookie中提取Cursor会话令牌，用于后续的认证操作
    
    Args:
        tab: 浏览器标签页对象，用于获取cookie
        max_attempts: 最大尝试次数，默认为3次
        retry_interval: 重试间隔(秒)，默认为2秒
        
    Returns:
        str或None: 成功时返回提取的会话令牌，失败返回None
    """
    logging.info("开始获取cookie")  # 记录开始获取cookie的日志
    attempts = 0  # 初始化尝试计数器

    # 在最大尝试次数范围内循环
    while attempts < max_attempts:
        try:
            # 获取标签页中的所有cookie
            cookies = tab.cookies()
            # 遍历cookie寻找目标令牌
            for cookie in cookies:
                if cookie.get("name") == "WorkosCursorSessionToken":
                    # 找到令牌后，使用分隔符切分并返回第二部分
                    return cookie["value"].split("%3A%3A")[1]

            # 当前尝试未成功，增加计数并决定是否重试
            attempts += 1
            if attempts < max_attempts:
                # 还有重试机会，记录警告并等待
                logging.warning(
                    f"第 {attempts} 次尝试未获取到CursorSessionToken，{retry_interval}秒后重试..."
                )
                time.sleep(retry_interval)  # 等待指定的重试间隔
            else:
                # 已达最大尝试次数，记录错误
                logging.error(
                    f"已达到最大尝试次数({max_attempts})，获取CursorSessionToken失败"
                )

        except Exception as e:
            # 捕获获取cookie过程中的异常
            logging.error(f"获取cookie失败: {str(e)}")  # 记录错误日志
            attempts += 1  # 增加尝试计数
            if attempts < max_attempts:
                # 还有重试机会，等待后重试
                logging.info(f"将在 {retry_interval} 秒后重试...")
                time.sleep(retry_interval)

    # 所有尝试都失败，返回None
    return None


def update_cursor_auth(email=None, access_token=None, refresh_token=None):
    """
    更新Cursor的认证信息的便捷函数
    
    将新的认证信息更新到Cursor应用的配置中，使应用能够使用新账号
    
    Args:
        email: 账户邮箱，可选
        access_token: 访问令牌，可选
        refresh_token: 刷新令牌，可选
        
    Returns:
        bool: 更新是否成功
    """
    # 创建认证管理器实例
    auth_manager = CursorAuthManager()
    # 调用实例方法更新认证信息并返回结果
    return auth_manager.update_auth(email, access_token, refresh_token)


def sign_up_account(browser, tab):
    """
    执行Cursor账号注册的完整流程
    
    包括填写个人信息、设置密码、处理验证码、获取账户信息等全部注册步骤
    
    Args:
        browser: 浏览器对象，用于管理浏览器实例
        tab: 浏览器标签页对象，用于页面交互操作
        
    Returns:
        bool: 注册是否成功，成功返回True，失败返回False
    """
    logging.info("=== 开始注册账号流程 ===")  # 记录注册开始的日志
    logging.info(f"正在访问注册页面: {sign_up_url}")  # 记录访问注册页面的日志
    tab.get(sign_up_url)  # 导航到注册页面

    try:
        # 检查是否已到达个人信息填写页面
        if tab.ele("@name=first_name"):
            logging.info("正在填写个人信息...")  # 记录开始填写个人信息的日志
            
            # 填写名字
            tab.actions.click("@name=first_name").input(first_name)  # 点击名字输入框并输入
            logging.info(f"已输入名字: {first_name}")  # 记录名字输入完成的日志
            time.sleep(random.uniform(1, 3))  # 随机等待1-3秒，模拟人工操作

            # 填写姓氏
            tab.actions.click("@name=last_name").input(last_name)  # 点击姓氏输入框并输入
            logging.info(f"已输入姓氏: {last_name}")  # 记录姓氏输入完成的日志
            time.sleep(random.uniform(1, 3))  # 随机等待1-3秒

            # 填写邮箱
            tab.actions.click("@name=email").input(account)  # 点击邮箱输入框并输入
            logging.info(f"已输入邮箱: {account}")  # 记录邮箱输入完成的日志
            time.sleep(random.uniform(1, 3))  # 随机等待1-3秒

            # 提交个人信息表单
            logging.info("提交个人信息...")  # 记录开始提交的日志
            tab.actions.click("@type=submit")  # 点击提交按钮

    except Exception as e:
        # 捕获填写个人信息过程中的异常
        logging.error(f"注册页面访问失败: {str(e)}")  # 记录错误日志
        return False  # 返回失败

    # 处理此阶段可能出现的Turnstile人机验证
    handle_turnstile(tab)

    try:
        # 检查是否已到达密码设置页面
        if tab.ele("@name=password"):
            logging.info("正在设置密码...")  # 记录开始设置密码的日志
            tab.ele("@name=password").input(password)  # 输入密码
            time.sleep(random.uniform(1, 3))  # 随机等待1-3秒

            # 提交密码
            logging.info("提交密码...")  # 记录提交密码的日志
            tab.ele("@type=submit").click()  # 点击提交按钮
            logging.info("密码设置完成，等待系统响应...")  # 记录密码设置完成的日志

    except Exception as e:
        # 捕获设置密码过程中的异常
        logging.error(f"密码设置失败: {str(e)}")  # 记录错误日志
        return False  # 返回失败

    # 检查邮箱是否已被使用
    if tab.ele("This email is not available."):
        logging.error("注册失败：邮箱已被使用")  # 记录邮箱已使用的错误日志
        return False  # 返回失败

    # 处理此阶段可能出现的Turnstile人机验证
    handle_turnstile(tab)

    # 循环处理可能出现的验证码页面或直接进入账户设置页面的情况
    while True:
        try:
            # 检查是否已到达账户设置页面，表示注册成功且无需验证码
            if tab.ele("Account Settings"):
                logging.info("注册成功 - 已进入账户设置页面")  # 记录注册成功的日志
                break  # 跳出循环
                
            # 检查是否需要输入验证码
            if tab.ele("@data-index=0"):
                logging.info("正在获取邮箱验证码...")  # 记录开始获取验证码的日志
                code = email_handler.get_verification_code()  # 调用邮箱处理器获取验证码
                if not code:
                    logging.error("获取验证码失败")  # 记录获取验证码失败的日志
                    return False  # 返回失败

                logging.info(f"成功获取验证码: {code}")  # 记录获取验证码成功的日志
                logging.info("正在输入验证码...")  # 记录开始输入验证码的日志
                
                # 逐个字符输入验证码
                i = 0
                for digit in code:
                    tab.ele(f"@data-index={i}").input(digit)  # 在相应输入框中输入每个字符
                    time.sleep(random.uniform(0.1, 0.3))  # 随机等待0.1-0.3秒，模拟人工输入
                    i += 1
                logging.info("验证码输入完成")  # 记录验证码输入完成的日志
                break  # 跳出循环
        except Exception as e:
            # 捕获验证码处理过程中的异常
            logging.error(f"验证码处理过程出错: {str(e)}")  # 记录错误日志

    # 处理此阶段可能出现的Turnstile人机验证
    handle_turnstile(tab)
    
    # 随机等待3-6秒，给系统处理时间
    wait_time = random.randint(3, 6)
    for i in range(wait_time):
        logging.info(f"等待系统处理中... 剩余 {wait_time-i} 秒")  # 记录等待进度
        time.sleep(1)  # 等待1秒

    # 获取账户信息
    logging.info("正在获取账户信息...")  # 记录开始获取账户信息的日志
    tab.get(settings_url)  # 导航到设置页面
    try:
        # 定义查找账户额度信息的CSS选择器
        usage_selector = (
            "css:div.col-span-2 > div > div > div > div > "
            "div:nth-child(1) > div.flex.items-center.justify-between.gap-2 > "
            "span.font-mono.text-sm\\/\\[0\\.875rem\\]"
        )
        # 尝试获取额度信息元素
        usage_ele = tab.ele(usage_selector)
        if usage_ele:
            # 提取额度信息文本
            usage_info = usage_ele.text
            total_usage = usage_info.split("/")[-1].strip()  # 提取总额度部分
            logging.info(f"账户可用额度上限: {total_usage}")  # 记录账户额度信息
            logging.info(
                "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
            )
    except Exception as e:
        # 捕获获取账户额度信息过程中的异常
        logging.error(f"获取账户额度信息失败: {str(e)}")  # 记录错误日志

    # 注册完成，显示账号信息
    logging.info("\n=== 注册完成 ===")  # 记录注册完成的日志
    account_info = f"Cursor 账号信息:\n邮箱: {account}\n密码: {password}"  # 生成账号信息文本
    logging.info(account_info)  # 记录账号信息
    time.sleep(5)  # 等待5秒
    return True  # 返回成功


class EmailGenerator:
    """
    邮箱账号生成器类
    
    用于生成随机的用户名和邮箱地址，用于Cursor账号注册过程
    包括随机姓名、邮箱地址和密码的生成功能
    """
    def __init__(
        self,
        password="".join(
            random.choices(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*",
                k=12,
            )
        ),  # 默认生成一个包含字母、数字和特殊字符的12位随机密码
    ):
        """
        初始化邮箱生成器
        
        Args:
            password: 可选的自定义密码，默认生成随机密码
        """
        configInstance = Config()  # 创建配置实例
        configInstance.print_config()  # 打印当前配置信息
        self.domain = configInstance.get_domain()  # 从配置获取邮箱域名
        self.names = self.load_names()  # 加载随机名称数据集
        self.default_password = password  # 保存设置的密码
        self.default_first_name = self.generate_random_name()  # 生成随机名
        self.default_last_name = self.generate_random_name()  # 生成随机姓

    def load_names(self):
        """
        从文件加载随机名称数据集
        
        从本地文件读取名称列表，用于生成随机的用户名
        
        Returns:
            list: 名称列表
        """
        with open("names-dataset.txt", "r") as file:  # 打开名称数据文件
            return file.read().split()  # 读取内容并按空格分割成列表

    def generate_random_name(self):
        """
        生成随机用户名
        
        从预加载的名称列表中随机选择一个名称
        
        Returns:
            str: 随机选择的名称
        """
        return random.choice(self.names)  # 从名称列表中随机选择一个

    def generate_email(self, length=4):
        """
        生成随机邮箱地址
        
        结合随机名称和时间戳生成唯一的邮箱地址
        
        Args:
            length: 时间戳末尾使用的位数，默认为4
            
        Returns:
            str: 生成的完整邮箱地址
        """
        length = random.randint(0, length)  # 生成0到length之间的随机整数
        timestamp = str(int(time.time()))[-length:]  # 使用当前时间戳的最后length位
        return f"{self.default_first_name}{timestamp}@{self.domain}"  # 组合成完整邮箱地址

    def get_account_info(self):
        """
        获取完整的账号信息
        
        生成并返回包含邮箱、密码、名和姓的完整账号信息字典
        
        Returns:
            dict: 包含email、password、first_name和last_name的账号信息字典
        """
        return {
            "email": self.generate_email(),  # 生成随机邮箱
            "password": self.default_password,  # 使用默认密码
            "first_name": self.default_first_name,  # 使用默认名
            "last_name": self.default_last_name,  # 使用默认姓
        }


def get_user_agent():
    """
    获取浏览器user_agent
    
    通过创建临时浏览器实例获取真实的user agent字符串，用于后续浏览器操作
    避免使用固定的user agent被检测为自动化工具
    
    Returns:
        str或None: 成功时返回浏览器的user agent字符串，失败返回None
    """
    try:
        # 创建临时浏览器实例并获取user agent
        browser_manager = BrowserManager()  # 创建浏览器管理器实例
        browser = browser_manager.init_browser()  # 初始化浏览器
        # 执行JavaScript获取user agent
        user_agent = browser.latest_tab.run_js("return navigator.userAgent")
        browser_manager.quit()  # 关闭临时浏览器
        return user_agent  # 返回获取到的user agent
    except Exception as e:
        # 捕获获取过程中的异常
        logging.error(f"获取user agent失败: {str(e)}")  # 记录错误日志
        return None  # 获取失败时返回None


def check_cursor_version():
    """
    检查当前安装的Cursor版本
    
    读取Cursor应用的package.json文件获取版本号，判断是否大于等于指定的最低版本
    不同版本的Cursor需要使用不同的重置方法
    
    Returns:
        bool: 当前版本是否大于等于0.45.0
    """
    # 获取Cursor应用的路径
    pkg_path, main_path = patch_cursor_get_machine_id.get_cursor_paths()
    # 读取package.json文件获取版本号
    with open(pkg_path, "r", encoding="utf-8") as f:
        version = json.load(f)["version"]  # 提取版本号字段
    # 检查版本是否高于0.45.0
    return patch_cursor_get_machine_id.version_check(version, min_version="0.45.0")


def reset_machine_id(greater_than_0_45):
    """
    根据Cursor版本重置机器ID
    
    针对不同版本的Cursor使用不同的重置方法：
    - 0.45.0及更高版本：使用go_cursor_help方法
    - 低于0.45.0版本：直接使用MachineIDResetter
    
    Args:
        greater_than_0_45: 是否为0.45.0或更高版本
    """
    if greater_than_0_45:
        # 0.45.0及更高版本需要使用go_cursor_help方法
        go_cursor_help.go_cursor_help()
    else:
        # 低于0.45.0版本直接使用MachineIDResetter
        MachineIDResetter().reset_machine_ids()


def print_end_message():
    """
    打印程序结束信息
    
    在所有操作完成后显示完成信息、项目链接和作者信息
    """
    logging.info("\n\n\n\n\n")  # 打印多个空行作为分隔
    logging.info("=" * 30)  # 打印分隔线
    logging.info("所有操作已完成")  # 打印完成信息
    logging.info("\n=== 获取更多信息 ===")  # 打印信息标题
    logging.info("📺 B站UP主: 想回家的前端")  # 打印作者B站信息
    logging.info("🔥 公众号: code 未来")  # 打印作者公众号信息
    logging.info("=" * 30)  # 打印分隔线
    logging.info(
        "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
    )  # 打印项目链接


if __name__ == "__main__":
    """
    主程序入口
    
    执行Cursor免费自动化流程，包括重置机器码和注册新账号两种模式
    """
    print_logo()  # 打印程序徽标
    greater_than_0_45 = check_cursor_version()  # 检查Cursor版本
    browser_manager = None  # 初始化浏览器管理器变量为None
    try:
        logging.info("\n=== 初始化程序 ===")  # 记录程序初始化的日志
        ExitCursor()  # 确保所有Cursor进程已关闭

        # 提示用户选择操作模式
        print("\n请选择操作模式:")
        print("1. 仅重置机器码")  # 选项1：只重置机器ID
        print("2. 完整注册流程")  # 选项2：完整注册新账号并重置机器ID

        # 循环获取用户输入，直到输入有效选项
        while True:
            try:
                choice = int(input("请输入选项 (1 或 2): ").strip())  # 读取并转换用户输入
                if choice in [1, 2]:  # 检查输入是否为有效选项
                    break  # 输入有效，跳出循环
                else:
                    print("无效的选项,请重新输入")  # 提示无效输入
            except ValueError:
                # 输入不是数字时提示错误
                print("请输入有效的数字")

        if choice == 1:
            # 选项1：仅执行重置机器码
            reset_machine_id(greater_than_0_45)  # 调用重置函数
            logging.info("机器码重置完成")  # 记录重置完成的日志
            print_end_message()  # 显示结束信息
            sys.exit(0)  # 正常退出程序

        # 以下是选项2的处理流程：完整注册
        logging.info("正在初始化浏览器...")  # 记录开始初始化浏览器的日志

        # 获取浏览器的user_agent
        user_agent = get_user_agent()  # 调用函数获取真实user agent
        if not user_agent:
            # 获取失败时使用默认值
            logging.error("获取user agent失败，使用默认值")  # 记录使用默认值的日志
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        # 修改user_agent，移除可能被检测的特征
        user_agent = user_agent.replace("HeadlessChrome", "Chrome")  # 删除无头浏览器标识

        # 创建浏览器实例
        browser_manager = BrowserManager()  # 创建浏览器管理器
        browser = browser_manager.init_browser(user_agent)  # 初始化带自定义user agent的浏览器

        # 获取并验证浏览器的user-agent
        user_agent = browser.latest_tab.run_js("return navigator.userAgent")  # 从浏览器获取实际使用的user agent

        # 显示项目信息
        logging.info(
            "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
        )
        
        # 设置注册流程需要的URL
        logging.info("\n=== 配置信息 ===")  # 记录开始配置信息的日志
        login_url = "https://authenticator.cursor.sh"  # Cursor登录页面URL
        sign_up_url = "https://authenticator.cursor.sh/sign-up"  # Cursor注册页面URL
        settings_url = "https://www.cursor.com/settings"  # Cursor设置页面URL
        mail_url = "https://tempmail.plus"  # 临时邮箱服务URL

        # 生成随机账号信息
        logging.info("正在生成随机账号信息...")  # 记录开始生成账号信息的日志
        
        # 创建邮箱生成器实例并获取账号信息
        email_generator = EmailGenerator()  # 创建邮箱生成器实例
        first_name = email_generator.default_first_name  # 获取随机生成的名
        last_name = email_generator.default_last_name  # 获取随机生成的姓
        account = email_generator.generate_email()  # 生成随机邮箱地址
        password = email_generator.default_password  # 获取生成的密码

        logging.info(f"生成的邮箱账号: {account}")  # 记录生成的邮箱账号

        # 初始化邮箱验证处理器
        logging.info("正在初始化邮箱验证模块...")  # 记录开始初始化邮箱验证模块的日志
        email_handler = EmailVerificationHandler(account)  # 创建邮箱验证处理器实例

        # 是否自动更新Cursor认证信息的标志
        auto_update_cursor_auth = True

        # 获取当前标签页
        tab = browser.latest_tab

        # 重置任何可能存在的turnstile状态
        tab.run_js("try { turnstile.reset() } catch(e) { }")  # 执行JavaScript重置turnstile

        # 开始注册流程
        logging.info("\n=== 开始注册流程 ===")  # 记录开始注册流程的日志
        logging.info(f"正在访问登录页面: {login_url}")  # 记录访问登录页面的日志
        tab.get(login_url)  # 导航到登录页面

        # 调用注册函数执行注册
        if sign_up_account(browser, tab):  # 如果注册成功
            logging.info("正在获取会话令牌...")  # 记录开始获取会话令牌的日志
            token = get_cursor_session_token(tab)  # 获取会话令牌
            if token:  # 如果成功获取令牌
                logging.info("更新认证信息...")  # 记录开始更新认证信息的日志
                # 使用获取的令牌和账号信息更新Cursor认证
                update_cursor_auth(
                    email=account, access_token=token, refresh_token=token
                )
                # 显示项目信息
                logging.info(
                    "请前往开源项目查看更多信息：https://github.com/chengazhen/cursor-auto-free"
                )
                logging.info("重置机器码...")  # 记录开始重置机器码的日志
                reset_machine_id(greater_than_0_45)  # 重置机器ID
                logging.info("所有操作已完成")  # 记录操作完成的日志
                print_end_message()  # 显示结束信息
            else:
                # 获取令牌失败
                logging.error("获取会话令牌失败，注册流程未完成")  # 记录获取令牌失败的错误日志

    except Exception as e:
        # 捕获程序执行过程中的所有异常
        logging.error(f"程序执行出现错误: {str(e)}")  # 记录错误信息
        import traceback  # 导入追踪模块用于详细错误信息
        logging.error(traceback.format_exc())  # 记录完整的错误追踪信息
    finally:
        # 无论成功还是失败，确保清理资源
        if browser_manager:  # 如果浏览器管理器已创建
            browser_manager.quit()  # 关闭浏览器
        input("\n程序执行完毕，按回车键退出...")  # 等待用户按回车键退出
