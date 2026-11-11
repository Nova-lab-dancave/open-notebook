# Open Notebook (Nova-Notes fork)

Domain glossary for the fork. Terms only; no implementation detail.

## Podcasts

**Podcast Feed**:
The single RSS feed that lists every Published Episode, for subscribing from a podcast app by URL. One feed for the whole instance.
_Avoid_: Channel, show feed, per-notebook feed

**Published Episode**:
A completed podcast episode that a person has deliberately chosen to put in the Podcast Feed. Publishing is manual and reversible (unpublish).
_Avoid_: Released episode, live episode, auto-published episode

**Feed Token**:
The revocable secret that is part of the Podcast Feed URL and its audio URLs. Holding the URL is the only credential a podcast app needs. There is one token per instance; rotating it invalidates existing subscriptions.
_Avoid_: Feed password, API key, feed key

**Show Metadata**:
The instance-wide description of the Podcast Feed as a show: title, author, description, language and artwork.
_Avoid_: Channel info, feed settings
