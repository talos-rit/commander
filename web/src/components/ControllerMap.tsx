import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, type LucideIcon } from "lucide-react";
import { useEffect, useState, type CSSProperties } from "react";
import {
  armFromGamepads,
  BUTTON_GUIDE,
  bumpersPressed,
  buttonPressed,
  connectedGamepads,
  DIRECTION_ORDER,
  dpadFromGamepad,
  padActionsPressed,
  selectGamepad,
  STICK_CLICK_LEFT,
  STICK_CLICK_RIGHT,
  STICK_RELEASE,
  type ArmHold,
  type HatState,
} from "../gamepad";
import { readGamepads } from "../hooks/useGamepad";
import type { Direction } from "../types";
import talosLogo from "../assets/talos_logo.svg";
import { JOINT_MARKS } from "./DebugRail";

/** Matches the fade-out in styles.css, so the map stays mounted until it has faded. */
const EXIT_MS = 180;

export type MapGroup = "aim" | "arm" | "cameras" | "home" | "debug" | "track" | "virtual" | "layout";

type Glyph = "a" | "b" | "x" | "y" | "lb" | "rb" | "lt" | "rt" | "ls" | "rs" | "dpad" | "view" | "menu";
type Control = Glyph | Direction | "guide";
type Point = readonly [number, number];

type JointName = keyof typeof JOINT_MARKS;

/** Which way each direction of a stick or D-pad moves, drawn with the debug jog pad's icons. */
interface Compass {
  kind: "aim" | "joint";
  source: "ls" | "rs" | "dpad";
}

interface Callout {
  glyph: Glyph;
  title: string;
  detail?: string;
  compass?: Compass;
  /** Unset for B, which always works because it is what opens the map. */
  group?: MapGroup;
  align: "start" | "end";
  /** Center of the glyph in the label column. */
  at: Point;
  /** Leader from the label to the button. The last point is the button. */
  leader: readonly Point[];
}

const LEFT_X = 196;
const RIGHT_X = 804;

const CALLOUTS: readonly Callout[] = [
  { glyph: "lt", title: "Retract arm", detail: "hold", group: "arm", align: "end", at: [LEFT_X, 96], leader: [[214, 96], [304, 96], [338, 130]] },
  { glyph: "lb", title: "Previous camera", detail: "manual view", group: "cameras", align: "end", at: [LEFT_X, 150], leader: [[214, 150], [262, 150], [292, 172]] },
  { glyph: "ls", title: "Aim", compass: { kind: "aim", source: "ls" }, group: "aim", align: "end", at: [LEFT_X, 252], leader: [[214, 252], [334, 252]] },
  { glyph: "dpad", title: "Aim", compass: { kind: "aim", source: "dpad" }, group: "aim", align: "end", at: [LEFT_X, 330], leader: [[214, 330], [394, 330]] },
  { glyph: "view", title: "Home", detail: "return to rest", group: "home", align: "end", at: [466, 46], leader: [[466, 64], [466, 240]] },
  { glyph: "menu", title: "Debug mode", detail: "toggle", group: "debug", align: "start", at: [534, 46], leader: [[534, 64], [534, 240]] },
  { glyph: "rt", title: "Extend arm", detail: "hold", group: "arm", align: "start", at: [RIGHT_X, 96], leader: [[786, 96], [696, 96], [662, 130]] },
  { glyph: "rb", title: "Next camera", detail: "manual view", group: "cameras", align: "start", at: [RIGHT_X, 150], leader: [[786, 150], [738, 150], [708, 172]] },
  { glyph: "x", title: "Virtual Cam", detail: "toggle", group: "virtual", align: "start", at: [RIGHT_X, 192], leader: [[786, 192], [596, 192], [596, 235]] },
  { glyph: "y", title: "Manual / Dynamic", detail: "camera layout", group: "layout", align: "start", at: [RIGHT_X, 232], leader: [[786, 232], [712, 232], [651, 214]] },
  { glyph: "b", title: "Button map", detail: "hold", align: "start", at: [RIGHT_X, 272], leader: [[786, 272], [712, 272], [691, 256]] },
  { glyph: "a", title: "Auto-Track", detail: "toggle", group: "track", align: "start", at: [RIGHT_X, 312], leader: [[786, 312], [712, 312], [649, 298]] },
  { glyph: "rs", title: "Arm joints", compass: { kind: "joint", source: "rs" }, group: "arm", align: "start", at: [RIGHT_X, 380], leader: [[786, 380], [712, 380], [598, 350]] },
];

