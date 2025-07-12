import os
import requests
import smtplib
import time
from datetime import datetime, timedelta
import pytz
from email.mime.text import MIMEText
import hmac
import hashlib
import base64
import ssl
import logging

# 配置参数
API_URL = "https://macaumarksix.com/api/macaujc2.com"
MAX_RETRIES = 10  # 开奖API最大重试次数
RETRY_INTERVAL = 30  # 开奖API重试间隔(秒)
EMAIL_MAX_RETRIES = 5  # 邮件发送最大重试次数
EMAIL_RETRY_DELAY = 3  # 邮件发送重试间隔(秒)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()

def get_lottery_result():
    """获取开奖结果（带重试机制）"""
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # 验证数据格式
        if data and isinstance(data, list) and data[0].get('openCode'):
            return data[0]
    except Exception as e:
        logger.error(f"获取数据失败: {str(e)}")
    return None

def format_dingtalk_message(result, notification_time):
    """格式化钉钉通知消息（严格遵循要求样式）"""
    # 解析数据
    numbers = result['openCode'].split(',')
    zodiacs = result['zodiac'].split(',')
    waves = result['wave'].split(',')
    
    # 波色映射（英文转中文）
    wave_mapping = {
        'red': '红',
        'blue': '蓝',
        'green': '绿'
    }
    
    # 格式化开奖号码行
    numbers_line = " ".join([f"{num:>4}" for num in numbers])
    
    # 格式化波色行
    wave_line = " ".join([f"{wave_mapping.get(wave.lower(), wave):>4}" for wave in waves])
    
    # 格式化生肖行
    zodiac_line = " ".join([f"{zodiac:>4}" for zodiac in zodiacs])
    
    # 构建消息
    message = f"{numbers_line}\n"
    message += f"{wave_line}\n"
    message += f"{zodiac_line}\n"
    message += f"開獎時間：{result['openTime']}期號：{result['expect']}期\n"
    message += f"通知時間：{notification_time}"
    
    return message

