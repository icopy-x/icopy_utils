"""
    负责绘制UI
"""

import os
import time
import socket
import shutil
import datetime
import threading
import multiprocessing

import psutil
import select
import serial.tools.list_ports

from concurrent.futures.thread import ThreadPoolExecutor
from queue import Queue

from tkinter import *
from tkinter import simpledialog, messagebox
from tkinter.ttk import Progressbar

import data_control
import icopy_maps
import make_impl
import logging

# '''
#     请在外部一个层级新建一个build目录，然后再进入build目录进行执行
#     pyinstaller ../ipk_fac_production/gui_main_menu.py -p ../ipk_pack_center;
#       然后复制 `启动打包器.bat` 和打印机文件 `netcoreapp3.1` 。
# '''

# 创建一个logger
logger = logging.getLogger('mylogger')
logger.setLevel(logging.DEBUG)

# 创建一个handler，用于写入日志文件
fh = logging.FileHandler('factory.log')
fh.setLevel(logging.DEBUG)

# 再创建一个handler，用于输出到控制台
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# 定义handler的输出格式
formatter = logging.Formatter('[%(asctime)s][%(thread)d][%(filename)s][line: %(lineno)d][%(levelname)s] ## %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# 给logger添加handler
logger.addHandler(fh)
logger.addHandler(ch)


class SetQueue(Queue):
    """
        集合队列，不允许重复元素
    """

    def _init(self, maxsize):
        self.maxsize = maxsize
        self.queue = set()

    def _put(self, item):
        self.queue.add(item)

    def _get(self):
        return self.queue.pop()


class VerSelectGUI(Toplevel):
    """
        版本选择的对话框
    """

    def __init__(self, master=None):
        super().__init__(master)

        self.title(f"请选择你要生产的版本！")
        self.geometry("448x448")
        self.resizable(False, False)
        self.wm_attributes('-topmost', True)
        self.configure(background="#696969")

        # 此函数可以禁用主窗口
        self.grab_set()

        # 定义目前支持生产的版本列表
        self.ver_list = [
            self.create_ver_map(1, 5, "第一批量产"),
            self.create_ver_map(1, 7, "测试版本"),
            self.create_ver_map(1, 8, "第二批量产"),
            self.create_ver_map(1, 10, "第三批量产"),
        ]

        self.radio_btn = IntVar()

        # 拦截退出事件！
        self.protocol('WM_DELETE_WINDOW', self.on_exit)
        # 绘制UI
        self.draw_ver_select_ui()

    def on_cancel_select(self):
        """
            取消选择
        :return:
        """
        self.radio_btn.set(-1)
        self.destroy()
        logger.debug("取消生产")

    def on_confirm_select(self):
        """
            确认选择某个版本
        :return:
        """
        map_obj = self.ver_list[self.radio_btn.get()]
        text = self.make_btn_text(map_obj)
        message = ""
        for index in range(10):
            message += (text + "！！！\n")
        if messagebox.askyesno("警告！", f"你选择了版本: \n\n{message}\n再次确定生产该版本吗？", parent=self):
            self.destroy()
        else:
            logger.debug("重新选择")

    def draw_ver_select_ui(self):
        """
            绘制UI
        :return:
        """
        for ver in self.ver_list:
            Radiobutton(
                self,
                variable=self.radio_btn,
                value=self.ver_list.index(ver),
                text=self.make_btn_text(ver),
                font="黑体 12",
                bg="#8E8E8E"
            ).pack(anchor=S + W, padx=16, pady=10)

        # 默认选择最后一个，最后一个肯定是最新的。。。
        self.radio_btn.set(len(self.ver_list) - 1)

        tips_text = """
一、版本在哪里看？
    PCBA上面一般会印刷着版本号，
    你可以找找，找不到的话要去问工程
    
二、为什么PCBA上面的版本号不在列表里？
    有可能是因为硬件出来了，
    但是软件还没更新，需要让工程更新一下
    
三、请注意一定要选对硬件版本号，
    避免数据库入库错误
        """

        Label(
            self,
            text=tips_text,
            bg="#696969",
            fg="white",
            font="黑体 13",
            justify=LEFT,
            anchor=W
        ).pack(anchor=W, padx=16)

        btn_frame = Frame(
            self,
            bg="#696969",
        )
        btn_frame.place(x=190, y=390)

        Button(
            btn_frame,
            text="取消生产",
            bg="#696969",
            fg="white",
            font="黑体 12",
            height=2,
            command=self.on_cancel_select,
        ).grid(row=0, column=0)
        Button(
            btn_frame,
            text="确定该版本进入生产",
            bg="#696969",
            fg="white",
            font="黑体 12",
            height=2,
            command=self.on_confirm_select,
        ).grid(row=0, column=1, padx=16)

    def on_exit(self):
        """
            不允许退出
        :return:
        """

    @staticmethod
    def create_ver_map(major, minor, tips):
        """
            创建硬件版本号的映射对象
        :param tips:
        :param major:
        :param minor:
        :return:
        """
        return {
            "major": major,
            "minor": minor,
            "tips": tips,
        }

    def make_btn_text(self, map_obj):
        """
            创建按钮的文本
        :param map_obj:
        :return:
        """
        return f"PCBA: {map_obj['major']}. {map_obj['minor']} - {map_obj['tips']}"

    def wait_get_selected(self):
        """
            等待窗口结束并且返回值
        :return:
        """
        # 堵塞等待这个对话框窗口结束
        self.master.wait_window(self)
        pos = self.radio_btn.get()
        if pos == -1:
            return None
        return self.ver_list[pos]


class FactoryGUI(Tk):
    """
        用于管理初始化生产与信息入库的GUI实现
    """

    def __init__(self, typ, ver, screenName=None, baseName=None, className='Tk',
                 useTk=1, sync=0, use=None):
        super().__init__(screenName=screenName, baseName=baseName, className=className,
                         useTk=useTk, sync=sync, use=use)

        if typ is None or ver is None:
            messagebox.showerror("警告！！！", "开发者没有传递类型参数！！！")
            return
        else:
            self.typ = typ
            self.ver = ver
            logger.debug(f"当前需要生产的类型: {self.typ}, 当前要生产的版本: {self.ver}")

        self.title(f"生产 {self.typ}, PCBA版本: {ver['major']}.{ver['minor']}")
        self.geometry("448x448")
        self.resizable(False, False)
        self.wm_attributes('-topmost', True)

        self.var_device_count = IntVar(value="0")
        self.var_make_ok_count = IntVar(value="0")
        self.var_make_fw = StringVar(value="0")
        self.var_make_tag = StringVar(value="0")
        self.var_release_fw = StringVar(value="0")

        # 此函数可以禁用主窗口
        self.grab_set()
        # 开始绘制UI
        self.draw_production_ui()

        # 拦截退出事件！
        self.protocol('WM_DELETE_WINDOW', self.on_exit)

        # 设备列表
        self.device_list = list()
        # 缓存com到设备的sn映射
        self.sn_com_map = dict()
        # 标签只能顺序一个一个粘贴，所以需要队列
        self.queue_tag_make = SetQueue()
        # 目前的话，固件生产只能一个一个来，所以也需要队列
        self.queue_fw_make = SetQueue()
        # 保存标签已经生产成功的设备列表
        self.sn_tag_list = list()
        # 保存ipk文件对应到设备的映射
        self.sn_ipk_map = dict()

        # 线程池，维护任务创建的线程队列
        self.threadPool = ThreadPoolExecutor(max_workers=multiprocessing.cpu_count(), thread_name_prefix="production_")
        # 开始启动生产过程的子线程！
        threading.Thread(target=self.thread_device_make_tag).start()
        threading.Thread(target=self.thread_device_make_fw).start()
        threading.Thread(target=self.thread_device_make_release).start()
        threading.Thread(target=self.thread_device_search).start()

    def get_type_detailed(self):
        """
            获得版本对应的详细信息
        :return:
        """
        return icopy_maps.get_type_factory_name(self.typ)

    def run_test_label_print(self, btn):
        """
            测试标签的打印
        :return:
        """
        btn['state'] = DISABLED
        self.print_sn_for_dev("12345678")
        btn['state'] = NORMAL

    def run_self_label_print(self, btn):
        """
            测试标签的打印
        :return:
        """
        btn['state'] = DISABLED
        newWin = Tk()
        newWin.withdraw()
        msg = "请输入您的SN，然后点击确定\n注意，SN的位数是8位纯数字，\n具体请看数据库或者手持机About页面！"
        sn: str = simpledialog.askstring("SN输入", msg, parent=newWin)

        if sn is None or len(sn) != 8 or not sn.isdigit():
            messagebox.showerror("错误", "您的SN不在基础规范内！", parent=newWin)
        else:
            self.print_sn_for_dev(sn)

        newWin.destroy()
        btn['state'] = NORMAL

    def draw_production_ui(self):
        """
            绘制在生产时的UI
            一、设备连接后，信息就可以请求获取，此时我们可以直接进行入库，然后进行下一步的发布固件生产流程

            二、生产固件的过程和贴标签的过程可以分开，也就是说，当我们获取到了设备的信息后，就可以排队生产
            ，但是生产完成并不能进行固件派发，需要等标签贴好后才能派发，也就说，生产流程就是：
                1、插入设备，得到信息
                2、固件生产，准备下发
                3、设备闪烁，要贴标签
                3、标签贴好，可以下发

            三，系统分两个，分别有固件生产系统和标签生产系统
                1、固件生产系统的结果文件会被保存到硬盘，直到标签生产系统完成生产后下发文件
                2、标签系统如果提前完成了标签生产，但是固件生产系统还没完成，此时直接进入下一台设备的标签生产流程，
                    然后将这台设备的固件生产过程安排进队列里面，完成后自动下发
        :return:
        """
        # 绘制上方的大字，用于计数
        frame_production_info = LabelFrame(self, text="生产信息：", width=212, height=212)
        frame_production_info.grid(row=0, column=0, padx=6, pady=6, sticky="NW")
        frame_production_info.grid_propagate(False)

        Label(frame_production_info, text="已连接的设备数量: ").grid(padx=6, pady=6, row=0, column=0, )
        Label(frame_production_info, textvariable=self.var_device_count).grid(padx=6, pady=6, row=0, column=1, )

        Label(frame_production_info, text="已经完成生产数量: ").grid(padx=6, pady=6, row=2, column=0, )
        Label(frame_production_info, textvariable=self.var_make_ok_count).grid(padx=6, pady=6, row=2, column=1, )

        Label(frame_production_info, text="正在生产固件序号: ").grid(padx=6, pady=6, row=3, column=0, )
        Label(frame_production_info, textvariable=self.var_make_fw).grid(padx=6, pady=6, row=3, column=1, )

        Label(frame_production_info, text="正在打印标签序号: ").grid(padx=6, pady=6, row=4, column=0, )
        Label(frame_production_info, textvariable=self.var_make_tag).grid(padx=6, pady=6, row=4, column=1, )

        Label(frame_production_info, text="正在下发固件序号: ").grid(padx=6, pady=6, row=6, column=0, )
        Label(frame_production_info, textvariable=self.var_release_fw).grid(padx=6, pady=6, row=6, column=1, )

        frame_production_result = LabelFrame(self, text="今日已完成的生产数量：", width=212, height=212)
        frame_production_result.grid(row=0, column=1, padx=6, pady=6)
        frame_production_result.grid_propagate(False)

        Label(
            frame_production_result,
            font=("宋体", 68),
            textvariable=self.var_make_ok_count,
        ).grid(padx=28, pady=38)

        frame_production_tool = LabelFrame(self, text="生产工具：", width=212, height=212)
        frame_production_tool.grid(row=1, column=0, padx=6, pady=6, sticky="NW")
        frame_production_tool.grid_propagate(False)

        btn_test_print_sn = Button(
            frame_production_tool,
            text="测试打印标签(平时不要用)",
            command=lambda: threading.Thread(target=self.run_test_label_print, args=(btn_test_print_sn,)).start()
        )
        btn_test_print_sn.grid(padx=6, pady=6, row=0, column=0, )

        btn_self_print_sn = Button(
            frame_production_tool,
            text="手动打印标签(缺漏标签用)",
            command=lambda: threading.Thread(target=self.run_self_label_print, args=(btn_self_print_sn,)).start()
        )
        btn_self_print_sn.grid(padx=6, pady=6, row=1, column=0, )

        frame_production_msg = LabelFrame(self, text="当前生产的设备类型：", width=212, height=212)
        frame_production_msg.grid(row=1, column=1, padx=6, pady=6)
        frame_production_msg.grid_propagate(False)

        Message(
            frame_production_msg,
            text=self.get_type_detailed(),
            font=("Consolas", 30, "bold",),
            fg="red"
        ).grid(padx=6, pady=30)

    def sendMsg2Port(self, port, msg, resp=False, retry_max=5):
        """
            发送一个指令到端口，一次通信打开一次端口
        :param resp:
        :param msg:
        :param retry_max:
        :param port:
        :return:
        """
        if port not in self.searchCOM():
            logger.debug(f"端口丢失: {port}，将自动取消消息发送！")
            return None
        if retry_max == 0:
            return None
        try:
            if isinstance(msg, str):
                msg = msg.encode()
            if not msg.endswith(b"\r\n"):
                msg += b"\r\n"
            with serial.Serial(port, 115200, timeout=3) as serial_port:
                if serial_port.is_open:
                    # 先刷新缓存
                    serial_port.flush()
                    # 然后写数据
                    serial_port.write(msg)
                    serial_port.flush()
                    if resp:
                        ret = serial_port.readline().decode()
                        # logger.debug(f"sendMsg2Port() -> 接收到的消息: {ret}")
                        return ret
                    return ""
                else:
                    logger.debug("打开失败，请检查出现的异常。")
        except Exception as e:
            logger.debug(f"在发送消息的过程中出现了异常: {e}")
            time.sleep(1)
            return self.sendMsg2Port(port, msg, resp, retry_max - 1)
        return None

    def backlight_flash_dev(self, sn, flash=True):
        """
            闪烁指定的SN的设备
        :param flash:
        :param sn:
        :return:
        """
        # 先取出信息封包
        port = self.sn_com_map[sn][1]
        # 再把串口信息取出来
        if flash:
            # 然后进行串口通信，使能闪烁
            self.sendMsg2Port(port, "TAG_START")
        else:  # 关闭闪烁
            self.sendMsg2Port(port, "TAG_FINISH")

    def print_sn_for_dev(self, sn):
        """
            打印SN
        :param sn:
        :return:
        """
        self.serial_number_print(sn)

    def thread_device_search(self):
        """
            自动轮询新的设备，并且添加到列表中
        :return:
        """
        while True:
            # 先搜索最新的设备
            new_device_list = self.searchCOM()

            # 进行对比，看看是否有设备移除，移除则做停止相关的操作
            for old_device in self.device_list:
                if old_device not in new_device_list:
                    logger.debug(f"移除了一个手持机设备: {old_device}")
                    self.device_list.remove(old_device)
                    self.remove_task_for_dev(old_device)

            for new_device in new_device_list:
                # 如果新的设备不在设备列表里面，则说明是新增的设备
                if new_device not in self.device_list:
                    logger.debug(f"插入了新的手持机设备: {new_device}")
                    self.device_list.append(new_device)
                    self.create_task_for_dev(new_device)

            self.var_device_count.set(len(self.device_list))

            # 每秒延时
            time.sleep(0.01)

    def thread_device_make_tag(self):
        """
            专门负责标签制作的任务系统轮询
        :return:
        """
        while True:
            # 取出信息
            sn = self.queue_tag_make.get()
            tag_make = True

            if self.is_tag_make_already(sn):
                msg = f"SN为 {sn} 的设备可能已经生产过标签了，是否需要重新生产？"
                if not messagebox.askyesno("警告！", msg):
                    tag_make = False

            if tag_make:
                logger.debug(f"需要生产该标签: {sn}")
                self.var_make_tag.set(sn)
                # 进行打印任务执行
                self.print_sn_for_dev(sn)
                # 进行设备闪烁任务
                self.backlight_flash_dev(sn)
                # 堵塞询问操作者（也就是生产工人）是否完成了标签生产操作
                msg = "亲爱的生产者，我们有一个标签已经打印，请寻找闪烁的设备，" \
                      "然后粘贴到指定位置，完成后，请点击确定，开启下一个任务。（全程都不要移除设备）"
                messagebox.showinfo("标签粘贴", msg)
                # 关闭闪烁
                self.backlight_flash_dev(sn, False)
                # 此处需要将出厂状态设置为已粘贴标签
                self.set_tag_make_ok(sn)
                logger.debug("标签生产完成\n")

            # 需要告知固件生产系统，该设备可以进行固件的最终生产了。
            self.sn_tag_list.append(sn)
            # 告知任务完成，可以进行下一轮循环
            self.queue_tag_make.task_done()

    def thread_device_make_fw(self):
        """
            专门负责固件制作的任务系统
            每次制作完成后都检查一下标签制作的结果，
            如果标签制作系统的设备已经完成制作，
            并且固件制作系统的设备也已经完成制作，
            则进行最终的固件下发操作,
            注意，每次只能制作一个固件！！！
        :return:
        """
        while True:
            # 取出我们目前需要生产的固件的信息
            sn = self.queue_fw_make.get()
            logger.debug(f"需要生产该固件: {sn}")
            self.var_make_fw.set(sn)
            # 提取信息封包
            infos = self.sn_com_map[sn][0]
            # 注意，此处添加了一个键值对，用来区分生产和正常OTA
            infos['fac_auto_make'] = True

            # 进行ipk的制作
            ipk_file = self.make_ipk_for_infos(infos)
            # 然后制作完成后，我们需要告知ipk的下发系统，有相关的设备可以下发固件了
            if ipk_file is not None:
                # 缓存sn和ipk的关系映射
                self.sn_ipk_map[sn] = ipk_file
            else:
                messagebox.showerror("警告！", f"有一个固件包生产失败，设备的序列号是: {sn}, 设备的信息是: {infos}")
            self.queue_fw_make.task_done()

    def thread_device_make_release(self):
        """
            专门负责最终的固件下发，
            这个步骤应当是最终步骤
        :return:
        """
        while True:
            # 我们需要查看哪些设备已经贴好了标签，
            # 固件生产好了可以不用，但是标签必须要贴
            # 因此，我们以标签的生产结果为主要的判断依据
            # 然后以固件的生产结果为次要的判断依据，
            # 如果两者同时符合条件，则进行最终的固件下发
            for sn in self.sn_tag_list:
                if sn in self.sn_ipk_map:  # 我们如果查到了ipk的映射关系，则进行下发
                    self.var_release_fw.set(sn)
                    if not self.make_ipk_release(sn, self.sn_ipk_map[sn]):
                        messagebox.showerror("警告！",
                                             f"SN为 {sn} 的设备在进行最后一项操作：'固件发布操作' 的时候出现问题，发布失败！")
                    self.sn_tag_list.remove(sn)  # 无论如何，下发完成后都要移除当前的序列号记录
                    del self.sn_ipk_map[sn]

            time.sleep(0.1)

    def get_device_type_int(self):
        """
            获取设备的类型锁映射的int型
        :return:
        """
        return icopy_maps.get_device_type_int(self.typ)

    def create_task_for_dev(self, dev):
        """
            根据设备信息创建生产任务
        :param dev:
        :return:
        """

        def run():
            try:
                # 查看两者的SN是否已经一样，一样则不再重复发布
                sn_from_device = self.sendMsg2Port(dev, "SN_GET", True)
                logger.debug(f"设备已经存在的固件包中的SN: {sn_from_device}")
                if sn_from_device is None:
                    logger.debug("获取到了真的 None 的SN，应该是通信有问题。")
                    return

                # 得先判断SN是否正常，如果不正常可能是该设备并没有被生产过！
                sn_from_device = sn_from_device.strip()
                if sn_from_device.isnumeric():
                    if self.is_fw_release_already(sn_from_device):
                        logger.debug(f"此 {sn_from_device} 设备的固件已经在数据库中标志为生产完毕！")
                    else:
                        logger.debug(f"此 {sn_from_device} 设备的固件已经在数据库中标志为生产到最终阶段！")
                        self.set_fw_release_ok(sn_from_device)
                        self.var_make_ok_count.set(self.var_make_ok_count.get() + 1)
                        logger.debug(f"此 {sn_from_device} 设备发布成功，入库成功！")
                    return
                else:
                    logger.debug(f"该设备没有SN，可能是新的机器，将尝试进行生产: {dev}")

                # 先读取信息
                infos = self.get_infos_for_device(dev)
                if infos is None or len(infos) <= 0:
                    logger.debug(f"从{dev}读取信息失败，可能是STM32和PM3其中一个硬件有问题。")
                    return
                else:
                    logger.debug(f"信息读取成功: {infos}，接下来开始进行信息入库，然后开启编译任务。")

                # 解析下位机的字符串信息，组装为字典形式
                infos = self.parse_infos(infos)
                if infos is None:
                    raise Exception(f"解析设备数据为字典类型失败: {infos}")

                logger.debug(f"解析设备数据为字典类型完成：{infos}")

                # 读取信息成功了，此时我们需要判断
                device_old_infos = data_control.get_row_from_database_for_infos(infos)
                if device_old_infos is not None:
                    logger.debug(f"云端检查设备历史信息结果不为空，该设备需要继续生产")
                    device_old_type = icopy_maps.get_device_type_str(device_old_infos['type'])
                    if self.typ != device_old_type:
                        device_old_sn = device_old_infos['sn_str']
                        # 信息非空而且两次生产的类型不一致的话，我们就需要进行提示生产者
                        # 告诉生产者，这台机器被生产过了，仅仅替换SD卡是不行
                        # 还需要生产者确认一下，去修改数据库中的数据！
                        msg = f"判断你当前有一个设备已经有完整的信息存在于数据库中，但是该设备响应了工厂生产操作指令，"
                        msg += f"程序已经自动确认该设备是正常生产过的设备，但是他被更换了新的内存卡然后需要被重新发布。\n\n"

                        msg += f"请确认是否将SN为 {device_old_sn} 的 {device_old_type} 设备，重新生产为 {self.typ} 类型。"
                        if messagebox.askyesno("设备换卡重新发布警告！", msg):
                            logger.debug(
                                f"生产者同意将SN为 {device_old_sn} 的 {device_old_type} 设备，重新生产为 {self.typ} 类型。")
                            # 生产者同意修改版本类型，我们在此处操作修改数据库！
                            # 虽然能修改版本类型，但是我们还是需要确认生产者有没有使用了正确的硬件版本信息，如果错了的话，后果很严重
                            is_hw_major_same = device_old_infos['hw_version_main'] == self.ver['major']
                            is_hw_minor_same = device_old_infos['hw_version_sub'] == self.ver['minor']
                            if is_hw_major_same and is_hw_minor_same:
                                # 硬件版本一样，我们可以更新数据库中的信息！
                                result = data_control.update_device_type_for_sn(device_old_sn,
                                                                                self.get_device_type_int())
                                if result:
                                    logger.debug("更新成功！")
                                else:
                                    raise Exception("更新失败，请联系开发者检测数据库是否异常！")
                            else:
                                hvm = device_old_infos['hw_version_main']
                                hvs = device_old_infos['hw_version_sub']
                                # 硬件版本不一样，我们需要拒绝这个生产操作，并且警告生产者
                                msg = f"您选择生产的PCBA版本是: {self.ver['major']}.{self.ver['minor']}\n"
                                msg += f"数据库中记录到该设备是: {hvm}.{hvs}\n"
                                msg += f"\n检测到两个PCBA版本不一致，这是致命问题！因此无法基于旧的记录自动更新，"
                                msg += f"如果你已经选择了PCBA上丝印的正确版本，但是数据库错误记录，请联系开发者解决此问题！"
                                msg += f"否则请退出生产，在版本选择页面选定指定版本的生产过程！！！"
                                messagebox.showerror("设备PCBA版本不一致错误！", msg)
                                logger.error("出现PCBA版本不一致的错误，拒绝生产此设备！")
                                return
                        else:
                            logger.debug(
                                f"生产者拒绝将SN为 {device_old_sn} 的 {device_old_type} 设备，重新生产为 {self.typ} 类型。")
                            return
                    else:
                        logger.debug("两次生产的类型一致，默认使用旧的数据库信息进行生产！")
                else:
                    logger.debug(f"云端检查设备历史信息结果为空，该设备需要全新入库")
                    # 信息是空的，说明该设备没有入库过，我们在此处进行入库
                    state = data_control.save_info(
                        infos,  # 信息字典，单个关键信息
                        self.get_device_type_int(),  # 当前的设备的类型，整形int
                        self.ver['major'], self.ver['minor']  # 根据传入的版本信息入库
                    )
                    if not state:
                        logger.debug("信息入库失败，请开发者检查上述错误。")
                        return
                    else:
                        logger.debug("信息入库成功，开始获取SN等相关信息。")

                # 获取SN
                sn = data_control.get_sn_for_device_info(infos)
                if sn is None or len(sn) <= 0:
                    logger.debug("SN查询失败，这个是个很严重的问题，请检查上面有没有出现异常信息！！！")
                    return
                else:
                    logger.debug("SN查询成功，接下来将进行SN上报到设备...")

                # 入库成功后，设备会创建一个SN信息文件在U盘中，
                # 并且创建成功后，设备的从机模式会切换，串口会重启，我们需要处理这个问题
                # 此时我们需要询问，他们是否有创建了，没有的话需要创建，已经创建的话就可以继续下面的步骤了
                if "OK" in self.sendMsg2Port(dev, f"SN_SAVE:{sn}", True):
                    # 返回值是OK的时候，说明保存成功了，也就是说会重启串口设备，此时我们可以直接跳过接下来的操作，
                    # 等待设备上线，重新进入流程
                    logger.debug("保存SN到设备的U盘目录成功，将会跳过接下来的任务创建，等待设备重新初始化。")
                    return

                logger.debug("SN已经上报成功，将会创建固件构建任务和标签构建任务...")

                logger.debug(f"正在根据SN重新查询入库的信息: {sn}")
                infos = data_control.get_row_from_database_for_sn(sn)
                if infos is None:
                    logger.debug("查询信息失败，数据可能入库异常了！")
                    return
                logger.debug(f"查询入库的信息成功，新的信息集合为: {infos}\n")

                # 进行信息缓存        设备信息  串口号
                self.sn_com_map[sn] = (infos, dev)
                # 然后我们需要将此设备加入标签粘贴的任务系统
                # 创建信息封包，加入标签队列
                self.queue_tag_make.put(sn, False)
                # 再把此设备加入到固件生产的任务系统
                # 将固件生成的任务加入到队列中，自动处理
                self.queue_fw_make.put(sn, False)
            except Exception as e:
                logger.debug(f"出现异常: {e}")

        # 往线程池里面提交任务
        # fix: 串口上线需要延迟8秒钟，让设备先初始化完成
        threading.Timer(8, lambda: self.threadPool.submit(run)).start()

    def remove_task_for_dev(self, dev):
        """
            根据设备信息移除生产任务
                如果有标签生产任务，则移除标签生产任务
                如果有固件生产任务，则移除固件生产任务
        :param dev:
        :return:
        """
        # TODO 待实现
        logger.debug("由于移除任务的实现比较复杂，暂不实现。")

    @staticmethod
    def parse_infos(infos):
        """
            解析信息组，返回三个信息
        :param infos:
        :return:
        """
        infos_g = str(infos).split(",")

        if len(infos_g) != 3:
            logger.debug(f"没有获取到正确的设备信息: {infos}")
            return None

        id_cpu = infos_g[0]
        id_pm3 = infos_g[1]
        id_stm32 = infos_g[2]

        if len(id_cpu) == 0 or len(id_pm3) == 0 or len(id_stm32) == 0:
            logger.debug(f"出现了空的信息 -> id_cpu:{id_cpu},id_pm3:{id_pm3},id_stm32:{id_stm32}")
            return None

        return {
            "id_cpu": id_cpu.strip(),
            "id_pm3": id_pm3.strip(),
            "id_stm32": id_stm32.strip(),
        }

    @staticmethod
    def is_tag_make_already(sn):
        """
            判断数据库中的标签制作是否已经入库！
            标签状态用第一位的值来操作！
        :return:
        """
        status = data_control.get_factory_status_for_sn(sn)
        return status & 1

    @staticmethod
    def set_tag_make_ok(sn):
        """
            设置数据库中的标签制作完成并且入库！
        :return:
        """
        status = data_control.get_factory_status_for_sn(sn)
        status |= 1
        data_control.update_factory_status_for_sn(sn, status)

    @staticmethod
    def is_fw_release_already(sn):
        """
            判断固件发布是否已经入库！
            固件状态用第二位的值来操作！
        :return:
        """
        status = data_control.get_factory_status_for_sn(sn)
        return status >> 1 & 1

    @staticmethod
    def set_fw_release_ok(sn):
        """
            设置固件发布完成并且入库！
        :return:
        """
        status = data_control.get_factory_status_for_sn(sn)
        status |= 2
        data_control.update_factory_status_for_sn(sn, status)

    def get_infos_for_device(self, dev):
        """
            从串口设备尝试获取信息，在一定的时间内
        :param dev:
        :return:
        """
        resp = self.sendMsg2Port(dev, "FAC_START", True)
        if resp is not None and isinstance(resp, str):
            resp = resp.strip()
        # logger.debug(f"接收到的信息数据应答: {resp}")
        return resp

    def make_ipk_for_infos(self, infos):
        """
            使用信息进行固件制作
        :param infos:
        :return:
        """
        # 使用数据库中对应的版本信息
        typ_for_database = icopy_maps.get_device_type_str(infos['type'])
        if typ_for_database is None:
            raise Exception("make_ipk_for_infos异常，无法将数据库中的版本码信息对应到设备类型字符串。")
        return make_impl.make_ipk_for_infos(typ_for_database, infos)

    @staticmethod
    def delete_ipk_for_path(path):
        """
            删除某个目录下的所有ipk文件！
        :param path:
        :return:
        """
        try:
            for ipk_file_history in os.listdir(path):
                if ipk_file_history.endswith(".ipk"):
                    ipk_file_history_file = os.path.join(path, ipk_file_history)
                    if os.path.isfile(ipk_file_history_file):
                        os.remove(ipk_file_history_file)
        except:
            pass

    def send_file_to_upan(self, com, ipk_file, sn, start_msg=b"IPK_START\r\n"):
        """
            发送文件到串口
        :param sn:
        :param start_msg:
        :param com:
        :param ipk_file:
        :return:
        """
        try:
            logger.debug("开始复制IPK文件到U盘...")
            can_start = False
            try:
                for device in psutil.disk_partitions():
                    # logger.debug(f"当前的盘符: {device.device}")
                    # 先判断哪个盘有SN文件
                    sn_file = os.path.join(device.device, f"sn=={sn}.txt")
                    if os.path.exists(sn_file):
                        # 还要深入判断此目录下是否有ipk文件，有的话要先删除！
                        self.delete_ipk_for_path(device.device)
                        # 删除完成后，我们需要移动新的ipk到U盘目录下！
                        target_file = os.path.join(device.device, f"{sn.lower()}.ipk")
                        shutil.copyfile(ipk_file, target_file)
                        # 移动完成后，我们需要删除源文件与标志文件！
                        os.remove(sn_file)
                        os.remove(ipk_file)
                        can_start = True
                        break
            except Exception as e:
                logger.debug(f"移动{sn}的固件的时候出现了异常: ", e)
            if can_start:
                # 传输完成之后，我们需要进行通知关闭复合设备
                self.sendMsg2Port(com, start_msg)
                logger.debug("复制IPK文件完成，已通知设备端开始更新固件。\n")
                return True
        except Exception as e:
            logger.debug(f"send_file_to_com(): {e}")
            return False

    def make_ipk_release(self, sn, ipk_file):
        """
            进行最终的ipk下发操作，
            此处应当调用串口进行IO，传输文件
        :param ipk_file:
        :param sn:
        :return:
        """
        try:
            # 先取出信息封包
            item = self.sn_com_map[sn]
            # 再把串口信息取出来
            port = item[1]
            return self.send_file_to_upan(port, ipk_file, sn)
        except Exception as e:
            logger.debug(f"下发固件的过程中出现了异常: {e}")
            return False

    @staticmethod
    def serial_number_print(sn, bmp=False):
        """
            序列号打印！
        :return:
        """
        logger.debug(f"开始打印标签: {sn}")
        result = None
        try:
            s = socket.socket()
            t = s.gettimeout()
            s.settimeout(3)
            s.connect(("127.0.0.1", 2000))
            s.settimeout(t)
            s.sendall(f"{'show' if bmp else 'print'}:{sn}".encode())
            s.setblocking(False)  # 设置非阻塞编程

            start_time = time.time()
            while True:
                if time.time() - start_time > 25:
                    raise Exception("等待打印机控制程序回复超时！")

                in_fds, out_fds, err_fds = select.select([s, ], [], [], 0)
                if len(in_fds) == 0:
                    time.sleep(0.01)
                    continue

                result = s.recv(1024)
                if b'notok' in result:
                    raise Exception("打印机控制程序报告失败！")
                break

        except Exception as e:
            msg = f"打印超时或出错，请查看打印机是否连接，并且确保打印机舱门已关闭，错误信息：{e}"
            messagebox.showerror("警告！", msg)

        logger.debug("标签打印结束")

        return result

    @staticmethod
    def searchCOM():
        """
            搜索可用的手持机串口
        :return:
        """
        # """
        #     串口名: COM33
        #     设备信息: USB VID:PID=1D6B:0106 SER=9
        # """
        port_list = list(serial.tools.list_ports.comports())
        ret_list = list()
        if len(port_list) == 0:
            # logger.debug('找不到串口')
            pass
        else:
            for i in range(0, len(port_list)):
                port = port_list[i]
                # logger.debug(f"串口名: {port.device}\n设备信息: {port.usb_info()}\n")
                vid_hex = "{:04X}".format(port.vid or 0)
                pid_hex = "{:04X}".format(port.pid or 0)
                # 复合设备的USB ID
                if vid_hex == "1D6B" and pid_hex == "0106" and len(port.device) > 0:
                    # logger.debug(f"发现手持机串口设备：{port.hwid}")
                    ret_list.append(port.device)
                # 单串口设备模拟时的USB ID
                # VID 0525     PID A4A7
                if vid_hex == "0525" and pid_hex == "A4A7" and len(port.device) > 0:
                    # logger.debug(f"发现手持机串口设备：{port.hwid}")
                    ret_list.append(port.device)
        return ret_list

    def on_exit(self):
        count = self.var_device_count.get()
        if count > 0:
            msg = f"当前电脑插着{count}个手持机，为了生产安全，不允许结束生产程序，请确认生产完毕后，移除所有的手持机再关闭软件！"
            messagebox.showwarning("警告", msg)
        else:
            logger.debug("申请退出生产！")
            self.destroy()
            os._exit(0)


class MainGui:
    """
        负责开始绘制主要的GUI
    """

    def __init__(self):
        self.init_window_main()

        self.color_layout_bg = "#696969"
        self.color_disable_fg = "#9C9C9C"
        self.color_text_fg = "white"

        self.tk['bg'] = self.color_layout_bg

        self.text_input_sn = None
        self.list_box_type = None

        self.btn_start = Button(
            self.tk,
            text="启动任务",
            font=("Consolas", 14,),
            bg=self.color_layout_bg,
            fg=self.color_text_fg,
        )

    def init_window_main(self):
        """
            初始化主页面的控件
        :return:
        """
        self.tk = Tk()
        self.tk.title("ICopy量产工具（由DXL强力驱动）")
        self.tk.geometry("512x512")
        self.tk.resizable(False, False)

    def init_default_style(self, window):
        """
            初始化默认的UI风格属性
        :return:
        """
        for child in window.winfo_children():
            try:
                # logger.debug(child.keys())
                if "disabledforeground" in child.keys():
                    child['disabledforeground'] = self.color_disable_fg

                if child.widgetName == 'frame' or child.widgetName == 'labelframe':
                    self.init_default_style(child)

            except Exception as e:
                # logger.debug(e)
                pass

    def icopy_type_wrong(self, msg):
        """
            显示icopy确认类型错误的消息
        :param msg:
        :return:
        """
        if msg is None:
            pass
        else:
            messagebox.showerror("确认类型失败！！！", f"您在确认生产类型的时候出现了异常，您的输入: {msg}")

    def confirm_version_and_go_product(self, typ):
        """
            确认版本再生产
        :param typ:
        :return:
        """
        # 创建对话框提示选择生产版本号
        ver_select_dialog = VerSelectGUI(self.tk)
        ver = ver_select_dialog.wait_get_selected()
        if ver is None:
            logger.debug("生产者取消选择，不进入下一步操作！")
        else:
            self.tk.destroy()
            FactoryGUI(typ, ver).mainloop()

    def start_production_and_exit_main(self, typ):
        """
            进入生产页面，并且关闭当前的主页面！
        :return:
        """
        msg = f"您将要开始生产 {typ} 类型的设备，您确认吗？\n确认请输入(大小写不敏感) {typ}"
        r: str = simpledialog.askstring("请确认您的生产操作！！！", msg)
        logger.debug(f"用户输入的值: {r}")
        if r is not None and len(r) > 0 and r.upper() != typ.upper():
            self.icopy_type_wrong(r)
            return
        elif r is None or len(r) == 0:
            logger.debug("取消了操作")
            return
        else:
            self.confirm_version_and_go_product(typ)
        return

    def btn_make_for_sn_onclick(self):
        """
            在需要生成指定的SN的设备的固件时
        :return:
        """
        # 先获得用户输入的SN
        str_input: str = self.text_input_sn.get("0.0", END).strip()

        str_input_arr = str_input.split(",")
        logger.debug(f"输入了SN: {str_input_arr}")

        for str_input in str_input_arr:
            str_input = str_input.strip()
            if len(str_input) == 0:
                continue
            if len(str_input) != 8:
                msg = "您有输入的SN不足8位，请检查您的输入。（标准的SN前4位是距离20210101到目前的天数，后四位是生产批次。）"
                messagebox.showerror("警告！", msg)
                return

        msg = f"确认开始生产固件吗？"
        r = messagebox.askyesno("请确认您的生产操作！！！", msg)
        if r:
            for str_input in str_input_arr:
                str_input = str_input.strip()
                if len(str_input) == 0:
                    continue

                logger.debug("开始查询数据库中的信息: ")
                infos = data_control.get_row_from_database_for_sn(str_input)
                logger.debug(f"获取到的信息: {infos}")
                if infos is None:
                    messagebox.showerror("警告！", f"未查询到与SN: {str_input} 的信息有关的设备。")
                else:
                    logger.debug("有合适的信息行，将会开始进行生产该固件...")
                    threading.Thread(
                        target=self.run_on_make_fw_for_sn,
                        args=(infos, str_input,)
                    ).start()
        else:
            logger.debug("取消了生产操作！")

    def run_on_make_fw_for_sn(self, infos, sn_str: str):
        """
            进行固件生产
        :return:
        """
        try:
            # 创建UI
            frame = Frame(self.tk)
            frame.place(x=48, y=448)

            p_bar = Progressbar(frame, length=250, mode="indeterminate")
            p_bar.grid()
            p_bar.start()
            Label(frame, text="正在生产中，请尽量不要做任何操作......").grid()

            self.btn_start['state'] = DISABLED
            # 开始生产
            file = make_impl.make_ipk_for_infos(
                icopy_maps.get_device_type_str(infos["type"]),
                infos,
            )

            if file is None:
                frame.destroy()
                messagebox.showerror("警告！", f"SN为 `{sn_str}` 的设备生产升级固件失败！")
                return

            file_suffix = os.path.splitext(file)[-1]
            new_name = os.path.join(
                os.path.dirname(file),  # 路径
                f"{sn_str}_{int(time.time())}{file_suffix}"  # 文件名
            )
            os.rename(file, new_name)
            # 在目录中显示文件
            os.startfile(os.path.dirname(file))
            frame.destroy()
            logger.debug(f"生产完成，文件: {file}")
        finally:
            self.btn_start['state'] = NORMAL

    def draw_factory_ui(self, left_frame, right_frame, text, get_right_content, on_start_click):
        """
            绘制出厂按钮
        :param on_start_click:
        :param get_right_content:
        :param right_frame:
        :param left_frame:
        :param text:
        :return:
        """
        btn_mode = Button(
            left_frame,
            text=text,
            font=("Consolas", 14,),
            bg=self.color_layout_bg,
            fg=self.color_text_fg,
        )
        btn_mode.grid(padx=6, pady=6)
        btn_mode.on_start_click = on_start_click

        if callable(get_right_content):
            content_frame = get_right_content(right_frame)
        else:
            content_frame = None

        arrow_focus = '  >>'

        def run_click():
            if content_frame is not None:
                # 先隐藏所有的，其他的控件
                for child_frame in right_frame.winfo_children():
                    name = child_frame.widgetName
                    if name in ['frame', 'labelframe', 'canvas']:
                        child_frame.grid_forget()

                # 然后还需要重置按钮的文本
                for child_btn in left_frame.winfo_children():
                    name = child_btn.widgetName
                    if name in ['button']:
                        child_btn['text'] = str(child_btn['text']).rstrip(arrow_focus)

                # 然后再显示自己
                btn_mode['text'] += arrow_focus
                content_frame.grid()

                # 然后显示最终的启动按钮
                if btn_mode.on_start_click is None:
                    fun_click = NONE
                else:
                    fun_click = btn_mode.on_start_click

                self.btn_start['command'] = fun_click
                self.btn_start.place(x=408, y=448)

        btn_mode['command'] = run_click

    def get_sn_input_ui(self, frame):
        """
            绘制SN输入的用户接口！
        :return:
        """
        frame = LabelFrame(
            frame,
            text="请输入目标机器的SN，\n批量以逗号分割: ",
            font=("Consolas", 12,),
            bg=self.color_layout_bg,
            fg=self.color_text_fg,
        )
        # frame.grid(padx=6, pady=6)

        self.text_input_sn = Text(
            frame,
            font=("Consolas", 16,),
            width=24,
            height=4,
            wrap=WORD
        )
        self.text_input_sn.grid(row=0, column=0)

        return frame

    def get_msg_ui(self, frame, msg):
        """
            绘制提示信息的页面！
        :return:
        """
        frame = LabelFrame(
            frame,
            text="模式信息:",
            font=("Consolas", 16,),
            bg=self.color_layout_bg,
            fg=self.color_text_fg,
        )

        Label(
            frame,
            font=("Consolas", 12,),
            bg=self.color_layout_bg,
            fg=self.color_text_fg,
            text=msg,
        ).grid(row=0, column=0)

        return frame

    def draw_main(self):
        """
            绘制主页的布局
        :return:
        """
        left_frame = LabelFrame(
            self.tk,
            text="量产模式：",
            font=("Consolas", 14,),
            bg=self.color_layout_bg,
            fg=self.color_text_fg,
        )
        left_frame.grid(padx=6, pady=6, row=0, column=0)

        right_frame = Frame(
            self.tk,
            bg=self.color_layout_bg,
        )
        right_frame.grid(padx=6, pady=6, row=0, column=1)

        # 写死一个菜单项目，这个项目用于生产已经存在于数据库中的设备的固件
        # 可以使用此菜单项目进行固件更新
        self.draw_factory_ui(left_frame, right_frame, "出厂固件更新", self.get_sn_input_ui,
                             self.btn_make_for_sn_onclick)

        # 从此处开始，动态生成菜单项目，根据映射表中的定义
        for typ in icopy_maps.TYPE_TO_NAME_MAPS:
            typ = icopy_maps.TYPE_TO_NAME_MAPS[typ]
            msg = f"生产 {typ} 专用固件，\n\n请注意，请确保您选择的类型\n\n匹配您的生产需求！"

            def run_go_fac(type_str=typ):
                return self.start_production_and_exit_main(type_str)

            def run_msg_gui(frame):
                return self.get_msg_ui(frame, msg)

            self.draw_factory_ui(left_frame, right_frame, typ, run_msg_gui, run_go_fac)

        self.get_msg_ui(
            right_frame,
            "你好，欢迎使用ICopy量产工具！\n请选择您的量产模式，然后按照指引开始量产。"
        ).grid()

    def start_gui(self):
        self.draw_main()
        self.init_default_style(self.tk)
        self.tk.mainloop()


if __name__ == '__main__':
    main_gui = MainGui()
    main_gui.start_gui()
