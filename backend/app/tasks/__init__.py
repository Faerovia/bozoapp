"""Cron / background tasky spouštěné mimo request cycle.

Každý task má svůj CLI entry-point v samostatném modulu. Spouští se
přes `python -m app.tasks.<name>` (v produkci z systemd timeru nebo crontabu).

Kvůli asyncio se task tvaruje jako `async def main()` a pouští přes
`asyncio.run(main())`.
"""