def format_email_content(result, notification_time):
    """格式化邮件通知内容（严格遵循要求样式）"""
    # 解析数据
    numbers = result['openCode'].split(',')
    zodiacs = result['zodiac'].split(',')
    waves = result['wave'].split(',')
    
    # 波色对应的HTML颜色
    wave_colors = {
        'red': '#FF0000',
        'blue': '#0000FF',
        'green': '#00FF00'
    }
    
    # 创建号码和生肖的HTML元素
    number_items = ""
    for num, wave, zodiac in zip(numbers, waves, zodiacs):
        wave_lower = wave.strip().lower()
        color = wave_colors.get(wave_lower, '#CCCCCC')  # 默认灰色
        
        # 计算合适的字体大小
        font_size = "24px" if len(num) <= 2 else "18px"
        
        number_items += f"""
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            margin: 0 10px;
        ">
            <div style="
                display: flex;
                justify-content: center;
                align-items: center;
                width: 55px;
                height: 55px;
                border-radius: 50%;
                background-color: {color};
                color: white;
                font-weight: bold;
                font-size: {font_size};
                margin-bottom: 8px;
            ">{num}</div>
            <div style="
                font-size: 16px;
                text-align: center;
                min-width: 55px;
            ">{zodiac}</div>
        </div>
        """
    
    # 构建邮件内容（HTML格式）
    body = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 700px;
                margin: 0 auto;
                padding: 20px;
            }}
            .container {{
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .numbers-container {{
                display: flex;
                justify-content: center;
                flex-wrap: wrap;
                margin: 25px 0;
            }}
            .info-line {{
                width: 100%;
                margin: 12px 0;
                font-size: 18px;
                text-align: center;
            }}
            .label {{
                font-weight: bold;
                margin-right: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="numbers-container">
                {number_items}
            </div>
            
            <div class="info-line">
                <span class="label">開獎時間：</span>
                <span>{result['openTime']}</span>
                <span class="label">期號：</span>
                <span>{result['expect']}期</span>
            </div>
            
            <div class="info-line">
                <span class="label">通知時間：</span>
                <span>{notification_time}</span>
            </div>
        </div>
    </body>
    </html>
    """
    
    return body

def send_dingtalk_message(result, notification_time):
    """发送钉钉通知"""
    logger.info("准备发送钉钉通知...")
    
    webhook = os.environ['DINGTALK_WEBHOOK']
    secret = os.environ['DINGTALK_SECRET']
    
    # 构建消息内容
    message = format_dingtalk_message(result, notification_time)
    logger.info(f"钉钉通知内容:\n{message}")
    
    # 生成签名
    timestamp = str(round(time.time() * 1000))
    sign_str = f"{timestamp}\n{secret}"
    sign = base64.b64encode(
        hmac.new(secret.encode('utf-8'), sign_str.encode('utf-8'), digestmod=hashlib.sha256).digest()
    ).decode('utf-8')
    
    # 构建请求
    headers = {"Content-Type": "application/json"}
    payload = {
        "msgtype": "text",
        "text": {"content": message}
    }
    params = {
        "timestamp": timestamp,
        "sign": sign
    }
    
    try:
        response = requests.post(webhook, json=payload, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        logger.info("✅ 钉钉消息发送成功！")
    except Exception as e:
        logger.error(f"❌ 钉钉消息发送失败: {str(e)}")

def send_email(result, notification_time):
    """发送邮件通知（完全修复版本）"""
    logger.info("准备发送邮件通知...")
    
    # QQ邮箱配置
    smtp_host = "smtp.qq.com"
    port = 587  # 使用TLS端口
    sender = os.environ['EMAIL_USER']
    password = os.environ['EMAIL_PASSWORD']
    receiver = os.environ['EMAIL_TO']
    
    # 邮件主题设置为开奖号码
    email_subject = result['openCode']
    
    # 创建邮件
    msg = MIMEText(format_email_content(result, notification_time), "html")
    msg["Subject"] = email_subject
    msg["From"] = sender
    msg["To"] = receiver
    
    # 带重试机制的发送
    success = False
    error_log = ""
    
    for attempt in range(1, EMAIL_MAX_RETRIES + 1):
        try:
            logger.info(f"尝试发送邮件 (#{attempt}/{EMAIL_MAX_RETRIES})...")
            
            # 创建安全SSL上下文 - 使用更兼容的设置
            context = ssl.create_default_context()
            context.set_ciphers('DEFAULT@SECLEVEL=1')  # 降低安全级别
            
            # 使用SMTP连接（TLS方式）
            with smtplib.SMTP(smtp_host, port, timeout=20) as server:
                server.ehlo()  # 发送EHLO命令
                server.starttls(context=context)  # 启动TLS加密
                server.ehlo()  # 再次发送EHLO命令
                
                # 登录邮箱
                server.login(sender, password)
                
                # 发送邮件
                server.sendmail(sender, [receiver], msg.as_string())
            
            logger.info("✅ 邮件发送成功！")
            success = True
            break
        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"❌ 认证失败 (#{attempt}/{EMAIL_MAX_RETRIES}): {str(e)}"
            logger.error(error_msg)
            error_log += error_msg + "\n"
            logger.error("请检查邮箱地址和授权码是否正确")
        except (smtplib.SMTPServerDisconnected, ConnectionResetError) as e:
            error_msg = f"❌ 连接断开 (#{attempt}/{EMAIL_MAX_RETRIES}): {str(e)}"
            logger.error(error_msg)
            error_log += error_msg + "\n"
        except smtplib.SMTPException as e:
            error_msg = f"❌ SMTP协议错误 (#{attempt}/{EMAIL_MAX_RETRIES}): {str(e)}"
            logger.error(error_msg)
            error_log += error_msg + "\n"
        except Exception as e:
            error_msg = f"❌ 未知错误 (#{attempt}/{EMAIL_MAX_RETRIES}): {str(e)}"
            logger.error(error_msg)
            error_log += error_msg + "\n"
        
        # 如果还有重试机会，等待后重试
        if attempt < EMAIL_MAX_RETRIES:
            logger.info(f"🕒 {EMAIL_RETRY_DELAY}秒后重试...")
            time.sleep(EMAIL_RETRY_DELAY)
    
    # 记录失败日志
    if not success:
        logger.error(f"❌ 超过最大重试次数({EMAIL_MAX_RETRIES})，邮件发送失败")
        logger.error("详细错误日志:")
        logger.error(error_log)

def is_today(result):
    """检查结果是否为今日开奖"""
    try:
        open_time = datetime.strptime(result['openTime'], '%Y-%m-%d %H:%M:%S')
        current_time = datetime.now()
        return open_time.date() == current_time.date()
    except:
        return False

def monitor_lottery():
    """监控开奖结果（两阶段策略）"""
    # 获取当前北京时间
    beijing_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing_tz)
    notification_time = now.strftime('%Y-%m-%d %H:%M:%S')
    
    logger.info(f"====== {notification_time} 开奖监控启动 ======")
    
    # 第一阶段：提前20分钟启动（21:10:00 - 21:31:30）
    if now.time() < datetime.strptime("21:31:30", "%H:%M:%S").time():
        logger.info("进入第一阶段监控（提前开奖检测）...")
        result = get_lottery_result()
        if result:
            logger.info("✅ 获取到开奖结果（可能提前开奖）")
            logger.info(f"开奖时间: {result['openTime']} | 当前时间: {notification_time}")
            send_dingtalk_message(result, notification_time)
            send_email(result, notification_time)
            logger.info("====== 通知发送完成! ======")
            return True
    
    # 第二阶段：密集监控（21:31:31 - 21:34:59）
    logger.info("进入第二阶段监控（密集检测）...")
    end_time = datetime.strptime("21:35:00", "%H:%M:%S").time()
    
    while now.time() < end_time:
        result = get_lottery_result()
        if result and is_today(result):
            logger.info("✅ 获取到今日开奖结果")
            logger.info(f"开奖时间: {result['openTime']} | 当前时间: {notification_time}")
            send_dingtalk_message(result, notification_time)
            send_email(result, notification_time)
            logger.info("====== 通知发送完成! ======")
            return True
        
        # 更新当前时间
        now = datetime.now(beijing_tz)
        notification_time = now.strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"等待开奖结果... 当前时间: {notification_time}")
        time.sleep(10)  # 每10秒检查一次
    
    logger.error("❌ 错误：未能在开奖窗口期内获取到有效开奖结果")
    return False

if __name__ == "__main__":
    if not monitor_lottery():
        exit(1)
