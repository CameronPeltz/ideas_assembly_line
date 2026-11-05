import { test } from 'node:test';
import assert from 'node:assert/strict';
// metrics.js is a classic script with a CommonJS export (it must also run on file:// pages, where
// ES modules are blocked), so it arrives here as one default object.
import metrics from './metrics.js';

const { headerMetrics, binLags, filterRecords, monthlySeries, cumulativeSeries, cumulativePages, histogramMax, dateBounds, longestLags, oldestWaiting, billLabel, billUrl, ordinal, exportName, toCsv } = metrics;

const rec = (o) => ({ type: 'hr', number: '1', stage: 'introduced', text_date: '2025-01-10',
  summary_date: null, lag_days: null, pages: null, reported: false, title: 't', ...o });

test('headerMetrics counts bills, summarized, waiting, reported, pages', () => {
  const m = headerMetrics([
    rec({ number: '1', lag_days: 10, summary_date: '2025-01-20', pages: 5 }),
    rec({ number: '1', stage: 'reported', text_date: '2025-02-01' }),
    rec({ number: '2', lag_days: 30, summary_date: '2025-02-09', pages: null }),
    rec({ number: '3' }),
    rec({ number: '3', stage: null, pages: 7 }),
  ]);
  assert.equal(m.bills, 3);
  assert.equal(m.summarized, 2);
  assert.equal(m.waiting, 1);
  assert.equal(m.reported, 1);
  assert.equal(m.pagesTotal, 12);
  assert.equal(m.pagesCounted, 2);
  assert.equal(m.versions, 5);
  assert.equal(m.n, 2);
  assert.equal(m.lagMean, 20);
  assert.equal(m.lagMedian, 20);
  assert.equal(m.lagMax, 30);
});

test('headerMetrics median of odd count and null lags when nothing summarized', () => {
  const odd = headerMetrics([rec({ lag_days: 1 }), rec({ lag_days: 5 }), rec({ lag_days: 100 })]);
  assert.equal(odd.lagMedian, 5);
  const none = headerMetrics([rec(), rec({ number: '2' })]);
  assert.equal(none.n, 0);
  assert.equal(none.lagMean, null);
  assert.equal(none.lagMedian, null);
  assert.equal(none.lagMax, null);
  assert.equal(headerMetrics([]).bills, 0);
});

test('binLags puts lags in fixed-width bins from 0 to the max lag, waiting ignored', () => {
  const bins = binLags([rec({ lag_days: 0 }), rec({ lag_days: 29 }), rec({ lag_days: 30 }),
    rec({ lag_days: 100 }), rec()], 30);
  assert.deepEqual(bins, [
    { from: 0, to: 30, count: 2 },
    { from: 30, to: 60, count: 1 },
    { from: 60, to: 90, count: 0 },
    { from: 90, to: 120, count: 1 },
  ]);
});

test('binLags on empty input and on only-waiting input', () => {
  assert.deepEqual(binLags([], 30), []);
  assert.deepEqual(binLags([rec()], 30), []);
});

test('filterRecords by stage, type, and inclusive day range', () => {
  const rs = [
    rec({ number: '1', stage: 'introduced', type: 'hr', text_date: '2025-01-10' }),
    rec({ number: '2', stage: 'reported', type: 'hr', text_date: '2025-03-10' }),
    rec({ number: '3', stage: 'introduced', type: 's', text_date: '2025-06-30' }),
  ];
  assert.equal(filterRecords(rs, { stage: 'all', type: 'all', range: null }).length, 3);
  assert.deepEqual(filterRecords(rs, { stage: 'introduced', type: 'all', range: null }).map((r) => r.number), ['1', '3']);
  assert.deepEqual(filterRecords(rs, { stage: 'all', type: 's', range: null }).map((r) => r.number), ['3']);
  assert.deepEqual(filterRecords(rs, { stage: 'all', type: 'all', range: { from: '2025-03-10', to: '2025-06-30' } }).map((r) => r.number), ['2', '3']);
  assert.deepEqual(filterRecords(rs, { stage: 'all', type: 'all', range: { from: '2026-01-01', to: '2026-12-31' } }), []);
});

test('filterRecords honours day ranges: from-only, to-only, both inclusive at the boundary day, inverted = none', () => {
  const rs = ['2025-01-31', '2025-02-01', '2025-03-15', '2025-04-30'].map((d, i) => rec({ number: String(i), text_date: d }));
  const nums = (range) => filterRecords(rs, { range }).map((r) => r.number);
  assert.deepEqual(nums({ from: '2025-02-01', to: null }), ['1', '2', '3']);
  assert.deepEqual(nums({ from: '2025-02-02', to: null }), ['2', '3']);
  assert.deepEqual(nums({ from: null, to: '2025-03-15' }), ['0', '1', '2']);
  assert.deepEqual(nums({ from: null, to: '2025-03-14' }), ['0', '1']);
  assert.deepEqual(nums({ from: '2025-02-01', to: '2025-03-15' }), ['1', '2']);
  assert.deepEqual(nums({ from: '2025-04-30', to: '2025-04-30' }), ['3']);
  assert.deepEqual(nums({ from: '2025-04-01', to: '2025-02-01' }), ['0', '1', '2', '3']);
  assert.deepEqual(nums({ from: null, to: null }), ['0', '1', '2', '3']);
});

