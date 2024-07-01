"""
    代码生成用到的一些工具实现
"""
import logging
import os
import shutil
import time
import random
import requests

from urllib.parse import unquote
from urllib.request import urlopen
from urllib.request import Request

user_agent = [
    "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
    "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1; AcooBrowser; .NET CLR 1.1.4322; .NET CLR 2.0.50727)",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; Acoo Browser; SLCC1; .NET CLR 2.0.50727; Media Center PC 5.0; .NET CLR 3.0.04506)",
    "Mozilla/4.0 (compatible; MSIE 7.0; AOL 9.5; AOLBuild 4337.35; Windows NT 5.1; .NET CLR 1.1.4322; .NET CLR 2.0.50727)",
    "Mozilla/5.0 (Windows; U; MSIE 9.0; Windows NT 9.0; en-US)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64; x64; Trident/5.0; .NET CLR 3.5.30729; .NET CLR 3.0.30729; .NET CLR 2.0.50727; Media Center PC 6.0)",
    "Mozilla/5.0 (compatible; MSIE 8.0; Windows NT 6.0; Trident/4.0; WOW64; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30729; .NET CLR 1.0.3705; .NET CLR 1.1.4322)",
    "Mozilla/4.0 (compatible; MSIE 7.0b; Windows NT 5.2; .NET CLR 1.1.4322; .NET CLR 2.0.50727; InfoPath.2; .NET CLR 3.0.04506.30)",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; zh-CN) AppleWebKit/523.15 (KHTML, like Gecko, Safari/419.3) Arora/0.3 (Change: 287 c9dfb30)",
    "Mozilla/5.0 (X11; U; Linux; en-US) AppleWebKit/527+ (KHTML, like Gecko, Safari/419.3) Arora/0.6",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.8.1.2pre) Gecko/20070215 K-Ninja/2.1.1",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; zh-CN; rv:1.9) Gecko/20080705 Firefox/3.0 Kapiko/3.0",
    "Mozilla/5.0 (X11; Linux i686; U;) Gecko/20070322 Kazehakase/0.4.5",
    "Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.8) Gecko Fedora/1.9.0.8-1.fc10 Kazehakase/0.5.6",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/535.11 (KHTML, like Gecko) Chrome/17.0.963.56 Safari/535.11",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_3) AppleWebKit/535.20 (KHTML, like Gecko) Chrome/19.0.1036.7 Safari/535.20",
    "Opera/9.80 (Macintosh; Intel Mac OS X 10.6.8; U; fr) Presto/2.9.168 Version/11.52"
]


def get_darkside_headers():
    """
        随机一个浏览器的头
    :return:
    """
    return {
        'User-Agent': random.choice(user_agent),  # 浏览器头部
        'Accept': 'application/json',  # 客户端能够接收的内容类型
        'Accept-Language': 'en-US,en;q=0.5',  # 浏览器可接受的语言
        'Connection': 'keep-alive',  # 表示是否需要持久连接
    }


def get_server_resp(url, str_resp=True, method="", params=None, timeout=(8, 21)):
    """
        请求获取一个URL的回复内容
    :param timeout: 请求超时
    :param params:  请求的附带参数
    :param method: 请求方法，默认为get
    :param str_resp: 是否需要字符串类型的返回
    :param url:  将被请求的地址
    :return:
    """
    if len(method) == 0 or method.lower() == "get":
        method = requests.get
    elif method.lower() == "post":
        method = requests.post
    else:
        raise Exception(f"不支持的请求方法: {method}")

    if params is None:
        resp = method(url, timeout=timeout, headers=get_darkside_headers())
    else:
        resp = method(url, params, timeout=timeout, headers=get_darkside_headers())

    result = resp.content
    if str_resp:
        result = result.decode()

    resp.close()
    del resp

    return result


