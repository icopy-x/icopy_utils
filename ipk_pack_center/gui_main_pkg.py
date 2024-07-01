"""
    多线程打包器，负责打包
"""

import re
import os
import hashlib
import logging
import subprocess
import threading
import time

from concurrent.futures.thread import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
from flask import Flask, request, current_app

import app_generator
import icopy_maps


class AtomInt(object):

    def __init__(self, value=None):
        self.value = value
        self.lock = threading.RLock()

    def get(self):
        with self.lock:
            return self.value

    def set(self, value):
        with self.lock:
            self.value = value

    def increment(self):
        with self.lock:
            self.value += 1

    def decrement(self):
        with self.lock:
            self.value -= 1


# 存放项目的仓库的信息
PROJECT_GIT_PROTOCOL = "https://"
PROJECT_APP_GIT_URL = "github.com/icopy-x/icopy_app.git"
PROJECT_DEP_GIT_URL = "github.com/icopy-x/icopy_dep_res.git"
PROJECT_GIT_PWD = "password"
PROJECT_GIT_USR = f"user"

# 我们默认使用工厂仓库进行生产
BRANCH_NAME = "factory"

# 提供服务需要使用到的一些参数
ADDR = "127.0.0.1"
PORT = "7878"

# 定义一些路径变量
PROJECT_BUILD_PATH = os.path.join(os.path.expanduser('~'), "Desktop", "icopy_build", BRANCH_NAME)
PROJECT_APP_SOURCE_PATH = os.path.join(PROJECT_BUILD_PATH, "app")
PROJECT_APP_OUTPUT_PATH = os.path.join(PROJECT_BUILD_PATH, "ipk")
PROJECT_STD_APPPKG_BASE = os.path.join(PROJECT_BUILD_PATH, "std")
PROJECT_DEP_SOURCE_PATH = os.path.join(PROJECT_BUILD_PATH, "dep")
PROJECT_STD_APPPKG_NAME = "icopy_std_pkg.ipk"
PROJECT_STD_APPPKG_PATH = os.path.join(PROJECT_STD_APPPKG_BASE, PROJECT_STD_APPPKG_NAME)

# 克隆APP仓库使用的指令
PROJECT_APP_CLONE_CMD = "git clone {}{}:{}@{} {}".format(
    PROJECT_GIT_PROTOCOL,
    PROJECT_GIT_USR,
    PROJECT_GIT_PWD,
    PROJECT_APP_GIT_URL,
    PROJECT_APP_SOURCE_PATH
)

# 克隆DEP仓库使用的指令
PROJECT_DEP_CLONE_CMD = "git clone {}{}:{}@{} {}".format(
    PROJECT_GIT_PROTOCOL,
    PROJECT_GIT_USR,
    PROJECT_GIT_PWD,
    PROJECT_DEP_GIT_URL,
    PROJECT_DEP_SOURCE_PATH
)

# 任务的状态变量
TASK_MAX = AtomInt(value=os.cpu_count() * 5)
TASK_COUNT = AtomInt(value=0)

# 仓库更新
GIT_UPDATING_LOCK = threading.RLock()
GIT_UPDATING = False

# 任务队列
QUEUE_TASK = Queue()
# 线程池，用于分配子编译任务
POOL_TASK = ThreadPoolExecutor(max_workers=TASK_MAX.get())
# 任务对象列表
STATE_LIST = dict()

# 锁
ADD_TASK_LOCK = threading.RLock()

# HTTP服务
FLASK_APP = Flask(__name__)

logging.basicConfig(level=logging.NOTSET, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)


def set_git_updating(updating):
    global GIT_UPDATING
    with GIT_UPDATING_LOCK:
        GIT_UPDATING = updating


def is_git_updating():
    with GIT_UPDATING_LOCK:
        return GIT_UPDATING


def get_output(cmd, cwd=PROJECT_APP_SOURCE_PATH) -> str:
    """
        运行一个指令然后获得它的结果输出
    :param cwd:
    :param cmd:
    :return:
    """
    # 执行指令，并且获得执行结果
    process = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        cwd=cwd,
    )
    # 获得程序输出的结果，并且去掉前后的空白字符
    result_stdout = process.stdout.decode().strip()
    result_stderr = process.stderr.decode().strip()
    return result_stdout + result_stderr