test('monthlySeries groups by month of text_date into summarized and waiting counts', () => {
  const s = monthlySeries([
    rec({ number: '1', text_date: '2025-01-03', lag_days: 10 }),
    rec({ number: '2', text_date: '2025-01-20', lag_days: 30 }),
    rec({ number: '3', text_date: '2025-01-25' }),
    rec({ number: '4', text_date: '2025-03-01' }),
    rec({ number: '5', stage: null, text_date: '2025-01-28', pages: 3 }), // later edition: never counted
  ]);
  assert.deepEqual(s, [
    { month: '2025-01', summarized: 2, waiting: 1 },
    { month: '2025-03', summarized: 0, waiting: 1 },
  ]);
  assert.deepEqual(monthlySeries([]), []);
});

test('binLags at width 7 over lags up to 626 gives 90 fixed bins whose counts sum to n, no open bin', () => {
  const rs = [rec({ lag_days: 3 }), rec({ lag_days: 45 }), rec({ lag_days: 200 }), rec({ lag_days: 626 })];
  const bins = binLags(rs, 7);
  assert.equal(bins.length, 90);
  assert.ok(bins.every((b) => b.to === b.from + 7));
  assert.equal(bins.reduce((s, b) => s + b.count, 0), 4);
  for (const w of [30, 90]) assert.equal(binLags(rs, w).reduce((s, b) => s + b.count, 0), 4);
});

test('cumulativeSeries counts distinct bills with text and with a summary by date', () => {
  const s = cumulativeSeries([
    rec({ number: '1', text_date: '2025-01-03', summary_date: '2025-01-20', lag_days: 17 }),
    rec({ number: '2', text_date: '2025-01-03' }),
    rec({ number: '3', text_date: '2025-02-01', summary_date: '2025-02-01', lag_days: 0 }),
    rec({ number: '3', stage: null, text_date: '2025-03-01', pages: 4 }),
  ]);
  assert.deepEqual(s, [
    { date: '2025-01-03', withText: 2, summarized: 0 },
    { date: '2025-01-20', withText: 2, summarized: 1 },
    { date: '2025-02-01', withText: 3, summarized: 2 },
  ]);
  assert.deepEqual(cumulativeSeries([]), []);
});

test('cumulativePages sums pages issued and pages of summarized bills by date', () => {
  const s = cumulativePages([
    rec({ number: '1', text_date: '2025-01-03', summary_date: '2025-01-20', lag_days: 17, pages: 10 }),
    rec({ number: '2', text_date: '2025-01-03', pages: null }),
    rec({ number: '1', stage: null, text_date: '2025-02-01', pages: 12 }),
  ]);
  assert.deepEqual(s, [
    { date: '2025-01-03', pagesIssued: 10, pagesSummarized: 0, versionsWithoutPages: 1 },
    { date: '2025-01-20', pagesIssued: 10, pagesSummarized: 10, versionsWithoutPages: 1 },
    { date: '2025-02-01', pagesIssued: 22, pagesSummarized: 10, versionsWithoutPages: 1 },
  ]);
  assert.deepEqual(cumulativePages([]), []);
});

test('headerMetrics: summarized + waiting === bills; a bill summarized at one stage is not waiting at another', () => {
  const m = headerMetrics([
    rec({ number: '1', stage: 'introduced', lag_days: 10, summary_date: '2025-01-20' }),
    rec({ number: '1', stage: 'reported' }),
    rec({ number: '2' }),
    rec({ number: '2', stage: null, pages: 3 }),
  ]);
  assert.equal(m.bills, 2);
  assert.equal(m.summarized, 1);
  assert.equal(m.waiting, 1);
  assert.equal(m.summarized + m.waiting, m.bills);
});


