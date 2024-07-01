"""
    提供一个编译服务，并且简单的通过GUI进行控制
"""

import os
import hashlib
import json
import logging
import shutil
import tempfile
import threading
import time

import requests

from queue import Queue
from flask import Flask, request, send_file


class TaskQueue(Queue):
    """
        集合队列，不允许重复元素
    """

    def exists(self, code):
        # 如果非空，我们就需要判断当前是否有这个对象
        with self.not_empty:
            for item in self.queue:
                if code in item:
                    return True
            return False


TITLE = "ICopy-X 分布式编译集群服务端 by DXL"
FLASK_APP = Flask(__name__)

SIZE = "568x198"
ADDR = "0.0.0.0"
PORT = 5858
TIPS = f"""
    服务端提供了以POST和GET为基础的URL操作API
    
    {ADDR}:{PORT}/help -> 查询所有支持的API的帮助

    {ADDR}:{PORT}/busy -> 查询是否当前机器是否处于繁忙状态
                            (当前任务队列已经满了则是繁忙状态)

    {ADDR}:{PORT}/count -> 查询当前的任务计数

    {ADDR}:{PORT}/up -> 表单类型，向此url提交一个py文件，
                            将自动获取其MD5并且返回，
                            同时开启一个编译任务。

    {ADDR}:{PORT}/ok?code=MD5 -> 查询一个任务是否完成
                            将自动查询运行时的任务列表，如果未发现
                            将自动查询输出目录下是否有相同MD5的文件

    {ADDR}:{PORT}/down?code=MD5 -> 下载一个资源，
                            如果该资源已经完成处理
                            
                            
    {ADDR}:{PORT}/del?code=MD5 -> 删除一个资源，请注意并发使用文件的问题！
                   
""".strip()

UPLOAD_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Title</title>
</head>
<body>
<form action="/up" method="post" enctype="multipart/form-data">
    <p><input type="file" name="file"></p>
    <input type="submit" value="upload">
