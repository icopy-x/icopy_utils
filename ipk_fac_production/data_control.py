"""
    此脚本文件用于提供公共的数据库接入实现，
    所有的生产过程，都应该使数据录入到同一个数据库
    1、需要根据SN查询所有的信息
    2、需要根据三个信息来查询SN，就是H3、PM3、STM32的ID
    3、需要实现SN的拼接
"""
import configparser
import json
import logging
import os.path
import sys
import threading
import time
import tkinter
from tkinter import messagebox

import generator_utils

URL_ADMIN_BASE = "http://127.0.0.1:8080/"
URL_ADMIN_LOGIN = URL_ADMIN_BASE + "openapi/login"
URL_ADMIN_GET_DEVICE_INFO_BY_ID = URL_ADMIN_BASE + "api/icopy/qc/get/device/by/id"
URL_ADMIN_GET_DEVICE_INFO_BY_SN = URL_ADMIN_BASE + "api/icopy/qc/get/device/by/sn"
URL_ADMIN_UPDATE_DEVICE_STATUS = URL_ADMIN_BASE + "api/icopy/qc/update/device/status"
URL_ADMIN_UPDATE_DEVICE_TYPE = URL_ADMIN_BASE + "api/icopy/qc/update/device/type"
URL_ADMIN_ADD_DEVICE_INFO = URL_ADMIN_BASE + "api/icopy/qc/save/device/info"

# 日志打印
LOGGER = logging.getLogger(__name__)
# 在登录时加锁，永远只有一个线程在请求登录
LOCK_LOGIN = threading.RLock()


def show_error_msg_and_exit(msg):
    """
        显示错误消息和退出程序
    :param msg:
    :return:
    """
    messagebox.showerror("出现错误",
                         "发生无法解决的错误，请联系开发者解决：" + msg + "（确认后将自动退出，请解决问题后继续操作）")
    sys.exit(0)


def get_icopy_admin_account():
    """
        获得配置文件中存放的icopy质检账户配置
    :return:
    """
    # 定义账户密码，这个信息只在第一次启动时使用
    account = "icopyqc"
    password = "password"

    # 过滤密码中的特殊字符
    if '%' in password:
        password = password.replace("%", "%%")

    # 定义配置
    cf = configparser.ConfigParser()
    ini_file_name = "生产系统账户密码.ini"
    if not os.path.exists(ini_file_name):
        cf["DEFAULT"] = {"账户": account, "密码": password}
        with open(ini_file_name, mode="w+") as f:
            cf.write(f)
    else:
        cf.read(ini_file_name, "gbk")
    return {'user': cf["DEFAULT"]['账户'], 'password': cf["DEFAULT"]['密码']}


class DataRequest:
    """
        数据请求的封装类
    """

    def __init__(self):
        # 登录会话的uuid
        self.login_session = None

    def auto_login_and_lock(self):
        """
            自动加锁进行登录
        :return:
        """
        # 进行加锁登录，避免多线程调用此接口导致重复登录刷新token
        with LOCK_LOGIN:
            # 判断到没登录的话，就先登录
            if self.login_session is None:
                LOGGER.info("需要重新登录")
                login_retry_max = 100  # 登录的重试上限次数
                # 请求登录接口，然后得到登录结果
                for retry_login_count in range(login_retry_max):
                    try:
                        # 调用接口尝试登录
                        ret_str = generator_utils.get_server_resp(
                            URL_ADMIN_LOGIN, method="POST", params=get_icopy_admin_account())
                        # 登录完成，我们不需要再次重试登录，直接操作成功退出此逻辑
                        break
                    except Exception as e:
                        LOGGER.warning(f"登录时出现异常，可能是某些网络波动或者其他异常情况：{str(e)}")
                        # 最后一次干活了，还是登录没完成，肯定是有问题的，那我们直接抛出异常告知开发者
                        if retry_login_count == login_retry_max - 1:
                            show_error_msg_and_exit("致命错误导致无法登录，已经超过重试上限")
                            return None
                # 接口请求完成，我们可以根据应答进行登录结果判断了
                ret_json = json.loads(ret_str)
                if ret_json['code'] == 1000:
                    self.login_session = ret_json['result']
                    LOGGER.info(f"登录成功，会话已经保存到内存中: {ret_json}")
                else:
                    show_error_msg_and_exit(f"{ret_json['msg']}")
        return

    def request_json_api_auto_login(self, url, data, method="GET"):
        """
            请求API，并且根据需要自动登录，在请求成功后，将返回的数据转换为json对象返回
        :return:
        """
        # 请求的重试次数
        retry_count_max = 100
        # 循环请求，自动重试，避免网络波动导致的间接性登录失败
        for retry_request_count in range(retry_count_max):
            try:
                # 检查和尝试登录
                self.auto_login_and_lock()
                # 登录了的话，我们就可以去请求后续的资源了
                data['token'] = self.login_session
                ret_str = generator_utils.get_server_resp(url, method=method, params=data)
                ret_json = json.loads(ret_str)
                LOGGER.info(ret_json)
                # 检查返回值，确认操作成功
                if ret_json['code'] == 1000:
                    return ret_json
                # 登录信息失效，我们尝试重新登录
                if ret_json['code'] == 1004:
                    # 加锁后重置登录会话的缓存
                    with LOCK_LOGIN: self.login_session = None
                    continue
                # 其他的异常错误，我们直接报错抛给上层UI提醒用户找人处理
                show_error_msg_and_exit(ret_json['msg'])
            except Exception as e:
                LOGGER.warning(f"请求时异常，可能是某些网络波动导致的请求失败: {str(e)}")
                # 如果重试次数已经没了的话，那我们直接抛出异常不再重试了
                if retry_request_count == retry_count_max - 1:
                    show_error_msg_and_exit(f"请求出现异常（{str(e)}）")
        # 为了好看，对齐一下
        return None


