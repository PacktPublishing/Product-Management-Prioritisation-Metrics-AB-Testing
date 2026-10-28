#!/usr/bin/env python3
"""
Tallyrow demo data loader for PostHog  ·  "Product Management Models & Measurements"
=====================================================================================

Loads invented Tallyrow data into YOUR OWN PostHog project, for four hands-on lessons of the
course:
  * the metric tree's live branch: the share of invoices paid through the payment link, and the
    on-time rate, week by week, with the payment link launching in week 5 (weeks 1-10);
  * funnels, cohorts and diagnosing a metric drop: the payment link's funnel by device, weekly
    retention cohorts of new businesses, and week 11, when the on-time rate seems to drop;
  * reading an experiment readout: the smart-reminders A/B test (businesses assigned in weeks 8-9),
    whose exposure log has a sample ratio mismatch, and the same test read by assignment;
  * the measurement cadence: a weekly review dashboard (North Star, inputs, guardrails with limits),
    with a guardrail that trips in week 10.

Every number is invented for the course. Nothing here is real customer data.

What you need
  * a free PostHog Cloud account and one project (posthog.com; no credit card)
  * your project's API key: PostHog -> Settings -> Project -> "Project API key" (starts with phc_)
  * your project's host: https://us.i.posthog.com (US Cloud) or https://eu.i.posthog.com (EU Cloud)
  * Python 3.8 or newer. No extra packages.

Run it
  1. Look before you load (sends nothing, writes tallyrow_demo_events.csv next to this file):
         python3 Tallyrow_PostHog-Demo-Data-Loader.py --dry-run
  2. Load it (about 138,000 events; well inside PostHog's free monthly allowance):
         python3 Tallyrow_PostHog-Demo-Data-Loader.py --send --key phc_XXXX --host https://us.i.posthog.com
     (or set POSTHOG_PROJECT_KEY and POSTHOG_HOST instead of --key and --host)
     Already loaded the metric-tree weeks with an earlier copy? Add --only-funnels to send just the new events.
  3. Wait a few minutes for PostHog to process the events, then follow the steps the loader prints.

Dates
  The ten weeks end shortly before the day you run it, so the data is never in the future and
  stays inside PostHog's retention window. To pin the calendar (the course recording does), pass
  --quarter-end YYYY-MM-DD, a Saturday: the end of week 12 of the quarter. Week 1 then starts
  on the Sunday eleven weeks and six days earlier.

Run it once per project. Re-running sends the same event IDs again; PostHog usually merges
duplicates, and the rates you chart are unchanged either way. There is no way to delete
individual events in PostHog, so use a fresh project if you want a clean slate.

The events (every one on a Tuesday, Wednesday or Thursday, so weekly charts bucket the same way
whether your week starts on Sunday or Monday)
  invoice_due, one per invoice, timestamped on its due date.
  Properties:
    paid_on_time    1 if paid by the due date, else 0   (average = on-time rate)
    paid_via_link   1 if paid through the payment link, else 0   (average = share paid through the link)
    payment_method  "payment link", "bank transfer", "card" or "unpaid"
    market          "Market A", "Market B", "Market C" or "Newest market"
    issue_date, due_date, paid_date (empty if unpaid), quarter_week (1-11), invoice_id
    invoice_format  week 11 only: "standard" or "e-invoice"
  distinct_id is an invented business ID; no person profiles are created.
  Week 11: e-invoicing goes live in the newest market, and its e-invoices arrive WITHOUT a
  due_date. The dashboard's rule treats a missing due date as due on the issue date, so they
  count as due that week, and late. (That is the drop the lesson diagnoses.)
  invoice_opened -> pay_link_clicked -> payment_started -> payment_completed
                  clients paying through the payment link, weeks 5-11; property $device_type.
  invoice_sent    new businesses, one event in each week they send invoices (retention cohorts).
  The smart-reminders experiment, for the experiment readout lesson (feature flag key smart-reminders; variants control / test):
  smart_reminders_assigned   one per business assigned (22,800; the assignment log)
  $feature_flag_called and $experiment_exposure   the exposure log PostHog reads by default (older and newer
                             default event). Test businesses whose clients had
                             thin payment history fell back to standard reminders and never sent it.
  invoice_paid_on_time       one per business whose enrolled invoice was paid by its due date
  Properties: $feature/smart-reminders, business_type (six segments), client_history ("thin" / "enough").
  Already loaded the earlier lessons? Add --only-experiment to send just these events.
  The weekly review dashboard, for the measurement cadence lesson (weeks 1-10):
  weekly_totals   one per week, posted by Tallyrow's billing system (a weekly job that counts every invoice and
                  payment, not a sample): invoices_due, invoices_paid_on_time (the North Star; chart it as
                  Property value -> Sum), payments_attempted, payments_failed, payment_failure_rate (a percent),
                  clients_reminded_28d, clients_opted_out_28d, reminder_opt_out_rate (a percent, last 28 days),
                  client_complaints, complaints_per_10k (per 10,000 invoices due). In week 10 the payment failure
                  rate jumps from 3.2% to 4.9%, above its 4% limit: the guardrail trip the lesson reviews.
  Already loaded the earlier lessons? Add --only-cadence to send just these events.
"""
import argparse
import csv
import json
import os
import random
import shutil
import ssl
import subprocess
import sys
import tempfile
import uuid
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta, timezone

