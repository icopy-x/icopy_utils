import json
import os
import logging
import time
import uuid
import zipfile
import generator_utils

import concurrent.futures
from concurrent.futures.thread import ThreadPoolExecutor

from tempfile import NamedTemporaryFile, TemporaryDirectory

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)


def get_compiler_resp(addr, url, str_resp=True, method="", params=None):
    """
        获取来自编译服务器的回复
    :param params: 请求的附带参数
    :param method: 请求方法
    :param addr: 服务器地址
    :param url: 资源链接
    :param str_resp: 是否以文本形式的返回
    :return:
    """
    return generator_utils.get_server_resp(f"http://{addr}:5858/{url}", str_resp, method, params)


def is_ipv4_addr(ip_addr: str):
    """md
        检查ip是否合法
        :param: ip ip地址
        :return: True 合法 False 不合法
     """
    return True if [1] * 4 == [x.isdigit() and 0 <= int(x) <= 255 for x in ip_addr.split(".")] else False


def get_compiler_list():
    """
        获取在线的编译器的列表
    :return:
    """
    # print("开始请求获取当前的在线的编译服务器的列表......")
    # 我们需要请求网域控制器，查询当前可以用来编译的服务器
    resp: str = generator_utils.get_server_resp("http://127.0.0.1:6868/getlist")
    # LOGGER.info(f"服务器列表请求结果 {resp}")
    compiler_list = []
    for addr in resp.split(','):
        if is_ipv4_addr(addr):
            compiler_list.append(addr)

    return compiler_list


def build_2lib(source, so_target_path):
    """
        内部构建实现
    :return:
    """

    try:
        while True:  # 寻找已注册的空闲的服务器并且发起任务
            exit_loop = False
            task_addr = None
            md5_code = None
            compiler_list = get_compiler_list()

            if len(compiler_list) == 0:
                raise Exception("没有发现在线的编译服务器！！！")

            # 迭代所有的服务器，申请创建任务
            for addr in compiler_list:
                try:
                    # 先判断是否繁忙
                    busy_test = get_compiler_resp(addr, "busy")
                    if busy_test == "yes" or busy_test == "True":
                        continue

                    # 不繁忙的情况下，我们需要申请进行编译任务的创建
                    # print(f"选定了编译服务器: {addr} 编译: {source}")
                    md5 = generator_utils.upload_file(f"http://{addr}:5858/up", source)
                    if md5 is not None and md5 != "failed":
                        task_addr = addr
                        md5_code = md5
                        # 选定了之后，我们需要退出外部循环
                        exit_loop = True
                        # LOGGER.info(f"编译任务提交成功: {md5} : {source}")
                        break
                except Exception as e:
                    LOGGER.error(f"选定的编译服务器有异常: {e}")
                    compiler_list.remove(addr)  # 从列表中直接移除这个服务器
                    if len(compiler_list) == 0:
                        raise Exception(f"已经没有可以用来编译的服务器。")

            if exit_loop:
                break

            LOGGER.info(f"{source} 正在选择编译服务器...")

        while True:  # 查询任务是否编译完成
            # 任务已经创建，我们需要不停的问任务完成了没
            time.sleep(1)
            # LOGGER.info(f"目标为 {task_addr} 的机器， 任务{md5_code} 完成了没？")
            if get_compiler_resp(task_addr, f"ok?code={md5_code}") == "True":
                # print(f"编译完成，将自动下载到指定目录: {so_target_path}......")
                file_path = generator_utils.download_file(
                    # 下载链接
                    f"http://{task_addr}:5858/down?code={md5_code}",
                    # 在ipk中的相对目录
                    so_target_path,
                )
                # LOGGER.info(f"[+] 编译完成: {file_path}")
                break
            # print("没有哦。")
            time.sleep(2)

            LOGGER.info(f"{source} 正在进行编译...")

    except Exception as e:
        print("编译:", source, "时出现异常:", e)
        return None

    return file_path