test('cumulativePages over a stage-filtered set counts only that stage, issued and summarized', () => {
  const rs = [
    rec({ number: '1', stage: 'introduced', text_date: '2025-01-03', summary_date: '2025-01-20', lag_days: 17, pages: 10 }),
    rec({ number: '1', stage: 'reported', text_date: '2025-02-01', summary_date: '2025-02-10', lag_days: 9, pages: 5 }),
    rec({ number: '2', stage: 'reported', text_date: '2025-02-02', pages: 7 }),
    rec({ number: '3', stage: null, text_date: '2025-02-03', pages: 100 }),
  ];
  const last = (set) => cumulativePages(set).at(-1);
  const all = last(rs);
  assert.equal(all.pagesIssued, 122); // every edition, including the unmapped one
  assert.equal(all.pagesSummarized, 15);
  const rep = rs.filter((r) => r.stage === 'reported');
  assert.equal(last(rep).pagesIssued, 12);
  assert.equal(last(rep).pagesSummarized, 5);
  assert.equal(headerMetrics(rep).pagesTotal, 12);
  assert.equal(headerMetrics(rep).pagesCounted, 2);
  assert.equal(headerMetrics(rep).versions, 2);
  assert.equal(headerMetrics(rs).pagesTotal, 122);
  assert.equal(last(rs.filter((r) => r.stage === 'passed')), undefined);
});

test('headerMetrics.reported counts distinct bills with a reported-stage record, even without an introduced record', () => {
  const rs = [
    rec({ number: '1', stage: 'reported', type: 'hr' }),
    rec({ number: '1', stage: 'reported', type: 'hr', text_date: '2025-03-01' }), // second edition, same bill
    rec({ number: '2', stage: 'introduced', reported: true }), // flag alone does not count
    rec({ number: '3', stage: 'reported', type: 's', text_date: '2025-05-01' }),
  ];
  assert.equal(headerMetrics(rs).reported, 2);
  const ranged = filterRecords(rs, { type: 'all', range: { from: '2025-04-01', to: '2025-06-30' } });
  assert.equal(headerMetrics(ranged).reported, 1);
});

test('histogramMax is one scale: the tallest bin, or the waiting count when that bar is drawn and taller', () => {
  const bins = binLags([rec({ lag_days: 5 }), rec({ lag_days: 6 }), rec({ lag_days: 40 })], 30);
  assert.equal(histogramMax(bins), 2);
  assert.equal(histogramMax(bins, 500), 500);
  assert.equal(histogramMax(bins, 1), 2);
  assert.equal(histogramMax([]), 1);
});

test('cumulativeSeries over a filtered subset ends at the headerMetrics of that subset', () => {
  const rs = [
    rec({ number: '1', text_date: '2025-04-02', lag_days: 10, summary_date: '2025-04-12' }),
    rec({ number: '2', text_date: '2025-05-02' }),
    rec({ number: '3', text_date: '2025-01-05', lag_days: 4, summary_date: '2025-01-09' }),
    rec({ number: '4', text_date: '2025-11-05' }),
  ];
  const subset = filterRecords(rs, { stage: 'introduced', type: 'all', range: { from: '2025-04-01', to: '2025-10-31' } });
  const m = headerMetrics(subset), end = cumulativeSeries(subset).at(-1);
  assert.equal(end.summarized, m.summarized);
  assert.equal(end.withText, m.summarized + m.waiting);
  assert.equal(end.withText, 2);
});

test('dateBounds is the earliest and latest text_date, ISO strings', () => {
  const rs = [rec({ text_date: '2025-03-10' }), rec({ text_date: '2025-01-02' }), rec({ text_date: '2026-10-01' })];
  assert.deepEqual(dateBounds(rs), { min: '2025-01-02', max: '2026-10-01' });
  assert.deepEqual(dateBounds([]), { min: null, max: null });
});

test('billLabel and billUrl cover all four bill types', () => {
  assert.equal(billLabel('hr', '360'), 'H.R. 360');
  assert.equal(billLabel('s', '12'), 'S. 12');
  assert.equal(billLabel('hjres', '5'), 'H.J.Res. 5');
  assert.equal(billLabel('sjres', '7'), 'S.J.Res. 7');
  assert.equal(billUrl('119', 'hr', '360'), 'https://www.congress.gov/bill/119th-congress/house-bill/360');
  assert.equal(billUrl(119, 's', '12'), 'https://www.congress.gov/bill/119th-congress/senate-bill/12');
  assert.equal(billUrl('119', 'hjres', '5'), 'https://www.congress.gov/bill/119th-congress/house-joint-resolution/5');
  assert.equal(billUrl('119', 'sjres', '7'), 'https://www.congress.gov/bill/119th-congress/senate-joint-resolution/7');
});

test('ordinal handles st/nd/rd/th and the teens', () => {
  assert.deepEqual([1, 2, 3, 4, 11, 12, 13, 21, 101, 112, 119].map(ordinal),
    ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '101st', '112th', '119th']);
  assert.equal(billUrl('118', 'hr', '1'), 'https://www.congress.gov/bill/118th-congress/house-bill/1');
});

