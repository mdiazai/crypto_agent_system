from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging
import httpx

log = logging.getLogger(__name__)

# Retry for external HTTP/API calls: 3 attempts, backoff 1s → 2s → 4s
http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError, ConnectionError, TimeoutError)),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)

# Retry for exchange calls: up to 5 attempts, longer backoff
exchange_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