def build_2libs(source_paths, so_path):
    """
        编译所有的py项目到指定的临时目录
    :param so_path: 存放最终的运行库的目录
    :param source_paths: 源文件路径
    :return:
    """
    # 确保文件夹存在
    for source_item in source_paths:
        if not os.path.exists(source_item):
            LOGGER.error(f"源代码文件不存在: {os.path.abspath(source_item)}")
            return False

    if not os.path.exists(so_path):
        os.makedirs(so_path)

    source_paths = list(filter(lambda item: not item.endswith("__init__.py"), source_paths))

    # 添加任务到线程池
    failed = False
    with ThreadPoolExecutor() as pool:
        # 提交并且生成任务列表
        task_list = [
            pool.submit(
                # 可执行对象
                build_2lib,

                # 参数
                source_item,
                so_path
            ) for source_item in source_paths
        ]
        # 已经完成的任务的列表
        done_list = []

        # 判断任务是否有失败的！
        while True:
            for task_item in task_list:
                # 这里需要严谨判断，仅在任务成功并且不在已经记录中的时候，才去验证结果！
                if task_item.done() and task_item not in done_list:
                    done_list.append(task_item)
                    result = task_item.result()

                    # 这里判断一下之前的任务是否已经失败过了，再判断当前任务是否失败了！
                    if result is None and not failed:
                        LOGGER.error(f"有构建任务失败！")
                        # 标志为失败
                        failed = True
                        # 然后我们需要取消剩下的任务，加速退出！
                        for cancel_task in task_list:
                            cancel_task.cancel()

            # 在所有的任务都完成后，我们才能结束任务！
            if len(done_list) == len(task_list):
                break

            # LOGGER.error(f"等待所有任务结束: {len(done_list)}, {len(task_list)}")

    return not failed


def gen_code_fun(py_file, generator, build_dir):
    """
        代码生成函数与保存函数
    :return:
    """
    os.makedirs(build_dir, exist_ok=True)
    # 读取文件
    with open(py_file, encoding='utf-8') as fd:
        py_content = fd.read()
    # 调用生成器生成代码
    new_py_content: str = generator.onGenerator(py_file, py_content)
    new_py_file = os.path.join(build_dir, os.path.basename(py_file))
    if new_py_content is None:
        return
    # 写入生成结果到文件
    with open(new_py_file, "w+", encoding='utf-8') as fd:
        fd.write(new_py_content.replace("\r\n", "\n"))


def make_code_only_lr(zipfd: zipfile.ZipFile, src, dst):
    """
        确保某个文件之中只有换行，没有回车
    :return:
    """
    if os.path.isfile(src) and src.endswith(".py"):
        with open(src, "rb+") as fd:
            content = fd.read().replace(b"\r\n", b"\n")
            zipfd.writestr(dst, content)
    else:
        zipfd.write(src, dst)


