import re
import time

import generator_utils
import icopy_maps

# 定义一个包构建器的设备的IP地址
IP_PACKAGER_ADDR = "127.0.0.1"


def get_packager_resp(addr, url, str_resp=True, method="", params=None):
    """
        获取来自打包服务器的回复
    :param params: 请求的附带参数
    :param method: 请求方法
    :param addr: 服务器地址
    :param url: 资源链接
    :param str_resp: 是否以文本形式的返回
    :return:
    """
    return generator_utils.get_server_resp(f"http://{addr}:7878/{url}", str_resp, method, params)


def make_ipk_for_infos(typ, infos):
    """
        使用信息进行固件制作
    :param typ:
    :param infos:
    :return:
    """
    if infos is None:
        print("make_ipk_for_infos() 解析信息数据失败。")
        return None

    if typ not in icopy_maps.TYPE_TO_CLZ_MAPS:
        print("开发者未实现的生产类型: ", typ)
        return None

    # 添加一些无关设备的信息进去
    infos['type'] = typ

    # 发起ipk生产请求
    try:
        uuid = get_packager_resp(
            IP_PACKAGER_ADDR,
            "add",
            True,
            "POST",
            infos,
        )
        uuid = uuid.strip()
    except Exception as e:
        print("发起ipk生产请求时网络出现异常:", e)
        return None

    if re.match(r"^[A-Fa-f0-9]+$", str(uuid)) is not None:
        # 得到了16进制数据，认为是uuid
        print(f"创建任务成功，任务的UUID为: {uuid}")
    else:
        print("建立编译任务时得到了未知错误，错误信息: ", uuid)
        return None

    unknown_retry = 5

    # 运行到这里说明uuid正常，任务开始了，开始询问任务运行的咋样了
    while True:
        # 不断询问是否运行完成
        try:
            res = get_packager_resp(IP_PACKAGER_ADDR, f"ok?code={uuid}")
        except Exception as e:
            print("询问是否运行(编译）完成时网络出现异常:", e)
            return None

        if res == "unknown":
            if unknown_retry == 0:
                print("询问任务是否运行(编译）完成时发现任务确实尚未创建！")
                return None
            else:
                print("询问任务是否运行(编译）完成时得到了任务尚未创建的结果，自动重问！")
                unknown_retry = unknown_retry - 1
                time.sleep(1)
                continue

        elif res == "noparam":
            print("询问任务是否运行(编译）完成时得到了任务参数为空的结果！")
            return None
        elif res == "notget":
            print("询问任务是否运行(编译）完成时得到了访问媒介不是GET型的结果！")
            return None
        elif res == "True":
            # True 说明文件已经编译运行完成
            break
        elif res == "False":
            # False 说明文件已经编译运行尚未完成
            time.sleep(1)
        else:
            print("询问任务完成时得到了未知错误，内容为:", res)
            return None

    # 运行到这里说明任务执行完成，编译已经完成，可以申请下载文件了
    try:
        print("开始下载ipk文件...")
        res = generator_utils.download_file(f"http://{IP_PACKAGER_ADDR}:7878/download?code={uuid}", r"./")
        print("ipk文件下载完成！")
    except Exception as e:
        print("下载目标文件时网络出现异常:", e)
        return None
    if res == "failed":
        print("远端文件异常！")
        return None
    elif res is None:
        print("下载文件时出错，请检查网络连接或者服务器方的异常！")
        return None
    else:
        return res
