import { Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import type { AppSettings, RobotConfig, RobotInput } from "../types";
import { JOG_OPTIONS } from "./DebugRail";
import { ModelSlider } from "./ModelSlider";
import { Rocker } from "./Rocker";

interface Props {
  open: boolean;
  modelOptions: string[];
  onClose: () => void;
  onChanged: () => void;
}

type RobotDraft = {
  socket_host: string;
  socket_port: string;
  camera_index: string;
  fps: string;
  manual_only: boolean;
};

const EMPTY_DRAFT: RobotDraft = { socket_host: "", socket_port: "61616", camera_index: "", fps: "30", manual_only: false };

function toDraft(robot: RobotConfig): RobotDraft {
  return {
    socket_host: robot.socket_host,
    socket_port: String(robot.socket_port),
    camera_index: String(robot.camera_index),
    fps: String(robot.fps),
    manual_only: robot.manual_only,
  };
}

const asInt = (value: string) => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : value.trim());

function fromDraft(draft: RobotDraft): RobotInput {
  return {
    socket_host: draft.socket_host.trim(),
    socket_port: asInt(draft.socket_port),
    camera_index: asInt(draft.camera_index),
    fps: Number(draft.fps) || 30,
    manual_only: draft.manual_only,
  };
}

function SwitchField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="field field--switch">
      <span>{label}</span>
      {children}
    </div>
  );
}

function errorText(err: unknown) {
  return err instanceof ApiError ? err.message : "Something went wrong";
}

