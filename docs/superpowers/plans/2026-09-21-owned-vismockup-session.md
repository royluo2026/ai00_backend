# Owned VisMockup Session Implementation Plan

1. Add failing connection tests proving an unrelated running process does not block creation of an owned session and that an existing retained session is reused.
2. Add dispatch/lifecycle tests for the verified outer document collection ids and visible-window transition.
3. Change `WindowsVisMockupCom` to create, retain, and identify its own `VFFrame.Application` session without process discovery.
4. Make `BreakawayVisMockupCom` use the owned COM activation path while preserving executable signature verification.
5. Replace dynamic document open and the incorrect close dispatch with the verified raw dispatch calls.
6. Run focused Connector tests, the full Connector test project, and the real Siemens JT smoke probe.
7. Restart the test frontend/backend/Connector and validate the model-file open and control path.
