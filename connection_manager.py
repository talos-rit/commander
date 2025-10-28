import tkinter
from tkinter import ttk

class ConnectionManager(tkinter.Toplevel):
    def __init__(self, parent, connections, config):
        super().__init__(parent)
        self.title("Connection Manager")
        self.geometry("350x300")
        self.connections = connections
        self.config = config
        self.parent = parent

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.list_frame = ttk.Frame(self)
        self.list_frame.pack(pady=10, fill="x")

        # Controls for adding connections
        control_frame = ttk.Frame(self)
        control_frame.pack(pady=10, fill="x")

        ttk.Button(control_frame, text="Add", command=self.show_host_port_input).pack(side="left", padx=5)
        self.render_list()
    
    def on_close(self):
        self.grab_release()
        self.destroy()

    def render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        ttk.Label(self.list_frame, text="Available Configs:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5, pady=(5, 0))
        for _, cfg in self.config.items():
            if "socket_host" not in cfg or "socket_port" not in cfg:
                print("config missing socket_host or socket_port, skipping")
                continue
            frame = ttk.Frame(self.list_frame)
            frame.pack(fill="x", padx=10, pady=2)

            ttk.Label(frame, text=f"{cfg['socket_host']}:{cfg['socket_port']}").pack(side="left", fill="x", expand=True)
            ttk.Button(
                frame,
                text="Connect",
                command=lambda hostname=cfg["socket_host"]: self.add_from_config(hostname)
            ).pack(side="right")

        ttk.Label(self.list_frame, text="Current Connections:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5, pady=(5, 0))
        ttk.Separator(self.list_frame, orient="horizontal").pack(fill="x", pady=5)

        for _, host in enumerate(self.connections):

            row = ttk.Frame(self.list_frame)
            row.pack(fill="x", pady=2, padx=5)

            ttk.Label(row, text=f"{host}:{self.config[host]["socket_port"]}").pack(side="left", expand=True, fill="x")
            ttk.Button(
                row, 
                text="X", 
                command=lambda h=host: self.remove_connection(h)
            ).pack(side="right")

    def remove_connection(self, hostname):
        if hostname in self.connections:
            self.parent.close_connection(hostname)
            self.render_list()
    
    def add_connection(self, new_connection):
        self.parent.open_new_connection(new_connection[0], new_connection[1])
        self.render_list()
    
    def add_from_config(self, hostname):
        self.parent.open_connection(hostname)
        self.render_list()

    def show_host_port_input(self, parent=None):
      """Open a popup to request host and port, return them as a (host, port) tuple."""
      popup = tkinter.Toplevel(parent)
      popup.title("Enter Host and Port")
      popup.geometry("300x160")
      popup.resizable(False, False)
      popup.grab_set()  # make it modal (block interaction with parent)
      popup.transient(parent)

      ttk.Label(popup, text="Host:").pack(pady=(15, 5))
      host_var = tkinter.StringVar()
      ttk.Entry(popup, textvariable=host_var).pack(fill="x", padx=20)

      ttk.Label(popup, text="Port:").pack(pady=(10, 5))
      port_var = tkinter.StringVar()
      ttk.Entry(popup, textvariable=port_var).pack(fill="x", padx=20)

      result = None
      def submit():
          nonlocal result
          host = host_var.get().strip()
          port = port_var.get().strip()
          if host and port:
              #TODO: input validation
              result = (host, port)
              popup.destroy()
          self.add_connection(result)

      ttk.Button(popup, text="Submit", command=submit).pack(pady=15)
      popup.bind("<Return>", lambda e: submit())
