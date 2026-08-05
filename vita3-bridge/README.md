# vita3-bridge does NOT live here

The real plugin is in the vita repo:

    /home/apps/vita-srv-v3/hermes/profile/plugins/vita3-bridge/

That copy is the one `vita3-hermes` runs and the one that ships to prod with
the app, so it is the only one that can be right. This directory exists solely
as a **mount point**: `plugin-test` bind-mounts vita's copy over it, and the
parent (`/home/repos/hermes-plugins`) is mounted read-only, so the path has to
exist here for that mount to land.

## Why there is no code here any more

There used to be a second copy, and on 2026-08-05 the two silently disagreed
while carrying the SAME `PLUGIN_VERSION` — this one had the `_fn_schema` fix
and vita's did not. The result was that vita's live agent read all 26 of its
tools as argument-less and description-less for an unknown length of time,
while a sweep against this copy would have come back green. The drift guard
could not see it because both files claimed to be the same version.

By 2026-08-06 this copy was four tools and two versions behind again, within a
day, without anyone touching it. A duplicate that only rots is worse than no
copy at all.

**If you need to change vita3's tools, change them in the vita repo.** See
[[claude/conventions/process/plugin-sweeps]], rule 1: sweep the file that RUNS,
never its twin — and treat the duplication itself as a bug.
