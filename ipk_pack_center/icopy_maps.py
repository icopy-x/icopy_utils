"""
    版本生成实现类
"""
import base64
import os
import re

from Crypto.Cipher import AES

import icopy_iclass
import abs_generator

# 设备版本名，用于标志版本类型
# 请开发者在此处定义版本名称
TYPE_ICOPY_D = "iCopy-Debug"
TYPE_ICOPY_F = "iCopy-Factory"
TYPE_ICOPY_X = "iCopy-X"
TYPE_ICOPY_XR = "iCopy-XR"
TYPE_ICOPY_XS = "iCopy-XS"
TYPE_ICOPY_ZH = "iCopy-XS(CN)"
TYPE_ICOPY_UK = "iCopy-XS(UK)"
TYPE_ICOPY_XSC = "iCopy-XSC(CN)"

# 定义从版本名称到版本的 内部标志码 的表
# 该版本信息不会保存到数据库中，只会被打包进
# IPK中的模块： Version.UID 中（被加密保存）
TYPE_TO_CODE_MAPS = {
    TYPE_ICOPY_D: "xs",
    TYPE_ICOPY_F: "f",

    TYPE_ICOPY_ZH: "zh",

    TYPE_ICOPY_X: "x",
    TYPE_ICOPY_XR: "xr",
    TYPE_ICOPY_XS: "xs",

    TYPE_ICOPY_UK: "uk",
    TYPE_ICOPY_XSC: "xsc",
}

# 定义从版本名称到数据库中的 类型标志码 的映射
# 类型标志码将会被保存到生产数据库中
# 在进行更新的时候将首先调用版本标志码进行版本匹配，
# 自动完成上述的版本名称到版本内部标志码的映射
TYPE_TO_INT_MAPS = {
    TYPE_ICOPY_X: 0,
    TYPE_ICOPY_XR: 1,
    TYPE_ICOPY_XS: 2,
    TYPE_ICOPY_ZH: 3,
    TYPE_ICOPY_UK: 4,
    TYPE_ICOPY_XSC: 5,
}

# 定义从版本名称到数据库中的 类型名称 的映射
# 这个名称是显示在包括生产系统和手持机APP上的
TYPE_TO_NAME_MAPS = {
    TYPE_ICOPY_X: TYPE_ICOPY_X,
    TYPE_ICOPY_XR: TYPE_ICOPY_XR,
    TYPE_ICOPY_XS: TYPE_ICOPY_XS,
    TYPE_ICOPY_ZH: TYPE_ICOPY_ZH,
    TYPE_ICOPY_UK: TYPE_ICOPY_UK,
    TYPE_ICOPY_XSC: TYPE_ICOPY_XSC,
}

# 显示在工厂生产工具中的版本信息
# 只是单纯在生产的时候标志当前的硬件以及软件的匹配信息
TYPE_TO_FAC_MAPS = {
    TYPE_ICOPY_D: "调试版本(16G)",
    TYPE_ICOPY_F: "工程版本(4G)",

    TYPE_ICOPY_ZH: "中文版本(16G)",

    TYPE_ICOPY_X: "低配版本(4G)",
    TYPE_ICOPY_XR: "中配版本(8G)",
    TYPE_ICOPY_XS: "高配版本(16G)",

    TYPE_ICOPY_UK: "英国版本(16G)",
    TYPE_ICOPY_XSC: "跃力安防(16G)",
}


