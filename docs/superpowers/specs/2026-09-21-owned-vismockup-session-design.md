# Owned VisMockup Session Design

## Status

Approved on 2026-09-21.

## Goal

Make a model document the one-way source for a dedicated VisMockup session. Opening a model must not depend on discovering or attaching to an unrelated VisMockup process.

## User workflow

Teamcenter product structure remains lazy. The initial view contains the root and its direct children. A user expands the required path first; only an expanded node with a complete occurrence path can be opened.

Opening creates an AI00-owned `VFFrame.Application` COM session on the Connector STA, opens the selected visualization material in that session, and shows its window. The same retained COM object serves all later tree and control operations.

## Runtime ownership

- Do not infer ownership from process names, window counts, or the global active document.
- Ignore unrelated VisMockup processes.
- Resolve the inner automation object once through outer dispatch member 21 and retain both objects.
- Record the inner server process id and start time as the owned session identity.
- Route document open, tree reads, visibility, and selection through that retained session.
- If the session is lost, report a session failure and recreate it from the model source; never attach to an arbitrary window.

## Model and control projection

The Teamcenter tree remains the navigation/opening source. After VisMockup loads the material, its complete loaded tree is the control projection. Control keys are document-session scoped `cad:` locators produced from the VisMockup tree. Teamcenter occurrence paths remain accepted for compatibility but are not the primary control locator after the viewer snapshot exists.

## Verified Siemens API details

- `VFFrame.Application` outer member 21 returns the full VisAutomation application.
- The outer document collection uses `Count=3`, `Close=4`, `Open=5`, and `Item=6`.
- The inner application exposes the active document and view through members 4 and 5.
- A runtime probe successfully opened a JT file, read its node, hid it, verified hidden state, restored it, and verified visible state.

## Compatibility and governance

Public capability ids, schemas, effects, confirmation policy, and Teamcenter lazy-read behavior remain unchanged. This is an internal provider/runtime correction, so no new capability or descriptor version is introduced.

## Failure handling

COM work remains serialized on the Connector STA. The Connector keeps exact ownership identity for diagnostics and must not return `vismockup_process_identity_unavailable` merely because another VisMockup process exists. A later watchdog enhancement may terminate only the owned server after a blocked call.