</form>
</body>
</html>
"""

ROOT_PATH = "output"

VAR_COMPILER_TASK_COUNT_LOCK = threading.RLock()
VAR_COMPILER_TASK_COUNT = 0  # 当前在运行的任务个数

# 任务队列
QUEUE_TASK = TaskQueue()

# 存放当前编译状态的列表
STATE_LOCK = threading.RLock()
STATE_TASK = set()  # 操作状态列表时需要持有的锁

# 存放编译信息的配置文件
JSON_LOCK = threading.RLock()  # 操作json文件时需要持有的锁
PY_INFO_FILE = os.path.join(ROOT_PATH, "config", "py_file_map.json")
SETTING_FILE = os.path.join(ROOT_PATH, "config", "setting_map.json")
KEY_TASK_MAX = "task_max"
KEY_TOOLS_PATH = "tools_path"
KEY_UPLOAD_PATH = "upload_path"
KEY_OUTPUT_PATH = "output_path"
DEFAULT_PATH_TOOLS = os.path.join(ROOT_PATH, "arm-gcc")
DEFAULT_PATH_UPLOAD = os.path.join(ROOT_PATH, "upload")
DEFAULT_PATH_OUTPUT = os.path.join(ROOT_PATH, "build")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)


def make_sure_dir_exists(path):
    """
        确保目录存在
    :param path:
    :return:
    """
    try:
        if path is None or len(path) == 0:
            return

        if os.path.isfile(path):
            path = os.path.dirname(path)

        if not os.path.exists(path):
            os.makedirs(path)

        return os.path.exists(path)
    except Exception as e:
        LOGGER.info(str(e))
        return False


def get_kv_data(key, value=None, file=PY_INFO_FILE):
    """
        获取键值对数值
    :param file:
    :param key:
    :param value:
    :return:
    """
    make_sure_dir_exists(os.path.dirname(file))
    if os.path.exists(file):
        with JSON_LOCK:
            with open(file, 'r') as f:
                data = json.load(f)
                return data.get(key, value)
    return value


def save_kv_data(key, value, file=PY_INFO_FILE):
    """
        保存键值对数值
    :param file:
    :param key:
    :param value:
    :return:
    """
    try:
        with JSON_LOCK:  # 在锁中操作，确保不会被多线程影响
            # 先确保文件存在
            if not os.path.exists(file):
                with open(file, mode="w+"):
                    pass

            with open(file, mode="r") as fd:
                data = fd.read()

            with open(file, mode="w") as fd:
                try:
                    if len(data) != 0:
                        json_obj = json.loads(data)
                    else:
                        json_obj = {
                            key: value
                        }
                    if value is None:
                        if key in json_obj:
                            del json_obj[key]
                    else:
                        json_obj[key] = value
                except Exception as e:
                    LOGGER.info(f"保存键值对出现了小异常，将自动修复: {e}", )
                json.dump(json_obj, fd)
    except Exception as e:
        LOGGER.error(f"保存键值对异常: {e}")


VAR_COMPILER_MAX = get_kv_data(KEY_TASK_MAX, os.cpu_count(), SETTING_FILE)  # 编译器的运行时任务上限

VAR_COMPILER_PATH = get_kv_data(KEY_TOOLS_PATH, DEFAULT_PATH_TOOLS, SETTING_FILE)  # 编译器的目录

VAR_COMPILER_UPLOAD = get_kv_data(KEY_UPLOAD_PATH, DEFAULT_PATH_UPLOAD, SETTING_FILE)  # 上传到服务器的文件的保存目录
make_sure_dir_exists(VAR_COMPILER_UPLOAD)

VAR_COMPILER_OUTPUT = get_kv_data(KEY_OUTPUT_PATH, DEFAULT_PATH_OUTPUT, SETTING_FILE)  # 编译器的输出目录
make_sure_dir_exists(VAR_COMPILER_OUTPUT)


def is_cc_exists():
    """
        判断编译工具链在不在！
    :return:
    """
    toolchain_dir = os.path.abspath(VAR_COMPILER_PATH)
    bin_dir = os.path.join(toolchain_dir, "bin")
    cc = os.path.join(bin_dir, "arm-linux-gnueabihf-gcc.exe")
    return os.path.exists(cc)


def task_count_increment():
    with VAR_COMPILER_TASK_COUNT_LOCK:
        global VAR_COMPILER_TASK_COUNT
        VAR_COMPILER_TASK_COUNT += 1


def task_count_decrement():
    with VAR_COMPILER_TASK_COUNT_LOCK:
        global VAR_COMPILER_TASK_COUNT
        VAR_COMPILER_TASK_COUNT -= 1


def get_task_count():
    with VAR_COMPILER_TASK_COUNT_LOCK:
        global VAR_COMPILER_TASK_COUNT
        return VAR_COMPILER_TASK_COUNT


def start_flask_api():
    """
        启动flask以提供api功能
    :return:
    """

    # 关闭我们不需要的某些日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    FLASK_APP.run(host=ADDR, port=PORT, debug=False)


def get_md5_for_data(databyte):
    myhash = hashlib.md5()
    myhash.update(databyte)
    return myhash.hexdigest()


def create_md5_file_name(code, suffix=".so"):
    """
        生成一个以md5命名的文件名
    :param suffix:
    :param code:
    :return:
    """
    return f"md5_{code}{suffix}"


def get_upload_file(code, name=None):
    """
        获取文件存放的完整路径
    :param code:
    :param name:
    :return:
    """
    path = VAR_COMPILER_UPLOAD
    make_sure_dir_exists(path)
    if name is None:
        suffix = ".py"
    else:
        suffix = os.path.splitext(name)[-1]
    return os.path.join(
        path,  # 文件的路径
        create_md5_file_name(code, suffix)  # 文件名，我们以md5为名称，使用原本的后缀名
    )


def get_build_file(code):
    """
        获取文件存放的完整路径
    :param code:
    :return:
    """
    path = VAR_COMPILER_OUTPUT
    make_sure_dir_exists(path)
    return os.path.join(
        path,  # 文件的路径
        create_md5_file_name(code),  # 文件名，我们以md5为名称，使用原本的后缀名
    )


def is_upload_file_exists(code, name):
    """
        判断上传的文件是否存在
    :param code:
    :param name:
    :return:
    """
    if not os.path.exists(get_upload_file(code, name)):
        save_kv_data(code, None)
        return False
    return True


def is_build_file_exists(code):
    """
        判断构建的结果文件是否存在
    :param code:
    :return:
    """
    if not os.path.exists(get_build_file(code)):
        return False
    return True


def is_task_exists(code, name):
    """
        判断队列中是否存在相同任务或者历史构建记录中是否存在
    :param code:
    :param name:
    :return:
    """
    with STATE_LOCK:
        b0 = code in STATE_TASK  # 判断编译任务是否存在于编译过程中但是不存于编译队列中
        if b0:
            return True

    b1 = QUEUE_TASK.exists(code)
    b2 = get_kv_data(code, file=PY_INFO_FILE) is not None

    if b1:
        LOGGER.warning("任务已经存在于队列中。")
        return b1

    if b2:
        # 如果py文件已经存在于历史中，但是py或者so文件不存在，我们需要删除历史记录，并且告知上层调用
        if (b2 and
                (not is_upload_file_exists(code, name) or
                 not is_build_file_exists(code))):
            if not b1:  # 注意，如果so存在的话，那么b2的构建不是很重要，也就是说, py文件其实是可以删除的
                return False

        LOGGER.warning(f"任务已经存在于历史中: {code}")

    return b1 or b2


def compile2_c(file, target_path=None):
    """
        编译python文件为.c
    :param target_path:
    :param file:
    :return:
    """
    # """
    #     Cython.Compiler.Options.docstrings = False | -D
    #     Cython.Compiler.Options.emit_code_comments = False | -X emit_code_comments=False
    #     Cython.Compiler.Options.embed_pos_in_docstring = False | 不添加-p就是此效果
    # """
    name = os.path.splitext(os.path.basename(file))[0] + ".c"
    if target_path is not None:
        out_file = os.path.join(target_path, name)
    else:
        out_file = name
    # print("compile2C输出文件: ", out_file)
    # 移除旧的.c文件
    if os.path.exists(out_file):
        os.remove(out_file)

    # 这个实现会内存泄漏，具体原因未知，但我们无法继续使用此实现
    # ret = list()
    #
    # # 配置参数
    # Cython.Compiler.Options.docstrings = False
    # Cython.Compiler.Options.emit_code_comments = False
    # Cython.Compiler.Options.embed_pos_in_docstring = False
    # compiler_directives = {'optimize.unpack_method_calls': False, 'always_allow_keywords': True}
    #
    # # 开始生成
    # extensions = Cython.Build.cythonize(
    #     file,
    #     exclude=None,
    #     quiet=True,
    #     language_level=3,
    #     compiler_directives=compiler_directives,
    # )
    #
    # for mod in extensions:
    #     # 每次生成完毕后，移动文件到指定的目录下
    #     for source_file in mod.sources:
    #         name = os.path.basename(source_file)
    #         target_file = os.path.join(target_path, name)
    #         # LOGGER.info(f"构建完成，将会自动移动源文件: {file} 到 {target_path}")
    #         if os.path.exists(source_file) and not os.path.exists(target_file):
    #             ret.append(
    #                 shutil.move(
    #                     source_file,
    #                     target_path
    #                 )
    #             )
    #
    #         if os.path.exists(target_file):
    #             ret.append(target_file)
    # if len(ret) == 0:
    #     return None
    # if len(ret) == 1:
    #     return ret[0]
    # return ret

    final_cmd = 'cython -3 -D -X emit_code_comments=False {} -o {}'.format(file, out_file)
    # subprocess.run(
    #     cmd,
    #     shell=True,
    # )
    os.system(final_cmd)
    if os.path.exists(out_file) and (os.path.getsize(out_file) > 0):
        return out_file
    return None


