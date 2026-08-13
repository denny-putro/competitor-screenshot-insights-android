# iPhone App Bundle Registry

This table is the verified cache for an explicitly named app's launch target. Do not manually select a bundle ID, infer a brand from a company name, reuse the foreground session, or inspect the installed-app list to choose a launch target.

Use `scripts/open-mapped-app.sh` for every named-app launch. It first accepts only an exact App value or explicit Alias from this table. If no entry exists, it alone may query the phone's installed-app inventory: only one exact display-name match is eligible. It opens that discovered bundle, captures a launch screenshot, and requires the installed name, foreground bundle, and visible application label to agree before automatically appending a mapping and writing a target manifest. No match, duplicate display name, or identity mismatch is a hard stop.

The automation may append a previously unknown mapping only after this complete verification. Do not manually add, change, or delete mappings during research. Treat corrections to an existing mapping as a separate, user-authorized maintenance task.

| App | Bundle ID | Visible brand | Aliases | Verified |
|---|---|---|---|---|
| Airbnb | `com.airbnb.app` | Airbnb | — | 2026-07-15 |
| Agoda | `com.agoda.consumer` | Agoda | — | 2026-07-16 |
| Trip.com | `com.ctrip.EBooking` | Trip.com | Trip | 2026-07-15 |
| 携程旅行 | `ctrip.com` | 携程旅行 | 携程; Ctrip | 2026-07-28 |
| Tripadvisor | `com.tripadvisor.LocalPicks` | Tripadvisor | — | 2026-07-17 |
| Traveloka | `com.traveloka.traveloka` | Traveloka | — | 2026-07-29 |
| 东方航空 | `com.ceair.b2m` | 东方航空 | 东航 | 2026-07-16 |
| Settings | `com.apple.Preferences` | Settings | — | 2026-07-15 |
| 淘宝 | `com.taobao.taobao4iphone` | 淘宝 | — | 2026-08-04 |
| Arc Search | `company.thebrowser.ArcMobile2` | Arc Search | Arc | 2026-07-17 |
| Booking.com | `com.booking.BookingApp` | Booking.com | — | 2026-07-17 |
| Booking.com缤客 | `cn.booking.GuestApp` | Booking.com缤客 | 缤客 | 2026-07-17 |
| Cathay Pacific | `com.mccann.CXMobile` | Cathay Pacific | 国泰航空 | 2026-07-30 |
| Skyscanner | `net.skyscanner.iphone` | Skyscanner | — | 2026-07-28 |
| Disney Resort | `com.disney.shanghaidisneyland` | Disney Resort | — | 2026-07-17 |
| Expedia | `com.expedia.booking` | Expedia | — | 2026-07-17 |
| 飞猪旅行 | `com.taobao.travel` | 飞猪旅行 | 飞猪 | 2026-07-27 |
| Google Maps | `com.google.Maps` | Google Maps | 谷歌地图 | 2026-07-17 |
| 圆周旅迹 | `com.chaochaoshishi.slytherin` | 圆周旅迹 | — | 2026-07-17 |
| Mindtrip | `ai.mindtrip.Mindtrip` | Mindtrip | — | 2026-07-17 |
