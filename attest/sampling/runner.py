"""
Orchestrates parallel sampling of a prompt battery with rate limiting.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from attest.models import PromptItem, RawSample
from attest.sampling.base import ProviderAdapter


class SamplingBatteryError(Exception):
    """Raised when sampling battery exceeds error tolerance threshold."""


async def run_sampling_battery(
    adapter: ProviderAdapter,
    prompts: list[PromptItem],
    concurrency: int = 5,
    on_sample_done: Callable[[RawSample], None] | None = None,
    max_error_rate: float = 0.20,
) -> list[RawSample]:
    """
    Executes all prompt queries in the battery using an asyncio semaphore.
    Fault-tolerant: allows up to max_error_rate transient request failures
    without discarding successfully collected samples.
    """
    semaphore = asyncio.Semaphore(concurrency)

    # Flatten prompt sampling tasks
    tasks = []
    for p in prompts:
        if p.id is None:
            raise ValueError(f"Prompt '{p.text[:30]}' has no assigned database ID.")
        for _ in range(p.samples_count):
            tasks.append((p.id, p.text, p.params, p.messages))

    async def _worker(
        prompt_id: int, text: str, params: dict, messages: list[dict] | None
    ) -> RawSample:
        async with semaphore:
            sample = await adapter.sample(
                prompt_id=prompt_id,
                prompt_text=text,
                params=params,
                messages=messages,
            )
        if on_sample_done:
            on_sample_done(sample)
        return sample

    completed = await asyncio.gather(
        *[_worker(pid, txt, prms, msgs) for pid, txt, prms, msgs in tasks],
        return_exceptions=True,
    )

    samples: list[RawSample] = []
    errors: list[Exception] = []
    for item in completed:
        if isinstance(item, Exception):
            errors.append(item)
        elif isinstance(item, RawSample):
            samples.append(item)

    total_tasks = len(tasks)
    if total_tasks > 0:
        error_rate = len(errors) / total_tasks
        if error_rate > max_error_rate:
            first_err = errors[0] if errors else "unknown error"
            raise SamplingBatteryError(
                f"Sampling battery failed: {len(errors)}/{total_tasks} requests failed "
                f"({error_rate * 100:.1f}% > {max_error_rate * 100:.0f}% max error threshold). "
                f"First error: {first_err}"
            )

    return samples


def safe_async_run(coro):
    """
    Safely runs an async coroutine synchronously.
    Handles existing active event loops (such as pytest-asyncio) via a dedicated thread.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()

    return asyncio.run(coro)