def compile2_so(file, target_path=None):
    """
        将文件编译为.so
    :param file:
    :param target_path:
    :return:
    """

    # 首先需要配置环境
    toolchain_dir = os.path.abspath(VAR_COMPILER_PATH)
    bin_dir = os.path.join(toolchain_dir, "bin")

    cc = os.path.join(bin_dir, "arm-linux-gnueabihf-gcc.exe")

    if not os.path.exists(cc):
        raise Exception(f"你忘了设置GCC工具链目录，此服务端无法工作: {cc}")

    header_py = os.path.join(toolchain_dir, "include_py")
    header_inc = os.path.join(toolchain_dir, "arm-linux-gnueabihf", "libc", "usr", "include")
    header_sys = os.path.join(header_inc, "sys")
    # sysroot = toolchain_dir + r"arm-linux-gnueabihf\\libc"

    compile_cmd = cc + " -I{} -I{} -I{} -shared -pthread -fPIC -fwrapv -O3 -w -fno-strict-aliasing".format(
        header_inc,
        header_sys,
        header_py,
    )

    name = os.path.basename(file).split(".")[0]
    so_name = str(name) + ".so"

    if target_path is None:
        output = "-o {} {}".format(so_name, file)
    else:
        so_name = os.path.join(target_path, so_name)
        output = "-o {} {}".format(so_name, file)

    # 然后执行命令进行编译
    final_cmd = "{} {}".format(compile_cmd, output)
    # os.system(final_cmd) 不要使用这个函数，pyinstaller打包后执行指令时会出现黑框
    # subprocess.run(
    #     final_cmd,
    #     shell=True,
    # )
    os.system(final_cmd)
    return so_name


