"""Service helpers for single and streaming Jimbo runtime requests."""

from jimbo_runtime_executor import run_runtime_request


def execute_runtime_request(request):
    """Execute one runtime request and return its structured response."""
    return run_runtime_request(request)


def stream_runtime_requests(requests, *, continue_on_error=False):
    """Yield responses for each runtime request in a stream."""
    for request in requests:
        try:
            yield execute_runtime_request(request)
        except Exception as exc:
            if not continue_on_error:
                raise
            yield {
                "ok": False,
                "request_id": request.get("request_id"),
                "error": str(exc),
                "request": request,
            }
