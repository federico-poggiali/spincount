import { Link } from "react-router-dom";
import type { RecordOut } from "../api/api";
import { Cover } from "./Cover";
import styles from "./RecentlyTraded.module.css";

/** Beside the wishlist: records that left it because you got them (moved by hand or found on Discogs). */
export function RecentlyTraded({ items }: { items: RecordOut[] }) {
  return (
    <aside className={styles.aside} aria-labelledby="recently-traded">
      <header>
        <span className="micro">last 90 days</span>
        <h2 id="recently-traded">Recently traded</h2>
      </header>
      <ul className={styles.list}>
        {items.map((r) => (
          <li key={r.id}>
            <Link to={`/records/${r.id}`} className={styles.row}>
              <Cover url={r.cover_url} size={40} alt="" />
              <span className={styles.text}>
                <b>{r.title}</b>
                <span>{r.artist}</span>
              </span>
              <time className={styles.when} dateTime={r.traded_at ?? undefined}>{short(r.traded_at)}</time>
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function short(iso?: string | null): string {
  return iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "";
}