def build_impl(code, name, sources, so_target_path):
    """
        内部构建实现
    :return:
    """
    if sources.endswith("__init__.py"):
        # 不让编译init.py
        return

    # 确保文件夹存在
    if not os.path.exists(so_target_path):
        os.makedirs(so_target_path)

    # 使用临时文件夹进行编译
    with tempfile.TemporaryDirectory() as temp_path:
        # 第零，先移动资源到临时目录并且重命名
        sources = shutil.copyfile(sources, os.path.join(temp_path, name))
        # 第一，先编译该文件为.c
        csource = compile2_c(sources, temp_path)
        # 第二，编译该文件为.so
        ssource = compile2_so(csource, temp_path)
        # 第四，移动到指定的输出目录，以指定的文件名格式
        so_path = os.path.join(so_target_path, create_md5_file_name(code))
        if not os.path.exists(so_path):
            if ssource is not None:
                shutil.move(ssource, so_path)
        LOGGER.info(f"[+] 编译完成: {ssource} : {so_path}")

    with STATE_LOCK:
        if code in STATE_TASK:
            STATE_TASK.remove(code)

    task_count_decrement()


def run_compiler_task():
    """
        实际上的编译器编译实现的过程
    :return:
    """
    while True:
        task: dict = QUEUE_TASK.get()

        # 此处我们需要进行任务数量的限制
        if get_task_count() >= VAR_COMPILER_MAX:
            while get_task_count() >= VAR_COMPILER_MAX:
                time.sleep(0.5)

        LOGGER.info(f"开启一个信息的任务: {task}")

        for code in task.keys():
            name = task[code]
            file = get_upload_file(code, task[code])
            build_path = VAR_COMPILER_OUTPUT
            p = threading.Thread(
                target=build_impl,
                args=(
                    code,
                    name,
                    file,
                    build_path,
                )
            )
            p.start()

        # 当前任务计数递增
        task_count_increment()
        # 设置任务完成标志位
        QUEUE_TASK.task_done()


@FLASK_APP.route("/help")
def flask_api_help():
    return TIPS.replace("\n", "<br>")


@FLASK_APP.route("/online")
def flask_api_online():
    """
        判断服务是否在线
    :return:
    """
    return "yes"