def genTagTypesMapRow(content: str, typ, readable=None, writeable=None):
    """
        根据指定的类型生成字典行
    :param content:
    :param typ:
    :param readable:
    :param writeable:
    :return:
    """
    # 这个正则用来匹配全部行
    regex0 = rf'(.*?\s*:\s*\(.*\))'
    # 这个正则用来匹配小参数
    regex1 = rf'(.*?)\s*:\s*\(\s*"(.*)"\s*,\s*(False|True)\s*,\s*(False|True)\s*,*\)'

    find_obj0 = re.findall(regex0, content)
    find_obj1 = re.findall(regex1, content)

    typ = str(typ).strip()

    if len(find_obj0) == 0 or len(find_obj1) == 0:
        print("无法搜索到指定的类型的标签映射数据: ", typ)
        return content

    # print("\n匹配到的数据0: {}".format(find_obj0))
    # print("匹配到的数据1: {}\n".format(find_obj1))

    replace_line = None
    for maps in find_obj0:
        maps = maps.strip()
        regex2 = r"{}\s*:".format(str(typ))
        # print(f"使用正则 {regex2} 查询替换映射关系: {maps}")
        if re.match(regex2, maps):
            replace_line = maps
            # print("发现匹配的行: ", maps)
            break

    if replace_line is None:
        # print("\n没有发现指定的类型的替换行！！！\n")
        return content

    match_maps = None
    for maps in find_obj1:
        ml = str(maps[0]).strip()
        # print("参数映射关系: ", maps)
        if ml == typ:
            match_maps = maps
            break

    if match_maps is None:
        print("没有发现指定的类型的映射行！！！")
        return content

    if readable is None:
        readable = match_maps[2]
    if writeable is None:
        writeable = match_maps[3]

    # 创建一个样例范本，将匹配的数据行需要的数据进行填充，达到替换的目的
    new_row = '{}: ("{}", {}, {})'.format(typ, match_maps[1], readable, writeable)
    return content.replace(replace_line, new_row)


class BaseICopyGenerator(abs_generator.ICopyGenerator):
    """
        基础生产实现类定义
    """

    def getTypeCode(self):
        return TYPE_TO_CODE_MAPS[self.getTypeName()]


class DGen(BaseICopyGenerator):
    """
        单独实现的ICopy开发者版本的代码生成工具类
        仅供开发者使用
    """

    def onGetGenFileMap(self):
        return {
            "appfiles.py": None,
            "commons.py": None,
            "container.py": None,
            "executor.py": None,
            "felicaread.py": None,
            "hf14ainfo.py": None,
            "hf14aread.py": None,
            "hffelica.py": None,
            "hficlass.py": None,
            "hfmfkeys.py": None,
            "hfmfread.py": None,
            "hfmfuinfo.py": None,
            "hfmfuread.py": None,
            "hfmfuwrite.py": None,
            "hfmfwrite.py": None,
            "hfsearch.py": None,
            "iclassencrypt.py": None,
            "iclassread.py": None,
            "iclasswrite.py": None,
            "hf15read.py": None,
            "hf15write.py": None,
            "legicread.py": None,
            "lfem4x05.py": None,
            "lfread.py": None,
            "lfsearch.py": None,
            "lft55xx.py": None,
            "lfverify.py": None,
            "lfwrite.py": None,
            "mifare.py": None,
            "read.py": None,
            "scan.py": None,
            "sniff.py": None,
            "tagtypes.py": None,
            "trans.py": None,
            "write.py": None,
            "actbase.py": None,

            "activity_debug.py": None,
            "activity_factory.py": None,
            "activity_main.py": None,
            "activity_tools.py": None,
            "activity_update.py": None,

            "actmain.py": None,
            "actstack.py": None,
            "application.py": None,
            "audio.py": None,
            "audio_copy.py": None,
            "batteryui.py": None,
            "bytestr.py": None,
            "config.py": None,
            "debug.py": None,
            "games.py": None,
            "hmi_driver.py": None,
            "images.py": None,
            "keymap.py": None,
            "resources.py": None,
            "settings.py": None,
            "template.py": None,
            "update.py": None,
            "version.py": None,
            "widget.py": None,
            "ymodem.py": None,
            "gadget_linux.py": None,
            "vsp_tools.py": None,

            # 服务承载
            "serpool.py": None,
            "sermain.py": None,

        }

    def getTypeName(self):
        return TYPE_ICOPY_D


