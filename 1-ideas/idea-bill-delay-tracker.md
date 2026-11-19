# Bill Delay Tracker: how long do bill summaries lag behind bill text?

**Target user:** A congressional staffer or reporter who needs a quick overview of newly introduced legislation and relies on the CRS summary on Congress.gov, which often appears days or weeks after the bill text itself.

Origin: Congressional Tech proposal [IV.2 Bill Delay Tracker](https://civictechdc.github.io/congressional-tech/proposals/IV.2/) (Civic Tech DC × American Governance Institute). This entry restates it in the assembly-line format so it can be prototyped here.

## The problem

Bill text is published on GovInfo and Congress.gov quickly. The plain-language CRS summary that most readers actually use arrives later, and nobody measures how much later, for how many bills, or whether the lag is getting better or worse. Users who need the overview today have no way to know whether to wait or to read the text themselves.

## The proposed idea

A dashboard that, for the current Congress, measures the lag between each bill text version and its summary: how many bills have text, how many are summarized, how many are still waiting, average / median / maximum lag, lag broken out by stage (introduced, reported by committee, passed), and the pages of bill text involved. Refreshed daily from the public APIs, with charts on the Congressional Tech site.

## Why this seems promising

- Both inputs are public, keyed APIs with list endpoints: GovInfo's BILLS collection gives every text version with its date, and the Congress.gov API's summaries endpoint gives every summary with its date. No scraping.
- The metric is simple and hard to argue with once the definition is written down.
- It gives CRS and Congress.gov a measurable service level that nobody publishes today.

## Open questions / risks

- The Congress.gov API exposes a summary's last update date, not its first publication date, so a revised summary looks slower than it was. A daily snapshot history fixes this going forward but cannot recover the past.
- API keys: `DEMO_KEY` is capped at roughly 30 requests per hour, so a full sweep needs a free registered key.
- Page counts are one GovInfo call per text version; thousands per Congress, so they need an incremental cache.