N_PER_WEEK = 2000
LINK_PCT = [0, 0, 0, 0, 9, 22, 24, 26, 28, 29]
ONTIME_PCT = [61.0, 60.9, 61.1, 61.0, 61.1, 61.3, 61.4, 61.5, 61.7, 61.8]
LINK_ONTIME = 0.70
LAUNCH_WEEK, LAUNCH_WEEKDAY = 5, 3
MARKETS = [("Market A", .45), ("Market B", .30), ("Market C", .16), ("Newest market", .09)]
BUSINESSES = 330
TERMS_DAYS = 14
DATASET = "tallyrow-demo-4.3"

# ---- The funnels and cohorts lesson ----
DATASET_45 = "tallyrow-demo-4.5"
W11_ONTIME_DASH = 1178      # on time, as the dashboard counts week 11: 1,178 / 2,000 = 58.9%
W11_E_INVOICES = 91         # newest-market e-invoices with no due_date: counted as due (and late) on their issue date
W11_NEWEST_ONTIME = 54      # newest market's standard invoices paid on time (54 of 89)
W11_LINK = 600              # paid through the link, week 11 (30% of 2,000; 31% by week 12)
FUNNEL = {"Desktop": (900, 621, 470, 430), "Mobile": (1100, 539, 350, 310)}   # opened, clicked, started, completed
COHORT_SIZE = [200, 300, 200, 300, 200, 300, 200, 300, 200, 300, 200]         # new businesses joining in weeks 1-11
RET_BEFORE = [100, 80, 72, 66, 62, 59, 57, 56, 55, 54, 53]   # % still sending invoices k weeks after joining, joined weeks 1-4
RET_AFTER = [100, 85, 77, 72, 69, 67, 65, 64, 63, 62, 61]    # joined in week 5 or later (payment link live)


def split(total, shares):
    """Whole numbers in proportion to shares that add up exactly to total (largest remainder)."""
    raw = [total * s for s in shares]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: -(raw[i] - out[i]))[:total - sum(out)]:
        out[i] += 1
    return out


def default_quarter_end(today):
    """The latest Saturday at least two days before today."""
    d = today - timedelta(days=2)
    return d - timedelta(days=(d.weekday() - 5) % 7)


def week_sunday(qend, k):
    return qend - timedelta(days=6) - timedelta(weeks=12 - k)


def generate(qend):
    """Return the list of invoice_due events, deterministic for a given quarter end."""
    assert qend.weekday() == 5, "--quarter-end must be a Saturday"
    rng = random.Random(4303)
    ev = []
    shares = [s for _, s in MARKETS]
    for k in range(1, 11):
        sun = week_sunday(qend, k)
        n = N_PER_WEEK
        L = round(n * LINK_PCT[k - 1] / 100)
        O = round(n * ONTIME_PCT[k - 1] / 100)
        lo = round(L * LINK_ONTIME)
        no = O - lo
        nm = split(n, shares)
        Lm = split(L, shares)
        lom = split(lo, shares)
        nom = split(no, shares)
        seq = 0
        for (mk, _), n_, L_, lo_, no_ in zip(MARKETS, nm, Lm, lom, nom):
            rows = [("link", 1)] * lo_ + [("link", 0)] * (L_ - lo_) + [("other", 1)] * no_ + [("other", 0)] * (n_ - L_ - no_)
            rng.shuffle(rows)
            for via, ontime in rows:
                seq += 1
                if via == "link" and k == LAUNCH_WEEK:
                    wd = rng.choice([3, 4])          # the link goes live on Wednesday of week 5
                else:
                    wd = 2 + seq % 3                 # Tuesday, Wednesday or Thursday
                due = sun + timedelta(days=wd)
                ts = datetime(due.year, due.month, due.day, 9 + seq % 8, seq * 7 % 60, seq % 60, tzinfo=timezone.utc)
                if ontime:
                    paid = due - timedelta(days=rng.randint(0, 10))
                    method = "payment link" if via == "link" else ("bank transfer" if rng.random() < 0.7 else "card")
                elif via == "link" or rng.random() < 0.8:
                    paid = due + timedelta(days=rng.randint(2, 27))
                    method = "payment link" if via == "link" else ("bank transfer" if rng.random() < 0.7 else "card")
                else:
                    paid, method = None, "unpaid"
                inv = f"INV-{k:02d}-{seq:05d}"
                ev.append({"event": "invoice_due", "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET}/{qend.isoformat()}/{inv}")),
                           "properties": {"distinct_id": f"tallyrow-biz-{rng.randrange(BUSINESSES):04d}",
                                          "$process_person_profile": False, "invoice_id": inv, "quarter_week": k,
                                          "market": mk, "issue_date": (due - timedelta(days=TERMS_DAYS)).isoformat(),
                                          "due_date": due.isoformat(), "paid_date": paid.isoformat() if paid else "",
                                          "paid_on_time": ontime, "paid_via_link": 1 if via == "link" else 0,
                                          "payment_method": method, "demo_dataset": DATASET}})
    return ev


