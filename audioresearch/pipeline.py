"""Stages 2 to 6 wired together, level by level, per release."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from . import config, decide as decide_mod, events as ev, fetch as fetch_mod, verify as verify_mod
from .adapters import Registry, default_registry
from .adapters.base import Adapter, AdapterUnavailable
from .decide import Accepted, confidence, decide_track
from .health import AdapterHealth
from .identify import identify
from .matcher import Match, MatchOutcome, match_candidates
from .models import Candidate, Quality, Reading, ReleaseIdentity, ReleaseResult, Status, TrackRef, TrackResult

log = logging.getLogger(__name__)
FAILED = object()


@dataclass
class _AdapterRun:
    adapter: Adapter
    candidates: list[Candidate] = field(default_factory=list)
    outcome: MatchOutcome | None = None
    failed: bool = False


class Run:
    """All state of one research run."""

    def __init__(self, identity: ReleaseIdentity, registry: Registry, emitter: ev.Emitter, *, store=None,
                 refresh: bool = False, audio_dir: Path | None = None, review_threshold: float | None = None,
                 max_candidates: int = 3, health: AdapterHealth | None = None, search_all: bool = False):
        self.identity, self.registry, self.em, self.store = identity, registry, emitter, store
        self.refresh = refresh
        self.search_all = search_all   # test mode: every level searches every track, nothing is ever skipped
        self.audio_dir = audio_dir or config.AUDIO_CACHE_DIR
        self.review_threshold = config.REVIEW_THRESHOLD if review_threshold is None else review_threshold
        self.max_candidates = max_candidates
        self.health = health or AdapterHealth()
        self.accepted: dict[str, list[Accepted]] = {t.position: [] for t in identity.tracks}
        self.readings: dict[str, list[Reading]] = {t.position: [] for t in identity.tracks}
        self.results: dict[str, TrackResult] = {t.position: TrackResult(t.position) for t in identity.tracks}
        self.overrides = store.overrides(identity.discogs_release_id) if store else {}
        self.rejected_urls = {o["detail"] for o in self.overrides.values() if o["action"] == "reject" and o["detail"]}

    # ---- helpers -------------------------------------------------------------------------------
    def settled(self, pos: str) -> bool:
        r = self.results[pos]
        return r.level == 0 and r.status == Status.FOUND or (r.status == Status.FOUND and r.quality == Quality.FULL)

    def eligible(self, adapter: Adapter, pos: str) -> bool:
        if self.search_all:
            return True
        r = self.results[pos]
        if r.status == Status.NOT_FOUND:
            return True
        if r.level == 0 and r.status == Status.FOUND:
            return False  # level 0 always wins and is never replaced
        if r.status == Status.FOUND and r.quality.rank >= adapter.max_quality.rank:
            return False
        return True

    def unfound(self) -> list[str]:
        if self.search_all:
            return list(self.results)
        return [p for p in self.results if not self.settled(p)]

    def _guard(self, adapter: Adapter, fn: Callable, *args):
        """Call an adapter; failures are counted, and enough of them switch it off."""
        if self.health.is_off(adapter.name):
            return FAILED
        try:
            out = fn(*args)
            self.health.ok(adapter.name)
            return out
        except Exception as e:  # network, parser, site change: never kill the run
            log.warning("%s failed: %s", adapter.name, e)
            switched = self.health.disable(adapter.name, e) if isinstance(e, AdapterUnavailable) else self.health.fail(adapter.name, e)
            if switched:
                self.em.emit(ev.ADAPTER_OFF, adapter=adapter.name, reason=str(e)[:200])
            self.last_error = str(e)
            return FAILED

    # ---- stage 2 + 3 for one group of adapters -------------------------------------------------
    def _run_group(self, level: int, group: list[Adapter]) -> list[_AdapterRun]:
        runs: list[_AdapterRun] = []
        taken: set[str] = set()   # positions an earlier adapter of the group already matched
        for adapter in group:
            run = _AdapterRun(adapter)
            runs.append(run)
            tracks = [t for t in self.identity.tracks if t.position not in taken and self.eligible(adapter, t.position)]
            if not tracks or self.health.is_off(adapter.name):
                if self.health.is_off(adapter.name):
                    run.failed = True
                continue
            self.em.emit(ev.STAGE_STARTED, level=level, adapter=adapter.name, stage=ev.SEARCH, tracks=len(tracks))
            t = self.em.timer()
            got = self._cached_search(adapter, tracks)
            if got is FAILED:
                run.failed = True
                self.em.emit(ev.STAGE_FINISHED, level=level, adapter=adapter.name, stage=ev.SEARCH, ms=t.ms,
                             candidates=0, error=getattr(self, "last_error", "failed"))
                continue
            run.candidates = got
            for d in adapter.take_diagnostics():
                self.em.emit(ev.CANDIDATE_REJECTED, level=level, adapter=adapter.name, url=d["url"], reason=d["reason"])
                if self.store:
                    self.store.add_provenance(self.identity.discogs_release_id, self.em.run_id, adapter.name, d["url"], None,
                                              None, "rejected", d["reason"], {})
            self.em.emit(ev.STAGE_FINISHED, level=level, adapter=adapter.name, stage=ev.SEARCH, ms=t.ms, candidates=len(got))

            self.em.emit(ev.STAGE_STARTED, level=level, adapter=adapter.name, stage=ev.MATCH)
            t = self.em.timer()
            run.outcome = self._match(adapter, tracks, got)
            for cand, reason in run.outcome.rejected:
                self.em.emit(ev.CANDIDATE_REJECTED, level=level, adapter=adapter.name, url=cand.url, reason=reason)
                self._provenance(adapter, cand, None, "rejected", reason)
            for pos, ms in run.outcome.matches.items():
                for m in ms:
                    self.em.emit(ev.CANDIDATE_MATCHED, level=level, adapter=adapter.name, position=pos, url=m.candidate.url,
                                 score=round(m.score, 3), quality=m.candidate.quality_hint.value, via=m.via)
            self.em.emit(ev.STAGE_FINISHED, level=level, adapter=adapter.name, stage=ev.MATCH, ms=t.ms,
                         releases=len(run.outcome.releases), tracks=len(run.outcome.matches),
                         rejected=len(run.outcome.rejected))
            taken |= set(run.outcome.matches)
        return runs

    def _match(self, adapter: Adapter, tracks: list[TrackRef], cands: list[Candidate]) -> MatchOutcome:
        trusted = [c for c in cands if c.extra.get("trusted")]
        rest = [c for c in cands if not c.extra.get("trusted")]
        out = match_candidates(self.identity, tracks, rest, top=self.max_candidates)
        wanted = {t.position for t in tracks}
        for c in trusted:  # level 0: the adapter's own claim (your file, your pasted link) is final
            if c.position in wanted:
                out.matches.setdefault(c.position, []).insert(0, Match(c.position, c, 1.0, "trusted"))
        return out

    def _cached_search(self, adapter: Adapter, tracks: list[TrackRef]):
        cacheable = adapter.level > 0  # level 0 reads your own files and links: always fresh
        if self.store and not self.refresh and cacheable:
            hit = self.store.get_candidates(self.identity.discogs_release_id, adapter.name, [t.position for t in tracks])
            if hit is not None:
                return hit
        got = self._guard(adapter, adapter.search, self.identity, tracks)
        if got is not FAILED and self.store and cacheable:
            self.store.save_candidates(self.identity.discogs_release_id, adapter.name, [t.position for t in tracks], got)
        return got

    def _provenance(self, adapter, cand: Candidate, score, outcome: str, reason: str, **extra) -> None:
        if self.store:
            self.store.add_provenance(self.identity.discogs_release_id, self.em.run_id, adapter.name, cand.url,
                                      cand.position, score, outcome, reason, extra)

    # ---- stages 4 to 6 for one level -----------------------------------------------------------
    def _fetch_verify(self, level: int, runs: list[_AdapterRun]) -> None:
        by_adapter = {r.adapter.name: r.adapter for r in runs}
        per_pos: dict[str, list[Match]] = {}
        for r in runs:
            if r.outcome:
                for pos, ms in r.outcome.matches.items():
                    per_pos.setdefault(pos, []).extend(ms)
                    self._collect_readings(pos, ms)
        for pos in per_pos:  # best quality first, then best score; keep the top few overall
            per_pos[pos].sort(key=lambda m: (-m.candidate.quality_hint.rank, -m.score))
            per_pos[pos] = per_pos[pos][:self.max_candidates]
        if not per_pos:
            return
        stats = {"fetched": 0, "failed": 0, "accepted": 0, "rejected": 0}
        by = {a: {"fetched": 0, "failed": 0, "accepted": 0, "rejected": 0} for a in by_adapter}
        self.em.emit(ev.STAGE_STARTED, level=level, stage=ev.FETCH, tracks=len(per_pos))
        tf = self.em.timer()
        verify_ms = 0

        def work(pos: str):
            return self._work_position(level, pos, per_pos[pos], by_adapter)

        with ThreadPoolExecutor(max_workers=min(4, len(per_pos))) as pool:
            outcomes = list(pool.map(work, per_pos))
        for pos, o in zip(per_pos, outcomes):
            verify_ms += o["verify_ms"]
            for k in ("fetched", "failed", "accepted", "rejected"):
                for adapter_name, n in o[k].items():
                    stats[k] += n
                    by[adapter_name][k] += n
            self.accepted[pos].extend(o["accepted_items"])
        fetch_ms = max(0, tf.ms - verify_ms)
        self.em.emit(ev.STAGE_FINISHED, level=level, stage=ev.FETCH, ms=fetch_ms, fetched=stats["fetched"],
                     failed=stats["failed"], by_adapter={a: {"fetched": s["fetched"], "failed": s["failed"]} for a, s in by.items()})
        self.em.emit(ev.STAGE_STARTED, level=level, stage=ev.VERIFY)
        self.em.emit(ev.STAGE_FINISHED, level=level, stage=ev.VERIFY, ms=verify_ms, accepted=stats["accepted"],
                     rejected=stats["rejected"], by_adapter={a: {"accepted": s["accepted"], "rejected": s["rejected"]} for a, s in by.items()})

    def _collect_readings(self, pos: str, matches: list[Match]) -> None:
        for m in matches:
            for r in m.candidate.readings:
                if not any((r.source, r.bpm, r.key) == (x.source, x.bpm, x.key) for x in self.readings[pos]):
                    self.readings[pos].append(r)

    def _work_position(self, level: int, pos: str, matches: list[Match], adapters: dict[str, Adapter]) -> dict:
        """Fetch candidates best first; stop at the first one that verifies."""
        track = self.identity.track(pos)
        out = {"fetched": {}, "failed": {}, "accepted": {}, "rejected": {}, "accepted_items": [], "verify_ms": 0}
        bump = lambda k, name: out[k].__setitem__(name, out[k].get(name, 0) + 1)  # noqa: E731
        for m in matches:
            adapter = adapters.get(m.candidate.adapter)
            if adapter is None or self.health.is_off(adapter.name):
                continue
            if m.candidate.url in self.rejected_urls:
                self.em.emit(ev.CANDIDATE_REJECTED, level=level, adapter=adapter.name, position=pos,
                             url=m.candidate.url, reason="rejected by you in review")
                continue
            dest = fetch_mod.dest_for(self.audio_dir, self.identity, pos, adapter.name)
            got, from_cache = self._cached_fetch(adapter, m.candidate, dest, pos)
            if got is FAILED:
                bump("failed", adapter.name)
                self.em.emit(ev.CANDIDATE_REJECTED, level=level, adapter=adapter.name, position=pos,
                             url=m.candidate.url, reason="fetch failed")
                self._provenance(adapter, m.candidate, m.score, "rejected", "fetch failed")
                continue
            bump("fetched", adapter.name)
            fetched = got if from_cache else fetch_mod.finalize(got, None if m.via == "trusted" else track.duration)
            tv = self.em.timer()
            if m.via == "trusted":
                v = verify_mod.Verification(True, ["your own file or link"])
            else:
                v = verify_mod.verify(track, fetched, m.candidate)
            out["verify_ms"] += tv.ms
            if self.store and not from_cache:
                self.store.save_fetched(self.identity.discogs_release_id, pos, fetched)
            if not v.ok:
                bump("rejected", adapter.name)
                reason = "; ".join(v.reasons) or "verification failed"
                self.em.emit(ev.CANDIDATE_REJECTED, level=level, adapter=adapter.name, position=pos,
                             url=m.candidate.url, reason=reason)
                self._provenance(adapter, m.candidate, m.score, "rejected", reason, quality=fetched.quality.value)
                continue
            bump("accepted", adapter.name)
            self._provenance(adapter, m.candidate, m.score, "accepted", "; ".join(v.reasons) or "verified",
                             quality=fetched.quality.value, warnings=v.warnings)
            self.em.emit(ev.CANDIDATE_ACCEPTED, level=level, adapter=adapter.name, position=pos, url=m.candidate.url,
                         quality=fetched.quality.value, score=round(m.score, 3))
            out["accepted_items"].append(Accepted(m, fetched, v, level))
            if not self.search_all:
                break
        return out

    def _cached_fetch(self, adapter: Adapter, cand: Candidate, dest: Path, position: str):
        rid = self.identity.discogs_release_id
        if self.store and not self.refresh and adapter.level > 0:
            hit = self.store.get_fetched(rid, position, adapter.name, cand.url)
            if hit:
                return hit, True
        got = self._guard(adapter, adapter.fetch, cand, dest)
        return got, False

    def _decide(self, level: int) -> None:
        self.em.emit(ev.STAGE_STARTED, level=level, stage=ev.DECIDE)
        t = self.em.timer()
        found = review = 0
        for pos in self.results:
            items = self.accepted[pos]
            for a in items:
                a.agreement = verify_mod.cross_check_all(a, items) if hasattr(verify_mod, "cross_check_all") else None
            new = decide_track(pos, items, self.readings[pos], self.review_threshold)
            old = self.results[pos]
            self.results[pos] = new
            found += new.status == Status.FOUND
            review += new.status == Status.REVIEW
            changed = (old.status, old.source, old.quality, old.url) != (new.status, new.source, new.quality, new.url)
            if changed and new.status != Status.NOT_FOUND:
                self.em.emit(ev.TRACK_RESOLVED, level=level, position=pos, status=new.status.value, source=new.source,
                             quality=new.quality.value if new.quality else None, confidence=round(new.confidence, 3),
                             reason=new.reason, url=new.url)
        self.em.emit(ev.STAGE_FINISHED, level=level, stage=ev.DECIDE, ms=t.ms, found=found, review=review)

    # ---- one level -----------------------------------------------------------------------------
    def run_level(self, level: int) -> None:
        before = {p: (r.status, r.source, r.quality) for p, r in self.results.items()}
        unfound = self.unfound()
        self.em.emit(ev.LEVEL_STARTED, level=level, unfound=len(unfound), positions=unfound,
                     adapters=[a.name for a in self.registry.for_level(level)])
        tl = self.em.timer()
        groups = self.registry.groups(level)
        runs: list[_AdapterRun] = []
        if groups and unfound:
            with ThreadPoolExecutor(max_workers=len(groups)) as pool:
                for rs in pool.map(lambda g: self._run_group(level, g), groups):
                    runs.extend(rs)
            self._fetch_verify(level, runs)
            self._decide(level)
        resolved = [p for p, r in self.results.items()
                    if r.status != Status.NOT_FOUND and (r.status, r.source, r.quality) != before[p]]
        self.em.emit(ev.LEVEL_FINISHED, level=level, resolved=resolved, unfound=self.unfound(), ms=tl.ms)

    def final(self) -> ReleaseResult:
        tracks = []
        for t in self.identity.tracks:
            r = self.results[t.position]
            alts = [{"source": a.fetched.adapter, "quality": a.fetched.quality.value,
                     "confidence": round(confidence(a, self.review_threshold), 3), "audio_path": str(a.fetched.path), "url": a.fetched.url,
                     "level": a.level, "page": a.match.candidate.extra.get("release_url")}
                    for a in self.accepted[t.position] if str(a.fetched.path) != r.audio_path]
            r.alternatives = alts
            o = self.overrides.get(t.position)
            if o and o["action"] == "accept" and r.status == Status.REVIEW and o["detail"] == r.url:
                r.status, r.reason = Status.FOUND, f"{r.reason}; accepted by you in review"
            tracks.append(r)
        return ReleaseResult(self.identity.discogs_release_id, tracks, sorted(self.health.off))


def research(url_or_id: str | int, levels: Iterable[int] = range(0, 6), refresh: bool = False, on_event=None, *,
             registry: Registry | None = None, identity: ReleaseIdentity | None = None, discogs=None, store=None,
             audio_dir: Path | None = None, run_id: str | None = None, review_threshold: float | None = None,
             max_candidates: int = 3, search_all: bool = False) -> ReleaseResult:
    levels = sorted(set(levels))
    callback = on_event
    if store is not None:
        def callback(e, _user=on_event):  # noqa: F811  every event is stored so a run can be replayed
            store.add_event(e)
            if _user:
                _user(e)
    em = ev.Emitter(run_id, callback)
    if store is not None:
        store.start_run(em.run_id, str(url_or_id))
    em.emit(ev.RUN_STARTED, url=str(url_or_id), levels=levels, search_all=search_all)
    t = em.timer()
    if identity is None:
        identity = identify(url_or_id, discogs, store, refresh)
    elif store is not None:
        store.save_identity(identity)
    em.emit(ev.RELEASE_IDENTIFIED, artist=identity.artist, title=identity.title, catno=identity.catno,
            label=identity.label, year=identity.year, cover=identity.cover, release_id=identity.discogs_release_id,
            tracks=[t_.to_dict() for t_ in identity.tracks], track_count=len(identity.tracks), ms=t.ms)
    registry = registry or default_registry(store=store)
    total = em.timer()
    if store is not None and not refresh and not search_all:
        cached = store.cached_result(identity.discogs_release_id, levels)
        saved_at = (store.get_result(identity.discogs_release_id) or (None, None, ""))[2]
        if cached and not any(a.changed_since(identity.discogs_release_id, saved_at) for a in registry.all()):
            em.emit(ev.CACHE_HIT, saved_at=saved_at)
            em.emit(ev.RUN_FINISHED, **cached.counts(), ms=total.ms, adapters_off=cached.adapters_off,
                    release_id=identity.discogs_release_id, cached=True)
            if store is not None:
                store.save_run_result(em.run_id, cached)
            return cached
    run = Run(identity, registry, em, store=store, refresh=refresh, audio_dir=audio_dir,
              review_threshold=review_threshold, max_candidates=max_candidates, search_all=search_all)
    for level in levels:
        run.run_level(level)
    result = run.final()
    if store is not None:
        store.save_result(result, levels, em.run_id)
        store.save_readings(identity.discogs_release_id, em.run_id, run.readings)
        store.save_run_result(em.run_id, result)
    em.emit(ev.RUN_FINISHED, **result.counts(), ms=total.ms, adapters_off=result.adapters_off,
            release_id=identity.discogs_release_id)
    return result