class FGen(BaseICopyGenerator):
    """
        单独实现的ICopy工厂初始化专用的代码生成工具类
    """

    def onGetGenFileMap(self):
        return {
            "commons.py": None,
            "executor.py": None,
            "actbase.py": None,
            "actmain.py": None,
            "actstack.py": None,
            "application.py": None,
            "activity_factory.py": None,  # 工厂生产专用的活动
            "activity_update.py": None,  # 安装APP必备的act咯
            "audio.py": None,
            "batteryui.py": None,
            "bytestr.py": None,
            "config.py": None,
            "debug.py": None,
            "hmi_driver.py": None,
            "images.py": None,
            "keymap.py": None,
            "resources.py": None,
            "settings.py": None,
            "update.py": None,
            "widget.py": None,
            "version.py": None,
            "ymodem.py": None,
            "gadget_linux.py": None,
            "vsp_tools.py": None,

            # 服务承载
            "serpool.py": None,
            "sermain.py": None,

        }

    def onAppGenStart(self, app_path):
        """
            我们需要在APP开始生成的时候，创建一个工厂固件专用的文件标志
            以此达到一些标志的效果，让启动器把工厂固件的包删除掉，不要备份
        :param app_path:
        :return:
        """
        file = os.path.join(app_path, "disallow_backup")
        if os.path.exists(file):
            return
        print(f"将在 {app_path} 目录下自动生成工厂标志文件。")
        try:
            with open(file, mode="w+"):
                pass
        except Exception as e:
            print("创建标志文件失败: ", e)

    def onAppGenFile(self, src_file, app_file):
        """
            在APP生成文件的时候我们需要过滤掉固件文件夹
            因为出产安装包默认不会带有更新固件功能
        :param src_file:
        :param app_file:
        :return:
        """
        fw_dir = os.path.join("res", "firmware")
        if fw_dir in app_file:
            #  print("忽略该文件的拷贝: ", app_file)
            return False
        # print("将拷贝该文件: ", src_file, " --- ", app_file)
        return True

    def getTypeName(self):
        return TYPE_ICOPY_F


class XGen(BaseICopyGenerator):
    """
        单独实现的ICopyX的代码生成工具类
    """

    def onGetGenFileMap(self):
        return {
            "appfiles.py": None,
            "commons.py": None,
            "container.py": None,
            "executor.py": None,
            "felicaread.py": None,
            "hf14ainfo.py": None,
            "hf14aread.py": None,
            "hffelica.py": None,
            "hficlass.py": None,
            "hfmfkeys.py": None,
            "hfmfread.py": None,
            "hfmfuinfo.py": None,
            "hfmfuread.py": None,
            "hfmfuwrite.py": None,
            "hfmfwrite.py": None,
            "hfsearch.py": None,

            # "iclassencrypt.py": None,
            # "iclassread.py": None,
            # "iclasswrite.py": None,

            "hf15read.py": None,
            "hf15write.py": None,
            "legicread.py": None,
            "lfem4x05.py": None,
            "lfread.py": None,
            "lfsearch.py": None,
            "lft55xx.py": None,
            "lfverify.py": None,
            "lfwrite.py": None,
            "mifare.py": None,
            "read.py": None,
            "scan.py": None,
            "sniff.py": None,
            "tagtypes.py": self.genTagFalseTypes,

            # "trans.py": None,

            "write.py": None,
            "actbase.py": None,

            "activity_main.py": None,
            "activity_tools.py": None,
            "activity_update.py": None,  # 安装APP必备的act咯

            "actmain.py": None,
            "actstack.py": None,
            "application.py": None,
            "audio.py": None,
            "audio_copy.py": None,
            "batteryui.py": None,
            "bytestr.py": None,
            "config.py": None,
            "debug.py": None,
            "games.py": None,
            "hmi_driver.py": None,
            "images.py": None,
            "keymap.py": None,
            "resources.py": None,
            "settings.py": None,
            "template.py": None,

            # "activity_debug.py": None,

            "update.py": None,
            "version.py": self.genVerAll,
            "widget.py": None,
            "ymodem.py": None,

            # "test.py": None,

            "gadget_linux.py": None,
            "vsp_tools.py": None,

            # 服务承载
            "serpool.py": None,
            "sermain.py": None,

        }

    def genTagFalseTypes(self, content):
        """
            生成tagtypes，X版本需要禁用
            1、M1卡除了1K4B卡之外的读写
            2、iclass的读写
        :return:
        """
        # content = self.genTagTypesMapRow(content, tagtypes.M1_S50_1K_4B, False, False)

        content = genTagTypesMapRow(content, "M1_S50_1K_7B", False, False)
        content = genTagTypesMapRow(content, "M1_S70_4K_4B", False, False)
        content = genTagTypesMapRow(content, "M1_S70_4K_7B", False, False)

        content = genTagTypesMapRow(content, "M1_POSSIBLE_4B", False, False)
        content = genTagTypesMapRow(content, "M1_POSSIBLE_7B", False, False)

        content = genTagTypesMapRow(content, "M1_MINI", False, False)
        content = genTagTypesMapRow(content, "M1_PLUS_2K", False, False)

        content = genTagTypesMapRow(content, "ICLASS_ELITE", False, False)
        content = genTagTypesMapRow(content, "ICLASS_LEGACY", False, False)
        return content

    def getTypeName(self):
        return TYPE_ICOPY_X


