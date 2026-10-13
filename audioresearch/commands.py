"""CLI command implementations (filled in as the pipeline is built)."""
from __future__ import annotations


def _todo(name: str) -> int:
    print(f"`{name}` is not implemented yet")
    return 2


def _store():
    from .store import Store

    return Store()


def _table(result) -> str:
    rows = [("pos", "status", "source", "quality", "conf", "level")]
    rows += [(t.position, t.status.value, t.source or "-", t.quality.value if t.quality else "-",
              f"{t.confidence:.2f}" if t.source else "-", str(t.level) if t.level is not None else "-") for t in result.tracks]
    widths = [max(len(r[i]) for r in rows) for i in range(6)]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def print_result(result, identity=None) -> None:
    print(_table(result))
    c = result.counts()
    print(f"\n{c['found']} found, {c['review']} review, {c['not_found']} not found"
          + (f"; adapters switched off: {', '.join(result.adapters_off)}" if result.adapters_off else ""))
    for t in result.tracks:
        if t.status.value != "found":
            print(f"  {t.position}: {t.reason}")


def research(args) -> int:
    import sys

    from .pipeline import research as run

    def progress(e):
        if e.type == "level_started":
            print(f"level {e.level}: {e.data['unfound']} track(s) to find", file=sys.stderr)
        elif e.type == "track_resolved":
            print(f"  {e.position}: {e.data['status']} via {e.data['source']} ({e.data['quality']})", file=sys.stderr)
        elif e.type == "adapter_off":
            print(f"  adapter {e.adapter} switched off: {e.data['reason']}", file=sys.stderr)

    result = run(args.url, args.levels, args.refresh, progress, store=_store())
    print_result(result)
    if args.json:
        from pathlib import Path

        Path(args.json).write_text(result.to_json())
        print(f"JSON written to {args.json}")
    return 0


def report(args) -> int:
    store = _store()
    got = store.get_result(args.release_id)
    prov = store.get_provenance(args.release_id)
    if not got and not prov:
        print(f"nothing stored for release {args.release_id}; run `research` first")
        return 1
    if got:
        print_result(got[0])
        print(f"\ndecided {got[2]}, levels {got[1]}")
    print("\nProvenance (latest run):")
    for p in prov:
        score = f"{p['score']:.2f}" if p["score"] is not None else "  - "
        print(f"  {p['position'] or '-':>3}  {p['adapter']:<18} {p['outcome']:<9} {score}  {p['reason']}\n       {p['url']}")
    return 0


def review(args) -> int:
    from .models import Status
    from .pipeline import research as run

    store = _store()
    got = store.get_result(args.release_id)
    if not got:
        print(f"nothing stored for release {args.release_id}; run `research` first")
        return 1
    result = got[0]
    todo = [t for t in result.tracks if t.status != Status.FOUND]
    if not todo:
        print("nothing to review: every track is found")
        return 0
    relink = False
    for t in todo:
        print(f"\n{t.position}: {t.status.value}; {t.reason}\n  {t.url or ''}")
        while True:
            ans = input("  [a]ccept  [r]eject  [l]ink (paste a URL)  [s]kip > ").strip().lower()
            if ans == "a" and t.status == Status.REVIEW:
                store.set_override(args.release_id, t.position, "accept", t.url)
                t.status = Status.FOUND
                t.reason += "; accepted by you in review"
            elif ans == "r" and t.url:
                store.set_override(args.release_id, t.position, "reject", t.url)
                t.status, t.audio_path, t.source, t.quality, t.confidence = Status.NOT_FOUND, None, None, None, 0.0
                t.reason = "rejected by you in review"
            elif ans == "l":
                url = input("  URL: ").strip()
                if not url:
                    continue
                store.set_manual_link(args.release_id, t.position, url)
                relink = True
            elif ans != "s":
                print("  (a/r/l/s; accept only applies to tracks in review, reject needs a result)")
                continue
            break
    store.save_result(result, got[1])
    if relink:
        print("\nre-running with your links ...")
        result = run(args.release_id, range(6), store=store)
    print_result(result)
    return 0


def viewer(args) -> int:
    from .viewer.app import serve

    return serve(args.fake, args.port)