# 创建一个数据请求的实例，单例即可。
DR = DataRequest()


def data_pre_processor(json_obj):
    """
        把后端返回的查询到的数据库信息转为我们关系的键值对信息
    :return:
    """
    # 如果查不到信息，就别解析了，免得报错
    if json_obj is None:
        return None
    data = json_obj['result']
    if data is None:
        return None
    return {
        "id_cpu": data['idCPU'],
        "id_pm3": data['idPM3'],
        "id_stm32": data['idSTM32'],
        "type": data['type'],
        "date": data['date'],
        "sn_str": data['snStr'],
        "fc_state": data['fcState'],
        "hw_version_main": data['hwVersionMain'],
        "hw_version_sub": data['hwVersionSub'],
    }


def save_info(infos, typ: int, hw_major_ver: int, hw_minor_ver: int):
    """
        保存信息和生成序列号
        saveinfo
    :return:
    """
    if hw_major_ver > 999:
        raise Exception("过大的主版本号")
    if hw_minor_ver > 999:
        raise Exception("过大的次版本号")
    if typ is None:
        raise Exception("空的设备类型")
    if infos is None:
        raise Exception("空的设备信息")
    # 把信息传过去入库
    response = DR.request_json_api_auto_login(URL_ADMIN_ADD_DEVICE_INFO, {
        'id_cpu': infos['id_cpu'],
        'id_pm3': infos['id_pm3'],
        'id_stm32': infos['id_stm32'],
        'type': typ, 'hw_major_ver': hw_major_ver, 'hw_minor_ver': hw_minor_ver,
    })
    return response['result']


def get_row_from_database_for_infos(infos):
    """
        从数据库获取指定的设备信息的设备的记录
    :param infos:
    :return:
    """
    response = DR.request_json_api_auto_login(URL_ADMIN_GET_DEVICE_INFO_BY_ID, {
        'id_cpu': infos['id_cpu'],
        'id_pm3': infos['id_pm3'],
        'id_stm32': infos['id_stm32'],
    })
    return data_pre_processor(response)


def get_row_from_database_for_sn(sn):
    """
        从数据库获取指定的设备信息的设备的记录
    :param sn:
    :return:
    """
    response = DR.request_json_api_auto_login(URL_ADMIN_GET_DEVICE_INFO_BY_SN, {
        'sn': sn,
    })
    return data_pre_processor(response)


def get_sn_for_device_info(infos):
    """
        从数据库获取指定的设备硬件ID信息的设备的记录的SN
    :param infos: 设备的ID信息
    :return: 设备的序列号
    """
    data_processed = get_row_from_database_for_infos(infos)
    if data_processed is None:
        return None
    return data_processed['sn_str']


def get_factory_status_for_sn(sn):
    """
        获取出厂状态
    :param sn:
    :return:
    """
    data_processed = get_row_from_database_for_sn(sn)
    if data_processed is None:
        return None
    return data_processed['fc_state']


def update_factory_status_for_sn(sn, status: int):
    """
        更新生产状态
        这个值，我们可以使用4位来进行操作！
    :param sn: 目标设备的SN，字符串型，8个字符
    :param status:厂商状态，1位（0-9）int型
    :return:
    """
    response = DR.request_json_api_auto_login(URL_ADMIN_UPDATE_DEVICE_STATUS, {'sn': sn, 'status': status})
    return response['result']


def update_device_type_for_sn(sn, newtype: int):
    """
        更新指定SN设备的类型
    :param sn:
    :param newtype:
    :return:
    """
    response = DR.request_json_api_auto_login(URL_ADMIN_UPDATE_DEVICE_TYPE, {'sn': sn, 'type': newtype})
    return response['result']


if __name__ == '__main__':
    # 这两行代码是为了在调试的时候不要弹出一个空白的window
    window = tkinter.Tk()
    window.withdraw()  # 退出默认 tk 窗口

    logging.basicConfig(level=logging.NOTSET, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # LOGGER.debug(get_icopy_admin_account())
    # resp = get_sn_for_device_info({
    #     'id_cpu': '02c0018172c21dd4',
    #     'id_pm3': '33662A9F780467C8',
    #     'id_stm32': '0670FF515153826687141042C86704789F7A5536',
    # })
    while True:
        resp = get_row_from_database_for_sn("00210003")
        # resp = save_info({
        #     'id_cpu': '02c0018172c21dd411',
        #     'id_pm3': '33662A9F780467C8',
        #     'id_stm32': '0670FF515153826687141042C86704789F7A5536',
        # }, 4, 1, 9)
        LOGGER.debug(f"操作结果：{resp}")
        time.sleep(1)
    pass
