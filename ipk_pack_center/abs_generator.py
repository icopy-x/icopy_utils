"""
    抽象的派发类封装
    封装了一系列的派发动作
    @author dxl
"""
import base64
import os
import hashlib
import re

from Crypto.Cipher import AES


class AppGenerator:
    """
        APP生成器
        可以通过此类控制基础的
        1、已编译的代码生成
        2、其他的文件生成
    """

    def __init__(self):
        # 是否关闭所有的print
        self.close_print = True
        # 是否关闭所有的debug代码块
        self.close_debug = True
        # 生成一个白名单文件列表
        # 只允许此列表中的文件被编译打包进最终的ipk中
        self.maps = self.onGetGenFileMap()

    def onGetGenFileMap(self):
        """
            获取从文件到生成函数的映射
            必须要返回一个dict
            例子: {
                py文件名  : 生成代码的处理函数
                "xxx.py" : fun_gen
            }
        :return:
        """
        return {}

    @staticmethod
    def genAttrKV(content: str, attr, value):
        """
            设置某个变量的值
        :param content:
        :param attr:
        :param value:
        :return:
        """
        regex = r'({}.*?=.*)'.format(attr)
        if isinstance(value, str):
            value = '"{}"'.format(value)
        else:
            value = '{}'.format(value)
        sea_obj = re.search(regex, content)
        if sea_obj is None:
            return content
        value = attr + ' = ' + value
        # print("匹配到的结果: ", sea_obj.group(1))
        return content.replace(sea_obj.group(1), value)

    @staticmethod
    def checkBundle(obj):
        if obj is None:
            raise Exception("不允许开发者提供空的键值对。")

    @staticmethod
    def printClose(content: str):
        """
            关闭print，替换为pass占位符
        :return:
        """
        regex = r'(?<= )print\(.*\)'
        return re.sub(regex, "pass", content)

    @staticmethod
    def debugClose(content: str):
        """
            关闭debug，删除Debug语句
            # 测试开始 <
                代码段
            # 测试结束 >
        :param content:
        :return:
        """
        regex = r'\s*?# 测试开始 <[\s\S]*?# 测试结束 >'
        debug_codes = re.findall(regex, content)
        for index, debug_code in enumerate(debug_codes):
            # print("\n\n************ 删除Debug语句（清空代码段！）************ ")
            # print("被删除的计数:", index + 1)
            # print("被删除的文本:")
            content = content.replace(debug_code, "")
            # print(debug_code)
            # print("\n*******************  删除完成 **********************\n\n")
        return content

    def onGenerator(self, name, content):
        """
            生成代码
        :param content:
        :param name:
        :return: 生成的最终的代码
        """
        name = os.path.basename(name)
        if not isinstance(self.maps, dict):
            raise Exception("开发者请实现 -> onGetGenFileMap() 函数返回指定的格式。")
        if name not in self.maps:
            # print("文件: ", name, "不允许被生成，自动忽略。")
            return None
        # 先关闭print打印
        if self.close_print:
            content = self.printClose(content)
        if self.close_debug:
            # 然后关闭debug逻辑
            content = self.debugClose(content)
        if self.maps[name] is None:
            # 如果没有实现内容处理函数，就直接返回源内容
            return content
        return self.maps[name](content)

    def onAppGenStart(self, app_path):
        """
            在APP开始打包的时候回调
        :param app_path: 打包的APP的根目录
        :return:
        """
        pass

    def onAppGenFile(self, src_file, app_file):
        """
            在生成一些APP文件时可以进行过滤
        :param src_file: 源文件
        :param app_file: 将被生成的文件的相对路径
        :return: 是否允许生成此文件，允许返回True，否则返回False
        """
        # print("\nonAppGenFile将生成该文件: ")
        # print("源文件: ", src_file)
        # print("新文件: ", app_file)
        # print()
        return True

    def onAppGenEnd(self, app: str):
        """
            在APP打包完成之后回调
        :param app: APP安装包文件本身
        :return:
        """
        pass


