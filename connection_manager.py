import tkinter
from tkinter import ttk

class ConnectionManager(tkinter.Toplevel):
    def __init__(self, parent, connections_list, config):
        super().__init__(parent)
        self.title("Connection Manager")
        self.geometry("350x300")
        self.connections_list = connections_list
        self.config = config
        self.parent = parent

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.list_frame = ttk.Frame(self)
        self.list_frame.pack(pady=10, fill="x")

        # Controls for adding connections_list
        control_frame = ttk.Frame(self)
        control_frame.pack(pady=10, fill="x")

        ttk.Button(control_frame, text="Add", command=self.add_connection).pack(side="left", padx=5)
        self.render_list()
    
    def on_close(self):
        self.grab_release()
        self.destroy()

    def render_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        for index, (host, port) in enumerate(self.connections_list):
            row = ttk.Frame(self.list_frame)
            row.pack(fill="x", pady=2, padx=5)

            ttk.Label(row, text=f"{host}:{port}").pack(side="left", expand=True, fill="x")
            ttk.Button(row, text="X", command=lambda i=index: self.remove_item(i)).pack(side="right")

    def remove_item(self, index):
        if 0 <= index < len(self.connections_list):
            self.connections_list.pop(index)
            self.render_list()
    
    def add_connection(self):
        new_connection = self.get_host_port(self)
        if new_connection:
            self.connections_list.append(new_connection)
            self.parent.add_connection(socket_host = new_connection[0], socket_port = new_connection[1])
            self.render_list()

    def get_host_port(self, parent=None):
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
              result = (host, port)
              popup.destroy()

      ttk.Button(popup, text="Submit", command=submit).pack(pady=15)
      popup.bind("<Return>", lambda e: submit())

      popup.wait_window()  # wait for the popup to close
      return result