function RobotForm({
  initial,
  editing,
  onSubmit,
  onCancel,
}: {
  initial: RobotDraft;
  editing: boolean;
  onSubmit: (draft: RobotDraft) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof RobotDraft>(key: K, value: RobotDraft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      if ((await onSubmit(draft)) && !editing) setDraft(EMPTY_DRAFT);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="robotform" onSubmit={submit} aria-label={editing ? `Edit ${initial.socket_host}` : "Add robot"}>
      <label className="field">
        <span>Operator host</span>
        <input
          required
          disabled={editing}
          placeholder="bluey.local"
          value={draft.socket_host}
          onChange={(e) => set("socket_host", e.target.value)}
        />
      </label>
      <label className="field field--narrow">
        <span>Port</span>
        <input
          required
          inputMode="numeric"
          value={draft.socket_port}
          onChange={(e) => set("socket_port", e.target.value)}
        />
      </label>
      <label className="field field--wide">
        <span>Camera (RTSP/HTTP URL or device index)</span>
        <input
          required
          placeholder="rtsp://bluey.local:8554/camera"
          value={draft.camera_index}
          onChange={(e) => set("camera_index", e.target.value)}
        />
      </label>
      <label className="field field--narrow">
        <span>FPS</span>
        <input inputMode="numeric" value={draft.fps} onChange={(e) => set("fps", e.target.value)} />
      </label>
      <label className="check">
        <input type="checkbox" checked={draft.manual_only} onChange={(e) => set("manual_only", e.target.checked)} />
        <span>Manual only (no auto-tracking)</span>
      </label>
      <div className="robotform__actions">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {editing ? <Save size={16} /> : <Plus size={16} />} {editing ? "Save robot" : "Add robot"}
        </button>
      </div>
    </form>
  );
}

export function SettingsPanel({ open, modelOptions, onClose, onChanged }: Props) {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [draft, setDraft] = useState<Partial<AppSettings>>({});
  const [robots, setRobots] = useState<Record<string, RobotConfig>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([api.settings(), api.robots()]);
      setSettings(s);
      setDraft(s);
      setRobots(r);
      setAdding(Object.keys(r).length === 0);
      setError(null);
    } catch (err) {
      setError(errorText(err));
    }
  }, []);

  useEffect(() => {
    if (open) {
      setSaved(false);
      void load();
    }
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const robotNames = Object.keys(robots);
  const set = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    setSaved(false);
    setDraft((d) => ({ ...d, [key]: value }));
  };

  const changes = (): Partial<AppSettings> => {
    if (!settings) return {};
    return Object.fromEntries(
      Object.entries(draft).filter(([key, value]) => settings[key as keyof AppSettings] !== value),
    ) as Partial<AppSettings>;
  };

  const saveSettings = async (event: FormEvent) => {
    event.preventDefault();
    const updates = changes();
    if (Object.keys(updates).length === 0) return;
    try {
      const next = await api.updateSettings(updates);
      setSettings(next);
      setDraft(next);
      setSaved(true);
      setError(null);
      onChanged();
    } catch (err) {
      setError(errorText(err));
    }
  };

  const addRobot = async (robotDraft: RobotDraft) => {
    try {
      await api.addRobot(fromDraft(robotDraft));
      setAdding(false);
      await load();
      onChanged();
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    }
  };

  const updateRobot = async (host: string, robotDraft: RobotDraft) => {
    try {
      const { socket_host: _ignored, ...rest } = fromDraft(robotDraft);
      await api.updateRobot(host, rest);
      setEditing(null);
      await load();
      onChanged();
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    }
  };

  const deleteRobot = async (host: string) => {
    if (!window.confirm(`Remove ${host} from Commander?`)) return;
    try {
      await api.deleteRobot(host);
      await load();
      onChanged();
    } catch (err) {
      setError(errorText(err));
    }
  };

  const dirty = Object.keys(changes()).length > 0;
  const portChanged = settings && (draft.web_port !== settings.web_port || draft.web_host !== settings.web_host);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer__head">
          <h2>Settings</h2>
          <button type="button" className="iconbtn" onClick={onClose} aria-label="Close settings">
            <X size={20} />
          </button>
        </header>

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        <div className="drawer__body">
          <section className="drawer__section">
            <h3>Robots</h3>
            <p className="muted">Saved to config/robot_configs.local.yaml.</p>
            <ul className="robots">
              {robotNames.map((host) =>
                editing === host ? (
                  <li key={host}>
                    <RobotForm
                      initial={toDraft(robots[host])}
                      editing
                      onSubmit={(d) => updateRobot(host, d)}
                      onCancel={() => setEditing(null)}
                    />
                  </li>
                ) : (
                  <li key={host} className="robots__item">
                    <div>
                      <strong>{host}</strong>
                      <span className="muted">
                        :{robots[host].socket_port} · {String(robots[host].camera_index)}
                        {robots[host].manual_only ? " · manual only" : ""}
                      </span>
                    </div>
                    <div className="robots__actions">
                      <button type="button" className="iconbtn" aria-label={`Edit ${host}`} onClick={() => setEditing(host)}>
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        className="iconbtn iconbtn--danger"
                        aria-label={`Remove ${host}`}
                        onClick={() => deleteRobot(host)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </li>
                ),
              )}
            </ul>
            {adding ? (
              <RobotForm
                initial={EMPTY_DRAFT}
                editing={false}
                onSubmit={addRobot}
                onCancel={robotNames.length ? () => setAdding(false) : undefined}
              />
            ) : (
              <button type="button" className="btn" onClick={() => setAdding(true)}>
                <Plus size={16} /> Add robot
              </button>
            )}
          </section>

          {settings && (
            <form className="drawer__section" onSubmit={saveSettings} aria-label="Defaults">
              <h3>Cameras</h3>
              <label className="field">
                <span>Camera 1 (primary)</span>
                <select
                  value={draft.camera_1_host ?? ""}
                  onChange={(e) => set("camera_1_host", e.target.value || null)}
                >
                  <option value="">— none —</option>
                  {robotNames.map((host) => (
                    <option key={host} value={host}>
                      {host}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Camera 2 (optional)</span>
                <select
                  value={draft.camera_2_host ?? ""}
                  onChange={(e) => set("camera_2_host", e.target.value || null)}
                  disabled={!draft.camera_1_host}
                >
                  <option value="">— none (single camera) —</option>
                  {robotNames
                    .filter((host) => host !== draft.camera_1_host)
                    .map((host) => (
                      <option key={host} value={host}>
                        {host}
                      </option>
                    ))}
                </select>
              </label>

              <h3>Tracking</h3>
              <div className="field">
                <span>Tracking model</span>
                <ModelSlider
                  label="Tracking model"
                  options={modelOptions}
                  value={draft.default_model ?? null}
                  onChange={(model) => set("default_model", model)}
                />
              </div>

              <h3>Interface</h3>
              <SwitchField label="Interface">
                <Rocker<AppSettings["ui_mode"]>
                  label="Interface"
                  value={draft.ui_mode ?? "simple"}
                  onChange={(v) => set("ui_mode", v)}
                  describe
                  options={[
                    { value: "simple", label: "Simple", description: "Only Home and Auto-Track" },
                    { value: "debug", label: "Debug", description: "Adds manual jog, the model slider and telemetry" },
                  ]}
                />
              </SwitchField>
              <SwitchField label="Layout with two cameras">
                <Rocker<AppSettings["display_mode"]>
                  label="Layout with two cameras"
                  value={draft.display_mode ?? "one_screen"}
                  onChange={(v) => set("display_mode", v)}
                  describe
                  options={[
                    { value: "one_screen", label: "One screen", description: "Show one camera at a time" },
                    { value: "two_screen", label: "Two screen", description: "Show both cameras side by side" },
                  ]}
                />
              </SwitchField>
              <SwitchField label="One-screen switching">
                <Rocker<AppSettings["one_screen_mode"]>
                  label="One-screen switching"
                  value={draft.one_screen_mode ?? "manual"}
                  onChange={(v) => set("one_screen_mode", v)}
                  describe
                  options={[
                    { value: "manual", label: "Manual", description: "You pick the camera" },
                    {
                      value: "dynamic",
                      label: "Dynamic",
                      description: "Commander picks the camera (coming in a later release)",
                    },
                  ]}
                />
              </SwitchField>
              <SwitchField label="Jog style (debug)">
                <Rocker<AppSettings["jog_mode"]>
                  label="Jog style"
                  value={draft.jog_mode ?? "discrete"}
                  onChange={(v) => set("jog_mode", v)}
                  describe
                  options={JOG_OPTIONS}
                />
              </SwitchField>

              <h3>Server</h3>
              <div className="field-row">
                <label className="field">
                  <span>Web host</span>
                  <input value={draft.web_host ?? ""} onChange={(e) => set("web_host", e.target.value)} />
                </label>
                <label className="field field--narrow">
                  <span>Web port</span>
                  <input
                    inputMode="numeric"
                    value={draft.web_port ?? ""}
                    onChange={(e) => set("web_port", Number(e.target.value))}
                  />
                </label>
              </div>
              {portChanged && <p className="hint">Host/port changes apply after restarting commander-web.</p>}
              <div className="drawer__foot">
                <span className="muted">Saved to config/app_settings.local.yaml.</span>
                {saved && !dirty && <span className="saved">Saved</span>}
                <button type="submit" className="btn btn--primary" disabled={!dirty}>
                  <Save size={16} /> Save
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
