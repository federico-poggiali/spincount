import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type JobOut } from "../api/api";
import styles from "./JobChip.module.css";

type Props = {
  label: string;
  jobId: number;
  onSettled?: (job: JobOut) => void;
  onRetry: () => void;
  retrying?: boolean;
};

/** A background job's progress, polled until it is done or failed; a failed job can be retried. */
export function JobChip({ label, jobId, onSettled, onRetry, retrying }: Props) {
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId),
    refetchInterval: (q) => (q.state.data && ["done", "failed"].includes(q.state.data.status) ? false : 1500),
    meta: { quiet: true },
  });
  const status = job.data?.status ?? "queued";
  const notified = useRef<number | null>(null);

  useEffect(() => {
    if (job.data && ["done", "failed"].includes(job.data.status) && notified.current !== job.data.id) {
      notified.current = job.data.id;
      onSettled?.(job.data);
    }
  }, [job.data, onSettled]);

  const skipped = job.data?.status === "done" && typeof (job.data.result as { skipped?: string } | null)?.skipped === "string";
  // A search stopped early because it stalled: what it found is kept, and it can be started again.
  const halted = job.data?.status === "done" ? (job.data.result as { halted?: string } | null)?.halted : undefined;
  const text =
    status === "queued" ? "waiting"
    : status === "running" ? "working…"
    : status === "failed" ? "failed"
    : skipped ? "skipped"
    : halted ? "stopped"
    : "done";

  return (
    <div className={`${styles.chip} ${styles[status]}`} data-status={status} data-testid={`job-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <span className={styles.pad} aria-hidden="true" />
      <div className={styles.text}>
        <span className="micro">{label}</span>
        <b role="status">{text}</b>
        {status === "failed" && job.data?.error && <small>{job.data.error}</small>}
        {halted && <small>Stopped: {halted}. What was found is kept.</small>}
        {skipped && <small>{(job.data!.result as { skipped: string }).skipped}</small>}
      </div>
      {(status === "failed" || halted) && <button className="ghost small" onClick={onRetry} disabled={retrying}>Retry</button>}
    </div>
  );
}