test('longestLags orders by lag desc, ties by number asc, drops waiting and null stage, caps at n', () => {
  const s = (o) => rec({ summary_date: '2025-06-01', ...o });
  const rs = [
    s({ number: '30', lag_days: 50 }), s({ number: '4', lag_days: 50 }), s({ number: '9', lag_days: 90 }),
    rec({ number: '1', lag_days: null }), s({ number: '2', lag_days: 500, stage: null }), s({ number: '8', lag_days: 5 }),
  ];
  assert.deepEqual(longestLags(rs).map((r) => r.number), ['9', '4', '30', '8']);
  assert.deepEqual(longestLags(rs, 2).map((r) => r.number), ['9', '4']);
  assert.deepEqual(longestLags([]), []);
  assert.equal(longestLags(Array.from({ length: 25 }, (_, i) => s({ number: String(i), lag_days: i }))).length, 10);
});

test('oldestWaiting computes whole days to as_of, orders desc, ties by number, drops summarized and null stage', () => {
  const rs = [
    rec({ number: '30', text_date: '2025-10-15' }), rec({ number: '4', text_date: '2025-10-15' }),
    rec({ number: '9', text_date: '2025-01-01' }), rec({ number: '2', text_date: '2024-01-01', stage: null }),
    rec({ number: '5', text_date: '2025-01-01', summary_date: '2025-02-01', lag_days: 31 }),
  ];
  const out = oldestWaiting(rs, '2026-10-15');
  assert.deepEqual(out.map((r) => r.number), ['9', '4', '30']);
  assert.deepEqual(out.map((r) => r.days_waiting), [652, 365, 365]);
  assert.equal(oldestWaiting(rs, '2026-10-15', 1).length, 1);
  assert.equal(rs[0].days_waiting, undefined); // input untouched
  assert.equal(oldestWaiting([rec({ text_date: '2024-02-28' })], '2024-03-01')[0].days_waiting, 2); // leap day
});

test('longestLags and oldestWaiting with no limit return every qualifying record in order', () => {
  const s = (o) => rec({ summary_date: '2025-06-01', ...o });
  const many = Array.from({ length: 25 }, (_, i) => s({ number: String(i), lag_days: i % 5 }));
  const all = longestLags(many, Infinity);
  assert.equal(all.length, 25);
  assert.ok(all.every((r, i) => i === 0 || all[i - 1].lag_days > r.lag_days || (all[i - 1].lag_days === r.lag_days && Number(all[i - 1].number) < Number(r.number))));
  const waiting = Array.from({ length: 15 }, (_, i) => rec({ number: String(i), text_date: `2025-0${1 + (i % 3)}-01` }));
  const w = oldestWaiting(waiting, '2026-01-01', Infinity);
  assert.equal(w.length, 15);
  assert.deepEqual(w.slice(0, 3).map((r) => r.number), ['0', '3', '6']); // oldest date first, ties by number
  assert.ok(w.every((r, i) => i === 0 || w[i - 1].days_waiting >= r.days_waiting));
});

test('exportName builds the filename stem, with the range only when it is usable', () => {
  const st = { type: 'all', range: { from: null, to: null } };
  assert.equal(exportName('histogram', st, '2026-10-15'), 'bill-delay-histogram-all-2026-10-15');
  assert.equal(exportName('timeseries', { ...st, type: 'hr', range: { from: '2025-01-01', to: '2025-03-31' } }, '2026-10-15'),
    'bill-delay-timeseries-hr-2025-01-01_2025-03-31-2026-10-15');
  assert.equal(exportName('cumulative', { ...st, range: { from: '2025-02-01', to: null } }, '2026-10-15'), 'bill-delay-cumulative-all-2025-02-01_end-2026-10-15');
  assert.equal(exportName('cumulative', { ...st, range: { from: '2025-05-01', to: '2025-01-01' } }, '2026-10-15'), 'bill-delay-cumulative-all-2026-10-15'); // inverted = none
  assert.equal(exportName('longest-lags', { type: 's' }, '2026-10-15'), 'bill-delay-longest-lags-s-2026-10-15');
});

test('toCsv quotes per RFC 4180 and ends rows with CRLF', () => {
  const rows = [{ a: 'plain', b: 'x,y', c: null }, { a: 'say "hi"', b: 'two\nlines', c: 0 }];
  assert.equal(toCsv(rows, ['a', 'b', 'c']), 'a,b,c\r\nplain,"x,y",\r\n"say ""hi""","two\nlines",0');
  assert.equal(toCsv([], ['a', 'b']), 'a,b');
  const title = 'Act to amend "Title 5", relating to pay, and for other purposes';
  assert.equal(toCsv([{ title }], ['title']), `title\r\n"Act to amend ""Title 5"", relating to pay, and for other purposes"`);
});

test('binLags leaves negative lags out instead of folding them into the first bin', () => {
  const bins = binLags([rec({ lag_days: -40 }), rec({ lag_days: 3 }), rec({ lag_days: 35 })], 30);
  assert.equal(bins.length, 2);
  assert.deepEqual(bins.map((b) => b.count), [1, 1]);
});