def generate_45(qend):
    """The funnels and cohorts lesson's events: week 11 of invoice_due (with the e-invoice fault), the payment-link funnel
    and the retention cohorts. Deterministic, and separate from generate() so the metric tree lesson's events stay identical."""
    assert qend.weekday() == 5, "--quarter-end must be a Saturday"
    rng = random.Random(4511)
    ev = []

    def add(event, distinct_id, day, n, props):
        ts = datetime(day.year, day.month, day.day, 9 + n % 8, n * 7 % 60, n % 60, tzinfo=timezone.utc)
        ev.append({"event": event, "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_45}/{qend.isoformat()}/{event}/{distinct_id}/{n}")),
                   "properties": dict(props, distinct_id=distinct_id, demo_dataset=DATASET_45)})

    # week 11: invoice_due. The newest market's e-invoices have no due_date at all.
    k, n = 11, N_PER_WEEK
    sun = week_sunday(qend, k)
    shares = [s for _, s in MARKETS]
    nm = split(n, shares)
    newest = len(MARKETS) - 1
    std = list(nm)
    std[newest] -= W11_E_INVOICES
    others = [i for i in range(len(MARKETS)) if i != newest]
    on = [0] * len(MARKETS)
    for i, v in zip(others, split(W11_ONTIME_DASH - W11_NEWEST_ONTIME, [shares[i] / sum(shares[j] for j in others) for i in others])):
        on[i] = v
    on[newest] = W11_NEWEST_ONTIME
    lo_all = round(W11_LINK * LINK_ONTIME)
    lk = split(W11_LINK, shares)
    lo = split(lo_all, shares)
    seq = 0
    for i, (mk, _) in enumerate(MARKETS):
        rows = ([("link", 1)] * lo[i] + [("link", 0)] * (lk[i] - lo[i]) + [("other", 1)] * (on[i] - lo[i])
                + [("other", 0)] * (std[i] - lk[i] - (on[i] - lo[i])))
        rows = [r + ("standard",) for r in rows]
        if i == newest:
            rows += [("other", 0, "e-invoice")] * W11_E_INVOICES
        rng.shuffle(rows)
        for via, ontime, fmt in rows:
            seq += 1
            day = sun + timedelta(days=2 + seq % 3)
            inv = f"INV-{k:02d}-{seq:05d}"
            p = {"$process_person_profile": False, "invoice_id": inv, "quarter_week": k, "market": mk,
                 "invoice_format": fmt, "paid_on_time": ontime, "paid_via_link": 1 if via == "link" else 0}
            if fmt == "e-invoice":   # the fault: no due_date; the dashboard counts it as due today, so late
                p.update(issue_date=day.isoformat(), paid_date="", payment_method="unpaid")
            else:
                if ontime:
                    paid = day - timedelta(days=rng.randint(0, 10))
                elif via == "link" or rng.random() < 0.8:
                    paid = day + timedelta(days=rng.randint(2, 27))
                else:
                    paid = None
                method = "payment link" if via == "link" else ("unpaid" if paid is None else ("bank transfer" if rng.random() < 0.7 else "card"))
                p.update(issue_date=(day - timedelta(days=TERMS_DAYS)).isoformat(), due_date=day.isoformat(),
                         paid_date=paid.isoformat() if paid else "", payment_method=method)
            add("invoice_due", f"tallyrow-biz-{rng.randrange(BUSINESSES):04d}", day, seq, p)

    # the payment link's funnel, weeks 5-11 (one client per invoice opened)
    c = 0
    for device, counts in FUNNEL.items():
        for j in range(counts[0]):
            c += 1
            day = week_sunday(qend, 5 + rng.randrange(7)) + timedelta(days=2 + rng.randrange(3))
            steps = ["invoice_opened", "pay_link_clicked", "payment_started", "payment_completed"]
            for s_, step in enumerate(steps):
                if j < counts[s_]:
                    add(step, f"tallyrow-client-{c:05d}", day, 8 * c + s_, {"$device_type": device})

    # retention cohorts: new businesses, invoice_sent in each week they are active
    for cw in range(1, 12):
        size, curve = COHORT_SIZE[cw - 1], (RET_BEFORE if cw < LAUNCH_WEEK else RET_AFTER)
        ids = [f"tallyrow-new-w{cw:02d}-{j:03d}" for j in range(size)]
        for w in range(0, 12 - cw):
            pct = curve[w] if w in (0, 4) else curve[w] + rng.choice((-1, 0, 0, 1))   # week 4 stays exact
            active = ids if w == 0 else sorted(rng.sample(ids, round(size * pct / 100)))
            for j, b in enumerate(active):
                add("invoice_sent", b, week_sunday(qend, cw + w) + timedelta(days=2 + j % 3), 100 * w + j,
                    {"joined_week": cw, "weeks_since_joining": w})
    return ev