def is_app_git_exists():
    """
        判断APP资源是否存在
    :return:
    """
    return len(os.listdir(PROJECT_APP_SOURCE_PATH)) > 0


def is_dep_git_exists():
    """
        判断依赖资源是否存在
    :return:
    """
    return len(os.listdir(PROJECT_DEP_SOURCE_PATH)) > 0


def clone_resource_from_git():
    """
        从云端克隆项目下来
    :return:
    """
    # 自动拉取APP资源
    if is_app_git_exists():
        print("APP资源已经存在: ", PROJECT_APP_SOURCE_PATH)
    else:
        print("APP资源不存在，将自动拉取......")
        get_output(PROJECT_APP_CLONE_CMD, cwd=".")
        print("APP资源拉取成功")

    # 自动拉取依赖资源
    if is_dep_git_exists():
        print("依赖资源已经存在: ", PROJECT_DEP_SOURCE_PATH)
    else:
        print("依赖资源不存在，将自动拉取......")
        get_output(PROJECT_DEP_CLONE_CMD, cwd=".")
        print("依赖资源拉取成功")

    return


def parse_log(output: str):
    """
        解析日志
        commit 104f11e178e18003e486b4e58b27f295d212e4ae
        Author: dxl <64101226@qq.com>
        Date:   Thu Feb 25 11:09:52 2021 +0800

            修改了模块名。
    :param output:
    :return:
    """
    output = output.strip()

    ret = {}

    try:
        hash_sea_obj = re.search(r"hash=(.*)", output)
        author_sea_obj = re.search(r"author=(.*)", output)
        date_sea_obj = re.search(r"date=(.*)", output)
        commit_sea_obj = re.search(r"commit=(.*)", output)

        ret['hash'] = hash_sea_obj[1]
        ret['commit'] = commit_sea_obj[1]
        ret['author'] = author_sea_obj[1]
        ret['date'] = date_sea_obj[1]
    except Exception as e:
        LOGGER.error(f"无法解析git日志: {output} \n 异常是: {e}")
        return None

    return ret


def switch_app_to_default_branch():
    """
        切换到发布版本的分支
    :return:
    """
    can_switch = True
    result = get_output("git branch")
    for line in result.split('\n'):
        if line.startswith('*') and BRANCH_NAME in line:
            can_switch = False
            break
    if can_switch:
        # print("\n正在切换到发布版本的分支...")
        get_output(f"git checkout {BRANCH_NAME}")
        # print("切换成功。\n")


def create_log_cmd(ref, index="-1"):
    """
        根据指定的ref创建日志组
    :param index: 要显示的日志条目索引
    :param ref:  要显示的日志的引用
    :return:
    """
    pretty = '--pretty=format:"# Log begin # %n hash=%H %n author=%an %n date=%ai %n commit=%s %n# Log end #%n"'
    return f'git log {pretty} {ref} {index}'.strip()


def get_log(ref, index="-1"):
    """
        根据索引获取日志
    :param ref:
    :param index:
    :return:
    """
    return parse_log(get_output(create_log_cmd(ref, index)))


def branch_has_update():
    """
        分支中是否有内容可以更新
    :return:
    """
    # 检测云端仓库的标签
    # git ls-remote --refs --tags origin

    # 确保切换到此分支
    switch_app_to_default_branch()

    # 下拉云端的最新更新记录
    fetch_cmd = f"git fetch origin {BRANCH_NAME}"
    get_output(fetch_cmd)

    # 获得更新信息
    result_cloud = get_log("FETCH_HEAD")
    if result_cloud is None:
        return False

    result_local = get_log("")
    if result_local is None:
        return False

    return result_cloud.get('commit') != result_local.get('commit')


