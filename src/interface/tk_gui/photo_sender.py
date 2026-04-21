import tkinter
from tkinter import ttk
from typing import Callable
import io
import requests

from loguru import logger

from src.talos_app import App
from PIL import ImageTk

class TKPhotoSender(tkinter.Toplevel):
    def __init__(
        self,
        parent,
        app: App,
        photo: ImageTk.PhotoImage,
        update_gui_callback: Callable[[], None],
    ):
        super().__init__(parent)
        self.title("Send Photo")
        self.update_idletasks()
        self.geometry("")
        self.parent = parent
        self.app = app
        self.photo = photo
        self.update_gui_callback = update_gui_callback
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Photo preview
        preview_frame = ttk.Frame(self)
        preview_frame.pack(pady=10)
        photo_label = ttk.Label(preview_frame, image=self.photo)
        photo_label.pack()

        # Email input
        input_frame = ttk.Frame(self)
        input_frame.pack(pady=10, fill="x", padx=20)

        ttk.Label(input_frame, text="Recipient Name:").pack(anchor="w")
        self.name_var = tkinter.StringVar()
        self.name_entry = ttk.Entry(input_frame, textvariable=self.name_var, width=40)
        self.name_entry.pack(fill="x", pady=4)

        ttk.Label(input_frame, text="Recipient Email:").pack(anchor="w")
        self.email_var = tkinter.StringVar()
        self.email_entry = ttk.Entry(input_frame, textvariable=self.email_var, width=40)
        self.email_entry.pack(fill="x", pady=4)

        # Buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Send", command=self.on_send).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.on_close).pack(side="left", padx=5)

        self.update_idletasks()
        self.after_idle(self._set_modal_grab)

    def _set_modal_grab(self):
        self.grab_set()
        self.focus_set()
        self.name_entry.focus()

    def on_send(self):
        name = self.name_var.get().strip()
        email = self.email_var.get().strip()
        if not name:
            logger.warning("Name is required")
        if not email:
            logger.warning("Email is required")
        self.send_photo(name, email)

    def send_photo(self, name: str, email: str):
        SERVER_URL = "192.168.0.51:8080/send_imageroute"

        # Convert PhotoImage back to bytes
        img_bytes = io.BytesIO()
        ImageTk.getimage(self.photo).save(img_bytes, format="PNG")
        img_bytes.seek(0)

        try:
            response = requests.post(
                SERVER_URL,
                data={"name": name, "email": email},
                files={"photo": ("photo.png", img_bytes, "image/png")},
            )
            response.raise_for_status()
            self.on_close()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Send Failed: {e}")
            self.on_close()

    def on_close(self):
        self.grab_release()
        self.update_gui_callback()
        self.destroy()