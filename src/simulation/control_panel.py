"""Small Tk control panel for the interactive deterministic simulation."""

from __future__ import annotations

from src.robot_state import RobotStateSnapshot

from .controls import KEYBOARD_HELP_TEXT, InteractiveSimulationController


POLAR_HOLD_DIRECTIONS = (
    ("", None, "ALT +", (0, 1), "", None),
    ("AZ -", (-1, 0), "", None, "AZ +", (1, 0)),
    ("", None, "ALT -", (0, -1), "", None),
)

CARTESIAN_HOLD_DIRECTIONS = (
    ("X -", (-1, 0, 0)),
    ("X +", (1, 0, 0)),
    ("Y -", (0, -1, 0)),
    ("Y +", (0, 1, 0)),
    ("Z -", (0, 0, -1)),
    ("Z +", (0, 0, 1)),
)


class TkSimulationControlPanel:
    """Buttons call the controller, which calls Publishers; never the viewer."""

    def __init__(self, controller: InteractiveSimulationController) -> None:
        try:
            import tkinter as tk
            from tkinter import messagebox, ttk
        except ImportError as error:  # pragma: no cover - platform Python packaging
            raise RuntimeError(
                "Tkinter is required for the simulation control panel"
            ) from error

        self._tk = tk
        self._ttk = ttk
        self._messagebox = messagebox
        self.controller = controller
        self._open = True
        self.root = tk.Tk()
        self.root.title("Commander Simulation Controls")
        self.root.geometry("430x790")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.attributes("-topmost", True)

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Robot Controls",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        robot_row = ttk.Frame(container)
        robot_row.pack(fill="x", pady=(12, 6))
        ttk.Label(robot_row, text="Selected robot:").pack(side="left")
        self.robot_id = tk.StringVar(value=controller.selected_robot_id)
        ttk.OptionMenu(
            robot_row,
            self.robot_id,
            controller.selected_robot_id,
            *controller.robot_ids,
            command=self._select_robot,
        ).pack(side="right", fill="x", expand=True, padx=(10, 0))

        backend_row = ttk.Frame(container)
        backend_row.pack(fill="x", pady=6)
        ttk.Label(backend_row, text="Backend:").pack(side="left")
        self.backend = tk.StringVar(value=controller.selected_backend)
        self.backend_menu = ttk.Combobox(
            backend_row,
            textvariable=self.backend,
            state="readonly",
            width=12,
        )
        self.backend_menu.bind("<<ComboboxSelected>>", self._select_backend)
        self.backend_menu.pack(side="right", fill="x", expand=True, padx=(10, 0))
        self._refresh_backend_menu()

        action_row = ttk.Frame(container)
        action_row.pack(fill="x", pady=6)
        ttk.Button(
            action_row, text="HOME", command=controller.home_selected
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            action_row, text="STOP", command=controller.stop_selected
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Button(
            container,
            text="CLEAR SIM FAULT",
            command=controller.clear_selected_simulation_fault,
        ).pack(fill="x", pady=(0, 6))

        ttk.Label(container, text="Target presets").pack(anchor="w", pady=(12, 4))
        preset_row = ttk.Frame(container)
        preset_row.pack(fill="x")
        self.preset_buttons = []
        for preset in (1, 2, 3):
            button = ttk.Button(
                preset_row,
                text=str(preset),
                command=lambda value=preset: controller.move_to_preset(value),
            )
            button.pack(side="left", fill="x", expand=True, padx=2)
            self.preset_buttons.append(button)

        ttk.Label(container, text="Speed (0-255)").pack(anchor="w", pady=(12, 0))
        self.speed = tk.IntVar(
            value=controller.get_selected_speed()
        )
        speed_scale = ttk.Scale(
            container,
            from_=0,
            to=255,
            variable=self.speed,
            command=self._show_speed,
        )
        speed_scale.pack(fill="x")
        speed_scale.bind("<ButtonRelease-1>", self._commit_speed)
        self.speed_label = ttk.Label(container, text=str(self.speed.get()))
        self.speed_label.pack(anchor="e")

        ttk.Label(container, text="Polar movement (press and hold)").pack(
            anchor="w", pady=(12, 4)
        )
        polar = ttk.Frame(container)
        polar.pack()
        self._movement_grid(
            polar,
            POLAR_HOLD_DIRECTIONS,
            controller.start_polar_continuous,
            controller.stop_continuous,
        )

        ttk.Label(
            container,
            text="Cartesian movement (press and hold)",
        ).pack(anchor="w", pady=(12, 4))
        cartesian = ttk.Frame(container)
        cartesian.pack(fill="x")
        for label, values in CARTESIAN_HOLD_DIRECTIONS:
            button = ttk.Button(cartesian, text=label)
            self._bind_hold_button(
                button,
                lambda xyz=values: controller.start_cartesian_continuous(*xyz),
                controller.stop_continuous,
            )
            button.pack(side="left", fill="x", expand=True, padx=1)

        self.mapping_status = tk.StringVar(value="Mapping: unknown")
        ttk.Label(container, textvariable=self.mapping_status).pack(
            anchor="w", pady=(8, 10)
        )

        self.telemetry = tk.StringVar(value="Waiting for state...")
        ttk.Label(
            container,
            textvariable=self.telemetry,
            wraplength=400,
            justify="left",
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            container, text="Print full telemetry", command=controller.print_telemetry
        ).pack(fill="x", pady=(10, 0))

        keybinds = ttk.LabelFrame(container, text="Keyboard (focus the 3D window)")
        keybinds.pack(fill="x", pady=(12, 0))
        ttk.Label(
            keybinds,
            text=KEYBOARD_HELP_TEXT,
            justify="left",
            font=("Consolas", 9),
        ).pack(anchor="w", padx=8, pady=6)

    def poll(self, snapshots: tuple[RobotStateSnapshot, ...]) -> bool:
        if not self._open:
            return False
        selected = self.controller.selected_robot_id
        if self.robot_id.get() != selected:
            self.robot_id.set(selected)
            self.speed.set(self.controller.get_selected_speed())
            self._refresh_backend_menu()
        if self.backend.get() != self.controller.selected_backend:
            self.backend.set(self.controller.selected_backend)
        self.backend_menu.configure(
            values=self.controller.available_backends()
        )
        preset_state = (
            "disabled" if self.controller.selected_backend == "real" else "normal"
        )
        for button in self.preset_buttons:
            button.configure(state=preset_state)
        state = next(
            snapshot for snapshot in snapshots if snapshot.robot_id == selected
        )
        self.mapping_status.set(
            f"Mapping: {state.joint_mapping_quality.value.replace('_', ' ')}"
        )
        pose = state.logical_pose
        if pose is not None:
            self.telemetry.set(
                f"backend={self.controller.selected_backend.upper()}   "
                f"source={state.source_type.value}\n"
                f"t={state.timestamp:.2f}s   state={state.movement_state}\n"
                f"az={pose.azimuth:.2f}   alt={pose.altitude:.2f}\n"
                f"X={pose.x:.2f}   Y={pose.y:.2f}   Z={pose.z:.2f}\n"
                f"homed={state.homed}   fault={state.fault or 'none'}"
                f"\ncommand_error={self.controller.last_error[selected] or 'none'}"
            )
        try:
            self.root.update_idletasks()
            self.root.update()
        except self._tk.TclError as error:
            print(f"Simulation control panel closed: {error}")
            self._open = False
        return self._open

    def close(self) -> None:
        if self._open:
            try:
                self.root.destroy()
            except self._tk.TclError:
                pass
        self._open = False

    def _on_close(self) -> None:
        try:
            self.root.destroy()
        finally:
            self._open = False

    def _select_robot(self, robot_id: str) -> None:
        self.controller.select_robot(robot_id)
        self.speed.set(self.controller.get_selected_speed())
        self.speed_label.configure(text=str(self.speed.get()))
        self._refresh_backend_menu()

    def _select_backend(self, _event=None) -> None:
        requested = self.backend.get()
        if requested == "real" and not self._messagebox.askyesno(
            "Enable real robot",
            f"Send controls to the real {self.controller.selected_robot_id} robot?",
            icon="warning",
        ):
            self.backend.set(self.controller.selected_backend)
            return
        self.controller.set_selected_backend(requested)

    def _refresh_backend_menu(self) -> None:
        values = self.controller.available_backends()
        self.backend_menu.configure(values=values)
        self.backend.set(self.controller.selected_backend)

    def _show_speed(self, value: str) -> None:
        self.speed_label.configure(text=str(round(float(value))))

    def _commit_speed(self, _event) -> None:
        self.controller.set_selected_speed(round(self.speed.get()))

    def _movement_grid(self, parent, rows, start_callback, stop_callback) -> None:
        for row_index, row in enumerate(rows):
            for column in range(0, len(row), 2):
                label, values = row[column], row[column + 1]
                if not label:
                    continue
                parent.columnconfigure(column // 2, weight=1)
                button = self._ttk.Button(parent, text=label)
                self._bind_hold_button(
                    button,
                    lambda movement=values: start_callback(*movement),
                    stop_callback,
                )
                button.grid(
                    row=row_index,
                    column=column // 2,
                    padx=2,
                    pady=2,
                    sticky="ew",
                )

    @staticmethod
    def _bind_hold_button(button, start_callback, stop_callback) -> None:
        button.bind("<ButtonPress-1>", lambda _event: start_callback())
        button.bind("<ButtonRelease-1>", lambda _event: stop_callback())