def check_45(qend, ev):
    """Checks the figures the funnels and cohorts lesson shows; returns them for printing."""
    due = [e["properties"] for e in ev if e["event"] == "invoice_due"]
    w11 = [p for p in due if p["quarter_week"] == 11]
    rate = lambda xs: round(100 * sum(p["paid_on_time"] for p in xs) / len(xs), 1)
    dash, fixed = rate(w11), rate([p for p in w11 if "due_date" in p])
    assert len(w11) == N_PER_WEEK and dash == 58.9 and fixed == 61.7, (len(w11), dash, fixed)
    by_m = {m: rate([p for p in w11 if p["market"] == m]) for m, _ in MARKETS}
    assert by_m["Newest market"] < 35 and all(abs(v - 61.8) < 1.0 for m, v in by_m.items() if m != "Newest market"), by_m
    assert round(100 * sum(p["paid_via_link"] for p in w11) / len(w11)) == 30
    people = {}
    for e in ev:
        if e["event"] in ("invoice_opened", "pay_link_clicked", "payment_started", "payment_completed"):
            people.setdefault((e["event"], e["properties"]["$device_type"]), set()).add(e["properties"]["distinct_id"])
    steps = ["invoice_opened", "pay_link_clicked", "payment_started", "payment_completed"]
    tot = [sum(len(people[(s_, d)]) for d in FUNNEL) for s_ in steps]
    funnel = [round(100 * t / tot[0]) for t in tot]
    click = {d: round(100 * len(people[("pay_link_clicked", d)]) / len(people[("invoice_opened", d)])) for d in FUNNEL}
    assert funnel == [100, 58, 41, 37] and click == {"Desktop": 69, "Mobile": 49}, (funnel, click)
    act = {}
    for e in ev:
        if e["event"] == "invoice_sent":
            p = e["properties"]
            act.setdefault((p["joined_week"], p["weeks_since_joining"]), set()).add(p["distinct_id"])
    ret4 = {cw: round(100 * len(act.get((cw, 4), ())) / COHORT_SIZE[cw - 1], 1) for cw in range(1, 8)}
    assert all(ret4[cw] == 62.0 for cw in range(1, 5)) and all(ret4[cw] == 69.0 for cw in range(5, 8)), ret4
    days = {datetime.fromisoformat(e["timestamp"][:10]).weekday() for e in ev}
    assert days <= {1, 2, 3}, days
    assert len({e["uuid"] for e in ev}) == len(ev)
    return {"week11_dashboard": dash, "week11_fixed": fixed, "week11_by_market": by_m, "funnel": funnel,
            "click": click, "retention_week4": ret4}


# ---- The experiment readout lesson ----
DATASET_54 = "tallyrow-demo-5.4"
FLAG_54 = "smart-reminders"
ASSIGNED_54 = {"control": 11412, "test": 11388}       # every business assigned in week 8 (balanced: no mismatch)
LOGGED_TEST_54 = 10388                                # the exposure log lost 1,000 thin-history test businesses
ONTIME_54 = {"control": 6984, "test": 7072}          # by assignment: 61.2% vs 62.1%
THIN_54 = {"control": (1010, 470), "test": (1000, 465)}   # thin payment history: (businesses, paid on time), 46.5%
SEGMENTS_54 = [("Agency or studio", .263), ("Solo freelancer", .300), ("Consultant", .140),
               ("Trades", .110), ("Retail", .100), ("Other services", .087)]
SEG_RATE_54 = {"control": [60.7, 61.3, 62.4, 60.2, 61.0, 61.9],   # thick-history on-time % before rounding fixes
               "test": [63.8, 61.7, 62.6, 60.6, 60.9, 62.5]}


