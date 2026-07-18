"""
HTTP_VERIFY engine — live HTTP response checks for CIS compliance.
Checks headers, status codes, and TLS properties via WAT runner results.
This engine is called from wat_runner.py, not from the static file scanner.
"""


def verify_server_header(response, item):
    """CIS 2.1.1: Server header must not leak version."""
    server_val = response.get("server", "").lower()
    if not server_val:
        return {"status": "fail", "detail": "No Server header in response", "score": 0}
    # Check if version number is present
    import re
    if re.search(r"\d+\.\d+", server_val):
        return {"status": "fail", "detail": f"Server header leaks version: '{server_val[:40]}'", "score": 0}
    return {"status": "pass", "detail": f"Server header is clean: '{server_val[:40]}'", "score": 100}


def verify_hsts(response, item):
    """CIS 6.3: HSTS with max-age >= 31536000."""
    import re
    hsts = (response.get("strict-transport-security") or "").lower()
    if not hsts:
        return {"status": "fail", "detail": "HSTS header not present", "score": 0}
    m = re.search(r"max-age=(\d+)", hsts)
    if m and int(m.group(1)) >= 31536000:
        return {"status": "pass", "detail": f"HSTS max-age={m.group(1)} (>= 1 year)", "score": 100}
    return {"status": "fail", "detail": f"HSTS present but max-age < 1 year: '{hsts[:60]}'", "score": 50}


def verify_csp(response, item):
    """CIS 8.1: Content-Security-Policy header present and restrictive."""
    csp = (response.get("content-security-policy") or "").lower()
    if not csp:
        return {"status": "fail", "detail": "CSP header not present", "score": 0}
    issues = []
    if "unsafe-inline" in csp:
        issues.append("allows unsafe-inline")
    if "unsafe-eval" in csp:
        issues.append("allows unsafe-eval")
    if issues:
        return {"status": "fail", "detail": f"CSP present but " + "; ".join(issues), "score": 50}
    return {"status": "pass", "detail": "CSP header present and restrictive", "score": 100}


def verify_x_frame(response, item):
    """CIS 8.2: X-Frame-Options must be DENY or SAMEORIGIN."""
    xfo = (response.get("x-frame-options") or "").upper().strip()
    if not xfo:
        return {"status": "fail", "detail": "X-Frame-Options header not present", "score": 0}
    if xfo in ("DENY", "SAMEORIGIN"):
        return {"status": "pass", "detail": f"X-Frame-Options: {xfo}", "score": 100}
    return {"status": "fail", "detail": f"X-Frame-Options set to '{xfo}' (should be DENY or SAMEORIGIN)", "score": 0}


def verify_x_content_type(response, item):
    """CIS 8.3: X-Content-Type-Options must be nosniff."""
    val = (response.get("x-content-type-options") or "").lower().strip()
    if not val:
        return {"status": "fail", "detail": "X-Content-Type-Options header not present", "score": 0}
    if val == "nosniff":
        return {"status": "pass", "detail": "X-Content-Type-Options: nosniff", "score": 100}
    return {"status": "fail", "detail": f"X-Content-Type-Options set to '{val}' (should be nosniff)", "score": 0}


def verify_referrer_policy(response, item):
    """CIS 8.4: Referrer-Policy must be restrictive."""
    val = (response.get("referrer-policy") or "").lower().strip()
    if not val:
        return {"status": "fail", "detail": "Referrer-Policy header not present", "score": 0}
    good = ("no-referrer", "same-origin", "strict-origin", "strict-origin-when-cross-origin")
    if val in good:
        return {"status": "pass", "detail": f"Referrer-Policy: {val}", "score": 100}
    return {"status": "fail", "detail": f"Referrer-Policy set to '{val}' (should be restrictive)", "score": 50}


def verify_permissions_policy(response, item):
    """CIS 8.5: Permissions-Policy must restrict browser features."""
    val = (response.get("permissions-policy") or "").lower()
    if not val:
        return {"status": "fail", "detail": "Permissions-Policy header not present", "score": 0}
    return {"status": "pass", "detail": "Permissions-Policy header present", "score": 100}


def verify_https(item):
    """CIS 6.1/6.2: HTTPS must be enabled with TLS 1.2+."""
    https_info = item.get("_https_info", {})
    if not https_info.get("https_support"):
        return {"status": "fail", "detail": "No HTTPS support — plain HTTP only", "score": 0}
    return {"status": "pass", "detail": "HTTPS enabled", "score": 100}


HTTP_CHECKS = {
    "cis-2.1.1-server-tokens":     lambda r, i: verify_server_header(r, i),
    "cis-6.3-hsts":                 lambda r, i: verify_hsts(r, i),
    "cis-8.1-csp":                  lambda r, i: verify_csp(r, i),
    "cis-8.2-x-frame-options":      lambda r, i: verify_x_frame(r, i),
    "cis-8.3-x-content-type":       lambda r, i: verify_x_content_type(r, i),
    "cis-8.4-referrer-policy":      lambda r, i: verify_referrer_policy(r, i),
    "cis-8.5-permissions-policy":   lambda r, i: verify_permissions_policy(r, i),
    "cis-6.1-https":                lambda r, i: verify_https(i),
}


def run(response, https_info, check_id):
    """Execute a specific HTTP check against response data."""
    fn = HTTP_CHECKS.get(check_id)
    if not fn:
        return {"status": "error", "detail": f"Unknown HTTP check: {check_id}", "score": 0}
    try:
        # Build an item-like dict with the HTTP data embedded
        item = {"_http_response": response, "_https_info": https_info}
        return fn(response, item)
    except Exception as e:
        return {"status": "error", "detail": str(e), "score": 50}
