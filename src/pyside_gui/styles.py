import darkdetect

IS_SYSTEM_DARK = darkdetect.isDark()
# IS_SYSTEM_DARK = False  # Temporarily disable dark mode detection for testing

# Colors remain the same
COLOR_PALLETTE = {
    "black": "#000000",
    "gray_1": "#1c1c1c",
    "gray_2": "#3a3a3a",
    "gray_3": "#7A7A7A",
    "gray_4": "#c7c7c7",
    "gray_5": "#e5e5e5",
    "white": "#ffffff",
}

THEME_WINDOW_BG_COLOR = (
    COLOR_PALLETTE["gray_1"] if IS_SYSTEM_DARK else COLOR_PALLETTE["white"]
)
THEME_FRAME_BG_COLOR = (
    COLOR_PALLETTE["gray_2"] if IS_SYSTEM_DARK else COLOR_PALLETTE["gray_5"]
)


# Qt Stylesheets
def get_main_stylesheet():
    """Generate Qt stylesheet based on theme"""
    if IS_SYSTEM_DARK:
        return """
            /* QMainWindow, QDialog {
                background-color: #1c1c1c;
                color: #ffffff;
            } */
            QFrame {
                /* background-color: #2B2B2B; */
                border: 2px solid #3a3a3a;
                border-radius: 10px;
            }
            QPushButton {
                /* background-color: #1c1c1c;
                color: #e5e5e5; */
                border: 2px solid #3a3a3a;
                border-radius: 10px;
                padding: 10px;
                font: bold 16px "Cascadia Code";
            }
            /* QPushButton:hover {
                background-color: #2B2B2B;
            }
            QPushButton:disabled {
                color: #7A7A7A;
            } */
            QLabel {
                /* color: #ffffff; */
                font: 16px "Cascadia Code";
            }
            QComboBox {
                /* background-color: #1c1c1c;
                color: #e5e5e5; */
                border: 2px solid #3a3a3a;
                border-radius: 5px;
                padding: 5px;
            }
            /* QComboBox:hover {
                background-color: #2B2B2B;
            } */
            QCheckBox {
                /* color: #ffffff; */
                font: 16px "Cascadia Code";
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
        """
    else:
        return """
            /* QMainWindow, QDialog {
                background-color: #ffffff;
                color: #000000;
            } */
            QFrame {
                /* background-color: #DADADA; */
                border: 2px solid #c7c7c7;
                border-radius: 10px;
            }
            QPushButton {
                /* background-color: #e5e5e5; 
                color: #1c1c1c; */
                border: 2px solid #c7c7c7;
                border-radius: 10px;
                padding: 10px;
                font: bold 16px "Cascadia Code";
            }
            /* QPushButton:hover {
                background-color: #c7c7c7;
            }
            QPushButton:disabled {
                color: #7A7A7A;
            } */
            QLabel {
                /* color: #000000; */
                font: 16px "Cascadia Code";
            }
            QComboBox {
                /* background-color: #e5e5e5;
                color: #1c1c1c; */
                border: 2px solid #c7c7c7;
                border-radius: 5px;
                padding: 5px;
            }
            /*QComboBox:hover {
                background-color: #c7c7c7;
            }*/
            QCheckBox {
                /* color: #000000; */
                font: 16px "Cascadia Code";
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
        """

