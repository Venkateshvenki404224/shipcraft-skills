# Public Excalidraw libraries that proved useful

Fetch with `scripts/fetch_libraries.py` (defaults below). List item names with
`fetch_libraries.py --list <alias>`. Place with `icon(alias, item_name, x, y, height)`.

| alias | source | good items |
|---|---|---|
| network | dwelle/network-topology-icons | `Computer w/ keyboard (3D)`, `Computer w/ keyboard and mouse (3D)`, `Computer (3D)`, `Server`, `Switch`, `Router`, `Firewall` |
| aws | stojanovic/aws-serverless-icons-v2 | `APIGateway`, `Lambda`, `DynamoDB`, `Aurora`, `SQS`, `SNS`, `S3`, `CloudWatch`, `EventBridge` |
| locations | jgodoy/network-locations | `Corporate Office / Headquarterts` (sic), `Office`, `House`, `Datacenter` |
| people | dhtoran/stick-people | `Stick man standard`, `Stick woman standard`, `Stick man thinking` |
| files | xxxdeveloper/icons | `cloud`, `documents`, `download`, `upload`, `clipboard`, `password`, `search`, `sql`, `pdf` |
| ux | gabrielamacakova/basic-ux-wireframing-elements | `Search field`, `Filled button (text only)`, `Outlined button (text only)`, `Rounded toggle with text (ON/OFF)`, `Dropdown menu`, `Text area`, `Text field with text`, `Modal`, `Confirm button (text+icon)`, `Reject button (text+icon)`, `Checkbox (text+icon)` |
| lofi | spfr/lo-fi-wireframing-kit | legacy format, items by index: `18` sidebar nav, `17` search bar, `15` table, `14` card, `13` header, `21` desktop frame, `20` phone frame |
| dash | datavizfairy/dashboard-charts | `KPI Card`, `Data Table`, `Horizontal Bar`, `Vertical Bar`, `Line • 1 series`, `Gantt Timeline`, `Donut • 3 Segment`, `Heatmap` |
| sticky | ferminrp/post-it | legacy format, `0`–`12` are colours (0 grey, 1 dark grey, 2 red, 3 pink, 4 purple, 5 violet, …) |
| web | dhaval_godwani/webpage-frames | `viewable webpage`, `interactive webpage` |

## Two formats

New libraries have `libraryItems: [{name, elements}]`. Old ones have `library: [[elements], …]`
with no names — the builder exposes them by index string (`"18"`). `fetch_libraries.py --list`
shows both.

## Sample text

Wireframe and chart items ship with placeholder text ("Sidebar", "Default Item", "XXX",
"Button"). Pass `keep_text=False` to `icon()` and write your own labels on top; otherwise the two
collide.

## Scaling

`icon()` scales by **height**; width follows the item's aspect ratio and is returned, so you can
place text to its right. Stroke widths are clamped to 1–2 so a tiny icon does not turn into a blob.

## The user's own installed libraries

Installed libraries live in the browser's IndexedDB (`excalidraw-library-db`), not on the server, so
a headless session cannot see them. Ask for an export (Library panel → ⋮ → Export) and drop the
`.excalidrawlib` into the cache dir under an alias.
