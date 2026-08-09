# Privacy Policy — Paris Explorer channel automation

_Last updated: 9 August 2026_

This repository contains the internal automation used by the **Paris Explorer**
YouTube channel to produce and publish its own videos.

## Who uses this software

A single user: the owner of the Paris Explorer YouTube channel. It is an
internal tool. It is not distributed as a service, has no other users, no
accounts, and no audience-facing interface.

## What data it accesses

Through the YouTube Data API, with the channel owner's explicit OAuth consent,
the tool accesses **only the channel's own data**:

- `youtube.upload` — to upload videos produced by the pipeline to the
  channel, with their titles, descriptions and tags;
- `youtube.readonly` — to read the channel's own video list and statistics
  for scheduling and weekly measurement.

It does not access, collect, store or process any data about viewers,
subscribers, commenters, or any person other than the channel owner.

## How credentials are stored

OAuth credentials (`client_secrets.json`, `token.json`) are stored on a
private server, readable only by the owner's account (file mode 600). They
are excluded from version control and never shared with any third party.

## What is shared with third parties

Nothing. No data is sold, shared, or used for advertising. The only data
transmitted to YouTube is the content of the channel's own publications.

## Data retention and deletion

API responses (video identifiers, view counts) are kept as local log and
registry files on the private server, and can be deleted at any time by the
owner. Revoking the OAuth grant at <https://myaccount.google.com/permissions>
immediately cuts all API access.

## Contact

abellipaco@gmail.com
