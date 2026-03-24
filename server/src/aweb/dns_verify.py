"""DNS TXT record verification for aweb namespace authority.

Resolves _aweb.<domain> TXT records and parses the canonical format:
    aweb=v1; controller=<did:key>;
"""

from __future__ import annotations

import dns.asyncresolver
import dns.exception
import dns.resolver

from aweb.awid.did import validate_did


class DnsVerificationError(Exception):
    """Raised when DNS verification of a domain fails."""


_AWEB_PREFIX = "aweb="


async def verify_domain(domain: str) -> str:
    """Verify a domain's aweb TXT record and return the controller did:key.

    Raises DnsVerificationError on any failure (no record, malformed, etc.).
    """
    domain = _canonicalize_domain(domain)
    qname = f"_aweb.{domain}"

    try:
        answers = await dns.asyncresolver.resolve(qname, "TXT")
    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout,
    ):
        raise DnsVerificationError(f"No TXT records found for {qname}")

    aweb_records = []
    for rdata in answers:
        text = b"".join(rdata.strings).decode()
        if text.startswith(_AWEB_PREFIX):
            aweb_records.append(text)

    if not aweb_records:
        raise DnsVerificationError(f"No aweb TXT record found at {qname}")

    if len(aweb_records) > 1:
        raise DnsVerificationError(
            f"Multiple aweb TXT records found at {qname} — expected exactly one"
        )

    return _parse_aweb_record(aweb_records[0])


def _canonicalize_domain(domain: str) -> str:
    """Lowercase and strip trailing dot."""
    return domain.lower().rstrip(".")


def _parse_aweb_record(record: str) -> str:
    """Parse an aweb TXT record and return the controller did:key.

    Expected format: aweb=v1; controller=<did:key>;
    """
    fields: dict[str, str] = {}
    for part in record.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        fields[key.strip()] = value.strip()

    version = fields.get("aweb")
    if version != "v1":
        raise DnsVerificationError(f"Unsupported aweb version: {version}")

    controller = fields.get("controller")
    if not controller:
        raise DnsVerificationError("Missing controller field in aweb TXT record")

    if not validate_did(controller):
        raise DnsVerificationError(f"Invalid controller DID: {controller} (must be did:key Ed25519)")

    return controller
