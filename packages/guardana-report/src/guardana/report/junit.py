from xml.sax.saxutils import escape, quoteattr

from guardana.core.manifest.records import SuiteOutcome, SuiteSummary
from guardana.core.report import ScanResult
from guardana.core.suite import describe


class JUnitRenderer:
    """JUnit XML — what most CI systems render as a test report."""

    name = "junit"

    def render(self, result: ScanResult) -> str:
        """Render one scan result to text."""
        cases: list[str] = []
        # A suite is one testcase whatever it concluded, in place of its finding: a pass
        # rate is the suite's answer, and a pipeline counting testcases must see it pass.
        # A waived suite keeps its waived testcase instead.
        waived = {f.rule_id for f in result.waived}
        suites = {rule: s for rule, s in result.suites.items() if rule not in waived}
        findings = [f for f in result.findings if f.rule_id not in suites]
        unverified = [f for f in result.unverified if f.rule_id not in suites]
        declined = sum(1 for s in suites.values() if s.outcome is SuiteOutcome.INCONCLUSIVE)
        failed = sum(1 for s in suites.values() if s.outcome is SuiteOutcome.FAIL)
        cases.extend(
            _suite_case(rule_id, suite, _subject(result, rule_id))
            for rule_id, suite in sorted(suites.items())
        )
        for f in findings:
            name = quoteattr(f.rule_id)
            classname = quoteattr(f.target_ref)
            message = quoteattr(f.title)
            summary = escape(f.evidence.summary)
            cases.append(
                f"    <testcase name={name} classname={classname}>\n"
                f"      <failure message={message}>{summary}</failure>\n"
                f"    </testcase>"
            )
        for f in unverified:
            name = quoteattr(f.rule_id)
            classname = quoteattr(f.target_ref)
            message = quoteattr(f.title)
            reason = escape(f.verdict.rationale if f.verdict is not None else f.evidence.summary)
            cases.append(
                f"    <testcase name={name} classname={classname}>\n"
                f"      <skipped message={message}>{reason}</skipped>\n"
                f"    </testcase>"
            )
        for f in result.waived:
            name = quoteattr(f.rule_id)
            classname = quoteattr(f.target_ref)
            message = quoteattr(f.title)
            reason = escape(f"waived: {f.evidence.summary}")
            cases.append(
                f"    <testcase name={name} classname={classname}>\n"
                f"      <skipped message={message}>{reason}</skipped>\n"
                f"    </testcase>"
            )
        # `<error>` rather than `<failure>`: CI tooling reads the first as "the
        # test could not run" and the second as "the test ran and failed", which is
        # exactly the distinction this channel exists to make.
        for e in result.errors:
            name = quoteattr(e.source)
            classname = quoteattr(f"guardana.{e.stage}")
            message = quoteattr("check did not run")
            cases.append(
                f"    <testcase name={name} classname={classname}>\n"
                f"      <error message={message}>{escape(e.reason)}</error>\n"
                f"    </testcase>"
            )
        # Also `<error>`, and counted as one: a pipeline that renders this XML reads
        # `errors="0"` as a suite that ran cleanly, and coverage the operator demanded
        # and did not get is the one thing that must never look like that.
        for gap in result.coverage_shortfall:
            name = quoteattr(gap.name)
            classname = quoteattr(f"guardana.coverage.{gap.kind}")
            message = quoteattr("demanded coverage was not available")
            cases.append(
                f"    <testcase name={name} classname={classname}>\n"
                f"      <error message={message}>{escape(gap.detail)}</error>\n"
                f"    </testcase>"
            )
        # And once more, for the run as a whole. Every declined check above is a
        # `<skipped>`, which is the honest word for one of them — and a suite of
        # nothing but skips renders green on every dashboard that reads this file.
        # A run where not one check reached a verdict is the same fact as unmet
        # coverage: nothing was established, and it must not look like it was.
        if result.verified_nothing:
            detail = (
                f"{result.rules_run_count} check(s) ran and not one of them reached a "
                f"verdict, so this run established nothing"
            )
            cases.append(
                '    <testcase name="guardana.run" classname="guardana.coverage">\n'
                f'      <error message="nothing was verified">{escape(detail)}</error>\n'
                "    </testcase>"
            )
        # The same fact, one step weaker, and the one that actually arrives: some
        # checks declined while others concluded. `verified_nothing` is False then,
        # so the guard above never fired — and a model store nobody could parse
        # rendered as `failures="0" skipped="N"`, which every dashboard reads as a
        # pass. A skip is honest for one check and dishonest for the suite.
        if unverified and not result.verified_nothing:
            detail = (
                f"{len(unverified)} check(s) ran and could not reach a verdict, "
                f"so what they cover was not established"
            )
            cases.append(
                '    <testcase name="guardana.unverified" classname="guardana.coverage">\n'
                f'      <error message="some checks reached no verdict">{escape(detail)}</error>\n'
                "    </testcase>"
            )
        body = "\n".join(cases)
        skipped = len(unverified) + len(result.waived)
        errors = (
            len(result.errors)
            + len(result.coverage_shortfall)
            + declined
            + (1 if result.verified_nothing else 0)
            + (1 if unverified and not result.verified_nothing else 0)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<testsuite name="guardana" tests="{result.rules_run_count}" '
            f'failures="{len(findings) + failed}" skipped="{skipped}" '
            f'errors="{errors}">\n'
            f"{body}\n</testsuite>"
        )


def _subject(result: ScanResult, rule_id: str) -> str:
    """Name what a suite measured, from its assessments; a suite that recorded none has none."""
    refs = (a.subject_ref for a in result.assessments if a.rule_id == rule_id)
    return next(refs, "guardana.suite")


def _suite_case(rule_id: str, summary: SuiteSummary, subject: str) -> str:
    """Write one testcase for a suite: empty on a pass, a failure below its bar, an error declined.

    Declined is an error rather than a skip: its gate is a demand its author wrote.
    """
    statement = escape(describe(summary))
    verdict = ""
    if summary.outcome is SuiteOutcome.FAIL:
        verdict = f'      <failure message="suite below its bar">{statement}</failure>\n'
    elif summary.outcome is SuiteOutcome.INCONCLUSIVE:
        verdict = f'      <error message="suite declined">{escape(summary.reason or "")}</error>\n'
    return (
        f"    <testcase name={quoteattr(rule_id)} classname={quoteattr(subject)}>\n"
        f"{verdict}"
        f"      <system-out>{statement}</system-out>\n"
        f"    </testcase>"
    )