class ICopyGenerator(AppGenerator):
    """
        二级抽象的ICopy资源生成类
    """

    def __init__(self, bundle):
        """
            初始化对象
        :param bundle: 生成代码的时候需要的数据
                        注意，某些代码生成可能并不需要数据
        """
        self.bundle = bundle
        super().__init__()

    def getTypeName(self):
        """
            抽象的获取类型名称的函数
        :return:
        """
        raise Exception("必须覆盖")

    def getTypeCode(self):
        """
            抽象的获取类型代码的函数
        :return:
        """
        raise Exception("必须覆盖")

    def genSN(self, content):
        """
            动态生成序列号
        :param content:
        :return:
        """
        key = "sn_str"
        if key in self.bundle:
            sn = self.bundle[key]
            self.checkBundle(sn)
            return self.genAttrKV(content, "SERIAL_NUMBER", sn)
        raise Exception("必须传递序列号参数")

    def genVer(self, content):
        """
            动态生成版本号
        :param content:
        :return:
        """
        key1 = "os_ver_major"
        key2 = "os_ver_minor"

        if key1 in self.bundle:
            ver_major = self.bundle[key1]
            self.checkBundle(ver_major)
            content = self.genAttrKV(content, "VERSION_MAJOR", ver_major)

        if key2 in self.bundle:
            ver_minor = self.bundle[key2]
            self.checkBundle(ver_minor)
            content = self.genAttrKV(content, "VERSION_MINOR", ver_minor)

        return content

    def genHW(self, content):
        """
            动态生成硬件版本号
        :param content:
        :return:
        """
        key1 = "hw_version_main"
        key2 = "hw_version_sub"
        if key1 in self.bundle and key2 in self.bundle:
            ver_hw_main = self.bundle[key1]
            ver_hw_sub = self.bundle[key2]
            # 检查可用性
            self.checkBundle(ver_hw_main)
            self.checkBundle(ver_hw_sub)
            return self.genAttrKV(content, "HARDWARE_VER", f"{ver_hw_main}.{ver_hw_sub}")
        return content

    def genPM3(self, content):
        """
            动态生成PM3的版本号
        :param content:
        :return:
        """
        key = "pm"
        if key in self.bundle:
            ver_pm3 = self.bundle[key]
            self.checkBundle(ver_pm3)
            return self.genAttrKV(content, "PM3_VER", ver_pm3)
        return content

    def genTYP(self, content):
        """
            动态生成当前手持机的版本类型
        :param content:
        :return:
        """
        key = "type"
        if key in self.bundle:
            ver_typ = self.bundle[key]
        else:
            ver_typ = self.getTypeName()
            if ver_typ is None:
                raise ValueError("开发者没有提供设备类型值（非逻辑判断使用）")
        self.checkBundle(ver_typ)
        return self.genAttrKV(content, "TYP", ver_typ)

    def calcKey(self):
        """
            计算我们规定用于加密数据的秘钥，
            也就H3的ID经过三次MD5后求和的数据
        :return:
        """
        id_cpu = self.bundle["id_cpu"]
        # 合并，组成
        bytes_id_cpu = str(id_cpu).encode("utf-8")
        # 进行加密，单纯使用cpu_id进行加密
        # 经过三次MD5 16后，我们获得了解密UID的秘钥
        m = hashlib.md5()
        m.update(bytes_id_cpu)
        m.update(bytes_id_cpu)
        m.update(bytes_id_cpu)
        r = m.hexdigest()
        # 进行MD5求和
        count = 0
        ret = ""  # 这个是秘钥，
        while count < len(r):
            tmp = format(int(r[count], 16) + int(r[count + 1], 16), "x")
            ret += tmp[0]
            count += 2
        return ret

    def calcUID(self):
        """
            计算当前机器的UID
            UID的组成，请看 version.py
        :return:
        """
        # 取出包中的数据
        id_cpu = self.bundle["id_cpu"]
        id_pm3 = self.bundle["id_pm3"]
        id_stm32 = self.bundle["id_stm32"]

        key = "id_type"
        if key in self.bundle:
            id_type = self.bundle[key]
        else:
            id_type = self.getTypeCode()
            if id_type is None:
                raise ValueError("开发者没有提供设备类型值（存进UID，逻辑判断使用）")

        self.checkBundle(id_cpu)
        self.checkBundle(id_pm3)
        self.checkBundle(id_stm32)
        self.checkBundle(id_type)

        key = self.calcKey()

        # 很好，我们得到了秘钥，现在可以进行下一步操作了
        final_str = f"{id_cpu},{id_pm3},{id_stm32},{id_type}"
        # print("\n秘钥是: ", key)
        # print("加密的信息是: ", final_str)
        aes_obj = AES.new(
            key.encode("utf-8"),
            AES.MODE_CFB,
            "VB1v2qvOinVNIlv2".encode()
        )
        ret_str = base64.b64encode(  # 加密完成后用BASE64进行编码
            aes_obj.encrypt(  # 再进行加密
                final_str.encode("utf-8")  # 先转换为字节流
            )
        ).decode("utf-8")  # BASE64编码完成后转换为UTF-8字符串
        # print("加密后信息是: ", ret_str, "\n")
        return ret_str

    def genUID(self, content):
        """
            动态生成UID
        :param content:
        :return:
        """
        return self.genAttrKV(content, "UID", self.calcUID())

    def genVerAll(self, content):
        """
            生成所有的版本信息
        :param content:
        :return:
        """
        content = self.genSN(content)
        content = self.genVer(content)
        content = self.genHW(content)
        content = self.genPM3(content)
        content = self.genTYP(content)
        content = self.genUID(content)
        return content