def generate_54(qend):
    """The experiment readout lesson's events: the smart-reminders A/B test (businesses assigned in weeks 8-9 of the quarter).
      smart_reminders_assigned  one per assigned business, with $feature/smart-reminders (the assignment log)
      $feature_flag_called      the exposure log PostHog reads by default (also sent as $experiment_exposure,
                                PostHog's newer default exposure event, with the same properties): test businesses with thin client history
                                fell back to standard reminders and never sent it (the sample ratio mismatch)
      invoice_paid_on_time      one per business whose enrolled invoice was paid by its due date (within 13 days)
    Deterministic, and separate from generate() / generate_45()."""
    assert qend.weekday() == 5, "--quarter-end must be a Saturday"
    rng = random.Random(5404)
    start = week_sunday(qend, 8)                       # Sunday of week 8; enrolment runs 14 days
    ev = []

    def add(event, distinct_id, ts, n, props):
        ev.append({"event": event, "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_54}/{qend.isoformat()}/{event}/{distinct_id}/{n}")),
                   "properties": dict(props, distinct_id=distinct_id, demo_dataset=DATASET_54)})

    shares = [s for _, s in SEGMENTS_54]
    seq = 0
    for arm in ("control", "test"):
        n_arm, on_arm = ASSIGNED_54[arm], ONTIME_54[arm]
        n_thin, on_thin = THIN_54[arm]
        seg_n = split(n_arm, shares)
        seg_thin = split(n_thin, shares)
        thin_on = split(on_thin, [t / n_thin for t in seg_thin])
        thick = [a - b for a, b in zip(seg_n, seg_thin)]
        want = on_arm - on_thin
        raw = [t * r / 100 for t, r in zip(thick, SEG_RATE_54[arm])]
        thick_on = split(want, [x / sum(raw) for x in raw])
        rows = []
        for s, (seg, _) in enumerate(SEGMENTS_54):
            for hist, n, on in (("thin", seg_thin[s], thin_on[s]), ("enough", thick[s], thick_on[s])):
                rows += [(seg, hist, 1)] * on + [(seg, hist, 0)] * (n - on)
        rng.shuffle(rows)
        for seg, hist, ontime in rows:
            seq += 1
            biz = f"tallyrow-exp-{seq:05d}"
            t0 = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) + timedelta(
                days=rng.randrange(14), hours=8 + rng.randrange(10), minutes=rng.randrange(60), seconds=rng.randrange(60))
            base = {"$process_person_profile": False, f"$feature/{FLAG_54}": arm, "business_type": seg, "client_history": hist}
            add("smart_reminders_assigned", biz, t0, 0, dict(base))
            if not (arm == "test" and hist == "thin"):        # the bug: the fallback path never logged an exposure
                for n_, name in ((1, "$feature_flag_called"), (3, "$experiment_exposure")):   # older and newer PostHog default exposure events
                    add(name, biz, t0 + timedelta(seconds=30), n_,
                        dict(base, **{"$feature_flag": FLAG_54, "$feature_flag_response": arm}))
            if ontime:
                add("invoice_paid_on_time", biz, t0 + timedelta(days=1 + rng.randrange(12), hours=rng.randrange(12)), 2,
                    {"$process_person_profile": False, f"$feature/{FLAG_54}": arm, "business_type": seg})
    return ev


def check_54(ev):
    """The numbers the experiment readout lesson shows, recomputed from the events themselves."""
    from math import sqrt
    arm_of, hist_of, seg_of, logged, paid = {}, {}, {}, set(), set()
    for e in ev:
        p = e["properties"]
        b = p["distinct_id"]
        if e["event"] == "smart_reminders_assigned":
            arm_of[b], hist_of[b], seg_of[b] = p[f"$feature/{FLAG_54}"], p["client_history"], p["business_type"]
        elif e["event"] in ("$feature_flag_called", "$experiment_exposure"):
            logged.add(b)
        elif e["event"] == "invoice_paid_on_time":
            paid.add(b)

    def rate(ids):
        ids = list(ids)
        return len(ids), sum(b in paid for b in ids)

    out = {}
    for view, keep in (("log", lambda b: b in logged), ("assigned", lambda b: True)):
        r = {a: rate(b for b in arm_of if arm_of[b] == a and keep(b)) for a in ("control", "test")}
        (nc, cc), (nt, ct) = r["control"], r["test"]
        pc, pt = cc / nc, ct / nt
        e_ = (nc + nt) / 2
        se = sqrt(pc * (1 - pc) / nc + pt * (1 - pt) / nt)
        d = pt - pc
        out[view] = dict(n=(nc, nt), rate=(100 * pc, 100 * pt), diff=100 * d,
                         ci=(100 * (d - 1.959964 * se), 100 * (d + 1.959964 * se)),
                         rel=100 * d / pc, chi2=((nc - e_) ** 2 + (nt - e_) ** 2) / e_)
    segs = {}
    for seg, _ in SEGMENTS_54:
        r = {a: rate(b for b in arm_of if arm_of[b] == a and seg_of[b] == seg) for a in ("control", "test")}
        segs[seg] = (r["control"][0] + r["test"][0], 100 * (r["test"][1] / r["test"][0] - r["control"][1] / r["control"][0]))
    out["segments"] = segs
    # the figures the lesson shows, checked
    lg, asg = out["log"], out["assigned"]
    assert lg["n"] == (11412, 10388) and lg["chi2"] > 10.83, lg            # the lesson: the mismatch, p < 0.001
    assert round(lg["diff"], 1) == 2.4 and lg["ci"][0] > 0, lg             # the lesson: "+2.4 points, significant"
    assert asg["n"] == (11412, 11388) and asg["chi2"] < 3.84, asg          # the lesson: "the split is healthy"
    assert [round(x, 1) for x in asg["rate"]] == [61.2, 62.1] and round(asg["diff"], 1) == 0.9, asg
    assert [round(x, 1) for x in asg["ci"]] == [-0.4, 2.2], asg            # 95% interval -0.4 to +2.2 points
    assert round(asg["rel"], 1) == 1.5, asg                                 # PostHog shows the gap relative: about +1.5%
    assert round(segs["Agency or studio"][1], 1) == 2.8, segs              # the lesson: agencies +2.8
    assert all(v[1] < 2.8 for k, v in segs.items() if k != "Agency or studio"), segs
    assert 5900 <= segs["Agency or studio"][0] <= 6100, segs              # about 6,000 agencies
    return out


