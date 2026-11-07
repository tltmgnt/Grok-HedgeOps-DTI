"""Restricted HTTPS transport for fixed broker and xAI API hosts."""
import urllib.error
import urllib.request
from urllib.parse import urlsplit

_ALLOWED = frozenset({"api.x.ai", "paper-api.alpaca.markets", "data.alpaca.markets"})

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect prohibited", headers, fp)

def open_api(req, *, timeout=20):
    url = req.full_url if isinstance(req, urllib.request.Request) else req
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in _ALLOWED
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443)):
        raise ValueError("API URL must use an approved HTTPS host")
    # Do not follow redirects that might leak authentication headers.
    opener = urllib.request.build_opener(NoRedirect())
    return opener.open(req, timeout=timeout)
