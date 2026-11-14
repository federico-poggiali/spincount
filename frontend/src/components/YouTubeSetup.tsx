import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type YouTubeStatus } from "../api/api";
import { pushToast } from "../toast";
import styles from "./YouTubeSetup.module.css";

const CONSOLE = "https://console.cloud.google.com";
const ADD_COST = 50;

/** The steps to make your own Google app, each opening its Google Cloud page. Your own app means your own
 *  10,000 quota units a day (about 200 tracks added). */
const STEPS: { title: string; href: string; body: React.ReactNode }[] = [
  { title: "Create a project", href: `${CONSOLE}/projectcreate`,
    body: <>Any name, for example <i>Spin Count</i>. Keep it selected at the top of the page for the next steps.</> },
  { title: "Turn on the YouTube Data API v3", href: `${CONSOLE}/apis/library/youtube.googleapis.com`,
    body: <>Click <b>Enable</b>.</> },
  { title: "Set up the sign-in screen", href: `${CONSOLE}/auth/overview`,
    body: <>Click <b>Get started</b>: an app name, your email, audience <b>External</b>, your email again as contact.</> },
  { title: "Publish it", href: `${CONSOLE}/auth/audience`,
    body: <>Click <b>Publish app</b>, so the sign-in does not expire every 7 days. When you connect, Google warns that the
      app is unverified: it is your own, so continue.</> },
  { title: "Create the client", href: `${CONSOLE}/auth/clients/create`,
    body: <>Application type <b>Desktop app</b>, any name. Copy the <b>Client ID</b> and <b>Client secret</b> it shows into
      the fields below.</> },
];

export function YouTubeSetupGuide() {
  return (
    <ol className={styles.steps} aria-label="Set up your Google app">
      {STEPS.map((s, i) => (
        <li key={s.title} className={styles.step}>
          <span className={styles.number} aria-hidden>{i + 1}</span>
          <div className={styles.stepText}>
            <b>{s.title}</b>
            <p>{s.body}</p>
          </div>
          <a className="ghost small" href={s.href} target="_blank" rel="noopener noreferrer">Open ↗</a>
        </li>
      ))}
    </ol>
  );
}

/** Paste your Google app's client ID and secret; they are checked with Google before they are kept. */
export function YouTubeCredentialsForm({ onDone }: { onDone?: () => void }) {
  const client = useQueryClient();
  const [id, setId] = useState("");
  const [secret, setSecret] = useState("");
  const save = useMutation({
    mutationFn: () => api.saveYouTubeCredentials(id, secret),
    meta: { quiet: true }, // the error shows under the fields
    onSuccess: ({ checked }) => {
      pushToast(checked ? "Google app saved and checked." : "Saved, but Google could not be reached to check it.", "info");
      setId(""); setSecret("");
      client.invalidateQueries({ queryKey: ["youtube-status"] });
      onDone?.();
    },
  });
  return (
    <form className={styles.form} onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <label className={styles.field}>
        <span className="micro">Client ID</span>
        <input className="field-input mono" value={id} onChange={(e) => setId(e.target.value)} autoComplete="off"
          spellCheck={false} placeholder="123456789-abc….apps.googleusercontent.com" />
      </label>
      <label className={styles.field}>
        <span className="micro">Client secret</span>
        <input className="field-input mono" type="password" value={secret} onChange={(e) => setSecret(e.target.value)}
          autoComplete="off" spellCheck={false} placeholder="GOCSPX-…" />
      </label>
      <div className={styles.formActions}>
        <button className="primary" type="submit" disabled={!id.trim() || !secret.trim() || save.isPending}>
          {save.isPending ? "Checking with Google…" : "Save and check"}
        </button>
        {onDone && <button className="ghost" type="button" onClick={onDone}>Cancel</button>}
      </div>
      {save.isError && <p className={styles.error} role="alert">{(save.error as Error).message}</p>}
    </form>
  );
}

/** Today's quota, as counted by this app: units used, tracks that can still be added, when it resets. */
export function YouTubeQuota({ usage, compact = false }: { usage: NonNullable<YouTubeStatus["usage"]>; compact?: boolean }) {
  const left = Math.max(usage.limit - usage.used, 0);
  const share = Math.min(usage.used / usage.limit, 1);
  const resets = new Date(usage.resets_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const tracks = Math.floor(left / ADD_COST);
  return (
    <div className={compact ? `${styles.quota} ${styles.compact}` : styles.quota} data-testid="youtube-quota">
      <div className={styles.bar} role="meter" aria-label="YouTube quota used today" aria-valuemin={0}
        aria-valuemax={usage.limit} aria-valuenow={usage.used}>
        <span className={share >= 0.8 ? styles.fillLow : styles.fill} style={{ width: `${share * 100}%` }} />
      </div>
      <p className={styles.quotaText}>
        <span className="mono">{usage.used.toLocaleString()} / {usage.limit.toLocaleString()}</span> units today
        {" · "}{left === 0 ? "used up" : `about ${tracks} ${tracks === 1 ? "track" : "tracks"} left`}
        {" · "}resets at {resets}
      </p>
    </div>
  );
}