# ---- The measurement cadence lesson ----
DATASET_63 = "tallyrow-demo-6.3"
INVOICES_DUE_63 = 207700                                                  # every invoice due in a week (4.2: 61% of 207,700)
ATTEMPTS_63 = [38000, 38000, 39000, 38000, 42000, 49000, 50000, 51000, 52000, 52000]   # card and link payments tried
FAIL_PCT_63 = [3.2, 3.1, 3.3, 3.2, 3.2, 3.3, 3.1, 3.2, 3.2, 4.9]          # guardrail: limit 4.0%; week 10 trips it
REMINDED_63 = 100000                                                      # clients sent a reminder in the last 28 days
OPTOUT_PCT_63 = [0.30, 0.29, 0.31, 0.30, 0.30, 0.31, 0.30, 0.29, 0.30, 0.31]   # guardrail: limit 0.5%
COMPLAINTS_63 = [83, 85, 81, 83, 85, 83, 81, 83, 85, 89]                  # 4.0 ... 4.3 per 10,000; limit 6
LIMITS_63 = {"payment_failure_rate": 4.0, "reminder_opt_out_rate": 0.5, "complaints_per_10k": 6.0}


def generate_63(qend):
    """The measurement cadence lesson's events: weekly_totals for weeks 1-10, each on the Wednesday of its week at 12:00 UTC.
    Deterministic, and separate from the earlier generators."""
    assert qend.weekday() == 5, "--quarter-end must be a Saturday"
    ev = []
    for k in range(1, 11):
        day = week_sunday(qend, k) + timedelta(days=3)
        ts = datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=timezone.utc)
        att = ATTEMPTS_63[k - 1]
        failed = round(att * FAIL_PCT_63[k - 1] / 100)
        opted = round(REMINDED_63 * OPTOUT_PCT_63[k - 1] / 100)
        paid = round(INVOICES_DUE_63 * ONTIME_PCT[k - 1] / 100)
        comp = COMPLAINTS_63[k - 1]
        ev.append({"event": "weekly_totals", "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_63}/{qend.isoformat()}/weekly_totals/{k}")),
                   "properties": {"distinct_id": "tallyrow-billing-system", "$process_person_profile": False,
                                  "quarter_week": k, "week_starting": week_sunday(qend, k).isoformat(),
                                  "invoices_due": INVOICES_DUE_63, "invoices_paid_on_time": paid,
                                  "payments_attempted": att, "payments_failed": failed,
                                  "payment_failure_rate": round(100 * failed / att, 2),
                                  "clients_reminded_28d": REMINDED_63, "clients_opted_out_28d": opted,
                                  "reminder_opt_out_rate": round(100 * opted / REMINDED_63, 2),
                                  "client_complaints": comp, "complaints_per_10k": round(10000 * comp / INVOICES_DUE_63, 1),
                                  "demo_dataset": DATASET_63}})
    return ev


def check_63(ev):
    """The numbers the measurement cadence lesson shows, recomputed from the events themselves."""
    rows = sorted((e["properties"] for e in ev if e["event"] == "weekly_totals"), key=lambda p: p["quarter_week"])
    assert [p["quarter_week"] for p in rows] == list(range(1, 11)), rows
    ns = [p["invoices_paid_on_time"] for p in rows]
    fail = [p["payment_failure_rate"] for p in rows]
    opt = [p["reminder_opt_out_rate"] for p in rows]
    comp = [p["complaints_per_10k"] for p in rows]
    # the lesson: "Invoices paid on time per week is up ... the payment failure rate has jumped from 3.2% to 4.9%"
    assert ns[-1] > ns[-2] > ns[0] and 126000 <= ns[0] <= 127500, ns     # about 127,000, rising by week 10
    assert ns == [round(INVOICES_DUE_63 * x / 100) for x in ONTIME_PCT], ns   # same on-time rates as invoice_due
    assert fail[8] == 3.2 and fail[9] == 4.9 and all(x < 4.0 for x in fail[:9]), fail
    # the lesson: "above its limit of four percent": only the payment failure rate is over a limit
    assert fail[9] > LIMITS_63["payment_failure_rate"]
    assert all(x < LIMITS_63["reminder_opt_out_rate"] for x in opt) and all(x < LIMITS_63["complaints_per_10k"] for x in comp)
    assert round(sum(opt[:9]) / 9, 1) == 0.3 and round(sum(comp[:9]) / 9) == 4, (opt, comp)   # 4.6 baselines 0.3% / 4
    assert {datetime.fromisoformat(e["timestamp"][:10]).weekday() for e in ev} == {2}
    assert len({e["uuid"] for e in ev}) == len(ev) == 10
    return {"north_star": ns, "failure": fail, "opt_outs": opt, "complaints": comp,
            "link": LINK_PCT, "ontime": ONTIME_PCT}


