from datetime import datetime
import logging
import time
import re
from config import Config
import requests
import email
import imaplib
import poplib
from email.parser import Parser


class EmailVerificationHandler:
    def __init__(self,account):
        # 初始化IMAP配置
        self.imap = Config().get_imap()
        # 获取临时邮箱用户名
        self.username = Config().get_temp_mail()
        # 获取临时邮箱的epin验证码
        self.epin = Config().get_temp_mail_epin()
        # 创建会话对象，用于保持HTTP连接
        self.session = requests.Session()
        # 获取临时邮箱的域名后缀
        self.emailExtension = Config().get_temp_mail_ext()
        # 获取协议类型，默认为 POP3
        self.protocol = Config().get_protocol() or 'POP3'
        # 存储账户信息
        self.account = account

    def get_verification_code(self, max_retries=5, retry_interval=60):
        """
        获取验证码，带有重试机制。

        Args:
            max_retries: 最大重试次数。
            retry_interval: 重试间隔时间（秒）。

        Returns:
            验证码 (字符串或 None)。
        """

        for attempt in range(max_retries):
            try:
                logging.info(f"尝试获取验证码 (第 {attempt + 1}/{max_retries} 次)...")

                # 判断是否使用临时邮箱服务
                if not self.imap:
                    # 使用临时邮箱服务获取验证码
                    verify_code, first_id = self._get_latest_mail_code()
                    if verify_code is not None and first_id is not None:
                        # 清理已读取的邮件
                        self._cleanup_mail(first_id)
                        return verify_code
                else:
                    # 根据协议类型选择不同的邮件获取方法
                    if self.protocol.upper() == 'IMAP':
                        verify_code = self._get_mail_code_by_imap()
                    else:
                        verify_code = self._get_mail_code_by_pop3()
                    if verify_code is not None:
                        return verify_code

                # 如果未获取到验证码且未达到最大重试次数，则等待后重试
                if attempt < max_retries - 1:  # 除了最后一次尝试，都等待
                    logging.warning(f"未获取到验证码，{retry_interval} 秒后重试...")
                    time.sleep(retry_interval)

            except Exception as e:
                # 记录异常信息
                logging.error(f"获取验证码失败: {e}")  # 记录更一般的异常
                if attempt < max_retries - 1:
                    logging.error(f"发生错误，{retry_interval} 秒后重试...")
                    time.sleep(retry_interval)
                else:
                    # 达到最大重试次数，抛出异常
                    raise Exception(f"获取验证码失败且已达最大重试次数: {e}") from e

        # 所有重试都失败，抛出异常
        raise Exception(f"经过 {max_retries} 次尝试后仍未获取到验证码。")

    # 使用imap获取邮件
    def _get_mail_code_by_imap(self, retry = 0):
        # 如果是重试，等待3秒
        if retry > 0:
            time.sleep(3)
        # 设置最大重试次数为20
        if retry >= 20:
            raise Exception("获取验证码超时")
        try:
            # 连接到IMAP服务器
            mail = imaplib.IMAP4_SSL(self.imap['imap_server'], self.imap['imap_port'])
            # 登录邮箱
            mail.login(self.imap['imap_user'], self.imap['imap_pass'])
            # 默认不按日期搜索
            search_by_date=False
            # 针对网易系邮箱，imap登录后需要附带联系信息，且后续邮件搜索逻辑更改为获取当天的未读邮件
            if self.imap['imap_user'].endswith(('@163.com', '@126.com', '@yeah.net')):                
                # 构建ID信息
                imap_id = ("name", self.imap['imap_user'].split('@')[0], "contact", self.imap['imap_user'], "version", "1.0.0", "vendor", "imaplib")
                # 发送ID命令
                mail.xatom('ID', '("' + '" "'.join(imap_id) + '")')
                # 设置为按日期搜索
                search_by_date=True
            # 选择邮箱文件夹
            mail.select(self.imap['imap_dir'])
            # 根据搜索方式获取邮件
            if search_by_date:
                # 获取当天日期
                date = datetime.now().strftime("%d-%b-%Y")
                # 搜索当天未读邮件
                status, messages = mail.search(None, f'ON {date} UNSEEN')
            else:
                # 按收件人搜索邮件
                status, messages = mail.search(None, 'TO', '"'+self.account+'"')
            # 检查搜索状态
            if status != 'OK':
                return None

            # 获取邮件ID列表
            mail_ids = messages[0].split()
            if not mail_ids:
                # 没有获取到邮件，进行重试
                return self._get_mail_code_by_imap(retry=retry + 1)

            # 从最新的邮件开始处理
            for mail_id in reversed(mail_ids):
                # 获取邮件内容
                status, msg_data = mail.fetch(mail_id, '(RFC822)')
                if status != 'OK':
                    continue
                # 解析邮件内容
                raw_email = msg_data[0][1]
                email_message = email.message_from_bytes(raw_email)

                # 如果是按日期搜索的邮件，需要进一步核对收件人地址是否对应
                if search_by_date and email_message['to'] !=self.account:
                    continue
                # 提取邮件正文
                body = self._extract_imap_body(email_message)
                if body:
                    # 查找6位数字验证码
                    code_match = re.search(r"\b\d{6}\b", body)
                    if code_match:
                        # 提取验证码
                        code = code_match.group()
                        # 删除找到验证码的邮件
                        mail.store(mail_id, '+FLAGS', '\\Deleted')
                        # 执行删除操作
                        mail.expunge()
                        # 登出邮箱
                        mail.logout()
                        return code
            # 登出邮箱
            mail.logout()
            return None
        except Exception as e:
            print(f"发生错误: {e}")
            return None

    def _extract_imap_body(self, email_message):
        # 提取邮件正文
        if email_message.is_multipart():
            # 处理多部分邮件
            for part in email_message.walk():
                # 获取内容类型
                content_type = part.get_content_type()
                # 获取内容处理方式
                content_disposition = str(part.get("Content-Disposition"))
                # 只处理纯文本且非附件的部分
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    # 获取字符集，默认为utf-8
                    charset = part.get_content_charset() or 'utf-8'
                    try:
                        # 解码邮件内容
                        body = part.get_payload(decode=True).decode(charset, errors='ignore')
                        return body
                    except Exception as e:
                        logging.error(f"解码邮件正文失败: {e}")
        else:
            # 处理单部分邮件
            content_type = email_message.get_content_type()
            if content_type == "text/plain":
                # 获取字符集，默认为utf-8
                charset = email_message.get_content_charset() or 'utf-8'
                try:
                    # 解码邮件内容
                    body = email_message.get_payload(decode=True).decode(charset, errors='ignore')
                    return body
                except Exception as e:
                    logging.error(f"解码邮件正文失败: {e}")
        return ""

    # 使用 POP3 获取邮件
    def _get_mail_code_by_pop3(self, retry = 0):
        # 如果是重试，等待3秒
        if retry > 0:
            time.sleep(3)
        # 设置最大重试次数为20
        if retry >= 20:
            raise Exception("获取验证码超时")
        
        pop3 = None
        try:
            # 连接到POP3服务器
            pop3 = poplib.POP3_SSL(self.imap['imap_server'], int(self.imap['imap_port']))
            # 登录邮箱
            pop3.user(self.imap['imap_user'])
            pop3.pass_(self.imap['imap_pass'])
            
            # 获取最新的10封邮件
            num_messages = len(pop3.list()[1])
            for i in range(num_messages, max(1, num_messages-9), -1):
                # 获取邮件内容
                response, lines, octets = pop3.retr(i)
                # 解析邮件内容
                msg_content = b'\r\n'.join(lines).decode('utf-8')
                msg = Parser().parsestr(msg_content)
                
                # 检查发件人是否为Cursor
                if 'no-reply@cursor.sh' in msg.get('From', ''):
                    # 提取邮件正文
                    body = self._extract_pop3_body(msg)
                    if body:
                        # 查找验证码
                        code_match = re.search(r"\b\d{6}\b", body)
                        if code_match:
                            # 提取验证码
                            code = code_match.group()
                            # 关闭连接
                            pop3.quit()
                            return code
            
            # 关闭连接
            pop3.quit()
            # 未找到验证码，进行重试
            return self._get_mail_code_by_pop3(retry=retry + 1)
            
        except Exception as e:
            print(f"发生错误: {e}")
            # 确保连接被关闭
            if pop3:
                try:
                    pop3.quit()
                except:
                    pass
            return None

    def _extract_pop3_body(self, email_message):
        # 提取邮件正文
        if email_message.is_multipart():
            # 处理多部分邮件
            for part in email_message.walk():
                # 获取内容类型
                content_type = part.get_content_type()
                # 获取内容处理方式
                content_disposition = str(part.get("Content-Disposition"))
                # 只处理纯文本且非附件的部分
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        # 解码邮件内容
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        return body
                    except Exception as e:
                        logging.error(f"解码邮件正文失败: {e}")
        else:
            # 处理单部分邮件
            try:
                # 解码邮件内容
                body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                return body
            except Exception as e:
                logging.error(f"解码邮件正文失败: {e}")
        return ""

    # 从临时邮箱服务获取验证码
    def _get_latest_mail_code(self):
        # 构建获取邮件列表的URL
        mail_list_url = f"https://tempmail.plus/api/mails?email={self.username}{self.emailExtension}&limit=20&epin={self.epin}"
        # 发送请求获取邮件列表
        mail_list_response = self.session.get(mail_list_url)
        # 解析响应JSON数据
        mail_list_data = mail_list_response.json()
        # 等待0.5秒，避免请求过于频繁
        time.sleep(0.5)
        # 检查是否成功获取邮件列表
        if not mail_list_data.get("result"):
            return None, None

        # 获取最新邮件的ID
        first_id = mail_list_data.get("first_id")
        # 检查是否有邮件
        if not first_id:
            return None, None

        # 构建获取邮件详情的URL
        mail_detail_url = f"https://tempmail.plus/api/mails/{first_id}?email={self.username}{self.emailExtension}&epin={self.epin}"
        # 发送请求获取邮件详情
        mail_detail_response = self.session.get(mail_detail_url)
        # 解析响应JSON数据
        mail_detail_data = mail_detail_response.json()
        # 等待0.5秒，避免请求过于频繁
        time.sleep(0.5)
        # 检查是否成功获取邮件详情
        if not mail_detail_data.get("result"):
            return None, None

        # 从邮件文本中提取邮件内容和主题
        mail_text = mail_detail_data.get("text", "")
        mail_subject = mail_detail_data.get("subject", "")
        # 记录邮件主题
        logging.info(f"找到邮件主题: {mail_subject}")
        # 修改正则表达式，确保 6 位数字不紧跟在字母或域名相关符号后面
        code_match = re.search(r"(?<![a-zA-Z@.])\b\d{6}\b", mail_text)

        # 返回验证码和邮件ID
        if code_match:
            return code_match.group(), first_id
        return None, None

    def _cleanup_mail(self, first_id):
        # 构造删除请求的URL和数据
        delete_url = "https://tempmail.plus/api/mails/"
        # 准备请求参数
        payload = {
            "email": f"{self.username}{self.emailExtension}",
            "first_id": first_id,
            "epin": f"{self.epin}",
        }

        # 最多尝试5次删除操作
        for _ in range(5):
            # 发送删除请求
            response = self.session.delete(delete_url, data=payload)
            try:
                # 检查删除结果
                result = response.json().get("result")
                if result is True:
                    return True
            except:
                pass

            # 如果失败,等待0.5秒后重试
            time.sleep(0.5)

        return False


# 测试代码
if __name__ == "__main__":
    # 创建邮件验证处理器实例
    email_handler = EmailVerificationHandler()
    # 获取验证码
    code = email_handler.get_verification_code()
    # 打印验证码
    print(code)
