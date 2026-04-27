#!/usr/bin/env python3
"""Convert a Trivy JSON scan report into an OpenVEX v0.2.0 document.

One VEX statement per CVE, listing all affected products by purl.
Status is "affected" for every CVE Trivy detected (i.e. present in our
artifact at scan time). When Trivy knows of an upstream fix, the fix
version is recorded in `action_statement` so consumers can act on it.

Usage:
    python scripts/generate_vex.py <trivy-report.json> <vex.openvex.json> \\
        [--author=<author>] [--id=<doc-id>]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path


def build_statements(trivy: dict) -> list[dict]:
    by_cve: dict[str, dict] = defaultdict(
        lambda: {"products": set(), "fixed_versions": set()}
    )

    for result in trivy.get("Results", []):
        for vuln in result.get("Vulnerabilities") or []:
            cve = vuln.get("VulnerabilityID")
            if not cve:
                continue
            purl = (vuln.get("PkgIdentifier") or {}).get("PURL")
            if not purl:
                pkg = vuln.get("PkgName")
                ver = vuln.get("InstalledVersion")
                purl = f"pkg:generic/{pkg}@{ver}" if pkg and ver else None
            if purl:
                by_cve[cve]["products"].add(purl)
            fixed = vuln.get("FixedVersion")
            if fixed:
                by_cve[cve]["fixed_versions"].add(fixed)

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    statements = []
    for cve in sorted(by_cve):
        data = by_cve[cve]
        statement = {
            "vulnerability": {"@id": cve, "name": cve},
            "products": [{"@id": p} for p in sorted(data["products"])],
            "status": "affected",
            "timestamp": timestamp,
        }
        if data["fixed_versions"]:
            statement["action_statement"] = (
                "Upstream fix available in: "
                + ", ".join(sorted(data["fixed_versions"]))
            )
        statements.append(statement)
    return statements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trivy_report", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--author", default="github/actions")
    parser.add_argument("--id", default=None, dest="doc_id")
    args = parser.parse_args()

    if not args.trivy_report.exists():
        print(f"Trivy report not found: {args.trivy_report}", file=sys.stderr)
        return 1

    trivy = json.loads(args.trivy_report.read_text())
    statements = build_statements(trivy)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    document = {
        "@context": "https://openvex.dev/ns/v0.2.0",
        "@id": args.doc_id or f"urn:uuid:vex-{int(dt.datetime.now().timestamp())}",
        "author": args.author,
        "timestamp": timestamp,
        "version": 1,
        "tooling": "trivy/aquasecurity + scripts/generate_vex.py",
        "statements": statements,
    }

    args.output.write_text(json.dumps(document, indent=2) + "\n")
    print(
        f"Wrote {args.output} — {len(statements)} statement(s) "
        f"covering {sum(len(s['products']) for s in statements)} product(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