def weekly(ev):
    out = {}
    for e in ev:
        p = e["properties"]
        w = out.setdefault(p["quarter_week"], [0, 0, 0])
        w[0] += 1
        w[1] += p["paid_on_time"]
        w[2] += p["paid_via_link"]
    return {k: (n, 100 * o / n, 100 * l / n) for k, (n, o, l) in sorted(out.items())}


def post(host, body):
    url = host.rstrip("/") + "/batch/"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.URLError as err:
        # Some Python installs (often on macOS) lack root certificates; curl uses the system's.
        if not isinstance(getattr(err, "reason", None), ssl.SSLError) or not shutil.which("curl"):
            raise
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(data)
        try:
            out = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "-X", "POST", url,
                                  "-H", "Content-Type: application/json", "--data-binary", "@" + f.name],
                                 capture_output=True, text=True, check=True)
            return int(out.stdout.strip() or 0)
        finally:
            os.unlink(f.name)


def main():
    ap = argparse.ArgumentParser(description="Load Tallyrow's invented invoices into your PostHog project.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="send nothing; write a CSV and print the weekly rates")
    g.add_argument("--send", action="store_true", help="send the events to PostHog")
    ap.add_argument("--key", default=os.environ.get("POSTHOG_PROJECT_KEY", ""), help="project API key (phc_...)")
    ap.add_argument("--host", default=os.environ.get("POSTHOG_HOST", "https://us.i.posthog.com"))
    ap.add_argument("--quarter-end", default="", help="a Saturday, YYYY-MM-DD (default: the latest Saturday at least two days ago)")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--only-45", "--only-funnels", action="store_true", help="send only the funnels and cohorts lesson's events (use if the metric tree lesson's data is already in the project)")
    ap.add_argument("--only-54-exposure", "--only-exposure", action="store_true", help="send only the experiment readout lesson's $experiment_exposure events (if the rest of the experiment readout lesson is already loaded)")
    ap.add_argument("--only-54", "--only-experiment", action="store_true", help="send only the experiment readout lesson's experiment events (use if the metric tree lesson's and the funnels and cohorts lesson's data are already in the project)")
    ap.add_argument("--only-63", "--only-cadence", action="store_true", help="send only the measurement cadence lesson's weekly_totals events (use if the earlier lessons' data are already in the project)")
    a = ap.parse_args()
    if a.only_45 + a.only_54 + a.only_54_exposure + a.only_63 > 1:
        sys.exit("Use only one of --only-funnels, --only-experiment, --only-exposure, --only-cadence.")
    qend = date.fromisoformat(a.quarter_end) if a.quarter_end else default_quarter_end(date.today())
    if qend.weekday() != 5:
        sys.exit("--quarter-end must be a Saturday")
    ev = generate(qend)
    wk = weekly(ev)
    for k, (n, o, l) in wk.items():
        assert n == N_PER_WEEK and abs(o - ONTIME_PCT[k - 1]) < 1e-9 and abs(l - LINK_PCT[k - 1]) < 1e-9, k
    w1, w10 = week_sunday(qend, 1), week_sunday(qend, 10)
    launch = week_sunday(qend, LAUNCH_WEEK) + timedelta(days=LAUNCH_WEEKDAY)
    print(f"Tallyrow demo data: {len(ev):,} invoice_due events, weeks 1-10 (week 1 starts Sun {w1:%d %b %Y}; week 12 ends Sat {qend:%d %b %Y})\n")
    ev45 = generate_45(qend)
    c45 = check_45(qend, ev45)
    print(" week  starts (Sun)   on-time   paid via link")
    for k, (n, o, l) in wk.items():
        print(f"  {k:>2}   {week_sunday(qend, k):%d %b %Y}     {o:5.1f}%      {l:4.1f}%" + ("   <- payment link live" if k == LAUNCH_WEEK else ""))
    w11 = week_sunday(qend, 11)
    print(f"  11   {w11:%d %b %Y}     {c45['week11_dashboard']:5.1f}%   (the funnels and cohorts lesson: e-invoicing live; {c45['week11_fixed']:.1f}% once a missing due_date isn't counted as due)")
    print(f"\nThe funnels and cohorts lesson: +{len(ev45):,} events. Funnel {' -> '.join(f'{x}%' for x in c45['funnel'])}; "
          f"click-through Desktop {c45['click']['Desktop']}%, Mobile {c45['click']['Mobile']}%; "
          f"still sending invoices 4 weeks after joining: {c45['retention_week4'][1]:.0f}% before the link, {c45['retention_week4'][5]:.0f}% after.")
    print(f"Week 11 by market: " + ", ".join(f"{m} {v:.1f}%" for m, v in c45['week11_by_market'].items()))
    ev54 = generate_54(qend)
    c54 = check_54(ev54)
    lg, asg = c54["log"], c54["assigned"]
    print(f"The experiment readout lesson: +{len(ev54):,} events. Exposure log: control {lg['n'][0]:,} vs test {lg['n'][1]:,} "
          f"(chi-square {lg['chi2']:.0f}: a sample ratio mismatch); on time {lg['rate'][0]:.1f}% vs {lg['rate'][1]:.1f}% (+{lg['diff']:.1f} points).")
    print(f"  By assignment: control {asg['n'][0]:,} vs test {asg['n'][1]:,}; on time {asg['rate'][0]:.1f}% vs {asg['rate'][1]:.1f}%, "
          f"+{asg['diff']:.1f} points, 95% interval {asg['ci'][0]:+.1f} to {asg['ci'][1]:+.1f} (relative +{asg['rel']:.1f}%).")
    ev63 = generate_63(qend)
    c63 = check_63(ev63)
    print(f"The measurement cadence lesson: +{len(ev63)} weekly_totals events. Paid on time per week {c63['north_star'][0]:,} -> {c63['north_star'][-1]:,}; "
          f"payment failure rate {c63['failure'][8]}% in week 9, {c63['failure'][9]}% in week 10 (limit {LIMITS_63['payment_failure_rate']:.0f}%); "
          f"opt-outs {min(c63['opt_outs'])}-{max(c63['opt_outs'])}% (limit 0.5%); complaints {min(c63['complaints'])}-{max(c63['complaints'])} per 10,000 (limit 6).")
    ev = ev45 if a.only_45 else (ev54 if a.only_54 else ([e for e in ev54 if e["event"] == "$experiment_exposure"] if a.only_54_exposure
          else (ev63 if a.only_63 else ev + ev45 + ev54 + ev63)))
    if a.dry_run:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tallyrow_demo_events.csv")
        cols = ["timestamp", "event", "distinct_id", "invoice_id", "quarter_week", "market", "issue_date",
                "due_date", "paid_date", "paid_on_time", "paid_via_link", "payment_method",
                "$feature/smart-reminders", "business_type", "client_history",
                "invoices_paid_on_time", "payment_failure_rate", "reminder_opt_out_rate", "complaints_per_10k"]
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for e in ev:
                p = e["properties"]
                w.writerow([e["timestamp"], e["event"]] + [p.get(c, "") for c in cols[2:]])
        print(f"\nDry run: nothing sent. Wrote {path}")
        return
    if not a.key.startswith("phc_"):
        sys.exit("Give your PROJECT API key (starts with phc_) with --key or POSTHOG_PROJECT_KEY. "
                 "A personal API key (phx_) will not work here.")
    sent = 0
    for i in range(0, len(ev), a.batch):
        chunk = ev[i:i + a.batch]
        st = post(a.host, {"api_key": a.key, "batch": chunk})
        if st != 200:
            sys.exit(f"PostHog answered HTTP {st} after {sent:,} events. Check the key and host, then run again.")
        sent += len(chunk)
        print(f"\r  sent {sent:,} / {len(ev):,}", end="", flush=True)
    print("\n\nDone. Give PostHog a few minutes to process, then in PostHog:")
    print("  Product analytics -> New insight -> Trends")
    print("  Series A: invoice_due, aggregated by Property value -> Average -> paid_on_time   (rename: On-time rate)")
    print("  Series B: invoice_due, aggregated by Property value -> Average -> paid_via_link  (rename: Paid through the link)")
    print(f"  Date range: {w1 + timedelta(days=2):%d %b %Y} to {w10 + timedelta(days=4):%d %b %Y}, grouped by week")
    print("  Options -> Y-axis unit: the percentage option for 0-1 values")
    print(f"  Annotation on {launch:%d %b %Y}: Payment link live")
    print(f"For the funnel, retention and week-11 lesson: end every date range on {w11 + timedelta(days=4):%d %b %Y} (week 11).")
    w8, w13 = week_sunday(qend, 8), week_sunday(qend, 8) + timedelta(weeks=5, days=6)
    print(f"For the experiment readout: experiment 'Smart reminders' on flag smart-reminders, start date {w8:%d %b %Y}, "
          f"end date {w13:%d %b %Y}; Frequentist; primary metric: funnel to invoice_paid_on_time.")
    print(f"For the weekly review dashboard: event weekly_totals, date range {w1 + timedelta(days=2):%d %b %Y} to "
          f"{w10 + timedelta(days=4):%d %b %Y} (weeks 1-10), grouped by week; North Star = Property value -> Sum -> "
          f"invoices_paid_on_time; guardrails = Property value -> Average of payment_failure_rate (goal line 4), "
          f"reminder_opt_out_rate and complaints_per_10k (6).")


if __name__ == "__main__":
    main()
