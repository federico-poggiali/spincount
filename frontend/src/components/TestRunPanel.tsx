import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Activity, type ActivityJob, type ActivityStep } from "../api/api";
import styles from "./TestRunPanel.module.css";

/** `make run-test` only: a small panel with what runs in the background, step by step, and how long each
 *  search takes. In a normal run the feed answers 404 once and the panel never shows. */
export function TestRunPanel() {
  const feed = useQuery({
    queryKey: ["test-run-activity"],
    queryFn: ({ signal }) => api.activity(signal),
    refetchInterval: (q) => (q.state.status === "error" ? false : 1000),
    retry: false,
    meta: { quiet: true },
  });
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem("test-run-panel") !== "closed"; } catch { return true; }
  });
  const toggle = () => {
    setOpen(!open);
    try { localStorage.setItem("test-run-panel", open ? "closed" : "open"); } catch { /* private window */ }
  };
  const now = useClock(feed.data, !!feed.data?.current);
  const drag = useDrag();

  if (!feed.data) return null;
  const { current, recent, queued } = feed.data;
  const searches = recent.filter((j) => j.type === "audio" && j.status === "done" && !j.cached && j.finished);
  const average = searches.length ? searches.reduce((s, j) => s + (j.finished! - j.started), 0) / searches.length : null;

  return (
    <aside ref={drag.ref} className={styles.panel} aria-label="Test run" data-open={open} data-sized={open && drag.sized}
      style={drag.style(open)}>
      <button type="button" className={styles.bar} aria-expanded={open}
        title="Drag to move · double-click to put it back in the corner"
        onPointerDown={drag.onPointerDown} onDoubleClick={drag.reset}
        onClick={() => { if (!drag.moved()) toggle(); }}>
        <span className={styles.dot} data-live={!!current} aria-hidden="true" />
        <span className="micro">test run</span>
        <span className={styles.summary}>
          {current ? `${current.type} · ${fmt(now - current.started)}` : "idle"}
          {queued.length > 0 && ` · ${queued.length} queued`}
        </span>
        <span className={styles.chev} aria-hidden="true">{open ? "▾" : "▴"}</span>
      </button>

      {open && (
        <div className={styles.body}>
          <section>
            <h3 className="micro">now</h3>
            {current ? <Job job={current} now={now} live /> : <p className={styles.quiet}>Nothing is running.</p>}
          </section>

          {queued.length > 0 && (
            <section>
              <h3 className="micro">queued · {queued.length}</h3>
              <ol className={styles.queue}>
                {queued.slice(0, 6).map((q) => <li key={q.id}><b>{q.type}</b> {q.record ?? `#${q.id}`}</li>)}
                {queued.length > 6 && <li className={styles.quiet}>and {queued.length - 6} more</li>}
              </ol>
            </section>
          )}

          {recent.length > 0 && (
            <section>
              <h3 className="micro">
                recent{average != null && <> · audio search avg <span className="mono">{fmt(average)}</span> over {searches.length}</>}
              </h3>
              <ul className={styles.recent}>
                {recent.map((j) => (
                  <li key={j.id}>
                    <details>
                      <summary>
                        <span className={styles.status} data-status={j.status}>{j.status === "done" ? "✓" : "✕"}</span>
                        <b>{j.type}</b>
                        <span className={styles.name}>{j.record ?? `job ${j.id}`}</span>
                        <span className="mono">{j.cached ? "cached" : fmt(j.finished! - j.started)}</span>
                      </summary>
                      <Job job={j} now={j.finished!} />
                    </details>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
      {open && (
        <span className={styles.grip} aria-hidden="true" title="Drag to resize · double-click for the normal size"
          onPointerDown={drag.onResizeDown} onDoubleClick={drag.resetSize} />
      )}
    </aside>
  );
}

/** One job: its record, the time each source took, and every step with its duration. */
function Job({ job, now, live = false }: { job: ActivityJob; now: number; live?: boolean }) {
  const steps = job.steps.map((s) => ({ ...s, ms: s.ms ?? now - s.started }));
  const total = Math.max(1, (job.finished ?? now) - job.started);
  const bySource = new Map<string, number>();
  for (const s of steps) {
    const key = s.adapter ?? s.stage;
    bySource.set(key, (bySource.get(key) ?? 0) + s.ms);
  }
  const ranked = [...bySource].sort((a, b) => b[1] - a[1]);
  const peak = ranked[0]?.[1] ?? 1;
  const facts = [job.tracks != null && `${job.tracks} tracks`, job.found != null && `${job.found} found`,
    job.params.refresh ? "from scratch" : null, job.cached && "answered from cache"].filter(Boolean).join(" · ");
  const LIVE_ROWS = 8; // while running, only the latest steps: the whole list is there once the job is done
  const shown = live ? steps.slice(-LIVE_ROWS).reverse() : steps; // live: newest on top

  return (
    <div className={styles.job}>
      {live && (
        <p className={styles.head}>
          <b>{job.type}</b> <span className={styles.name}>{job.record ?? `job ${job.id}`}</span>
          <span className="mono">{fmt(now - job.started)}</span>
        </p>
      )}
      {facts && <p className={styles.quiet}>{facts}</p>}
      {job.error && <p className={styles.error}>{job.error}</p>}

      {ranked.length > 0 && (
        <ul className={styles.sources} aria-label="Time per source">
          {ranked.map(([name, ms]) => (
            <li key={name}>
              <span>{name}</span>
              <i style={{ width: `${(ms / peak) * 100}%` }} />
              <span className="mono">{fmt(ms)}</span>
              <span className="mono">{Math.round((ms / total) * 100)}%</span>
            </li>
          ))}
        </ul>
      )}

      {shown.length > 0 && (
        <table className={styles.steps}>
          <thead>
            <tr><th>lvl</th><th>source</th><th>stage</th><th>time</th><th>result</th></tr>
          </thead>
          <tbody>
            {shown.map((s) => (
              <tr key={`${s.started}-${s.level}-${s.adapter}-${s.stage}`} data-open={live && s.open}>
                <td className="mono">{s.level ?? "·"}</td>
                <td>{s.adapter ?? "all"}</td>
                <td>{s.stage}</td>
                <td className={`mono ${styles.time}`}>{fmt(s.ms)}</td>
                <td className={s.detail.error ? styles.error : styles.quiet}>{live && s.open ? "working…" : describe(s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {live && steps.length > LIVE_ROWS && <p className={styles.quiet}>and {steps.length - LIVE_ROWS} earlier steps</p>}
    </div>
  );
}

function describe(s: ActivityStep): string {
  if (s.detail.error) return String(s.detail.error);
  const d = s.detail;
  const parts = Object.entries(d).filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => `${v} ${k}`);
  if (!parts.length && s.tracks != null) return `${s.tracks} tracks`;
  return parts.join(" · ") || "·";
}

type Pos = { x: number; y: number };
type Size = { w: number; h: number };
const POS_KEY = "test-run-panel-pos";
const SIZE_KEY = "test-run-panel-size";
const MIN: Size = { w: 300, h: 160 };

function load<T>(key: string): T | null {
  try { return JSON.parse(localStorage.getItem(key) ?? "null"); } catch { return null; }
}
function store(key: string, value: unknown) {
  try { if (value) localStorage.setItem(key, JSON.stringify(value)); else localStorage.removeItem(key); } catch { /* private window */ }
}

/** Move the panel by dragging its bar; the spot is remembered and kept on screen. A press that moves less
 *  than a few pixels is still a click (open/close); double-click goes back to the corner. */
function useDrag() {
  const ref = useRef<HTMLElement>(null);
  const [pos, setPos] = useState<Pos | null>(() => load<Pos>(POS_KEY));
  const [size, setSize] = useState<Size | null>(() => load<Size>(SIZE_KEY));
  const movedRef = useRef(false);

  const clamp = useCallback((p: Pos): Pos => {
    const el = ref.current;
    const w = el?.offsetWidth ?? 200, h = el?.offsetHeight ?? 40;
    return { x: Math.min(Math.max(8, p.x), window.innerWidth - w - 8), y: Math.min(Math.max(8, p.y), window.innerHeight - h - 8) };
  }, []);
  const save = (p: Pos | null) => store(POS_KEY, p);

  // Keep it on screen when the window shrinks or the panel opens taller.
  useEffect(() => {
    if (!pos) return;
    const fit = () => setPos((p) => {
      if (!p) return p;
      const c = clamp(p);
      return c.x === p.x && c.y === p.y ? p : c;
    });
    fit();
    window.addEventListener("resize", fit);
    const ro = new ResizeObserver(fit);
    if (ref.current) ro.observe(ref.current);
    return () => { window.removeEventListener("resize", fit); ro.disconnect(); };
  }, [pos, clamp]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0 || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const start = { x: e.clientX, y: e.clientY };
    const grab = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    movedRef.current = false;
    let last: Pos | null = null;
    const move = (ev: PointerEvent) => {
      if (!movedRef.current && Math.hypot(ev.clientX - start.x, ev.clientY - start.y) < 5) return;
      movedRef.current = true;
      last = clamp({ x: ev.clientX - grab.x, y: ev.clientY - grab.y });
      setPos(last);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (last) save(last);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  /** The bottom-right grip: width and height follow the pointer; the top-left corner stays put. */
  const onResizeDown = (e: React.PointerEvent) => {
    if (e.button !== 0 || !ref.current) return;
    e.preventDefault();
    e.stopPropagation();
    const rect = ref.current.getBoundingClientRect();
    const origin = { x: rect.left, y: rect.top };
    if (!pos) { setPos(origin); save(origin); }  // anchored bottom-left until now: pin the top-left corner
    const start = { x: e.clientX, y: e.clientY, w: rect.width, h: rect.height };
    let last: Size | null = null;
    const move = (ev: PointerEvent) => {
      last = {
        w: Math.round(Math.min(Math.max(MIN.w, start.w + ev.clientX - start.x), window.innerWidth - origin.x - 8)),
        h: Math.round(Math.min(Math.max(MIN.h, start.h + ev.clientY - start.y), window.innerHeight - origin.y - 8)),
      };
      setSize(last);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (last) store(SIZE_KEY, last);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const reset = () => { setPos(null); save(null); };
  const resetSize = () => { setSize(null); store(SIZE_KEY, null); };
  const moved = () => { const m = movedRef.current; movedRef.current = false; return m; };
  // The size only applies while open: closed, the panel is just its bar.
  const style = (open: boolean): React.CSSProperties => ({
    ...(pos ? { left: pos.x, top: pos.y, bottom: "auto" } : {}),
    ...(open && size ? { width: Math.min(size.w, window.innerWidth - 16), height: Math.min(size.h, window.innerHeight - 16) } : {}),
  });
  return { ref, style, sized: !!size, onPointerDown, reset, moved, onResizeDown, resetSize };
}

/** The server's clock, ticking locally between polls so running times move smoothly. */
function useClock(data: Activity | undefined, running: boolean): number {
  const [offset, setOffset] = useState(0);
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => { if (data) setOffset(Date.now() - data.now); }, [data]);
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setTick(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [running]);
  return Math.max(tick, data ? data.now + offset : 0) - offset;
}

function fmt(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