@FLASK_APP.route("/busy")
def flask_api_busy():
    """
        返回当前的任务处理状态
    :return:
    """
    return str(get_task_count() == VAR_COMPILER_MAX)


@FLASK_APP.route("/count")
def flask_api_count():
    """
        返回当前的任务处理状态
    :return:
    """
    return str(get_task_count())


@FLASK_APP.route('/up', methods=['GET', 'POST'])
def flask_api_up():
    """
        接收上传的文件到服务器
    :return:
    """
    if request.method == 'POST':
        f = request.files['file']
        if f is not None:
            name = f.filename
            data = f.read()
            code = get_md5_for_data(data)
            kv = {code: name}

            # 判断一下当前是否已经存在相同的任务
            if is_task_exists(code, name):
                return code

            # 添加到任务状态列表记录中
            with STATE_LOCK:
                STATE_TASK.add(code)

            # 我们以md5为文件名，避免文件名冲突
            file = get_upload_file(code, name)

            with open(file, "wb+") as fd:  # 写入到磁盘进行保存
                fd.write(data)

            # 保存由md5码到原始文件名的唯一映射
            save_kv_data(code, name)
            # 然后提交一个编译任务
            QUEUE_TASK.put(kv)
            return code

    if request.method == 'GET':
        return UPLOAD_PAGE
    return "failed"


@FLASK_APP.route('/ok')
def flask_api_ok():
    """
        判断是否完成编译任务
    :return:
    """
    if request.method == "GET":
        code = request.values['code']
        return str(is_build_file_exists(code))
    return str(False)


@FLASK_APP.route('/down')
def flask_api_down():
    """
        判断是否完成编译任务
    :return:
    """
    if request.method == "GET":
        code = request.values['code']
        if is_build_file_exists(code):
            file = get_build_file(code)
            if file is not None:
                name = os.path.splitext(get_kv_data(code, "unknown"))[0]
                suffix = os.path.splitext(os.path.basename(file))[1]
                return send_file(file, as_attachment=True, attachment_filename=f"{name}{suffix}")
    return "failed"


@FLASK_APP.route('/del')
def flask_api_del():
    """
        删除一个md5对应的文件记录
    :return:
    """

    def del_if_exists(file):
        if file is not None and os.path.exists(file):
            os.remove(file)
            LOGGER.warning(f"删除文件成功: {file}")
            return True
        return False

    if request.method == "GET":
        code = request.values['code']
        file_so = get_build_file(code)
        file_py = get_upload_file(code)

        if del_if_exists(file_so) or del_if_exists(file_py):
            return "success"

    return "failed"


def start_queue_loop():
    """
        开启任务队列轮询
    :return:
    """
    thread = threading.Thread(target=run_compiler_task)
    thread.start()
    return thread


def icc_request(action):
    """
        向网域控制器注册自己
    :return:
    """
    url = f"http://127.0.0.1:6868/{action}"
    try:
        with requests.get(url) as result:
            return result.content.decode()
    except Exception as e:
        LOGGER.info(f"网域控制器请求失败: {e}")


def start_icc_register():
    """
        开启任务队列轮询
    :return:
    """

    def run_icc():
        # 进行ICC的注册，让打包器可以感知我们的存在
        while True:
            icc_request("online")
            time.sleep(1)

    thread = threading.Thread(target=run_icc)
    thread.start()
    return thread


def run_check_task():

    def run():
        while True:
            time.sleep(1)
            LOGGER.info("当前正在进行的的任务数量是: " + str(get_task_count()))

    threading.Thread(target=run).start()


def start_compiler():
    """
        启动该最终的GUI过程
    :return:
    """
    LOGGER.info(f"\n\n开发者请注意: {TIPS}\n\n")

    # 提醒部署者，GCC没有设置的问题！
    if not is_cc_exists():
        raise Exception("默认的GCC不存在，请确保后续设置GCC，否则此服务端将不可用！")

    start_icc_register()

    run_check_task()

    # 启动一些后台服务
    start_queue_loop()
    start_flask_api()


if __name__ == '__main__':
    start_compiler()
