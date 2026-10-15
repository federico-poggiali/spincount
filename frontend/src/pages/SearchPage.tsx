import { Fragment, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, type ExactResults } from "../api/api";
import { Cover } from "../components/Cover";
import { Skeleton } from "../components/Skeleton";
import { useDebounced } from "../hooks";
import styles from "./SearchPage.module.css";

/** Renders an FTS snippet whose matches are wrapped in \x02 ... \x03. */
function Snippet({ text }: { text: string }) {
  return (
    <>
      {text.split("\x02").map((part, i) => {
        const [hit, rest] = part.split("\x03");
        return i === 0 ? <Fragment key={i}>{part}</Fragment> : (
          <Fragment key={i}><mark>{hit}</mark>{rest}</Fragment>
        );
      })}
    </>
  );
}

function NoteHit({ hit }: { hit: ExactResults["notes"][number] }) {
  return (
    <li>
      <Link to={`/records/${hit.record.id}#note-${hit.note.id}`} className={styles.hit}>
        <Cover url={hit.record.cover_url} size={56} />
        <div className={styles.hitBody}>
          <p className={styles.snippet}><Snippet text={hit.snippet} /></p>
          <span className={styles.where}>
            {hit.track ? `${hit.track.position} ${hit.track.title} · ` : ""}{hit.record.artist} – {hit.record.title}
          </span>
        </div>
      </Link>
    </li>
  );
}

/** Word search over notes, artists, titles and labels. Embedded in the library popup it keeps its query
 *  locally, so it never touches the library's URL. */
export default function SearchPage({ embedded = false }: { embedded?: boolean }) {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(embedded ? "" : params.get("q") ?? "");
  const q = useDebounced(text.trim(), 300);
  const input = useRef<HTMLInputElement>(null);

  // "/" lands here with ?focus=1, also when the page is already open.
  useEffect(() => { input.current?.focus(); }, [params.get("focus")]);
  useEffect(() => {
    if (embedded || q === (params.get("q") ?? "")) return;
    setParams(q ? { q } : {}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const results = useQuery({
    queryKey: ["search", q],
    queryFn: ({ signal }) => api.search(q, signal),
    enabled: q.length > 0,
  });
  const data = results.data;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <span className="micro">search</span>
        <h1 className={embedded ? styles.compact : undefined}>Search your library</h1>
      </header>
      <label className={styles.field}>
        <span className="sr">Search your notes</span>
        <input ref={input} type="search" autoFocus autoComplete="off" value={text} onChange={(e) => setText(e.target.value)}
          placeholder="words in a note, an artist, a title" />
      </label>

      {q === "" && <p className={styles.hint}>Matches whole words and word starts in every note, plus record artist, title and label.</p>}
      {q !== "" && results.isFetching && !data && <Skeleton rows={4} height={72} />}
      {data && (
        data.notes.length === 0 && data.records.length === 0
          ? <p className={styles.hint}>Nothing matches “{q}”.</p>
          : <>
              {data.notes.length > 0 && (
                <ul className={styles.results} aria-label="Matching notes">
                  {data.notes.map((h) => <NoteHit key={h.note.id} hit={h} />)}
                </ul>
              )}
              {data.records.length > 0 && (
                <section aria-label="Matching records">
                  <h2 className="micro">records</h2>
                  <ul className={styles.recs}>
                    {data.records.map((r) => (
                      <li key={r.id}><Link to={`/records/${r.id}`}><Cover url={r.cover_url} size={40} /><span><b>{r.title}</b><small>{r.artist}</small></span></Link></li>
                    ))}
                  </ul>
                </section>
              )}
            </>
      )}
    </div>
  );
}
