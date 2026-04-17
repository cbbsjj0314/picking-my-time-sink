# Steam rankings payload fixtures

- `topsellers_global.payload.json` | target=topsellers | region=global | chart_url=https://store.steampowered.com/charts/topsellers/global | source_service=IStoreTopSellersService/GetWeeklyTopSellers/v1 | captured_at_utc=2026-03-09T18:42:39Z
- `topsellers_kr.payload.json` | target=topsellers | region=KR | chart_url=https://store.steampowered.com/charts/topsellers/KR | source_service=IStoreTopSellersService/GetWeeklyTopSellers/v1 | captured_at_utc=2026-03-09T18:42:39Z
- `mostplayed_global.payload.json` | target=mostplayed | region=global | chart_url=https://store.steampowered.com/charts/mostplayed/global | source_service=ISteamChartsService/GetGamesByConcurrentPlayers/v1 | captured_at_utc=2026-03-09T18:42:39Z
- `mostplayed_kr.payload.json` | target=mostplayed | region=KR | chart_url=https://store.steampowered.com/charts/mostplayed/KR | source_service=ISteamChartsService/GetGamesByConcurrentPlayers/v1 | captured_at_utc=2026-03-09T18:42:39Z
- `legacy_empty_chart.html` | sanitized legacy HTML structure with no app links | used only to verify that non-payload chart markup does not create rows