const LS: Point = [372, 252];
const RS: Point = [572, 330];
const DPAD: Point = [428, 330];
const FACE: Record<"a" | "b" | "x" | "y", Point> = {
  y: [634, 212],
  x: [594, 252],
  b: [674, 252],
  a: [634, 292],
};

const BODY =
  "M500 170C556 170 596 160 640 160C692 160 724 180 740 220C760 272 782 360 788 420C793 470 770 498 738 500" +
  "C708 502 690 486 676 458C660 426 632 402 590 400L410 400C368 402 340 426 324 458C310 486 292 502 262 500" +
  "C230 498 207 470 212 420C218 360 240 272 260 220C276 180 308 160 360 160C404 160 444 170 500 170Z";
const BUMPER_LEFT = "M252 236C264 180 300 144 360 144C404 144 436 150 456 158L456 190L252 250Z";
const TRIGGER_LEFT = "M316 168C314 136 328 116 352 116C376 116 390 134 392 162L392 168Z";

function mirror(path: string) {
  return { transform: "translate(1000 0) scale(-1 1)", d: path };
}

interface PadSnapshot {
  lit: ReadonlySet<Control>;
  ls: Point;
  rs: Point;
}

const IDLE: PadSnapshot = { lit: new Set(), ls: [0, 0], rs: [0, 0] };

function axis(value: number | undefined): number {
  if (value == null || !Number.isFinite(value) || Math.abs(value) < 0.1) return 0;
  return Math.round(Math.max(-1, Math.min(1, value)) * 20) / 20;
}

function readSnapshot(list: ArrayLike<Gamepad | null>, hats: Map<number, HatState>, arm: ArmHold): PadSnapshot {
  const pad = selectGamepad(list, null);
  const standard = pad?.mapping === "standard" ? pad : null;
  const actions = padActionsPressed(list);
  const bumpers = bumpersPressed(list);
  armFromGamepads(list, pad?.index ?? null, arm);

  const lit = new Set<Control>();
  for (const face of ["a", "b", "x", "y"] as const) if (actions[face]) lit.add(face);
  if (actions.back) lit.add("view");
  if (actions.menu) lit.add("menu");
  if (bumpers.left) lit.add("lb");
  if (bumpers.right) lit.add("rb");
  if (arm.retract) lit.add("lt");
  if (arm.extend) lit.add("rt");
  for (const gamepad of connectedGamepads(list)) {
    let hat = hats.get(gamepad.index);
    if (!hat) {
      hat = { axis: null };
      hats.set(gamepad.index, hat);
    }
    for (const direction of dpadFromGamepad(gamepad, hat)) {
      lit.add(direction);
      lit.add("dpad");
    }
  }

  const ls: Point = [axis(standard?.axes[0]), axis(standard?.axes[1])];
  const rs: Point = [axis(standard?.axes[2]), axis(standard?.axes[3])];
  if (Math.hypot(...ls) >= STICK_RELEASE || (standard && buttonPressed(standard, STICK_CLICK_LEFT))) lit.add("ls");
  if (Math.hypot(...rs) >= STICK_RELEASE || (standard && buttonPressed(standard, STICK_CLICK_RIGHT))) lit.add("rs");
  if (standard && buttonPressed(standard, BUTTON_GUIDE)) lit.add("guide");
  return { lit, ls, rs };
}

