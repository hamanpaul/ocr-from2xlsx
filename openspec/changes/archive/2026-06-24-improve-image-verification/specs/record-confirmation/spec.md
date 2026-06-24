# record-confirmation Specification (Delta)

**Change ID:** `improve-image-verification`
**Affects:** the source-image preview in the human confirmation UI (`ReviewApp`) and pure
pan/zoom / field-region helpers

## ADDED

### Requirement: Pan and wheel-zoom the source image during review

The system SHALL present the record's source page in a viewer that supports dragging to pan and using the
mouse wheel to zoom about the cursor, and SHALL remember the zoom level for the session, replacing the
previous center-crop-only zoom. The live-camera preview and the no-image placeholder SHALL continue to render
correctly through the viewer (the live preview fit to the pane).

#### Scenario: Drag pans and wheel zooms the source image
- **WHEN** a record's source page is shown and the reviewer drags on it or scrolls the mouse wheel
- **THEN** the image pans with the drag and zooms about the cursor with the wheel, staying within bounds

#### Scenario: Zoom is remembered for the session
- **WHEN** the reviewer sets a zoom level and then moves to another record's source image
- **THEN** the viewer keeps that zoom level for the session rather than resetting to center-crop

#### Scenario: Live preview and placeholder still render
- **WHEN** the live camera is previewing, or no source image is available
- **THEN** the live frame renders fit to the pane and the placeholder shows, through the same viewer, without
  error

### Requirement: Frame the source image to a focused field's region

The system SHALL, when a field receives focus, frame (scroll/zoom) the source-image viewer to that field's
region — the field's section band from the recognition layout geometry, or the name field's name crop when
available — so the reviewer sees the relevant area without hunting the whole page. A field with no known
region or with no source image loaded SHALL leave the view unchanged.

#### Scenario: Focusing a field frames its region
- **WHEN** a field with a known region is focused and a source image is loaded
- **THEN** the viewer frames that field's region (its section band, or the name crop for the name field)

#### Scenario: Unknown region leaves the view unchanged
- **WHEN** a focused field has no known region, or no source image is loaded
- **THEN** the viewer does not change its pan/zoom
