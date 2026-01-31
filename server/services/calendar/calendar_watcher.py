






def start():
    async with self._lock:
        if self._task and not self._task.done(): return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="calendar-watcher")
        logger.info("Calendar watcher started")

def stop():
    async with self._lock:
        self._running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
            self._task = None

async def _run(self) -> None:
        while self._running:
            try: await self._poll_start()
            except Exception as exc: logger.exception("Watcher poll failed", extra={"error": str(exc)})
            await asyncio.sleep(self._poll_interval)

async def _poll_start(self) -> None:
    composio_user_id = get_active_calendar_user_id()
    if not composio_user_id:
        logger.debug("Calendar not connected")
        return
    enable_calendar_trigger("google_calendar_new_event", composio_user_id)
    
