"""Small compatibility fix for TelethonFakeTLS 2022 and recent Telethon.

Telethon awaits writer.wait_closed() during disconnect. The legacy FakeTLS
writer delegates close()/drain() to its upstream writer but has no wait_closed().
Do not touch transport, proxy configuration or encryption.
"""


def patch_faketls_wait_closed():
    """Install the missing delegating method once; return whether patched.

    Safe to call repeatedly. Keep the name local to the caller so it doesn't
    import Telethon or the Telegram connection at module-import time.
    """
    from TelethonFakeTLS.FakeTLS.TLSInOut import FakeTLSStreamWriter

    if hasattr(FakeTLSStreamWriter, "wait_closed"):
        return False

    async def wait_closed(self):
        upstream_wait = getattr(self.upstream, "wait_closed", None)
        if upstream_wait is not None:
            await upstream_wait()

    FakeTLSStreamWriter.wait_closed = wait_closed
    return True
