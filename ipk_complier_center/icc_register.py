"""
    ICopy Compiler Center(ICC)
    编译器集群注册器
    提供一个注册与查询的服务接口
"""
import logging
import threading
import time

from urllib import request as http_request

from flask import Flask, request

ADDR = "127.0.0.1"
PORT = 6868
FLASK_APP = Flask(__name__)

logging.basicConfig(level=logging.NOTSET, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

ONLINE_LIST = set()
DATA_LOCK = threading.Lock()


def add_dev(addr):
    """
        添加在线设备
    :param addr:
    :return:
    """
    try:
        with DATA_LOCK:
            ONLINE_LIST.add(addr)
    except Exception:
        pass


def rm_dev(addr):
    """
        移除在线设备
    :param addr:
    :return:
    """
    try:
        with DATA_LOCK:
            ONLINE_LIST.remove(addr)
    except Exception:
        pass


def is_online(addr):
    """
        测试是否在线
    :return:
    """
    try:
        url = f"http://{addr}:5858/online"
        LOGGER.info(f"尝试检查该链接: {url}")
        with http_request.urlopen(url, timeout=8) as result:
            return result.read() == b'yes'
    except Exception as e:
        LOGGER.info(f"检查下线失败: {e}")
        return False


@FLASK_APP.route("/online")
def online():
    """
        上线一个设备
    :return:
    """
    user_addr = request.remote_addr
    # 我们需要进行反向测试客户端是否提供了编译器服务
    if is_online(user_addr):
        add_dev(user_addr)
        return "yes"
    else:
        try:
            rm_dev(user_addr)
        except Exception:
            pass
    LOGGER.info(f"主机名: {user_addr}")
    return "no"


@FLASK_APP.route("/offline")
def offline():
    """
        下线一个设备
    :return:
    """
    user_addr = request.remote_addr
    try:
        rm_dev(user_addr)
    except Exception:
        pass
    return "yes"


@FLASK_APP.route("/getlist")
def getlist():
    """
        获取当前在线的设备列表
    :return:
    """
    return ','.join(ONLINE_LIST)


def run_check():
    """
        检查客户端是否存活
    :return:
    """
    while True:
        if len(ONLINE_LIST) > 0:
            print("等待自检......")
            time.sleep(5)
            print("正在检测设备是否存活：")
            for ip_addr in ONLINE_LIST.copy():
                print("IP：", ip_addr)
                try:
                    if is_online(ip_addr):
                        continue
                    else:
                        rm_dev(ip_addr)
                except Exception:
                    pass
        else:
            time.sleep(0.1)


if __name__ == '__main__':
    threading.Thread(target=run_check).start()
    FLASK_APP.run(ADDR, PORT, debug=False)
