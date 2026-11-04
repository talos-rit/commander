import { LoaderCircle, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import type { AppSettings, RobotConfig, RobotInput } from "../types";
import { ModelSlider } from "./ModelSlider";
import { Rocker } from "./Rocker";

interface Props {
  open: boolean;
  modelOptions: string[];
  onClose: () => void;
  onChanged: () => void;
}

type RobotDraft = {
  robot_id: string;
  controller_profile: "native" | "esp-one-axis";
  socket_host: string;
  socket_port: string;
  camera_index: string;
  fps: string;
  manual_only: boolean;
  track_elbow: boolean;
  track_shoulder: boolean;
  track_polar_vertical: boolean;
  pi_vision_enabled: boolean;
  pi_vision_url: string;
};

const PI_VISION_PORT = 5050;

const EMPTY_DRAFT: RobotDraft = {
  robot_id: "",
  controller_profile: "native",
  socket_host: "",
  socket_port: "61616",
  camera_index: "",
  fps: "30",
  manual_only: false,
  track_elbow: false,
  track_shoulder: false,
  track_polar_vertical: true,
  pi_vision_enabled: true,
  pi_vision_url: "",
};

/** Usual camera stream for a robot: RTSP on the operator host. */
function suggestedCameraUrl(host: string): string {
  const trimmed = host.trim();
  return trimmed ? `rtsp://${trimmed}:8554/camera` : "";
}

/** Usual PiVision service: HTTP on the operator host. */
function suggestedPiVisionUrl(host: string): string {
  const trimmed = host.trim();
  return trimmed ? `http://${trimmed}:${PI_VISION_PORT}` : "";
}

/** Empty, or still the URL derived from this host, so host edits may rewrite it. */
function followsHost(value: string, host: string, suggest: (host: string) => string): boolean {
  return value === "" || value === suggest(host);
}

function toDraft(robot: RobotConfig): RobotDraft {
  return {
    robot_id: robot.robot_id ?? "",
    controller_profile: robot.controller_profile ?? "native",
    socket_host: robot.socket_host,
    socket_port: String(robot.socket_port),
    camera_index: String(robot.camera_index),
    fps: String(robot.fps),
    manual_only: robot.manual_only,
    track_elbow: robot.track_elbow ?? false,
    track_shoulder: robot.track_shoulder ?? false,
    track_polar_vertical: robot.track_polar_vertical ?? true,
    pi_vision_enabled: robot.pi_vision_enabled ?? Boolean(robot.pi_vision_url),
    pi_vision_url: robot.pi_vision_url ?? "",
  };
}

function verticalSummary(robot: RobotConfig): string {
  const axes = [
    robot.track_elbow ? "elbow" : "",
    robot.track_shoulder ? "shoulder" : "",
    (robot.track_polar_vertical ?? true) ? "polar" : "",
  ].filter(Boolean);
  return axes.length ? axes.join(", ") : "vertical off";
}

const asInt = (value: string) => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : value.trim());

