# Product Management: Prioritisation, Metrics & A/B Testing

5 multiple-choice questions. The correct answer is marked ✅; the explanation is shown after the learner answers.

## Quiz: Experiments Checkpoint

Comes after the lesson: **Experiments Checkpoint**

### Question 1

A B2B tool wants to A/B test a new pricing page. Each customer account has several users, and they often discuss upgrades together. The analyst suggests randomising users, “because there are more of them, so we'll get significance faster.”

**What should you randomise, and why?**

A. Users, because the bigger sample makes the test more trustworthy
B. Page views, because each one is an independent decision
C. Accounts, so everyone in an account sees the same version and nothing leaks between groups, accepting that you'll need more data than a per-user calculation suggests  ✅ correct
D. Users, but drop accounts where people saw different versions

*Explanation:* Randomise the unit whose behaviour would otherwise leak between groups. If colleagues in one account see two prices, the account sees two products, and the groups stop being independent. Users within an account behave alike, so the effective sample is smaller than the user count, and you plan for that. Dropping mixed accounts afterwards removes people unevenly, which is how a sample ratio mismatch starts.

*Lesson it draws on:* Designing the Test

### Question 2

Your test is sized to detect a one-point lift on a 20% conversion rate, at 5% significance and 80% power. Your manager asks you to make it detect half a point instead, “to be safe”, without changing the run.

**What happens to the sample you need?**

A. About twice as many per variant, because the effect is half the size
B. About four times as many per variant. With the same traffic, the test can't detect half a point unless it runs far longer  ✅ correct
C. The same sample, because the significance level hasn't changed
D. Fewer, because a smaller effect is easier to rule out

*Explanation:* Sample size scales with one over the effect squared (Evan Miller's rule of thumb is about sixteen times the variance divided by the effect squared), so halving the effect roughly quadruples the sample. “To be safe” isn't free: either run far longer, or accept that half a point is out of reach and size the test for the smallest effect you would actually act on.

*Lesson it draws on:* Sample Size and Run Time, Decided Before Launch

### Question 3

A 50/50 test: control has 25,300 users and the variant has 24,100. The variant shows +3% on the primary metric, flagged statistically significant. The test page loads an extra script that sometimes times out.

**Why can't you trust the +3%?**

A. Because the split is unhealthy: something removed users from one group and not the other, so the people left probably differ. Find the leak, fix it, and re-read the results by assignment or rerun  ✅ correct
B. You can trust it. Significance already accounts for the uneven split
C. Because 1,200 users is too small a gap to matter. Re-weight the groups to 50/50 and read on
D. Because significance needs a 99% threshold when groups are uneven

*Explanation:* That's a sample ratio mismatch. On a working 50/50 split, a gap that size is wildly unlikely by chance. The users who dropped out (perhaps the slow-loading ones) probably differ from those who stayed, so the variant group is no longer comparable. The significance test assumes healthy assignment, so it can't rescue a broken one, and re-weighting can't put back the users who left. Read health before results, every time.

*Lesson it draws on:* Reading a Readout

### Question 4

The signed decision rule says: ship if the whole 95% interval for the effect sits above zero and every guardrail holds; stop if the interval rules out an effect as big as one point; anything else, iterate. The result: +0.3 points, interval from −0.2 to +0.8. Guardrails all hold.

**What does the rule say?**

A. Ship, because the point estimate is positive and the guardrails hold
B. Iterate, because the interval includes zero
C. Rerun the test with more traffic until the interval clears zero
D. Stop: the whole interval sits below one point, so it rules out an effect as big as one point  ✅ correct

*Explanation:* Read the interval against the rule, not the point estimate. The upper end, +0.8, is below one point, so the data rules out an effect as big as one point. That is the stop condition. Including zero rules out shipping, but on its own it doesn't mean iterate. Rerunning until it clears zero is chasing the answer you wanted. That's why the rule is signed before the data arrives.

*Lesson it draws on:* Designing the Test

### Question 5

The overall result is flat. Afterwards, an analyst slices it eight ways and finds that mobile users in one region show +4 points, “clearly significant.” The regional lead wants to ship to that region now.

**What is the right call?**

A. Ship to that region, because +4 points is large and significant
B. Ignore it, because segment results are never meaningful
C. Treat it as a hypothesis: give it a reason, make it the planned segment of a new test, and size that test for it  ✅ correct
D. Re-run the same test and stop as soon as that segment looks significant again

*Explanation:* With enough slices, something always looks good. A segment you didn't plan to test is a hypothesis for the next test, not a result. Planned segments can be real, so ignoring all segments throws away a lead. Stopping when it first looks significant is peeking, which inflates false alarms. In Evan Miller's worst case, 5% becomes 26%.

*Lesson it draws on:* Reading a Readout
