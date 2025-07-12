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
PHASE1_RETRIES = 5  # 第一阶段最大重试次数
PHASE1_INTERVAL = 120  # 第一阶段重试间隔(秒)
PHASE2_RETRIES = 30  # 第二阶段最大重试次数
PHASE2_INTERVAL = 10  # 第二阶段重试间隔(秒)
EMAIL_MAX_RETRIES = 5  # 邮件发送最大重试次数
EMAIL_RETRY_DELAY = 3  # 邮件发送重试间隔(秒)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()

def get_lottery_result(phase):
    """获取开奖结果（带重试机制）"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    current_time = datetime.now(beijing_tz)
    
    # 根据阶段设置参数
    if phase == 1:
        max_retries = PHASE1_RETRIES
        retry_interval = PHASE1_INTERVAL
    else:
        max_retries = PHASE2_RETRIES
        retry_interval = PHASE2_INTERVAL
    
    logger.info(f"开始第{phase}阶段获取开奖结果...")
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"尝试 #{attempt}/{max_retries}: 请求开奖数据...")
            response = requests.get(API_URL, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"API响应: {data}")
            
            # 验证数据格式
            if data and isinstance(data, list) and data[0].get('openCode'):
                result = data[0]
                # 验证开奖时间是否为今日
                open_time = datetime.strptime(result['openTime'], '%Y-%m-%d %H:%M:%S')
                open_time = beijing_tz.localize(open_time)
                
                logger.info(f"开奖时间: {open_time} | 当前时间: {current_time}")
                
                # 第一阶段：只要获取到数据就返回（无论是否当日）
                if phase == 1:
                    logger.info("✅ 第一阶段获取到开奖结果")
                    return result
                
                # 第二阶段：只返回当日开奖结果
                if phase == 2 and open_time.date() == current_time.date():
                    logger.info("✅ 第二阶段获取到今日开奖结果")
                    return result
                else:
                    logger.warning(f"⚠️ 开奖时间非今日: {open_time.date()} vs {current_time.date()}")
            else:
                logger.warning("⚠️ API返回数据格式无效")
        except Exception as e:
            logger.error(f"❌ 请求异常: {str(e)}")
        
        # 未获取到有效结果时等待重试
        if attempt < max_retries:
            logger.info(f"🕒 {retry_interval}秒后重试...")
            time.sleep(retry_interval)
    
    logger.error(f"❌ 超过最大重试次数({max_retries})，未获取到有效结果")
    return None

def format_dingtalk_message(result):
    """格式化钉钉通知消息（严格遵循要求样式）"""
    # 获取当前北京时间作为通知时间
    beijing_tz = pytz.timezone('Asia/Shanghai')
    notification_time = datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
    
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
    
    # 创建带波色文字的号码（确保波色显示为中文）
    chinese_waves = []
    for wave in waves:
        wave_lower = wave.strip().lower()
        chinese_waves.append(wave_mapping.get(wave_lower, wave_lower))
    
    # 计算对齐所需的最大宽度
    max_num_width = max(len(num) for num in numbers)
    max_wave_width = max(len(wave) for wave in chinese_waves)
    max_zodiac_width = max(len(z) for z in zodiacs)
    
    # 对齐文本
    aligned_numbers = [num.ljust(max_num_width + 2) for num in numbers]
    aligned_waves = [wave.ljust(max_wave_width + 2) for wave in chinese_waves]
    aligned_zodiacs = [z.ljust(max_zodiac_width + 2) for z in zodiacs]
    
    # 构建消息 - 严格遵循要求样式
    message = "".join(aligned_numbers) + "\n"
    message += "".join(aligned_waves) + "\n"
    message += "".join(aligned_zodiacs) + "\n\n"
    message += f"開獎時間：{result['openTime']}期號：{result['expect']}期\n"
    message += f"通知時間：{notification_time}"
    
    return message

def format_email_content(result):
    """格式化邮件通知内容（严格遵循要求样式）"""
    # 获取当前北京时间作为通知时间
    beijing_tz = pytz.timezone('Asia/Shanghai')
    notification_time = datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M:%S')
    
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
    
    # 构建邮件内容（HTML格式） - 严格遵循要求样式
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

def send_dingtalk_message(result):
    """发送钉钉通知（严格遵循要求样式）"""
    logger.info("准备发送钉钉通知...")
    
    webhook = os.environ['DINGTALK_WEBHOOK']
    secret = os.environ['DINGTALK_SECRET']
    
    # 构建消息内容
    message = format_dingtalk_message(result)
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
        return True
    except Exception as e:
        logger.error(f"❌ 钉钉消息发送失败: {str(e)}")
        return False

def send_email(result):
    """发送邮件通知（严格遵循要求样式）"""
    logger.info("准备发送邮件通知...")
    
    # QQ邮箱配置
    smtp_host = "smtp.qq.com"
    port = 465  # SSL端口
    sender = os.environ['EMAIL_USER']
    password = os.environ['EMAIL_PASSWORD']
    receiver = os.environ['EMAIL_TO']
    
    # 邮件主题设置为开奖号码
    email_subject = result['openCode']
    
    # 创建邮件
    msg = MIMEText(format_email_content(result), "html")
    msg["Subject"] = email_subject
    msg["From"] = sender
    msg["To"] = receiver
    
    # 带重试机制的发送
    success = False
    error_log = ""
    
    for attempt in range(1, EMAIL_MAX_RETRIES + 1):
        try:
            logger.info(f"尝试发送邮件 (#{attempt}/{EMAIL_MAX_RETRIES})...")
            
            # 创建安全SSL上下文
            context = ssl.create_default_context()
            
            # 使用SMTP_SSL直接建立SSL连接
            with smtplib.SMTP_SSL(smtp_host, port, context=context, timeout=20) as server:
                # 登录邮箱
                server.login(sender, password)
                
                # 发送邮件
                server.sendmail(sender, [receiver], msg.as_string())
            
            logger.info("✅ 邮件发送成功！")
            success = True
            break
        except Exception as e:
            error_msg = f"❌ 邮件发送失败 (#{attempt}/{EMAIL_MAX_RETRIES}): {str(e)}"
            logger.error(error_msg)
            error_log += error_msg + "\n"
            if attempt < EMAIL_MAX_RETRIES:
                logger.info(f"🕒 {EMAIL_RETRY_DELAY}秒后重试...")
                time.sleep(EMAIL_RETRY_DELAY)
    
    # 记录失败日志
    if not success:
        logger.error(f"❌ 超过最大重试次数({EMAIL_MAX_RETRIES})，邮件发送失败")
        logger.error("详细错误日志:")
        logger.error(error_log)
    
    return success

def main():
    """主控制流程"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    current_time = datetime.now(beijing_tz)
    logger.info(f"====== {current_time.strftime('%Y-%m-%d %H:%M:%S')} 开奖监控启动 ======")
    
    # 第一阶段：提前20分钟启动（21:10）
    logger.info("===== 第一阶段监控开始 =====")
    phase1_result = get_lottery_result(phase=1)
    
    # 关键修复：第一阶段获取到任何结果都发送通知
    if phase1_result:
        logger.info("✅ 第一阶段获取到开奖结果，立即发送通知")
        send_dingtalk_message(phase1_result)
        send_email(phase1_result)
        logger.info("====== 通知发送完成! ======")
        return
    
    # 等待进入第二阶段（21:31:31 - 21:34:59）
    phase2_start = current_time.replace(hour=21, minute=31, second=31, microsecond=0)
    
    # 如果还没到第二阶段开始时间，等待
    if current_time < phase2_start:
        wait_seconds = (phase2_start - current_time).total_seconds()
        logger.info(f"🕒 等待 {wait_seconds:.0f} 秒进入第二阶段...")
        time.sleep(wait_seconds)
    
    # 第二阶段：密集监控（21:31:31 - 21:34:59）
    logger.info("===== 第二阶段监控开始 =====")
    phase2_result = get_lottery_result(phase=2)
    
    if phase2_result:
        logger.info("✅ 第二阶段获取到开奖结果")
        send_dingtalk_message(phase2_result)
        send_email(phase2_result)
        logger.info("====== 通知发送完成! ======")
    else:
        logger.error("❌ 错误：未获取到有效开奖结果，终止执行")
        exit(1)

if __name__ == "__main__":
    main()