class XRGen(BaseICopyGenerator):
    """
        单独实现的ICopyXR的代码生成工具类
    """

    def onGetGenFileMap(self):
        return {
            "appfiles.py": None,
            "commons.py": None,
            "container.py": None,
            "executor.py": None,
            "felicaread.py": None,
            "hf14ainfo.py": None,
            "hf14aread.py": None,
            "hffelica.py": None,
            "hficlass.py": None,
            "hfmfkeys.py": None,
            "hfmfread.py": None,
            "hfmfuinfo.py": None,
            "hfmfuread.py": None,
            "hfmfuwrite.py": None,
            "hfmfwrite.py": None,
            "hfsearch.py": None,

            # "iclassencrypt.py": None,
            # "iclassread.py": None,
            # "iclasswrite.py": None,

            "hf15read.py": None,
            "hf15write.py": None,
            "legicread.py": None,
            "lfem4x05.py": None,
            "lfread.py": None,
            "lfsearch.py": None,
            "lft55xx.py": None,
            "lfverify.py": None,
            "lfwrite.py": None,
            "mifare.py": None,
            "read.py": None,
            "scan.py": None,
            "sniff.py": None,
            "tagtypes.py": self.genTagFalseTypes,

            # "trans.py": None,

            "write.py": None,
            "actbase.py": None,

            "activity_main.py": None,
            "activity_tools.py": None,
            "activity_update.py": None,  # 安装APP必备的act咯

            "actmain.py": None,
            "actstack.py": None,
            "application.py": None,
            "audio.py": None,
            "audio_copy.py": None,
            "batteryui.py": None,
            "bytestr.py": None,
            "config.py": None,
            "debug.py": None,
            "games.py": None,
            "hmi_driver.py": None,
            "images.py": None,
            "keymap.py": None,
            "resources.py": None,
            "settings.py": None,
            "template.py": None,

            # "activity_debug.py": None,

            "update.py": None,
            "version.py": self.genVerAll,
            "widget.py": None,
            "ymodem.py": None,

            # "test.py": None,

            "gadget_linux.py": None,
            "vsp_tools.py": None,

            # 服务承载
            "serpool.py": None,
            "sermain.py": None,

        }

    def genTagFalseTypes(self, content):
        """
            生成tagtypes，XR版本需要禁用iclass的读写
        :return:
        """

        content = genTagTypesMapRow(content, "ICLASS_ELITE", False, False)
        content = genTagTypesMapRow(content, "ICLASS_LEGACY", False, False)
        return content

    def getTypeName(self):
        return TYPE_ICOPY_XR