def resource_update():
    """
        更新项目到最新提交的代码
        注：将会从release分支拉取
    :return:
    """
    # 需要先等待所有的任务都结束
    # 我们才能进入更新状态，避免用户被终止更新
    while TASK_COUNT.get() != 0:
        time.sleep(2)
        # LOGGER.info("正在等待所有的任务完成，完成后自动更新仓库...")

    set_git_updating(True)

    # 自动拉取依赖仓库的更新
    # 由于依赖仓库是可以直接更新的，不需要担心云端覆盖代码导致
    get_output("git pull", PROJECT_DEP_SOURCE_PATH)

    switch_app_to_default_branch()
    if branch_has_update():
        # 1、自动合并更新代码
        # 2、在代码有更新之后，我们需要进行新的ipk包的制作，避免使用了旧的IPK资源
        LOGGER.warning("\n正在更新合并代码...")
        get_output("git merge FETCH_HEAD")
        start_make_std_pkg()
        LOGGER.warning("合并完成！！！")

    set_git_updating(False)


def get_md5_for_data(databyte):
    myhash = hashlib.md5()
    myhash.update(databyte)
    return myhash.hexdigest()


def run_pkg_task():
    """
        实际上的编译器编译实现的过程
    :return:
    """
    while True:
        task: dict = QUEUE_TASK.get()

        # 此处我们需要判断是否有在更新，有在更新的话需要等待更新结束！
        while is_git_updating():
            LOGGER.warning("正在更新仓库，生产暂停中，稍后自动开启...")
            time.sleep(1)

        task_code = task['code']  # 任务的唯一标志码
        device_typ = task['type']  # 设备的软件区分类型

        # 获得映射的实体类
        clz_icopy = icopy_maps.getICopyClz4Name(device_typ)

        if clz_icopy is None:
            raise Exception("无法获得设备类型名称到具体类的映射。")

        # 建立对象
        obj_icopy = clz_icopy(task)

        # 提交一个任务到线程池
        STATE_LIST[task_code] = POOL_TASK.submit(
            # 将执行的打包处理函数
            app_generator.make_app_package,

            # 参数
            PROJECT_APP_SOURCE_PATH,  # 项目所在的目录
            PROJECT_DEP_SOURCE_PATH,  # 项目的依赖项所在的目录
            PROJECT_APP_OUTPUT_PATH,  # 项目编译后的输出目录
            PROJECT_STD_APPPKG_PATH,  # 标准规范包的路径
            obj_icopy,  # 需要被编译打包的固件类型实现类
        )
        # 在任务完成后自减计数
        STATE_LIST[task_code].add_done_callback(
            lambda x: TASK_COUNT.decrement()
        )

        # 当前任务计数递增
        TASK_COUNT.increment()

        # 设置队列任务完成标志位
        QUEUE_TASK.task_done()


def start_flask_api():
    """
        启动flask以提供api功能
    :return:
    """

    def run():
        # 关闭我们不需要的某些日志
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("urllib3").propagate = False
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        logging.getLogger("urllib").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)

        FLASK_APP.jinja_env.auto_reload = True
        FLASK_APP.config['TEMPLATES_AUTO_RELOAD'] = True
        FLASK_APP.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(seconds=1)
        FLASK_APP.run(host=ADDR, port=PORT, debug=False)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def run_res_update():
    """
        启动资源更新自动检查的线程
    :return:
    """
    while True:
        time.sleep(8)
        if is_git_updating():
            continue
        resource_update()
    return


def start_pkg_queue_loop():
    """
        启动打包生成队列轮询
    :return:
    """
    thread = threading.Thread(target=run_pkg_task)
    thread.start()

    return thread


def start_check_update():
    """
        检测代码更新
    :return:
    """
    thread = threading.Thread(target=run_res_update)
    thread.start()

    return thread


def start_make_repo_clone():
    """
        确保项目存在
    :return:
    """
    clone_resource_from_git()
    switch_app_to_default_branch()


def start_make_std_pkg():
    """
        先确保已经制作好标准的包
    :return:
    """
    if not os.path.exists(PROJECT_STD_APPPKG_BASE):
        os.makedirs(PROJECT_STD_APPPKG_BASE, exist_ok=True)

    make_success = app_generator.make_std_package(
        PROJECT_APP_SOURCE_PATH,
        PROJECT_STD_APPPKG_BASE,
        PROJECT_STD_APPPKG_NAME
    )
    if not make_success:
        raise Exception("无法构建有效的标准规范包！")


