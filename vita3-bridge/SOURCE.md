# The source of truth for this plugin is the vita repo

    /home/apps/vita-srv-v3/hermes/profile/plugins/vita3-bridge/__init__.py

That copy is what `vita3-hermes` runs and what ships to prod with the app.
**Edit it there, then copy it here** — never the other way round, and never only
one of them.

## Why this copy exists at all

Prod's hermes agents load their plugins from a checkout of THIS repo, so
deleting this copy takes vita's tools away from them. That was tried on
2026-08-06 and reverted within minutes for exactly that reason.

## Why the duplication is still dangerous

On 2026-08-05 the two copies silently disagreed while carrying the SAME
`PLUGIN_VERSION`: this one had the `_fn_schema` fix and vita's did not, so
vita's live agent served all 26 of its tools with empty schemas — no argument
names, no descriptions — while a sweep against this copy would have come back
green. The drift guard could not see it, because both files simply claim
whatever version they are given.

A day later this copy was four tools and two versions behind again, untouched.

**So: after any change to vita3's tools, copy the file here in the same commit,
and check `PLUGIN_VERSION` matches on both sides.**

    diff /home/apps/vita-srv-v3/hermes/profile/plugins/vita3-bridge/__init__.py \
         /home/repos/hermes-plugins/vita3-bridge/__init__.py

The real fix is for prod to load vita's copy directly, the way `plugin-test`
now does with a bind mount — until then, this file is a mirror that has to be
kept honest by hand.