/** Live button and stick state while the map is up. It reads the pad itself, so the map never sends commands. */
function usePadSnapshot(active: boolean): PadSnapshot {
  const [snapshot, setSnapshot] = useState(IDLE);
  useEffect(() => {
    if (!active) return;
    const hats = new Map<number, HatState>();
    const arm: ArmHold = { joint: null, retract: false, extend: false, negativeRest: new Set(), centered: new Set() };
    let key = "";
    let raf = 0;
    let stopped = false;
    const tick = () => {
      if (stopped) return;
      const next = readSnapshot(readGamepads(), hats, arm);
      const nextKey = `${[...next.lit].sort().join()}|${next.ls.join()}|${next.rs.join()}`;
      if (nextKey !== key) {
        key = nextKey;
        setSnapshot(next);
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      setSnapshot(IDLE);
    };
  }, [active]);
  return snapshot;
}

function GlyphMark({ kind, x = 0, y = 0 }: { kind: Glyph; x?: number; y?: number }) {
  const at = `translate(${x} ${y})`;
  switch (kind) {
    case "a":
    case "b":
    case "x":
    case "y":
      return (
        <g transform={at} className={`pmglyph pmglyph--face pmglyph--${kind}`}>
          <circle r={13} />
          <text y={0.5}>{kind.toUpperCase()}</text>
        </g>
      );
    case "lb":
    case "rb":
      return (
        <g transform={at} className="pmglyph">
          <path d="M-18 9V-1C-18-6-14-9-9-9H9C14-9 18-6 18-1V9Z" />
          <text y={1} className="pmglyph__small">
            {kind.toUpperCase()}
          </text>
        </g>
      );
    case "lt":
    case "rt":
      return (
        <g transform={at} className="pmglyph">
          <path d="M-14 11V-2C-14-9-8-13-1-13H1C8-13 14-9 14-2V11Z" />
          <text y={0} className="pmglyph__small">
            {kind.toUpperCase()}
          </text>
        </g>
      );
    case "ls":
    case "rs":
      return (
        <g transform={at} className="pmglyph">
          <circle r={13} />
          <circle r={8.5} className="pmglyph__inner" />
          <text y={0.5} className="pmglyph__small">
            {kind === "ls" ? "L" : "R"}
          </text>
        </g>
      );
    case "dpad":
      return (
        <g transform={at} className="pmglyph">
          <path d="M-4.5-13H4.5V-4.5H13V4.5H4.5V13H-4.5V4.5H-13V-4.5H-4.5Z" />
        </g>
      );
    case "view":
      return (
        <g transform={at} className="pmglyph">
          <circle r={13} />
          <rect x={-6.5} y={-5.5} width={8} height={7} rx={1.5} className="pmglyph__line" />
          <rect x={-1.5} y={-1.5} width={8} height={7} rx={1.5} className="pmglyph__fill" />
        </g>
      );
    case "menu":
      return (
        <g transform={at} className="pmglyph">
          <circle r={13} />
          <path d="M-6-4H6M-6 0H6M-6 4H6" className="pmglyph__line" />
        </g>
      );
  }
}

function Stick({ at, offset, lit }: { at: Point; offset: Point; lit: boolean }) {
  const [cx, cy] = at;
  return (
    <g className={`pm-stick${lit ? " is-lit" : ""}`}>
      <circle className="pm-stick__well" cx={cx} cy={cy} r={38} />
      <g className="pm-stick__cap" style={{ transform: `translate(${offset[0] * 9}px, ${offset[1] * 9}px)` }}>
        <circle className="pm-stick__skirt" cx={cx} cy={cy} r={27} />
        <circle className="pm-stick__top" cx={cx} cy={cy} r={21} />
        <circle className="pm-stick__ring" cx={cx} cy={cy} r={15} />
      </g>
    </g>
  );
}

function Controller({ lit, ls, rs }: PadSnapshot) {
  const on = (control: Control) => (lit.has(control) ? " is-lit" : "");
  const [dx, dy] = DPAD;
  const arm = 10;
  const reach = 27;
  return (
    <g className="pm-controller" aria-hidden="true">
      <path className={`pm-trigger${on("lt")}`} d={TRIGGER_LEFT} />
      <path className={`pm-trigger${on("rt")}`} {...mirror(TRIGGER_LEFT)} />
      <path className={`pm-bumper${on("lb")}`} d={BUMPER_LEFT} />
      <path className={`pm-bumper${on("rb")}`} {...mirror(BUMPER_LEFT)} />

      <path className="pm-body" d={BODY} />

      <Stick at={LS} offset={ls} lit={lit.has("ls")} />
      <Stick at={RS} offset={rs} lit={lit.has("rs")} />

      <circle className="pm-well" cx={dx} cy={dy} r={36} />
      <g className="pm-dpad">
        <rect className={`pm-dpad__arm${on("up")}`} x={dx - arm} y={dy - reach} width={arm * 2} height={reach - arm + 1} rx={3} />
        <rect className={`pm-dpad__arm${on("down")}`} x={dx - arm} y={dy + arm - 1} width={arm * 2} height={reach - arm + 1} rx={3} />
        <rect className={`pm-dpad__arm${on("left")}`} x={dx - reach} y={dy - arm} width={reach - arm + 1} height={arm * 2} rx={3} />
        <rect className={`pm-dpad__arm${on("right")}`} x={dx + arm - 1} y={dy - arm} width={reach - arm + 1} height={arm * 2} rx={3} />
        <rect className="pm-dpad__hub" x={dx - arm} y={dy - arm} width={arm * 2} height={arm * 2} />
      </g>

      {(Object.keys(FACE) as (keyof typeof FACE)[]).map((face) => (
        <g key={face} className={`pm-face pm-face--${face}${on(face)}`}>
          <circle cx={FACE[face][0]} cy={FACE[face][1]} r={16} />
          <text x={FACE[face][0]} y={FACE[face][1] + 0.5}>
            {face.toUpperCase()}
          </text>
        </g>
      ))}

      <g className={`pm-small${on("view")}`}>
        <circle cx={466} cy={252} r={11} />
        <rect x={461} y={247} width={7} height={6} rx={1.2} className="pm-small__line" />
        <rect x={465} y={250} width={7} height={6} rx={1.2} className="pm-small__fill" />
      </g>
      <g className={`pm-small${on("menu")}`}>
        <circle cx={534} cy={252} r={11} />
        <path d="M529 248.5H539M529 252H539M529 255.5H539" className="pm-small__line" />
      </g>
      <g className={`pm-guide${on("guide")}`}>
        <circle cx={500} cy={206} r={19} />
        <image href={talosLogo} x={500 - 17} y={206 - 17} width={34} height={34} />
      </g>
    </g>
  );
}

const COMPASS_STEP = 20;
const COMPASS_KEY = 18;
const COMPASS_ICON = 13;
const COMPASS_OFFSET: Record<Direction, Point> = {
  up: [0, -COMPASS_STEP],
  right: [COMPASS_STEP, 0],
  down: [0, COMPASS_STEP],
  left: [-COMPASS_STEP, 0],
};
const ARROWS: Record<Direction, LucideIcon> = { up: ArrowUp, right: ArrowRight, down: ArrowDown, left: ArrowLeft };
/** Right stick: sideways is the shoulder, up and down the elbow. Stick up commands elbow negative. */
const JOINT_CELLS: Record<Direction, { axis: JointName; direction: -1 | 1 }> = {
  up: { axis: "elbow", direction: -1 },
  down: { axis: "elbow", direction: 1 },
  left: { axis: "shoulder", direction: -1 },
  right: { axis: "shoulder", direction: 1 },
};

function markId(axis: JointName, direction: -1 | 1) {
  return `pm-mark-${axis}-${direction < 0 ? "neg" : "pos"}`;
}

/** The jog icons are black strokes on transparent, so they become alpha masks over a currentColor fill. */
function MarkMasks() {
  return (
    <defs>
      {Object.values(JOINT_CELLS).map(({ axis, direction }) => (
        <mask
          key={markId(axis, direction)}
          id={markId(axis, direction)}
          maskContentUnits="objectBoundingBox"
          style={{ maskType: "alpha" }}
        >
          <image href={JOINT_MARKS[axis][direction]} width={1} height={1} />
        </mask>
      ))}
    </defs>
  );
}

function stickDirections([x, y]: Point, oneAxis: boolean): Set<Direction> {
  const held = new Set<Direction>();
  const horizontal = Math.abs(x) >= STICK_RELEASE && (!oneAxis || Math.abs(x) >= Math.abs(y));
  const vertical = Math.abs(y) >= STICK_RELEASE && (!oneAxis || Math.abs(y) > Math.abs(x));
  if (horizontal) held.add(x < 0 ? "left" : "right");
  if (vertical) held.add(y < 0 ? "up" : "down");
  return held;
}

function compassHeld(source: Compass["source"], snapshot: PadSnapshot): ReadonlySet<Direction> {
  if (source === "ls") return stickDirections(snapshot.ls, false);
  // The hardware jogs one joint at a time.
  if (source === "rs") return stickDirections(snapshot.rs, true);
  return new Set(DIRECTION_ORDER.filter((direction) => snapshot.lit.has(direction)));
}

function CompassPad({ at, kind, held }: { at: Point; kind: Compass["kind"]; held: ReadonlySet<Direction> }) {
  const half = COMPASS_KEY / 2;
  const icon = COMPASS_ICON / 2;
  return (
    <g className="pm-compass">
      <circle className="pm-compass__hub" cx={at[0]} cy={at[1]} r={2} />
      {DIRECTION_ORDER.map((direction) => {
        const x = at[0] + COMPASS_OFFSET[direction][0];
        const y = at[1] + COMPASS_OFFSET[direction][1];
        const Arrow = ARROWS[direction];
        const joint = JOINT_CELLS[direction];
        return (
          <g key={direction} className={`pm-compass__cell${held.has(direction) ? " is-held" : ""}`}>
            <rect className="pm-compass__key" x={x - half} y={y - half} width={COMPASS_KEY} height={COMPASS_KEY} rx={3} />
            {kind === "aim" ? (
              <Arrow x={x - icon} y={y - icon} size={COMPASS_ICON} strokeWidth={2.75} />
            ) : (
              <rect
                className="pm-compass__mark"
                x={x - icon}
                y={y - icon}
                width={COMPASS_ICON}
                height={COMPASS_ICON}
                mask={`url(#${markId(joint.axis, joint.direction)})`}
              />
            )}
          </g>
        );
      })}
    </g>
  );
}

function CalloutLabel({
  callout,
  snapshot,
  dim,
  index,
}: {
  callout: Callout;
  snapshot: PadSnapshot;
  dim: boolean;
  index: number;
}) {
  const { align, at, leader, glyph, title, detail, compass } = callout;
  const side = align === "end" ? -1 : 1;
  const compassAt: Point = [at[0] + side * 52, at[1]];
  const textX = at[0] + side * (compass ? 92 : 24);
  const anchor = leader[leader.length - 1];
  const lit = snapshot.lit.has(glyph);
  const className = `pm-callout${lit ? " is-lit" : ""}${dim ? " is-dim" : ""}`;
  return (
    <g className={className} style={{ "--i": index } as CSSProperties} data-align={align}>
      <polyline className="pm-leader" points={leader.map((point) => point.join(",")).join(" ")} pathLength={1} />
      <circle className="pm-leader__dot" cx={anchor[0]} cy={anchor[1]} r={3} />
      <GlyphMark kind={glyph} x={at[0]} y={at[1]} />
      {compass && <CompassPad at={compassAt} kind={compass.kind} held={compassHeld(compass.source, snapshot)} />}
      <text className="pm-callout__title" x={textX} y={detail ? at[1] - 2 : at[1] + 5} textAnchor={align}>
        {title}
      </text>
      {detail && (
        <text className="pm-callout__detail" x={textX} y={at[1] + 13} textAnchor={align}>
          {detail}
        </text>
      )}
    </g>
  );
}

/** ⌘⇧/ on a Mac, Ctrl+Shift+/ elsewhere. */
export function isMapShortcut(event: KeyboardEvent): boolean {
  return event.shiftKey && (event.metaKey || event.ctrlKey) && (event.code === "Slash" || event.key === "?" || event.key === "/");
}

function shortcutLabel() {
  return /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ ?" : "Ctrl ?";
}

interface Props {
  open: boolean;
  /** What opened the map, so the footer names the right thing to release. */
  via: "pad" | "keys";
  /** Controller name, shown in the corner. */
  label: string | null;
  /** Why the controller can't drive right now. Unset when it can. */
  note: string | null;
  /** Bindings that would do something right now. The rest are dimmed. */
  available: Record<MapGroup, boolean>;
}

/** Xbox button map shown while B (or the keyboard shortcut) is held. It only reads the pad; it never sends commands. */
export function ControllerMap({ open, via, label, note, available }: Props) {
  const [mounted, setMounted] = useState(open);
  useEffect(() => {
    if (open) {
      setMounted(true);
      return;
    }
    const timer = window.setTimeout(() => setMounted(false), EXIT_MS);
    return () => window.clearTimeout(timer);
  }, [open]);
  const snapshot = usePadSnapshot(open || mounted);

  if (!open && !mounted) return null;
  return (
    <div className="padmap" data-state={open ? "open" : "closed"}>
      <section className="padmap__card" aria-label="Controller map">
        <header className="padmap__head">
          <span className="padmap__kicker">Controller map</span>
          {label && <span className="padmap__pad">{label}</span>}
        </header>

        <svg className="padmap__art" viewBox="0 30 1000 490" role="img" aria-label="Xbox controller button layout">
          <MarkMasks />
          <Controller {...snapshot} />
          {CALLOUTS.map((callout, index) => (
            <CalloutLabel
              key={callout.glyph}
              callout={callout}
              index={index}
              snapshot={snapshot}
              dim={callout.group ? !available[callout.group] : false}
            />
          ))}
        </svg>

        <footer className="padmap__foot">
          {via === "keys" ? (
            <span className="padmap__hold">
              Release <kbd className="padmap__kbd">{shortcutLabel()}</kbd> to close
            </span>
          ) : (
            <span className="padmap__hold">
              Release <span className="padmap__b">B</span> to close
            </span>
          )}
          <span className="padmap__note">
            {note ??
              (via === "keys"
                ? "Hold B on a controller to open this from the pad."
                : "Commands pause while the map is open. Press any button to find it.")}
          </span>
        </footer>
      </section>
    </div>
  );
}
