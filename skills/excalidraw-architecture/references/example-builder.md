# Example builder script

A single-diagram request ("draw how X talks to Y") looks like this. Save it as
`docs/architecture/_build/<name>.py`, run it, render, fix.

```python
import sys
sys.path.insert(0, "<this skill's directory>/scripts")
from excalidraw_builder import *

text(0, 0, "File import — how a partner's export becomes customer records", 36)
text(0, 52, "Read left to right. Built from importers/customer_import.py and relay/sync.py.", 18, color=MUTED)

zone(0, 120, 320, 520, "Partner", "green")
zone(360, 120, 420, 520, "Relay box", "purple")
zone(820, 120, 520, 520, "Our app", "blue")

source = card(20, 190, 280, 140, "Partner system export", "Nightly CSV / ZIP dropped over SFTP",
	"one folder per partner", "green", art=("network", "Computer (3D)"))
inbox = card(380, 190, 380, 100, "1 · Inbound folder", "one folder per partner · cron every 5 min", "", "purple")
split = card(380, 320, 380, 100, "2 · Split & map", "csv splitter → field map per partner", "", "purple")
post = card(380, 450, 380, 100, "3 · POST to app", "signed POST · retries on 5xx", "", "purple")
chain([inbox, split, post], "purple")

importer = card(840, 190, 480, 120, "4 · customer_import", "find-or-create under a lock · fills → Orders",
	"importers/customer_import.py", "blue", art=("network", "Server"))
done = card(840, 450, 480, 100, "5 · import_finished callback", "relay marks the file done", "", "blue", dashed=True)

connect(source, inbox, "green", "")
connect(post, importer, "blue", "", source_ratio=0.5, target_ratio=0.5)
arrow(importer, done, "blue", point(importer, "bottom"), point(done, "top"), "", dashed=True)

save(sys.argv[1])
```

Then:

```bash
python3 docs/architecture/_build/file-import.py docs/architecture/file-import.excalidraw
$S/render_local.sh docs/architecture/file-import.excalidraw docs/architecture/file-import.png 2
# look at the PNG, fix overlaps, rebuild, re-render
$S/render.sh docs/architecture/file-import.excalidraw 0 0.9 /tmp/render.png   # only to share a room
$S/publish_room.sh /tmp/room.png        # prints ROOM <url>; look at /tmp/room.png
```

For a multi-chapter pack, keep one `TOP` constant per chapter and compute each from the previous
chapter's real bottom; see `architecture-pack.md`.