class XSGen(BaseICopyGenerator):
    """
        单独实现的ICopyXR的代码生成工具类
    """

    def onGetGenFileMap(self):
        return {
            "appfiles.py": None,
            "commons.py": None,
            "container.py": None,
            "executor.py": None,
            "felicaread.py": None,
            "hf14ainfo.py": None,
            "hf14aread.py": None,
            "hffelica.py": None,
            "hficlass.py": self.genIClassKeys,
            "hfmfkeys.py": None,
            "hfmfread.py": None,
            "hfmfuinfo.py": None,
            "hfmfuread.py": None,
            "hfmfuwrite.py": None,
            "hfmfwrite.py": None,
            "hfsearch.py": None,

            # "iclassencrypt.py": None,

            "iclassread.py": None,
            "iclasswrite.py": None,
            "hf15read.py": None,
            "hf15write.py": None,
            "legicread.py": None,
            "lfem4x05.py": None,
            "lfread.py": None,
            "lfsearch.py": None,
            "lft55xx.py": None,
            "lfverify.py": None,
            "lfwrite.py": None,
            "mifare.py": None,
            "read.py": None,
            "scan.py": None,
            "sniff.py": None,
            "tagtypes.py": None,

            # "trans.py": None,

            "write.py": None,
            "actbase.py": None,

            "activity_main.py": None,
            "activity_tools.py": None,
            "activity_update.py": None,  # 安装APP必备的act咯

            "actmain.py": None,
            "actstack.py": None,
            "application.py": None,
            "audio.py": None,
            "audio_copy.py": None,
            "batteryui.py": None,
            "bytestr.py": None,
            "config.py": None,
            "debug.py": None,
            "games.py": None,
            "hmi_driver.py": None,
            "images.py": None,
            "keymap.py": None,
            "resources.py": None,
            "settings.py": None,
            "template.py": None,

            # "activity_debug.py": None,

            "update.py": None,
            "version.py": self.genVerAll,
            "widget.py": None,
            "ymodem.py": None,

            # "test.py": None,

            "gadget_linux.py": None,
            "vsp_tools.py": None,

            # 服务承载
            "serpool.py": None,
            "sermain.py": None,
            "server_iclassse.py": None,
        }

    def genIClassKeys(self, content):
        """
            生成秘钥组
        :return:
        """
        # 计算加解密所需要的秘钥
        key = self.calcKey()
        # 将iclass的秘钥文件进行加密
        aes_obj = AES.new(
            key.encode("utf-8"),
            AES.MODE_CFB,
            "VB1v2qvOinVNIlv2".encode()
        )
        iclass_key = base64.b64encode(  # 加密完成后用BASE64进行编码
            aes_obj.encrypt(  # 再进行加密
                icopy_iclass.KEYS.encode("utf-8")  # 先转换为字节流
            )
        ).decode("utf-8")  # BASE64编码完成后转换为UTF-8字符串
        # 然后替换打包进py中
        return self.genAttrKV(content, "KEYS_ICLASS_NIKOLA", iclass_key)

    def getTypeName(self):
        return TYPE_ICOPY_XS


class ZHGen(BaseICopyGenerator):
    """
        中文版本
    """

    def onGetGenFileMap(self):
        return {
            "appfiles.py": None,
            "commons.py": None,
            "container.py": None,
            "executor.py": None,
            "felicaread.py": None,
            "hf14ainfo.py": None,
            "hf14aread.py": None,
            "hffelica.py": None,
            "hficlass.py": None,
            "hfmfkeys.py": None,
            "hfmfread.py": None,
            "hfmfuinfo.py": None,
            "hfmfuread.py": None,
            "hfmfuwrite.py": None,
            "hfmfwrite.py": None,
            "hfsearch.py": None,
            "hf15read.py": None,
            "hf15write.py": None,
            "legicread.py": None,
            "lfem4x05.py": None,
            "lfread.py": None,
            "lfsearch.py": None,
            "lft55xx.py": None,
            "lfverify.py": None,
            "lfwrite.py": None,
            "mifare.py": None,
            "read.py": None,
            "scan.py": None,
            "sniff.py": None,
            "tagtypes.py": self.genTagFalseTypes,

            # "trans.py": None,

            "write.py": None,
            "actbase.py": None,

            "activity_main.py": None,
            "activity_tools.py": None,
            "activity_update.py": None,  # 安装APP必备的act咯

            "actmain.py": None,
            "actstack.py": None,
            "application.py": None,
            "audio.py": None,
            "audio_copy.py": None,
            "batteryui.py": None,
            "bytestr.py": None,
            "config.py": None,
            "debug.py": None,
            "games.py": None,
            "hmi_driver.py": None,
            "images.py": None,
            "keymap.py": None,
            "resources.py": None,
            "settings.py": None,
            "template.py": None,

            # "activity_debug.py": None,

            "update.py": None,
            "version.py": self.genVerAll,
            "widget.py": None,
            "ymodem.py": None,

            # "test.py": None,

            "gadget_linux.py": None,
            "vsp_tools.py": None,

            # 服务承载
            "serpool.py": None,
            "sermain.py": None,

        }

    def genTagFalseTypes(self, content):
        """
            生成tagtypes，XR版本需要禁用iclass的读写
        :return:
        """

        content = genTagTypesMapRow(content, "ICLASS_ELITE", False, False)
        content = genTagTypesMapRow(content, "ICLASS_LEGACY", False, False)
        return content

    def getTypeName(self):
        return TYPE_ICOPY_ZH


