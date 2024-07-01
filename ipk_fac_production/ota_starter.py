import sys

sys.path.append("../ipk_pack_center")


if __name__ == '__main__':
    import gui_main_ota
    otagui = gui_main_ota.OTAGui()
    otagui.gui_main_start()
