"""Small Tk control panel for the interactive deterministic simulation."""

from __future__ import annotations

from src.robot_state import RobotStateSnapshot

from .controls import KEYBOARD_HELP_TEXT, InteractiveSimulationController


POLAR_HOLD_DIRECTIONS = (
    ("", None, "Claw rotate +", (0, 1), "", None),
    ("Base rotate -", (-1, 0), "", None, "Base rotate +", (1, 0)),
    ("", None, "Claw rotate -", (0, -1), "", None),
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
        self.root.geometry("500x790")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<FocusOut>", self._stop_jog_if_window_loses_focus)
        self.root.attributes("-topmost", True)

        canvas = tk.Canvas(self.root, width=480, height=750)
        scrollbar = tk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        container = ttk.Frame(canvas, padding=12)

        container.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self._scroll_canvas = canvas
        self.root.bind_all("<MouseWheel>", self._scroll_with_mouse_wheel)
        self.root.bind_all("<Button-4>", self._scroll_with_mouse_wheel)
        self.root.bind_all("<Button-5>", self._scroll_with_mouse_wheel)

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
        self.virtual_controls = ttk.LabelFrame(container, text="Simulation controls")
        self.clear_fault_button = ttk.Button(
            self.virtual_controls,
            text="CLEAR SIM FAULT",
            command=controller.clear_selected_simulation_fault,
        )
        self.clear_fault_button.pack(fill="x", pady=(0, 6))

        ttk.Label(self.virtual_controls, text="Target presets").pack(anchor="w", pady=(8, 4))
        preset_row = ttk.Frame(self.virtual_controls)
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

        ttk.Label(self.virtual_controls, text="Speed (0-255)").pack(anchor="w", pady=(12, 0))
        self.speed = tk.IntVar(
            value=controller.get_selected_speed()
        )
        self.speed_scale = ttk.Scale(
            self.virtual_controls,
            from_=0,
            to=255,
            variable=self.speed,
            command=self._show_speed,
        )
        self.speed_scale.pack(fill="x")
        self.speed_scale.bind("<ButtonRelease-1>", self._commit_speed)
        self.speed_label = ttk.Label(self.virtual_controls, text=str(self.speed.get()))
        self.speed_label.pack(anchor="e")

        ttk.Label(container, text="Direct hardware axes (press and hold)").pack(
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
            self.virtual_controls,
            text="Cartesian movement (press and hold)",
        ).pack(anchor="w", pady=(12, 4))
        cartesian = ttk.Frame(self.virtual_controls)
        cartesian.pack(fill="x")
        self.cartesian_buttons = []
        for label, values in CARTESIAN_HOLD_DIRECTIONS:
            button = ttk.Button(cartesian, text=label)
            self._bind_hold_button(
                button,
                lambda xyz=values: controller.start_cartesian_continuous(*xyz),
                controller.stop_continuous,
            )
            button.pack(side="left", fill="x", expand=True, padx=1)
            self.cartesian_buttons.append(button)

        self.virtual_controls.pack(fill="x", pady=(10, 0))

        self.real_controls = ttk.LabelFrame(container, text="Real hardware")
        ttk.Label(self.real_controls, text="Joint jog — no visual estimate (hold)").pack(
            anchor="w", pady=(12, 4)
        )
        joint_jog = ttk.Frame(self.real_controls)
        joint_jog.pack(fill="x")
        self.joint_jog_buttons = []
        for label, axis, direction in (
            ("Shoulder -", 2, -1),
            ("Shoulder +", 2, 1),
            ("Elbow -", 3, -1),
            ("Elbow +", 3, 1),
        ):
            button = ttk.Button(joint_jog, text=label)
            self._bind_hold_button(
                button,
                lambda joint_axis=axis, joint_direction=direction: controller.start_joint_jog(
                    joint_axis, joint_direction
                ),
                controller.stop_joint_jog,
            )
            button.pack(side="left", fill="x", expand=True, padx=1)
            self.joint_jog_buttons.append(button)
        self.joint_jog_stop_button = ttk.Button(
            self.real_controls, text="Stop Joint Jog", command=controller.stop_joint_jog
        )
        self.joint_jog_stop_button.pack(fill="x", pady=(4, 0))
        endpoint_capture = ttk.LabelFrame(
            self.real_controls, text="Observed soft endpoints (TELP counts)"
        )
        endpoint_capture.pack(fill="x", pady=(10, 0))
        for axis in ("shoulder", "elbow"):
            row = ttk.Frame(endpoint_capture)
            row.pack(fill="x", padx=4, pady=1)
            ttk.Label(row, text=axis.title(), width=12).pack(side="left")
            ttk.Button(
                row, text="Capture min",
                command=lambda joint=axis: self._capture_soft_endpoint(joint, "min"),
            ).pack(side="left", fill="x", expand=True, padx=(0, 3))
            ttk.Button(
                row, text="Capture max",
                command=lambda joint=axis: self._capture_soft_endpoint(joint, "max"),
            ).pack(side="left", fill="x", expand=True)
        ttk.Label(self.real_controls, text="Coordinated joint target (counts; drag, then Move)").pack(anchor="w", pady=(10, 2))
        self.real_joint_target = []
        for label in ("Shoulder", "Elbow", "Wrist pitch"):
            row = ttk.Frame(self.real_controls)
            row.pack(fill="x")
            ttk.Label(row, text=label, width=12).pack(side="left")
            value = tk.IntVar(value=0)
            ttk.Scale(row, from_=-500, to=500, variable=value).pack(side="left", fill="x", expand=True)
            self.real_joint_target.append(value)
        self.real_joint_move_button = ttk.Button(
            self.real_controls, text="Move Real Robot (supervised)", command=self._move_real_joints
        )
        self.real_joint_move_button.pack(fill="x", pady=(4, 0))
        self.real_controls.pack(fill="x", pady=(10, 0))

        self.mapping_status = tk.StringVar(value="Mapping: unknown")
        self.mapping_status_label = ttk.Label(container, textvariable=self.mapping_status)
        self.mapping_status_label.pack(
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
        is_real = self.controller.selected_backend == "real"
        if is_real:
            self.virtual_controls.pack_forget()
            self.real_controls.pack(fill="x", pady=(10, 0), before=self.mapping_status_label)
        else:
            self.real_controls.pack_forget()
            self.virtual_controls.pack(fill="x", pady=(10, 0), before=self.mapping_status_label)
        preset_state = "disabled" if is_real else "normal"
        for button in self.preset_buttons:
            button.configure(state=preset_state)
        virtual_state = "disabled" if is_real else "normal"
        self.clear_fault_button.configure(state=virtual_state)
        self.speed_scale.configure(state=virtual_state)
        for button in self.cartesian_buttons:
            button.configure(state=virtual_state)
        joint_jog_state = "normal" if self.controller.joint_jog_available() else "disabled"
        for button in self.joint_jog_buttons:
            button.configure(state=joint_jog_state)
        self.joint_jog_stop_button.configure(state=joint_jog_state)
        self.real_joint_move_button.configure(state=joint_jog_state)
        state = next(
            snapshot for snapshot in snapshots if snapshot.robot_id == selected
        )
        self.mapping_status.set(
            f"Mapping: {state.joint_mapping_quality.value.replace('_', ' ')}"
        )
        if is_real:
            publisher = self.controller.real_publishers.get(selected)
            health_getter = getattr(self.controller.state_sources[selected], "telemetry_health", None)
            health = health_getter() if health_getter else None
            joint_counts = (
                publisher.get_erv_joint_counts()
                if publisher is not None and hasattr(publisher, "get_erv_joint_counts")
                else None
            )
            encoder_counts = (
                publisher.get_erv_encoder_counts()
                if publisher is not None and hasattr(publisher, "get_erv_encoder_counts")
                else None
            )
            if joint_counts is not None:
                names = ("base", "shoulder", "elbow", "pitch", "roll")
                joint_text = "  ".join(
                    f"{name}={value}" for name, value in zip(names[-len(joint_counts):], joint_counts)
                )
                source_text = "controller joint coordinates (TELP)"
            elif encoder_counts is not None:
                joint_text = "raw encoder counts (TEL); visual pose waiting for TELP"
                source_text = "controller raw encoders (TEL)"
            else:
                joint_text = "waiting for controller joint telemetry (TELP)"
                source_text = "controller telemetry"
            health_text = health.health.value.upper() if health is not None else "UNKNOWN"
            self.telemetry.set(
                f"backend=REAL   source={source_text}\n"
                f"{joint_text}\n"
                f"telemetry={health_text}"
                + (
                    f"   age={health.age_seconds:.2f}s"
                    f"   rate={health.estimated_rate_hz:.2f} Hz"
                    if health is not None and health.age_seconds is not None and health.estimated_rate_hz is not None
                    else ""
                )
                + "\nvisual pose: measured telemetry only; unknown while waiting\n"
                f"command_error={self.controller.last_error[selected] or 'none'}"
            )
            pose = None
        else:
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
        self.controller.stop_joint_jog()
        if self._open:
            try:
                self.root.destroy()
            except self._tk.TclError:
                pass
        self._open = False

    def _on_close(self) -> None:
        self.controller.stop_joint_jog()
        try:
            self.root.destroy()
        finally:
            self._open = False

    def _stop_jog_if_window_loses_focus(self, _event) -> None:
        # A button press can legitimately move focus among Tk child widgets.
        # Check after Tk finishes that transition, and stop only if focus left
        # this window entirely.  This preserves focus-loss safety without
        # racing a hold button's ButtonPress handler.
        self.root.after_idle(self._stop_jog_if_focus_is_external)

    def _stop_jog_if_focus_is_external(self) -> None:
        focused = self.root.focus_displayof()
        if focused is None or focused.winfo_toplevel() != self.root:
            self.controller.stop_joint_jog()

    def _scroll_with_mouse_wheel(self, event) -> None:
        """Forward platform-specific wheel events to the control canvas."""
        if event.widget.winfo_toplevel() != self.root:
            return
        if getattr(event, "num", None) == 4:
            units = -1
        elif getattr(event, "num", None) == 5:
            units = 1
        else:
            delta = getattr(event, "delta", 0)
            units = -1 if delta > 0 else 1 if delta < 0 else 0
        if units:
            self._scroll_canvas.yview_scroll(units, "units")

    def _select_robot(self, robot_id: str) -> None:
        self.controller.select_robot(robot_id)
        self.speed.set(self.controller.get_selected_speed())
        self.speed_label.configure(text=str(self.speed.get()))
        self._refresh_backend_menu()

    def _select_backend(self, _event=None) -> None:
        self.controller.set_selected_backend(self.backend.get())

    def _move_real_joints(self) -> None:
        values = tuple(int(value.get()) for value in self.real_joint_target)
        if not self._messagebox.askyesno(
            "Move real robot",
            f"Execute one coordinated joint move (counts):\nshoulder={values[0]}, elbow={values[1]}, pitch={values[2]}?",
            icon="warning",
        ):
            return
        self.controller.move_real_joints(*values)

    def _capture_soft_endpoint(self, axis: str, bound: str) -> None:
        try:
            self.controller.capture_real_joint_soft_endpoint(axis, bound)
        except (RuntimeError, ValueError) as error:
            self.controller.last_error[self.controller.selected_robot_id] = str(error)
            print(f"Endpoint capture failed: {error}")

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
        active = False

        def start(_event) -> None:
            nonlocal active
            if not active:
                active = True
                start_callback()

        def stop(_event) -> None:
            nonlocal active
            if active:
                active = False
                stop_callback()

        button.bind("<ButtonPress-1>", start)
        button.bind("<ButtonRelease-1>", stop)
        button.bind("<Leave>", stop)
