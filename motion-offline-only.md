# Motion Offline Only

## Goal
Remove inline motion processing and default the app to offline motion only to reduce runtime load.

## Tasks
- [x] Audit motion usage points in `app/core/recorder_worker.py` and related config/UI hooks -> Verify: list of functions/fields tied to inline motion and where they are referenced.
- [x] Remove inline motion code paths in `app/core/recorder_worker.py` (imports, state, handlers, writer usage) -> Verify: file has no `MotionClipWriter`, `apply_motion`, or `_handle_motion` references.
- [x] Force offline motion as the only mode in config and UI (no toggle) -> Verify: config defaults to offline and UI has no inline/offline selection.
- [x] Clean up unused imports/variables and run a quick search for leftover inline-motion references -> Verify: `rg "MotionClipWriter|apply_motion|_handle_motion" app/core/recorder_worker.py app/ui/recorder_view.py` returns none.

## Done When
- [x] Recorder runs without any inline motion code and offline motion is the sole path.
