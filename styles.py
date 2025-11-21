import darkdetect

IS_SYSTEM_DARK = darkdetect.isDark()
THEME_WINDOW_BG_COLOR = "#1c1c1c" if IS_SYSTEM_DARK else "#fafafa"
THEME_FRAME_BG_COLOR = "#2B2B2B" if IS_SYSTEM_DARK else "#DADADA"


COLOR_PALLETTE = {
    "black": "#000000",
    "gray_1": "#1c1c1c",
    "gray_2": "#3a3a3a",
    "gray_3": "#7A7A7A",
    "gray_4": "#c7c7c7",
    "gray_5": "#e5e5e5",
    "white": "#ffffff",
}
LIGHT_BORDER_STYLE = {
    "border_width": 2,
    "border_color": COLOR_PALLETTE["gray_4"],
}
DARK_BORDER_STYLE = {
    "border_width": 2,
    "border_color": COLOR_PALLETTE["gray_2"],
}
BORDER_STYLE = DARK_BORDER_STYLE if IS_SYSTEM_DARK else LIGHT_BORDER_STYLE

CONTROL_BTN_STYLE = {
    "corner_radius": 10,
    "font": ("Cascadia Code", 16, "bold"),
}
LIGHT_BTN_STYLE = {
    "fg_color": COLOR_PALLETTE["gray_5"],
    "text_color": COLOR_PALLETTE["gray_1"],
    "text_color_disabled": COLOR_PALLETTE["gray_3"],
    "hover_color": COLOR_PALLETTE["gray_4"],
    "bg_color": THEME_WINDOW_BG_COLOR,
    **BORDER_STYLE,
}
DARK_BTN_STYLE = {
    "fg_color": COLOR_PALLETTE["gray_1"],
    "text_color": COLOR_PALLETTE["gray_5"],
    "text_color_disabled": COLOR_PALLETTE["gray_3"],
    "hover_color": COLOR_PALLETTE["gray_2"],
    "bg_color": THEME_WINDOW_BG_COLOR,
    **BORDER_STYLE,
}
BTN_STYLE = DARK_BTN_STYLE if IS_SYSTEM_DARK else LIGHT_BTN_STYLE

CONTROL_BTN_GRID_FIT_STYLE = {
    "padx": 2,
    "pady": 2,
    "ipady": 25,
    "ipadx": 25,
    "sticky": "nsew",
}

LIGHT_OPTIONS_MENU_STYLE = {
    "button_color": COLOR_PALLETTE["gray_4"],
    "button_hover_color": COLOR_PALLETTE["gray_3"],
    "fg_color": COLOR_PALLETTE["gray_5"],
    "text_color": COLOR_PALLETTE["gray_1"],
}
DARK_OPTIONS_MENU_STYLE = {
    "button_color": COLOR_PALLETTE["gray_2"],
    "button_hover_color": COLOR_PALLETTE["gray_3"],
    "fg_color": COLOR_PALLETTE["gray_1"],
    "text_color": COLOR_PALLETTE["gray_5"],
}
OPTIONS_MENU_STYLE = (
    DARK_OPTIONS_MENU_STYLE if IS_SYSTEM_DARK else LIGHT_OPTIONS_MENU_STYLE
)