def make_std_package(project_path, output_path, zip_file_name):
    """
        制作一个通用包
        此包规范了通用资源
    :return:
    """
    # 先搜索包规范文件
    pkg_std_file_name = "ipk_package.txt"
    # 项目最基础的目录下，ICopy的中控程序的基础目录
    pkg_cpgui_path = project_path

    file = generator_utils.search_file("./", pkg_std_file_name)
    if file is None:
        print("未搜索到包格式规范文件！")
        return False

    try:
        # 进行解析规则的读取
        file_maps = []
        with open(file, encoding="utf-8") as fd:
            for line in fd.readlines():
                line = line.strip()
                if line.startswith("#") or line.isspace() or len(line) == 0:
                    continue
                file_maps.append(line)
        print(f"读取到的解析规则: {file_maps}")

        # 规范组
        rules = [
            '[-> ',  # 映射一个空的文件夹
            ']-> ',  # 映射一个空的文件
            ' -> ',  # 将左边的资源映射到右边的路径
        ]

        pkg_std_file_path = os.path.join(output_path, zip_file_name)

        # 生成规范包
        with zipfile.ZipFile(pkg_std_file_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_fd:
            for rule in file_maps:
                if rule.startswith(rules[0]):
                    fm = rule.strip().strip(rules[0]).strip()
                    zip_fd.write(".", fm)

                if rule.startswith(rules[1]):
                    with NamedTemporaryFile(mode="w+", delete=False) as f:
                        fm = rule.strip().strip(rules[1]).strip()
                        zip_fd.write(f.name, fm)
                    os.remove(f.name)  # 移除临时文件

                if rules[2] in rule:
                    fm = rule.split(rules[2])
                    fm = list(filter(lambda item: len(item) > 0 and not item.isspace(), fm))
                    if len(fm) != 2:
                        print(f"不是有效的规则: {rule}")
                        continue
                    raw_file = os.path.join(pkg_cpgui_path, fm[0])
                    if not os.path.exists(raw_file):
                        print(f"规则定义的文件或者文件夹不存在: {raw_file}")
                        continue
                    # zip_fd.write(raw_file, fm[1])
                    make_code_only_lr(zip_fd, raw_file, fm[1])
                    # 如果是文件夹，我们还需要递归文件进行压缩
                    if os.path.isdir(raw_file):
                        # 遍历文件或文件夹
                        for path, dirnames, filenames in os.walk(raw_file):
                            # print("\n", path, dirnames, filenames)
                            fpath = path.replace(os.path.dirname(raw_file), "")
                            # print(f"保存的路径: {fpath}\n")
                            for filename in filenames:
                                src = os.path.join(path, filename)
                                dst = os.path.join(fpath, filename)
                                # zip_fd.write(src, dst)
                                make_code_only_lr(zip_fd, src, dst)

    except Exception as e:
        raise e
    return True


def package_so2_ipk(ipk_zip, so_path, path_in_ipk):
    """
        打包so到ipk中
    :param ipk_zip: ipk文件包
    :param path_in_ipk: 在ipk中存放的位置
    :param so_path:  so的路径
    :return:
    """
    with zipfile.ZipFile(ipk_zip, mode="a", compression=zipfile.ZIP_DEFLATED) as zip_fd:
        paths = generator_utils.list_file_dirs(so_path, ".so")
        for path in paths:
            file_in_ipk = os.path.join(path_in_ipk, os.path.basename(path))
            # LOGGER.info(f"正在写入文件 {path} 到zip {file_in_ipk}")
            zip_fd.write(path, file_in_ipk)

        try:
            init_file_name = path_in_ipk + "/" + "__init__.py"
            zip_fd.getinfo(init_file_name)
        except KeyError:
            # 最终往有so的目录写入一个init文件
            zip_fd.writestr(init_file_name, "")


def package_file2_ipk(ipk_zip, file_path, path_in_ipk):
    """
        打包so到ipk中
    :param ipk_zip: ipk文件包
    :param path_in_ipk: 在ipk中存放的位置
    :param file_path:  so的路径
    :return:
    """
    try:
        with zipfile.ZipFile(ipk_zip, mode="a", compression=zipfile.ZIP_DEFLATED) as zip_fd:
            file_in_ipk = os.path.join(path_in_ipk, os.path.basename(file_path))
            # LOGGER.info(f"正在写入文件 {path} 到zip {file_in_ipk}")
            zip_fd.write(file_path, file_in_ipk)
    except Exception as e:
        LOGGER.info(e)
        return False
    return True


def package_info2_ipk(ipk_file, gen_obj):
    """
        打包信息进入
    :param ipk_file:
    :param gen_obj:
    :return:
    """
    try:
        # 最终，我们需要根据构建器中的信息，
        # 生成一个信息表，这个表使用通用的json格式，方便解析
        # 这个信息表，后期可以记录其他的一些信息，目前，我们只需要记录
        # 包括这个固件固定的SN，与这个固件的版本号
        # 与这个固件包的类型
        infos = {
            "package": "ipk",  # 包格式，目前只做了ipk，也就是icopy安装包
            "level": "full",  # 全量更新包，后期可以做增量更新包

            "uuid": uuid.uuid4().hex,  # 包的唯一ID，目前无用
            "keys": uuid.uuid4().hex,  # 包的唯一秘钥，目前无用

            "manifest": {  # 将所有的信息打包到单独的字典中
                # 记录IPK运行时的一些信息
                # 为了离线获取，此处直接单独缓存一份
                # 此处生成的信息，不应当影响正式运行时的逻辑
                # 但是可以被安装程序用来参考
                "info": {
                    # 打包类型信息
                    "sn": gen_obj.bundle['sn_str'],
                    "hw": f"{gen_obj.bundle['hw_version_main']}.{gen_obj.bundle['hw_version_sub']}",
                    # 暂时不打包这个版本号
                    # "os": f"{gen_obj.bundle['os_ver_major']}.{gen_obj.bundle['os_ver_minor']}",
                    # 暂时不需要版本信息被打包进去 例如 iCopy-XS
                    # "type": gen_obj.bundle['type'],
                },
                # 此处记录所有出现的文件夹的路径
                "path": [],
                # 此处记录了安装包中所有的文件的具体路径
                # 这是为了后期可以对比是否缺失了哪些文件
                "file": [],
                # 此处记录了所有的文件的hash
                # 此信息与上述的文件是有关联的
                # 为了避免文件被损坏或者更改，后期可以对比HASH，发现信息变动及时进行处理
                "crc32": {},
            },
        }

        with TemporaryDirectory() as build_tmp_dir:

            json_file = "manifest.json"
            json_path = os.path.join(build_tmp_dir, json_file)

            # 然后我们需要写进去这个压缩包中
            with zipfile.ZipFile(ipk_file, mode="a", compresslevel=zipfile.ZIP_DEFLATED) as zip_fd:

                # 先读出基本信息
                for info in zip_fd.infolist():
                    # 记录文件或者文件夹的路径
                    if info.is_dir():
                        infos['manifest']['path'].append(info.filename)
                    else:
                        infos['manifest']['file'].append(info.filename)
                        # 记录文件的CRC32
                        infos['manifest']['crc32'][info.filename] = info.CRC

                # 然后根据所有需要的信息生成一个临时的json文件
                with open(json_path, "w+") as json_fd:
                    json.dump(infos, json_fd)

                # 然后写入zip压缩包中
                zip_fd.write(json_path, json_file)

    except Exception as e:
        LOGGER.error("打包信息进入ipk失败: ", e)
        return False

    return True


def package_fw_2_ipk(depends_path, ipk_file, genobj):
    """
        打包stm32固件包进入ipk中
    :param genobj:  生成器对象
    :param depends_path: 依赖项所在的位置
    :param ipk_file: ipk文件
    :return:
    """
    hw_ver_major = genobj.bundle['hw_version_main']
    hw_ver_minor = genobj.bundle['hw_version_sub']
    hw_ver_code = f"{hw_ver_major}.{hw_ver_minor}"

    if genobj.bundle.get('fac_auto_make', False):
        LOGGER.info("此次操作为工厂申请生产固件。")

    # 1.5版本是旧的硬件，
    # 其中使用的MCU是STM32，
    # 我们需要打包对应的固件包
    if hw_ver_code == "1.5":
        # 我们在iCopy的APP端已经做了对低版本的STM32固件更新的禁用
        # 在STM32版本等于1.0的时候，禁止其更新
        typ_name = "STM32"
    else:  # 1.7是测试板，1.8是正式量产版本
        # GD32的硬件是新的版本，不存在更新不可用的漏洞
        # 因此我们可以其更新永远可用
        typ_name = "GD32"

    # 拼接固件资源路径
    path_all_ver = os.path.join(depends_path, typ_name)
    dirs_all_ver = os.listdir(path_all_ver)
    # 默认选取最新的固件
    vers = []
    for d in dirs_all_ver:
        if d.startswith("v"):
            vers.append(float(d[1:]))

    # 选取最大的那个值
    latest_ver = max(vers)
    ver_name = f"v{latest_ver}"
    if ver_name not in dirs_all_ver:
        raise Exception(f"没有发现对应的固件版本存在 {ver_name}")

    # OK，我们可以把里面的固件拿出来打包了
    # 但是要先拼接文件的最终路径
    # 类似: GD32_APP_v1.1.nib
    file_app_fw = os.path.join(
        path_all_ver,
        ver_name,
        f"{typ_name}_APP_{ver_name}.nib"
    )

    # 拼接完成后，直接打包进去
    return package_file2_ipk(
        ipk_file,
        file_app_fw,
        "res/firmware/app"
    )


def make_app_package(project_path, depends_path, output_path, std_ipk_path, gen_obj):
    """
        最终编译的启动入口
    :return:
    """
    LOGGER.info(f"项目所在目录: {project_path}")
    LOGGER.info(f"依赖所在目录: {depends_path}")
    LOGGER.info(f"编译输出目录: {output_path}")

    # 确保目录存在
    os.makedirs(output_path, exist_ok=True)

    # 定义由指定目录下的py文件编译后存放到zip包的路径的映射（需要生成代码）
    py_source_dirs_gencode = {
        os.path.join(project_path, "act"): "lib",
        os.path.join(project_path, "gui"): "lib",
    }

    # 同上（不需要生成代码）
    py_source_dirs_rawcode = {
        os.path.join(project_path, "app", "main"): "main",
    }

    LOGGER.info(f"开始拷贝规范ipk...")
    uuid_hex = uuid.uuid4().hex
    new_name = uuid_hex + ".ipk"
    app_file = generator_utils.copy_file(std_ipk_path, output_path, gen_obj, new_name)
    if app_file is None:
        LOGGER.info(f"复制ipk失败")
        return
    LOGGER.info(f"拷贝完成: {app_file}\n")

    start = time.perf_counter()

    try:
        for path in py_source_dirs_gencode.keys():  # 先编译需要生成代码的组件

            with TemporaryDirectory() as build_tmp_dir:

                # 路径创建完毕，我们需要开始生成代码
                pys = generator_utils.list_file_dirs(path, ".py")

                # 循环往线程池添加代码生成的任务
                with ThreadPoolExecutor() as pool:
                    task_list = [
                        pool.submit(
                            gen_code_fun, py, gen_obj, build_tmp_dir
                        ) for py in pys
                    ]
                    # 等待所有的线程完成工作
                    concurrent.futures.wait(task_list)

                pys = generator_utils.list_file_dir(build_tmp_dir, ".py")

                LOGGER.info("开始构建构建（生成过程）模块。")

                # 开始进行功能性组件库文件编译
                if build_2libs(pys, build_tmp_dir):
                    LOGGER.info("构建（生成过程）模块成功。")
                else:
                    raise Exception("构建（生成过程）模块失败。")

                # 非常重要的一步，将编译好的so打包进ipk中
                package_so2_ipk(
                    app_file,
                    build_tmp_dir,
                    py_source_dirs_gencode[path]
                )

        LOGGER.info(f"开始构建 构建（原生文件）模块。")

        for path in py_source_dirs_rawcode.keys():  # 再编译需要不生成代码的组件

            with TemporaryDirectory() as build_tmp_dir:

                # 路径创建完毕，我们需要开始复制代码
                generator_utils.copy_tree(path, build_tmp_dir, gen_obj)
                pys = generator_utils.list_file_dirs(path, ".py")

                # 开始进行功能性组件库文件编译
                if build_2libs(pys, build_tmp_dir):
                    LOGGER.info("构建（原生文件）模块成功。")
                else:
                    raise Exception("构建（原生文件）模块失败。")

                package_so2_ipk(
                    app_file,
                    build_tmp_dir,
                    py_source_dirs_rawcode[path]
                )

        # 打包信息为json，并且放到zip包中
        if package_info2_ipk(app_file, gen_obj):
            LOGGER.info("构建（版本信息）文件成功。")
        else:
            raise Exception("构建（版本信息）文件失败。")

        if package_fw_2_ipk(depends_path, app_file, gen_obj):
            LOGGER.info("含入（HMI固件包）文件成功。")
        else:
            raise Exception("含入（HMI固件包）文件失败。")

    except Exception as e:
        LOGGER.error(f"编译失败: {e}")
        os.remove(app_file)
        app_file = None

    LOGGER.info(
        f"\n构建完成，输ipk文件为: {app_file} \n "
        f"构建花费的时间(s): {time.perf_counter() - start}\n"
    )

    return app_file