def make_path_exists(path):
    """
        确保目录存在
    :param path:
    :return:
    """
    if not os.path.exists(path):
        os.makedirs(path)


def start_pkg_app():
    """
        最终的提供打包服务的程序的启动入口
    :return:
    """
    make_path_exists(PROJECT_BUILD_PATH)
    make_path_exists(PROJECT_APP_SOURCE_PATH)
    make_path_exists(PROJECT_DEP_SOURCE_PATH)
    make_path_exists(PROJECT_APP_OUTPUT_PATH)
    make_path_exists(PROJECT_STD_APPPKG_BASE)

    # 先从仓库克隆手持机资源
    start_make_repo_clone()
    # 然后检查资源更新
    resource_update()
    # 然后构建标准包
    start_make_std_pkg()
    # 启动打包器任务轮询队列
    # 此时进行一些构建任务了
    start_pkg_queue_loop()
    # 启动flask的监听线程
    # flask完全工作之后，就可以通过API进行任务创建了
    start_flask_api()
    # 启动自动检查git资源更新的线程
    start_check_update()


@FLASK_APP.route("/max")
def flask_api_task_max():
    """
        得到当前的任务的上限数
    :return:
    """
    return str(TASK_MAX.get())


@FLASK_APP.route("/count")
def flask_api_task_count():
    """
        当前在运行的任务计数
    :return:
    """
    return str(TASK_COUNT.get())


@FLASK_APP.route("/add", methods=['GET', 'POST'])
def flask_api_add_task():
    """
        添加一个任务到列表中
    :return:
    """
    if request.method == "GET":  # 测试提交任务的页面
        return "不支持的操作"

    if request.method == "POST":
        with ADD_TASK_LOCK:
            values = request.values
            valstr = ','.join(list(values.values()))
            code = get_md5_for_data(valstr.encode())

            if code in STATE_LIST:  # 先判断有没有重复的任务存在
                return code

        # 获得用户输入的欲构建的包的类型
        typ = values['type']
        if typ not in icopy_maps.TYPE_TO_CLZ_MAPS:
            return f"只支持: {','.join(icopy_maps.TYPE_TO_CLZ_MAPS.keys())} 这几种设备版本类型。"

        # 创建一个缓存信息的对象
        values_new = dict(values)
        # 添加一个UUID用于标志当前的任务
        values_new['code'] = code
        # 提交任务
        QUEUE_TASK.put(values_new)
        # 缓存任务
        LOGGER.info(f"将进行生产过程的数据: {values_new}")

        return code


@FLASK_APP.route("/progress")
def flask_api_progress():
    """
        获取一个任务的进度
    :return:
    """
    # TODO 待实现


@FLASK_APP.route("/ok")
def flask_api_ok():
    """
        获取一个任务的进度
    :return:
    """
    if request.method == 'GET':
        if 'code' in request.values:
            code = request.values['code']
            if code in STATE_LIST:
                task = STATE_LIST[code]
                return str(task.done())
            else:
                return "unknown"
        else:
            return "noparam"
    return "notget"


@FLASK_APP.route("/download")
def flask_api_download():
    """
        下载一个已经构建成功的资源
    :return:
    """
    if request.method == 'GET':
        code = request.values['code']
        if code in STATE_LIST:
            task = STATE_LIST[code]
            file = task.result()

            if file is None or not os.path.exists(file):
                del STATE_LIST[code]
                return "failed"

            def generate():
                with open(file, mode='rb') as f:
                    yield from f
                try:
                    os.remove(file)
                except Exception as e:
                    print("自动移除文件失败: ", e)
                try:
                    del STATE_LIST[code]
                except Exception as e:
                    print("移除任务失败: ", e)

            r = current_app.response_class(generate(), mimetype='application/octet-stream')
            r.headers.set('Content-Disposition', 'attachment', filename=os.path.basename(file))
            return r
        else:
            return "unknown"
    return "不支持非GET请求查询"


if __name__ == '__main__':
    start_pkg_app()