class UKGen(XSGen):
    """
        ICopy-XS(UK) 版本的生产定义
        由于UK版本基本与XS一样，仅仅版本标识符和名称有不同
        我们可以直接复用XS的定义
        只需要修改不同的项目
    """

    def getTypeName(self):
        return TYPE_ICOPY_UK


class XSCGen(XSGen):
    """
        iCopy-XSC(CN) 版本由跃力安防科技发起定制
        是属于中文版本，但是开放了iClass功能，因此
        我们可以直接复用XS的定义
        只需要修改不同的项目
    """

    def getTypeName(self):
        """
            类型名称要用XSC，因为这是个独立的设备类型，虽然与XS版本有极大的共性
        :return:
        """
        return TYPE_ICOPY_XSC

    def genTYP(self, content):
        """
            这个是设备的类型名称
        :param content:
        :return:
        """
        return self.genAttrKV(content, "TYP", "")


# 设备版本名到类的映射列表
TYPE_TO_CLZ_MAPS = {
    TYPE_ICOPY_D: DGen,
    TYPE_ICOPY_F: FGen,

    TYPE_ICOPY_X: XGen,
    TYPE_ICOPY_XR: XRGen,
    TYPE_ICOPY_XS: XSGen,

    TYPE_ICOPY_ZH: ZHGen,
    TYPE_ICOPY_UK: UKGen,
    TYPE_ICOPY_XSC: XSCGen,
}


def getICopyClz4Name(name):
    """
        获得从设备类型名称到设备类型实现类的映射
    :param name:
    :return:
    """
    return TYPE_TO_CLZ_MAPS.get(name, None)


def get_device_type_int(typ_str):
    """
        获取设备的类型锁映射的int型
    :return:
    """
    typ_str = TYPE_TO_INT_MAPS.get(typ_str, -1)

    if typ_str == -1:
        msg = "get_device_type_int() -> 类型异常，无法将不被识别的类型转换为int类型的映射。"
        print(msg)
        raise msg

    return typ_str


def get_device_type_str(type_int):
    """
        从ICOPY的数据中得到的int类型的
        值，转换为实际的字符串值
    :param type_int:
    :return:
    """
    ret = []

    for key, value in TYPE_TO_INT_MAPS.items():
        # 如果存在映射表里，则取出
        if type_int == value:
            ret.append(key)

    if len(ret) != 1:
        raise Exception("开发者映射异常，映射表里面存在多个同样的值映射到不同的键：", ret)
    else:
        typ = ret[0]

    if typ is None:
        print("get_device_type_int() -> 类型异常，无法将不被识别的类型转换为int类型的映射。")
        return None

    return typ


def get_type_factory_name(typ_str):
    """
        获得版本对应的工程详细名称
    :return:
    """
    return TYPE_TO_FAC_MAPS[typ_str]
