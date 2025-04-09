#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱验证码获取测试工具

这个脚本用于测试系统配置的邮箱验证码获取功能是否正常工作。
支持两种模式：
1. 临时邮箱方式：使用临时邮箱服务获取验证码
2. 邮箱服务器方式：使用POP3或IMAP协议从配置的邮箱服务器获取验证码

使用方法：
1. 确保.env文件中配置了正确的邮箱参数
2. 运行脚本: python test_email.py
3. 查看测试结果输出
"""

import os                                  # 用于访问环境变量
from dotenv import load_dotenv             # 用于从.env文件加载环境变量
from get_email_code import EmailVerificationHandler  # 导入邮箱验证码处理器
import logging                             # 用于日志记录

def test_temp_mail():
    """
    测试临时邮箱方式获取验证码
    
    使用临时邮箱服务(mailto.plus)检查系统是否能正确接收和解析验证码邮件
    临时邮箱的配置来自环境变量TEMP_MAIL
    
    Returns:
        无返回值，测试结果通过打印输出
    """
    # 创建验证处理器实例，临时邮箱模式
    handler = EmailVerificationHandler(os.getenv('TEMP_MAIL'))
    print("\n=== 测试临时邮箱模式 ===")
    print(f"临时邮箱: {os.getenv('TEMP_MAIL')}@mailto.plus")
    
    # 调用验证码获取函数，包含自动重试机制
    code = handler.get_verification_code()
    
    # 输出测试结果
    if code:
        print(f"成功获取验证码: {code}")
    else:
        print("未能获取验证码")

def test_email_server():
    """
    测试邮箱服务器方式获取验证码
    
    根据配置文件中设置的POP3或IMAP协议，从邮箱服务器获取验证码
    邮箱服务器配置来自环境变量：IMAP_SERVER, IMAP_PORT, IMAP_USER, IMAP_PASS
    
    Returns:
        无返回值，测试结果通过打印输出
    """
    # 创建验证处理器实例，传入账户参数
    handler = EmailVerificationHandler(os.getenv('IMAP_USER'))
    
    # 获取使用的邮件协议类型，默认为POP3
    protocol = os.getenv('IMAP_PROTOCOL', 'POP3')
    
    print(f"\n=== 测试 {protocol} 模式 ===")
    print(f"邮箱服务器: {os.getenv('IMAP_SERVER')}")
    print(f"邮箱账号: {os.getenv('IMAP_USER')}")
    
    # 调用验证码获取函数，内部会根据协议类型选择合适的方法
    code = handler.get_verification_code()
    
    # 输出测试结果
    if code:
        print(f"成功获取验证码: {code}")
    else:
        print("未能获取验证码")

def print_config():
    """
    打印当前环境变量配置
    
    显示系统中与邮件相关的环境变量配置，帮助用户检查配置是否正确
    根据临时邮箱或邮箱服务器模式，展示不同的配置项
    
    Returns:
        无返回值，配置信息通过打印输出
    """
    print("\n当前环境变量配置:")
    print(f"TEMP_MAIL: {os.getenv('TEMP_MAIL')}")
    
    # 如果TEMP_MAIL设置为null，表示使用邮箱服务器模式，显示相关配置
    if os.getenv('TEMP_MAIL') == 'null':
        print(f"IMAP_SERVER: {os.getenv('IMAP_SERVER')}")
        print(f"IMAP_PORT: {os.getenv('IMAP_PORT')}")
        print(f"IMAP_USER: {os.getenv('IMAP_USER')}")
        print(f"IMAP_PROTOCOL: {os.getenv('IMAP_PROTOCOL', 'POP3')}")
    
    print(f"DOMAIN: {os.getenv('DOMAIN')}")

def main():
    """
    主函数，程序入口点
    
    加载环境变量，显示当前配置，并根据配置执行相应的测试模式
    如果遇到异常，会捕获并显示错误信息
    """
    # 从.env文件加载环境变量
    load_dotenv()
    
    # 打印当前系统配置，便于调试
    print_config()
    
    try:
        # 根据TEMP_MAIL的值决定使用哪种测试模式
        if os.getenv('TEMP_MAIL') != 'null':
            # TEMP_MAIL不为null，使用临时邮箱模式
            test_temp_mail()
        else:
            # TEMP_MAIL为null，使用邮箱服务器模式
            test_email_server()
    except Exception as e:
        # 捕获并显示测试过程中的任何异常
        print(f"测试过程中发生错误: {str(e)}")

# 脚本入口点，确保在直接运行时才执行main()
if __name__ == "__main__":
    main() 