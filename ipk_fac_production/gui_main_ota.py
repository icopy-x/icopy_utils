import json
import os
import threading
import time

from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import wait, ALL_COMPLETED

import generator_utils
import data_control
import icopy_maps
import make_impl

from Crypto.Cipher import AES
from binascii import a2b_hex


class OTAGui:
    """
        用于OTA的后端实现的GUI
    """

    debug = False

    def __init__(self):
        """
            初始化GUI与必要变量
        """
        if self.debug:
            self.ota_server_addr = "127.0.0.1"
            self.ota_http_level = "http"
        else:
            self.ota_server_addr = "icopy-x.com"
            self.ota_http_level = "https"

        self.ota_data_password = "jrgfjrgfjrgfjrgf"
        self.ota_data_iv = "qwertyuiasdfghjk"

        self.ota_connection_pwd = "jrgfjrgf"

        # 定义需要用到的API
        if self.debug:
            self.action_get_wait_list = "get_wait_list.php"
            self.action_get_job_state = "get_job_state.php"
            self.action_ota_queue2_update = "ota_queue2_update.php"
            self.action_ota_queue_add = "ota_queue_add.php"
            self.action_rm_wait_list = "rm_wait_list.php"
            self.action_set_ok = "set_ok.php"
            self.action_upload = "upload.php"
            self.action_set_wait_list_no_sn = "set_wait_list_sn_state.php"
            self.action_rm_toofar_history = "rm_toofar_history.php"
        else:
            self.action_get_wait_list = "otasys/get_wait_list.php"
            self.action_get_job_state = "otasys/get_job_state.php"
            self.action_ota_queue2_update = "otasys/ota_queue2_update.php"
            self.action_ota_queue_add = "otasys/ota_queue_add.php"
            self.action_rm_wait_list = "otasys/rm_wait_list.php"
            self.action_set_ok = "otasys/set_ok.php"
            self.action_upload = "otasys/upload.php"
            self.action_set_wait_list_no_sn = "otasys/set_wait_list_sn_state.php"
            self.action_rm_toofar_history = "otasys/rm_toofar_history.php"

        # 即将被处理的任务
        self.list_wait_task = []
        # 正在进行处理的任务
        self.list_run_task = []

        # 操作时加锁
        self.lock_wait_list = threading.RLock()
        self.lock_run_list = threading.RLock()

        # 如果列表为空，那么数据应该是这个样子的
        self.str_wait_list_empty = "81de62dee1db4d64c5516ed14010eb87"

    def request_action(self, action, params=None, retry_max=8):
        """
            请求一个活动并且获得回复！
        :param retry_max: 自动重试的次数上限
        :param action:  活动类型，也就是域名之后的资源
        :param params:  活动需要的参数，键值对
        :return:
        """
        if retry_max == 0:
            print("重试次数达到上限，不允许接着重试。")
            return None

        try:
            result = generator_utils.get_server_resp(
                f"{self.ota_http_level}://{self.ota_server_addr}/{action}",
                False,  # 是否返回字符串，这里我们需要原始字节，所以关闭
                "POST",
                params,
                (8, 8)
            )
            if self.debug:
                try:
                    print(
                        f"{self.ota_http_level}://{self.ota_server_addr}/{action} request_action成功结果: ",
                        result.decode()
                    )
                except Exception as e:
                    print(
                        f"{self.ota_http_level}://{self.ota_server_addr}/{action} request_action失败结果:",
                        result,
                        ", e= ",
                        e)
        except Exception as e:
            print("链接出现异常，将会自动重试: ", e)
            time.sleep(3)
            return self.request_action(action, params, retry_max - 1)

        return result

    def get_wait_list(self):
        """
            获取等待生产的任务的列表
        :return:
        """
        try:
            # 先获取已经加密过的列表数据
            list_encrypted = self.request_action(self.action_get_wait_list)
            if list_encrypted is None or list_encrypted == self.str_wait_list_empty:
                return []

            # 然后我们需要使用AES解密
            aes = AES.new(
                self.ota_data_password.encode(),
                AES.MODE_CBC,
                self.ota_data_iv.encode()
            )

            # 解密
            list_decrypt = aes.decrypt(a2b_hex(list_encrypted))
            list_decrypt = list_decrypt[0: -int(list_decrypt[-1])]
            # print("解密结果", list_decrypt.decode())

            # 解密完成后加载位json字典
            return json.loads(list_decrypt.decode())
        except Exception as e:
            print("获取等待队列时出现异常: ", e)
            return []

    @staticmethod
    def is_sn_exists(sn):
        """
            提供一个判断SN是否合法的接口！
        :param sn:
        :return:
        """
        if sn is None or not isinstance(sn, str) or len(sn) != 8:
            print("SN输入不规范: ", sn)
            return False
        return data_control.get_row_from_database_for_sn(sn) is not None

    def update_task_to_server(self):
        """
           更新任务进度，状态，之类的到服务器
        :return:
        """
        json_ret = []
        with self.lock_wait_list:
            for task_item in self.list_wait_task:
                json_ret.append({
                    "hash": task_item['HASH'],
                    "progress": 0,  # TODO 后期可以添加进度跟踪，目前不想做
                })
        # print("列表2中的数据", json_ret)
        # print("正在处理中的数据", self.list_run_task)
        return self.request_action(
            self.action_ota_queue2_update,
            {
                "jsonstr": json.dumps(json_ret)
            }
        )

    def notify_task_finish(self, hash_code, state):
        """
            执行结束后，通知服务器端后端对于改任务的处理结果！
            目前只能传1 或者 2，用处随后定
        :param hash_code:
        :param state:
        :return:
        """
        return self.request_action(
            self.action_set_ok,
            {
                "hash": hash_code,
                "state": state
            }
        )

    def rm_wait_at_server(self, hash_code):
        """
            移除任务，从公共服务器上
        :return:
        """
        return self.request_action(
            self.action_rm_wait_list,
            {
                "hash": hash_code
            }
        )

    def notify_sn_state(self, hash_code, state):
        """
            通知PHP端，SN不存在
        :param state:
        :param hash_code:
        :return:
        """
        return self.request_action(
            self.action_set_wait_list_no_sn,
            {
                "hash": hash_code,
                "state": state,
            }
        )

    def upload_to_server(self, file, typ):
        """
            上传文件到服务器
        :param typ:
        :param file:
        :return:
        """
        try:
            ret = generator_utils.upload_file(
                f"{self.ota_http_level}://{self.ota_server_addr}/{self.action_upload}",
                file,  # 将要上传的文件
                "userfile",
                data={
                    "session_key": self.ota_connection_pwd,
                    "type": typ,
                }
            )
        except Exception as e:
            print("上传的时候出现异常，将会自动重试: ", e)
            return self.upload_to_server(file, typ)
        return ret

    def clear_toofar_history(self, history_range):
        """
            清理指定的日期之外的过期任务
            防止服务器空间不足
        :param history_range:
        :return:
        """
        return self.request_action(
            self.action_rm_toofar_history,
            {
                "session_key": self.ota_connection_pwd,
                "history_range": history_range,
            }
        )

    def upload_log_to_server(self):
        """
            上传日志到服务端
        :return:
        """
        with open("updates_log_zh.json") as fd:
            return self.upload_to_server(
                json.dumps(
                    json.load(
                        fd
                    )
                ), "changelog"
            )

    def run_action_server(self, index):
        """
            提供服务运行逻辑的实现
        :return:
        """
        while True:
            try:
                # print(f"线程{index} 正在拉取等待列表")
                # 我们需要下拉最新的等待处理任务的列表
                wait_list = self.get_wait_list()

                if len(wait_list) == 0:  # 判断是否需要处理
                    # print("不需要处理任何任务！")
                    time.sleep(0.1)
                else:
                    # print("需要处理的任务有", len(wait_list), "条")
                    for wait_item in wait_list:
                        # 取出数据
                        sn = wait_item['DEVICE_SN']
                        # SN不存在，我们需要更新状态到云端
                        code = wait_item['HASH']
                        # 判断SN是否存在
                        if self.is_sn_exists(sn):
                            # SN存在，我们需要添加到本地待处理的列表中
                            with self.lock_wait_list:
                                can_add = True  # 默认不存在，可以添加
                                # print("即时状态: ", self.list_wait_task)
                                for item_local in self.list_wait_task:  # 迭代本地的任务列表，判断是否有存在的记录
                                    if sn == item_local['DEVICE_SN'] and code == item_local['HASH']:  # SN和hash都一样，则任务存在
                                        can_add = False
                                        # print("已经存在任务: ", item_local)
                                        break
                                # 最终判断有木有重复的任务
                                if can_add:
                                    self.list_wait_task.append(wait_item)
                                    print(f"线程{index}添加了一项任务: ", wait_item)

                            # SN存在的情况下，我们需要通知PHP端
                            self.notify_sn_state(code, 4)
                        else:
                            print("SN不存在: ", sn)
                            # SN不存在的情况下，我们需要通知PHP端
                            self.notify_sn_state(code, 3)

                        # 从列表1中移除等待
                        self.rm_wait_at_server(code)

            except Exception as e:
                print(e)

            time.sleep(1)
            # print("")

    def make_ipk_for_sn(self, sn):
        """
            构建SN
        :param sn:
        :return:
        """
        infos = data_control.get_row_from_database_for_sn(sn)
        return make_impl.make_ipk_for_infos(
            icopy_maps.get_device_type_str(infos["type"]),
            infos,
        )

    @staticmethod
    def is_same_item(item1, item2):
        return item1['DEVICE_SN'] == item2['DEVICE_SN'] and item1['HASH'] == item2['HASH']

    def run_task_server(self):
        """
            处理本地任务的服务
            负责编译IPK更新包和向服务器端提供最新的状态消息
        :return:
        """
        while True:
            try:
                # 从任务队列里面取出信息进行构建！
                # 弹出一个头部元素
                task_item = None
                with self.lock_wait_list:
                    for index in range(len(self.list_wait_task) - 1, -1, -1):  # 逆序取出任务项
                        tmp_task_item = self.list_wait_task[index]
                        # 我们需要检查，正在处理的任务，有没有一样的
                        with self.lock_run_list:
                            if tmp_task_item not in self.list_run_task:
                                # 检查重复任务项通过，我们就需要添加进处理列表中
                                task_item = tmp_task_item
                                self.list_run_task.append(task_item)
                                break

                if task_item is None:
                    time.sleep(0.1)
                    continue

                # 取出数据
                sn = task_item['DEVICE_SN']
                code = task_item['HASH']

                # 然后我们需要开始构建
                ipk = self.make_ipk_for_sn(sn)
                if ipk is None:
                    self.notify_task_finish(code, 2)
                else:
                    new_file = f"{code}.ipk"
                    try:
                        # 文件存在，则需要改成HASH同名的文件
                        os.rename(ipk, new_file)
                        # 上传到服务器
                        self.upload_to_server(new_file, "otapkg")
                        ret = 1
                        # 用完就删除
                        os.remove(new_file)
                    except Exception as e:
                        print(e)
                        ret = 2
                    self.notify_task_finish(code, ret)  # 1表示成功, 2表示失败

                with self.lock_wait_list:
                    # 任务完成后后从待处理列表移除任务
                    self.list_wait_task.remove(task_item)
                    # for index in range(len(self.list_wait_task)):
                    #     item_in_list = self.list_wait_task[index]
                    #     if self.is_same_item(task_item, item_in_list):
                    #         del self.list_wait_task[index]

                with self.lock_run_list:
                    # 任务完成后后从待处理列表移除任务
                    self.list_run_task.remove(task_item)
                    # for index in range(len(self.list_run_task)):
                    #     item_in_list = self.list_run_task[index]
                    #     if self.is_same_item(task_item, item_in_list):
                    #         del self.list_run_task[index]

            except Exception as e:
                print(e)
                time.sleep(2)

            print(f"任务: {task_item}, 处理成功！")

    def run_task_status(self):
        """
            负责处理任务的状态更新到服务器端
        :return:
        """
        while True:
            try:
                self.update_task_to_server()
            except Exception as e:
                print("更新任务状态的时候出现了问题: ", e)
            time.sleep(2)

    def run_history_clear(self):
        """
            负责每隔一段时间请求清理服务端
            这个清理任务应该定时，然后还要比较长时间再请求一次，
            不然会浪费服务器的性能
        :return:
        """
        while True:
            try:
                # 清理存放时间大于等于四天的历史
                content = self.clear_toofar_history(4)
                content = content.decode().replace("<br/>", "\n")
                print("服务器清理结果: ")
                print(content)

                # 然后再等待一段时间，这段时间让线程一直休眠就好了
                # 这里的话，我们工作一次休眠三天
                time.sleep(((60 * 60) * 24) * 3)
            except Exception as e:
                print(e)
            time.sleep(2)

    def gui_main_start(self):
        """
            启动最终的GUI逻辑！
        :return:
        """
        max_wait_list_process = 2
        max_compile_task_process = 2
        max_task_status_update_process = 2
        max_task_clear_history_process = 1

        max_pool_count = (
                max_wait_list_process +
                max_compile_task_process +
                max_task_status_update_process +
                max_task_clear_history_process
        )

        thread_list = []

        with ThreadPoolExecutor(max_workers=max_pool_count) as t:
            # 创建等待任务处理队列的线程
            for count in range(max_wait_list_process):
                thread_list.append(t.submit(self.run_action_server, count))

            # 创建处理编译任务的线程
            for count in range(max_compile_task_process):
                thread_list.append(t.submit(self.run_task_server))

            # 创建处理更新任务的线程
            for count in range(max_task_status_update_process):
                thread_list.append(t.submit(self.run_task_status))

            # 创建自动清理历史任务的线程
            for count in range(max_task_clear_history_process):
                thread_list.append(t.submit(self.run_history_clear))

            wait(thread_list, return_when=ALL_COMPLETED)

        return


if __name__ == '__main__':
    otagui = OTAGui()
    otagui.gui_main_start()

    # 讲道理，出现这个的话明显有问题！
    while True:
        print("不能走到这里，有大问题")
        time.sleep(100)