def download_file(url, path):
    """
    :param url: to download file
    :param path: place to put the file
    """
    # print("开始请求头部信息......")
    url_connection = urlopen(Request(url, headers=get_darkside_headers()))
    url_info = url_connection.info()
    # print("头部信息请求完成：", url_info)

    filename = ''

    if 'Content-Type' in url_info:
        if "text/html" in url_info['Content-Type']:
            resp = url_connection.read().decode()
            url_connection.close()
            return resp

    if 'Content-Disposition' in url_info and url_info['Content-Disposition']:
        disposition_split = url_info['Content-Disposition'].split(';')
        if len(disposition_split) > 1:
            if disposition_split[1].strip().lower().startswith('filename='):
                file_name = disposition_split[1].split('=')
                if len(file_name) > 1:
                    filename = unquote(file_name[1])

    url_connection.close()

    if not filename and os.path.basename(url):
        filename = os.path.basename(url).split("?")[0]

    if not filename:
        filename = time.time()

    if not os.path.exists(path):
        os.makedirs(path)

    file_path = os.path.join(path, filename)

    with requests.get(url, stream=True) as req:
        # print("download_file() 开始下载....")
        with open(file_path, mode="wb") as fd:
            for dat in req.iter_content(1024 * 1024 * 8):
                fd.write(dat)
                # print(f"读取到的块大小: {len(dat)}")
    return file_path


def upload_file(url, path, name="file", **kwargs):
    """
        上传一个文件到服务器
    :param name: 文件的表单名称
    :param url:
    :param path:
    :return:
    """
    with open(path, 'rb') as f:
        with requests.post(url, files={name: f}, headers=get_darkside_headers(), **kwargs) as result:
            return result.content.decode()


def copy_tree(src, out, gen_obj):
    """
        简化文件夹拷贝，并且带确认
    :param gen_obj:
    :param src:
    :param out:
    :return:
    """
    if os.path.exists(out):
        shutil.rmtree(out)

    # print("源文件夹: ", src)
    # print("输出目录: ", out)

    def copy_tree_filter(folder, files):
        """
            回调函数，过滤文件
        :param folder: 文件夹
        :param files: 文件夹下面的文件
        :return:
        """
        if isinstance(folder, os.DirEntry):
            folder = folder.name
        elif isinstance(folder, str):
            pass
        else:
            raise TypeError("未知的文件夹参数格式: ", folder)
        ignore_list = []
        for file in files:
            old_path = os.path.join(folder, file)
            if not os.path.isdir(old_path):  # os.path.join的参数不应以斜杠开头
                new_file = os.path.join(out, folder.replace(src, "").strip(os.sep), file)
                if not gen_obj.onAppGenFile(old_path, new_file):
                    ignore_list.append(file)
        return ignore_list

    return shutil.copytree(src, out, ignore=copy_tree_filter)


def copy_file(src, out, gen_obj, new_name=None):
    """
        简化文件拷贝，并且带确认
    :param new_name: 新的文件名
    :param gen_obj:
    :param src:
    :param out:
    :return:
    """
    try:
        # 生成基础信息
        if new_name is None:
            new_name = os.path.basename(src)
        file_new = os.path.join(out, new_name)

        if os.path.exists(file_new):
            return None

        if gen_obj.onAppGenFile(src, file_new):  # 允许打包此文件
            return shutil.copy(src, file_new)
    except Exception as e:
        logging.getLogger().error(f"复制文件出错: {e}")
        return None


def search_file(path, name):
    # print("本次搜索的文件名: ", name)
    for root, dirs, files in os.walk(path):  # path 为根目录
        # print("\n搜索安装包文件迭代信息: ", root, dirs, files)
        if name in files:
            # root = str(root)
            # dirs = str(dirs)
            return os.path.join(root, name)
    return None


def list_file_dir(dir_path, suffix):
    """
        列出目录下的PY文件
    :param suffix: 需要过滤的文件尾缀
    :param dir_path: 目录
    :return:
    """
    files_internal = os.listdir(os.path.abspath(dir_path))
    ret = []
    for f in files_internal:
        f = os.path.join(dir_path, f)
        if os.path.isfile(f) and f.endswith(suffix):
            ret.append(f)
        if os.path.isdir(f):  # 如果是目录，则递归重查
            ret.extend(list_file_dir(f, suffix))
    return ret


def list_file_dirs(dirs, suffix):
    """
        列出给出的一些目录下的py文件
    :param suffix: 需要过滤的文件尾缀
    :param dirs: 目录；列表或者单个目录
    :return:
    """
    if isinstance(dirs, str):
        dirs = [dirs]

    ret = []
    for dir_item in dirs:
        ret.extend(list_file_dir(dir_item, suffix))
    return ret
