import tkinter
from tkinter import ttk
from typing import Callable

from loguru import logger

from src.config import ROBOT_CONFIGS, ConnectionConfig, editor
from src.talos_app import App


class TKConnectionManager(tkinter.Toplevel):
    def __init__(
        self,
        parent,
        app: App,
        update_gui_callback: Callable[[], None],
        connections: list[str],
    ):
        super().__init__(parent)
        self.title("Connection Manager")
        self.geometry("350x300")
        self.parent = parent
        self.app = app
        self.connections = connections
        self.update_gui_callback = update_gui_callback
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.list_frame = ttk.Frame(self)
        self.list_frame.pack(pady=10, fill="x")

        # Controls for adding connections
        control_frame = ttk.Frame(self)
        control_frame.pack(pady=10, fill="x")

        ttk.Button(control_frame, text="Add", command=self.show_host_port_input).pack(
            side="left", padx=5
        )
        self.render_list()

    def on_close(self):
        self.grab_release()
        self.destroy()

    def render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        ttk.Label(
            self.list_frame, text="Available Configs:", font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=5, pady=(5, 0))
        for cfg in ROBOT_CONFIGS.values():
            frame = ttk.Frame(self.list_frame)
            frame.pack(fill="x", padx=10, pady=2)

            ttk.Label(frame, text=f"{cfg.socket_host}:{cfg.socket_port}").pack(
                side="left", fill="x", expand=True
            )
            ttk.Button(
                frame,
                text="Connect",
                command=lambda hostname=cfg.socket_host: self.add_from_config(hostname),
            ).pack(side="right")

        ttk.Label(
            self.list_frame, text="Current Connections:", font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=5, pady=(5, 0))
        ttk.Separator(self.list_frame, orient="horizontal").pack(fill="x", pady=5)

        for hostname in self.connections:
            row = ttk.Frame(self.list_frame)
            row.pack(fill="x", pady=2, padx=5)
            ttk.Label(row, text=f"{hostname}").pack(side="left", expand=True, fill="x")
            ttk.Button(
                row, text="X", command=lambda h=hostname: self.remove_connection(h)
            ).pack(side="right")

    def remove_connection(self, hostname):
        if hostname in self.connections:
            self.app.remove_connection(hostname)
            self.connections = [h for h in self.connections if h != hostname]
            self.update_gui_callback()
            self.render_list()

    def add_connection(self, conn: ConnectionConfig):
        self.app.open_connection(conn.socket_host)
        self.update_gui_callback()
        self.connections.append(conn.socket_host)
        self.render_list()

    def add_from_config(self, hostname):
        self.app.open_connection(hostname)
        self.connections.append(hostname)
        self.update_gui_callback()
        self.render_list()

    def show_host_port_input(self, parent=None):
        """Open a popup to request host and port, return them as a (host, port) tuple."""
        popup = tkinter.Toplevel(parent)
        popup.title("Enter Host and Port")
        popup.resizable(False, False)
        popup.grab_set()  # make it modal (block interaction with parent)
        popup.transient(parent)

        ttk.Label(popup, text="Host:").pack(pady=(15, 5))
        host_var = tkinter.StringVar()
        ttk.Entry(popup, textvariable=host_var).pack(fill="x", padx=20)

        ttk.Label(popup, text="Port:").pack(pady=(10, 5))
        port_var = tkinter.StringVar()
        ttk.Entry(popup, textvariable=port_var).pack(fill="x", padx=20)

        ttk.Label(popup, text="Camera Address:").pack(pady=(10, 5))
        camera_var = tkinter.StringVar()
        ttk.Entry(popup, textvariable=camera_var).pack(fill="x", padx=20)

        def submit():
            host = host_var.get().strip()
            port_str = port_var.get().strip()
            camera_str = camera_var.get().strip()

            if not host or not port_str or not camera_str:
                logger.warning("Host, port, and camera inputs are required.")
                return

            valid, conf, error_msg = editor.validate_connection_config(
                host, port_str, camera_str
            )
            if not valid or conf is None:
                logger.warning(f"Invalid connection config: {error_msg}")
                return

            editor.add_config(conf)
            popup.destroy()
            self.add_connection(conf)

        ttk.Button(popup, text="Submit", command=submit).pack(pady=15)
        popup.bind("<Return>", lambda e: submit())