function fromDraft(draft: RobotDraft): RobotInput {
  return {
    ...(draft.robot_id.trim() ? { robot_id: draft.robot_id.trim() } : {}),
    controller_profile: draft.controller_profile,
    socket_host: draft.socket_host.trim(),
    socket_port: asInt(draft.socket_port),
    camera_index: asInt(draft.camera_index),
    fps: Number(draft.fps) || 30,
    manual_only: draft.manual_only,
    track_elbow: draft.track_elbow,
    track_shoulder: draft.track_shoulder,
    track_polar_vertical: draft.track_polar_vertical,
    pi_vision_enabled: draft.pi_vision_enabled,
    pi_vision_url: draft.pi_vision_url.trim() || null,
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
  const cameraHintId = useId();
  const piVisionHintId = useId();
  const identityHintId = useId();
  const [draft, setDraft] = useState(initial);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof RobotDraft>(key: K, value: RobotDraft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const setHost = (socket_host: string) => {
    setDraft((d) => ({
      ...d,
      socket_host,
      camera_index:
        !editing && followsHost(d.camera_index, d.socket_host, suggestedCameraUrl)
          ? suggestedCameraUrl(socket_host)
          : d.camera_index,
      pi_vision_url:
        !editing && followsHost(d.pi_vision_url, d.socket_host, suggestedPiVisionUrl)
          ? suggestedPiVisionUrl(socket_host)
          : d.pi_vision_url,
    }));
  };

  const setPiVisionEnabled = (pi_vision_enabled: boolean) => {
    setDraft((d) => ({
      ...d,
      pi_vision_enabled,
      pi_vision_url:
        pi_vision_enabled && followsHost(d.pi_vision_url, d.socket_host, suggestedPiVisionUrl)
          ? suggestedPiVisionUrl(d.socket_host)
          : d.pi_vision_url,
    }));
  };

  const derived = draft.camera_index !== "" && draft.camera_index === suggestedCameraUrl(draft.socket_host);
  const cameraHint = derived
    ? "Follows the operator host."
    : draft.camera_index
      ? "RTSP or HTTP URL, or a device index."
      : "Fills in from the operator host.";
  const piDerived = draft.pi_vision_url !== "" && draft.pi_vision_url === suggestedPiVisionUrl(draft.socket_host);
  const piVisionHint = !draft.pi_vision_enabled
    ? draft.pi_vision_url
      ? "PiVision is off. This address stays saved."
      : "PiVision is off. Commander talks to Operator directly."
    : piDerived
      ? "PiVision follows the operator host."
      : draft.pi_vision_url
        ? "Custom PiVision address."
        : "PiVision fills in from the operator host.";

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
          disabled={(editing && !draft.robot_id) || busy}
          placeholder="bluey.local"
          spellCheck={false}
          value={draft.socket_host}
          onChange={(e) => setHost(e.target.value)}
        />
      </label>
      <label className="field field--narrow">
        <span>Port</span>
        <input
          required
          disabled={busy}
          inputMode="numeric"
          value={draft.socket_port}
          onChange={(e) => set("socket_port", e.target.value)}
        />
      </label>
      <div className="robotform__pivision">
        <label className="check">
          <input
            type="checkbox"
            disabled={busy}
            checked={draft.pi_vision_enabled}
            aria-describedby={draft.pi_vision_enabled ? undefined : piVisionHintId}
            onChange={(e) => setPiVisionEnabled(e.target.checked)}
          />
          <span>Use PiVision</span>
        </label>
        {!draft.pi_vision_enabled && (
          <p id={piVisionHintId} className="robotform__hint">
            {piVisionHint}
          </p>
        )}
      </div>
      <div className="robotform__secondary">
        <p className="robotform__kicker">Rarely needs changing</p>
        <div className="robotform__pair">
          <label className="field">
            <span>Robot name</span>
            <input
              placeholder="bluey or bingo"
              spellCheck={false}
              disabled={editing || busy}
              aria-describedby={identityHintId}
              value={draft.robot_id}
              onChange={(e) => set("robot_id", e.target.value)}
            />
          </label>
          <label className="field">
            <span>Robot controller</span>
            <select
              disabled={busy}
              aria-describedby={identityHintId}
              value={draft.controller_profile}
              onChange={(e) => set("controller_profile", e.target.value as RobotDraft["controller_profile"])}
            >
              <option value="native">Bingo — native</option>
              <option value="esp-one-axis">Bluey — ESP one-axis demo</option>
            </select>
          </label>
        </div>
        <p id={identityHintId} className="robotform__hint">
          Name is optional; give each robot its own when both share a Pi. Saving doesn&apos;t restart Operator. On the
          Pi, run{" "}
          <code>
            {draft.controller_profile === "native" ? "tools/start-native.sh --confirm-home" : "tools/start-esp-one-axis.sh"}
          </code>
          {draft.controller_profile === "native" ? " (moves the arm through HOME)" : ""}. Controls unlock once Operator
          reports this controller.
        </p>
        <label className={`field${derived ? " field--derived" : ""}`}>
          <span>Stream</span>
          <input
            required
            disabled={busy}
            placeholder="rtsp://bluey.local:8554/camera"
            spellCheck={false}
            aria-describedby={cameraHintId}
            value={draft.camera_index}
            onChange={(e) => set("camera_index", e.target.value)}
          />
        </label>
        <p id={cameraHintId} className="robotform__hint">
          {cameraHint}
        </p>
        {draft.pi_vision_enabled && (
          <>
            <label className={`field${piDerived ? " field--derived" : ""}`}>
              <span>PiVision URL</span>
              <input
                required
                disabled={busy}
                placeholder="http://bluey.local:5050"
                spellCheck={false}
                aria-describedby={piVisionHintId}
                value={draft.pi_vision_url}
                onChange={(e) => set("pi_vision_url", e.target.value)}
              />
            </label>
            <p id={piVisionHintId} className="robotform__hint">
              {piVisionHint}
            </p>
          </>
        )}
        <div className="robotform__rare">
          <label className="field">
            <span>FPS</span>
            <input inputMode="numeric" disabled={busy} value={draft.fps} onChange={(e) => set("fps", e.target.value)} />
          </label>
          <label className="check">
            <input
              type="checkbox"
              disabled={busy}
              checked={draft.manual_only}
              onChange={(e) => set("manual_only", e.target.checked)}
            />
            <span>Manual only (no auto-tracking)</span>
          </label>
        </div>
        <fieldset className="robotform__axes" disabled={busy || draft.controller_profile === "esp-one-axis"}>
          <legend>Vertical tracking</legend>
          <label className="check">
            <input
              type="checkbox"
              checked={draft.track_elbow}
              onChange={(e) => set("track_elbow", e.target.checked)}
            />
            <span>Elbow</span>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={draft.track_shoulder}
              onChange={(e) => set("track_shoulder", e.target.checked)}
            />
            <span>Shoulder</span>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={draft.track_polar_vertical}
              onChange={(e) => set("track_polar_vertical", e.target.checked)}
            />
            <span>Polar up/down</span>
          </label>
        </fieldset>
        <p className="robotform__hint">
          {draft.track_elbow || draft.track_shoulder || draft.track_polar_vertical
            ? "Checked axes are commanded in this order: elbow, shoulder, then polar up/down. An unchecked axis is never commanded."
            : "Vertical tracking off. Auto-Track still pans left and right."}
        </p>
      </div>
      <div className="robotform__actions">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
        <button
          type="submit"
          className={`btn btn--primary${busy ? " btn--busy" : ""}`}
          disabled={busy}
          aria-busy={busy}
        >
          {busy ? <LoaderCircle className="spin" size={16} /> : editing ? <Save size={16} /> : <Plus size={16} />}
          {busy ? "Connecting…" : editing ? "Save robot" : "Add robot"}
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
      await api.updateRobot(host, robotDraft.robot_id ? { ...rest, socket_host: fromDraft(robotDraft).socket_host } : rest);
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
                        :{robots[host].socket_port}
                        {robots[host].manual_only ? " · manual only" : ""}
                        {` · ${verticalSummary(robots[host])}`}
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
              <h3>Feeds</h3>
              <label className="field">
                <span>Feed 1</span>
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
                <span>Feed 2</span>
                <select
                  value={draft.camera_2_host ?? ""}
                  onChange={(e) => set("camera_2_host", e.target.value || null)}
                  disabled={!draft.camera_1_host}
                >
                  <option value="">— none —</option>
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
                <span>Tracking model (local)</span>
                <ModelSlider
                  label="Tracking model (local)"
                  options={modelOptions}
                  value={draft.default_model ?? null}
                  onChange={(model) => set("default_model", model)}
                />
              </div>

              <h3>Interface</h3>
              <SwitchField label="Interface">
                <Rocker<AppSettings["ui_mode"]>
                  label="Interface"
                  value={draft.ui_mode ?? "debug"}
                  onChange={(v) => set("ui_mode", v)}
                  describe
                  options={[
                    { value: "simple", label: "Simple", description: "Only Home and Auto-Track" },
                    { value: "debug", label: "Debug", description: "Adds manual jog, the model slider and telemetry" },
                  ]}
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
